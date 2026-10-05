import { joinSession } from "@github/copilot-sdk/extension";
import { spawn } from "node:child_process";
import { readFileSync, lstatSync, realpathSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, resolve, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { createInterface } from "node:readline";

const ownPath = fileURLToPath(import.meta.url);
const installed = JSON.parse(readFileSync(join(dirname(ownPath), "installation.json"), "utf8"));
function verifyFile(path, expected) {
  const info = lstatSync(path);
  if (!info.isFile() || info.isSymbolicLink() ||
      createHash("sha256").update(readFileSync(path)).digest("hex") !== expected) {
    throw new Error(`Architrave trusted installation changed: ${path}`);
  }
}
verifyFile(ownPath, installed.extensionSha256);
verifyFile(installed.python, installed.pythonSha256);
for (const [path, digest] of Object.entries(installed.files)) verifyFile(path, digest);
const bridgePath = join(installed.root, "harness", "native_host.py");
const active = new Map();
let session;

function pipe(request) {
  for (const [path, digest] of Object.entries(installed.files)) verifyFile(path, digest);
  verifyFile(installed.python, installed.pythonSha256);
  const child = spawn(installed.python, ["-I", "-S", bridgePath], {
    cwd: installed.root, stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
  });
  const queue = [];
  const waiting = [];
  let failure;
  let stderr = "";
  const lines = createInterface({ input: child.stdout });
  function fail(error) {
    failure = error;
    while (waiting.length) waiting.shift().reject(error);
  }
  lines.on("line", line => {
    try {
      if (Buffer.byteLength(line) > 65536) throw new Error("Architrave bridge output exceeded bound");
      const value = JSON.parse(line);
      const waiter = waiting.shift();
      if (waiter) waiter.resolve(value);
      else queue.push(value);
    } catch (error) { fail(error); child.kill(); }
  });
  child.stderr.on("data", data => { stderr = (stderr + data.toString()).slice(-8192); });
  child.on("error", fail);
  const closed = new Promise(resolve => child.on("close", resolve));
  child.on("close", code => {
    failure ||= new Error(`Architrave bridge closed (${code}): ${stderr}`);
    if (waiting.length) fail(new Error(`Architrave bridge closed (${code}): ${stderr}`));
  });
  const next = () => queue.length ? Promise.resolve(queue.shift()) :
    failure ? Promise.reject(failure) : new Promise((resolve, reject) => waiting.push({ resolve, reject }));
  const send = value => {
    const line = JSON.stringify(value) + "\n";
    if (Buffer.byteLength(line) > 65536) throw new Error("Architrave bridge input exceeded bound");
    child.stdin.write(line);
  };
  send(request);
  return { child, next, send, close: async () => { child.stdin.end(); await closed; lines.close(); } };
}

async function hostTasks() {
  if (!session.rpc.tasks?.startAgent || !session.rpc.tasks?.list || !session.rpc.tasks?.cancel) {
    throw new Error("NATIVE_HOST_REQUIRED: this Copilot host lacks structured tasks RPC; no shell fallback");
  }
  return (await session.rpc.tasks.list()).tasks;
}

function result(value) {
  return { textResultForLlm: JSON.stringify(value),
    resultType: value.status === "failed" || ["FAIL", "failed"].includes(value.result?.status) ? "failure" : "success" };
}

const identitySchema = {
  repo: { type: "string", description: "Absolute adopted repository path" },
  run_id: { type: "string" },
  task_id: { type: "string" },
};
function request(args, action, invocation) {
  if (invocation.sessionId !== session.sessionId) throw new Error("Native host owner mismatch");
  if (!isAbsolute(args.repo)) throw new Error("Repository path must be absolute");
  const repo = realpathSync(args.repo);
  const trustRelation = relative(repo, installed.root);
  if (!trustRelation.startsWith("..") && !isAbsolute(trustRelation)) {
    throw new Error("Trusted native installation cannot be inside the target repository");
  }
  return { repo, action, runId: args.run_id, taskId: args.task_id, owner: session.sessionId };
}

const tools = [
  {
    name: "architrave_native_dispatch",
    description: "Dispatch one canonical WorkPacket through this Copilot host's structured tasks RPC. Produces a bounded candidate only; independent gates remain required. No CLI/provider/model override.",
    parameters: { type: "object", properties: { ...identitySchema,
      owner_handle: { type: "string", description: "Optional existing idle agent task ID in this joined session; preserves its context" },
    }, required: ["repo", "run_id", "task_id"], additionalProperties: false },
    handler: async (args, invocation) => {
      const tasks = await hostTasks();
      if (args.owner_handle && !tasks.some(task => task.id === args.owner_handle && task.type === "agent" && task.status === "idle")) {
        throw new Error("Existing owner must be an idle native agent in the current joined host session");
      }
      const connection = pipe(request(args, "dispatch", invocation));
      let hostTaskId;
      let timeout;
      let deadline;
      let entry;
      const dispatchedAt = Date.now();
      try {
        const prepared = await connection.next();
        if (prepared.status !== "prepared") return result(prepared);
        if (args.owner_handle) {
          hostTaskId = args.owner_handle;
          const sent = await session.rpc.tasks.sendMessage({ id: hostTaskId, message: prepared.prompt });
          if (!sent.sent) throw new Error(sent.error || "Host rejected WorkPacket delivery");
        } else {
          const admitted = await session.rpc.tasks.startAgent({
            agentType: prepared.agentType, prompt: prepared.prompt,
            name: `Architrave ${args.task_id}`, description: "Bounded native WorkPacket candidate",
          });
          hostTaskId = admitted.agentId;
        }
        connection.send({ status: "admitted", hostTaskId });
        const bound = await connection.next();
        if (bound.status !== "bound") throw new Error(bound.error?.message || "Run rejected host admission");
        const key = `${args.run_id}:${args.task_id}`;
        entry = { key, hostTaskId, connection, cancelled: false, repo: args.repo };
        active.set(key, entry);
        deadline = Date.parse(prepared.expiresAt);
        let observed;
        while (Date.now() < deadline) {
          observed = (await hostTasks()).find(task => task.id === hostTaskId && task.type === "agent");
          if (!observed) throw new Error("Joined host lost the admitted task; candidate cannot be reconstructed from repository JSON");
          const terminal = ["completed", "idle", "failed", "cancelled"].includes(observed.status);
          const fresh = !args.owner_handle || observed.prompt === prepared.prompt &&
            Date.parse(observed.idleSince || observed.completedAt || "") >= dispatchedAt;
          if (terminal && fresh) break;
          await new Promise(resolve => setTimeout(resolve, 250));
        }
        if (!observed || !["completed", "idle", "failed", "cancelled"].includes(observed.status)) {
          timeout = true;
          const cancelled = await session.rpc.tasks.cancel({ id: hostTaskId });
          if (!cancelled.cancelled) throw new Error("Host timeout cancellation was not confirmed");
          observed = { id: hostTaskId, status: "cancelled", error: "WorkPacket timeout" };
        }
        const text = String(observed.result || observed.latestResponse || observed.error || "").slice(0, 8192);
        connection.send({ hostTaskId, hostStatus: observed.status, text });
        const candidate = await connection.next();
        if (!args.owner_handle) {
          if (observed.status === "idle") await session.rpc.tasks.cancel({ id: hostTaskId });
          await session.rpc.tasks.remove({ id: hostTaskId });
        }
        return result({ ...candidate, hostTaskId, timedOut: Boolean(timeout) });
      } catch (error) {
        let cancellation;
        if (hostTaskId) cancellation = await session.rpc.tasks.cancel({ id: hostTaskId });
        connection.child.stdin.end();
        return result({ status: "failed", error: { code: "NATIVE_HOST_FAILED", message: String(error) },
          hostTaskId, hostCancellationConfirmed: cancellation?.cancelled ?? false });
      } finally {
        if (entry) active.delete(entry.key);
        await connection.close();
      }
    },
  },
  {
    name: "architrave_native_cancel",
    description: "Cancel an active native WorkPacket through its actual joined host owner; no fabricated result.",
    parameters: { type: "object", properties: identitySchema,
      required: ["repo", "run_id", "task_id"], additionalProperties: false },
    handler: async (args, invocation) => {
      request(args, "status", invocation);
      const entry = active.get(`${args.run_id}:${args.task_id}`);
      if (!entry || resolve(entry.repo) !== resolve(args.repo)) throw new Error("No live native bridge owns this WorkPacket");
      const outcome = await session.rpc.tasks.cancel({ id: entry.hostTaskId });
      if (!outcome.cancelled) throw new Error("Host cancellation was not confirmed");
      return result({ status: "ok", cancelled: true, hostTaskId: entry.hostTaskId });
    },
  },
  ...["status", "gate", "recover"].map(action => ({
    name: `architrave_native_${action}`,
    description: action === "recover" ?
      "Recover expired/orphaned records or an explicitly named failed side-effect-free task. Optionally withdraw only obsolete native-adapter-required integration wait, never human sign-in/policy/target checkpoints. Never executes tasks or replays side effects." :
      action === "gate" ? "Independently execute a configured test/build or installed quick gate through trusted Python, binding real source/evidence to this Run and task. Accepts no claimed result." :
      "Render current canonical status with revision, source, active/historical workers and authenticated evidence identities.",
    parameters: { type: "object", properties: { ...identitySchema,
      ...(action === "gate" ? { recipe: { type: "string", enum: ["quick", "build", "test", "ci", "task"] },
        ci_run_id: { type: "integer", minimum: 1, description: "Exact workflow Run id, observed from GitHub and bound to current source commit" } } : {}),
      ...(action === "recover" ? { checkpoint_id: { type: "string", enum: ["native-adapter-required"] } } : {}),
    }, required: action === "gate" ? ["repo", "run_id", "task_id"] : ["repo", "run_id"], additionalProperties: false },
    handler: async (args, invocation) => {
      await hostTasks();
      const input = { ...request(args, action, invocation), recipe: args.recipe, ciRunId: args.ci_run_id,
        checkpointId: args.checkpoint_id };
      const connection = pipe(input);
      try { return result(await connection.next()); }
      finally { await connection.close(); }
    },
  })),
];

session = await joinSession({ tools });
