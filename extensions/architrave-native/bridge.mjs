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
let pendingDispatches = 0;
let semanticScope;
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

function observeTask(maxTurns, requireCompletion = false) {
  const records = new Map();
  let id, fresh, resolve, reject, timer;
    let reading = false;
    let dirty = false;
    let done = false;
    let cancellationRequested = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      unsubscribe();
      clearTimeout(timer);
      if (error && reject) reject(error);
      else if (resolve) resolve(value);
    };
    const enforceTurns = () => {
      if (!id || cancellationRequested || (records.get(id)?.turns || 0) < maxTurns) return;
      cancellationRequested = true;
      void session.rpc.tasks.cancel({ id }).then(outcome => {
        if (!outcome.cancelled) finish(new Error("Host turn-budget cancellation was not confirmed"));
      }).catch(error => finish(error));
    };
    const inspect = async () => {
      if (done || !id) return;
      if (reading) { dirty = true; return; }
      reading = true;
      try {
        const task = (await hostTasks()).find(task => task.id === id && task.type === "agent");
        if (!task) finish(new Error("Joined host lost the admitted task"));
        else if (["completed", "idle", "failed", "cancelled"].includes(task.status) &&
                 (fresh(task) || cancellationRequested && task.status === "cancelled") &&
                 (!requireCompletion || records.get(id)?.completionEvent ||
                   ["failed", "cancelled"].includes(task.status))) {
          const record = records.get(id) || {};
          finish(null, { ...task, ...record, turnsObserved: record.turns || null,
            budgetStop: cancellationRequested ? "turns" : null });
        }
      } catch (error) { finish(error); }
      finally {
        reading = false;
        if (dirty && !done) { dirty = false; void inspect(); }
      }
    };
    const unsubscribe = session.on(event => {
      if (done) return;
      if (event.agentId && (!id || event.agentId === id) && event.type === "assistant.turn_start") {
        const record = records.get(event.agentId) || { turns: 0 };
        record.turns = (record.turns || 0) + 1;
        records.set(event.agentId, record);
        enforceTurns();
      }
      if (event.agentId && (!id || event.agentId === id) && ["subagent.completed", "subagent.failed"].includes(event.type)) {
        const completionEvent = {
          id: event.id, type: event.type, agentId: event.agentId, timestamp: event.timestamp,
          ephemeral: Boolean(event.ephemeral), cancelled: Boolean(event.data.cancelled),
          toolCallId: event.data.toolCallId, agentName: event.data.agentName,
          firstDispatchedModel: event.data.firstDispatchedModel || null,
          modelSelectionSource: event.data.modelSelectionSource || null,
        };
        const previous = records.get(event.agentId)?.completionEvent;
        if (previous && JSON.stringify(previous) !== JSON.stringify(completionEvent)) {
          finish(new Error("Conflicting host completion provenance"));
          return;
        }
        records.set(event.agentId, { ...records.get(event.agentId),
          usageTotal: event.data.totalTokens ?? null,
          totalToolCalls: event.data.totalToolCalls ?? null,
          effectiveModel: event.data.firstDispatchedModel || event.data.model || null, completionEvent });
      }
      if (event.type === "session.background_tasks_changed" || event.type.startsWith("subagent.")) {
        void inspect();
      }
    });
  return {
    wait(owner, deadline, isFresh) {
      id = owner;
      fresh = isFresh;
      for (const key of records.keys()) if (key !== id) records.delete(key);
      return new Promise((yes, no) => {
        resolve = yes;
        reject = no;
        timer = setTimeout(() => finish(null, null), Math.max(0, deadline - Date.now()));
        enforceTurns();
        void inspect();
      });
    },
    close() { finish(new Error("Native observation closed")); },
  };
}

function result(value) {
  return { textResultForLlm: JSON.stringify(value),
    resultType: value.status === "failed" || ["FAIL", "failed"].includes(value.result?.status) ? "failure" : "success" };
}

async function withAdmission(operation) {
  if (pendingDispatches >= 3) throw new Error("CHILD_LIMIT: three dispatches already admitted");
  pendingDispatches += 1;
  try { return await operation(); }
  finally { pendingDispatches -= 1; }
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
  return { repo, action, runId: args.run_id, taskId: args.task_id, owner: session.sessionId,
    nativeInstallation: { version: installed.version, extensionSha256: installed.extensionSha256,
      provenance: "executing user-installed extension manifest; pinned files rechecked" } };
}

const tools = [
  {
    name: "architrave_native_dispatch",
    description: "Dispatch one bounded canonical WorkPacket through the joined host. Candidate only; independent gates required. Model pin only when explicitly supplied by the user; otherwise host inheritance.",
    parameters: { type: "object", properties: { ...identitySchema,
      owner_handle: { type: "string", description: "Optional retained idle owner already bound to this same canonical task/objective; never repurpose another task's context" },
      model: { type: "string", description: "Optional explicit USER-requested host model pin; omit to inherit host settings" },
      retry_hypothesis: { type: "string", description: "New bounded hypothesis required for an intentional retry without new observed evidence" },
    }, required: ["repo", "run_id", "task_id"], additionalProperties: false },
    handler: async (args, invocation) => withAdmission(async () => {
      const tasks = await hostTasks();
      if (semanticScope) throw new Error("SEMANTIC_REVIEW_BUSY: frozen review owns this joined session");
      const owned = new Set([...active.values()].map(entry => entry.hostTaskId));
      const outside = tasks.filter(task => task.type === "agent" && task.status === "running" && !owned.has(task.id)).length;
      if (outside + pendingDispatches > 3) {
        throw new Error("CHILD_LIMIT: three active host children already exist, including child-originated work");
      }
      if (args.owner_handle && !tasks.some(task => task.id === args.owner_handle && task.type === "agent" && task.status === "idle")) {
        throw new Error("Existing owner must be an idle native agent in the current joined host session");
      }
      const connection = pipe({ ...request(args, "dispatch", invocation), retryHypothesis: args.retry_hypothesis,
        ownerHandle: args.owner_handle });
      let hostTaskId;
      let timeout;
      let deadline;
      let entry;
      let observer;
      const dispatchedAt = Date.now();
      try {
        const prepared = await connection.next();
        if (prepared.status !== "prepared") return result(prepared);
        observer = observeTask(prepared.maxTurns);
        if (args.owner_handle) {
          hostTaskId = args.owner_handle;
          const sent = await session.rpc.tasks.sendMessage({ id: hostTaskId, message: prepared.prompt });
          if (!sent.sent) throw new Error(sent.error || "Host rejected WorkPacket delivery");
        } else {
          const admitted = await session.rpc.tasks.startAgent({
            agentType: prepared.agentType, prompt: prepared.prompt,
            name: `Architrave ${args.task_id}`, description: "Bounded native WorkPacket candidate",
            ...(args.model ? { model: args.model } : {}),
          });
          hostTaskId = admitted.agentId;
        }
        deadline = Date.parse(prepared.expiresAt);
        const observation = observer.wait(hostTaskId, deadline, task => !args.owner_handle ||
          task.prompt === prepared.prompt && Date.parse(task.idleSince || task.completedAt || "") >= dispatchedAt);
        observation.catch(() => {}); // Binding can fail before the observation is awaited.
        connection.send({ status: "admitted", hostTaskId });
        const bound = await connection.next();
        if (bound.status !== "bound") throw new Error(bound.error?.message || "Run rejected host admission");
        const key = `${args.run_id}:${args.task_id}`;
        entry = { key, hostTaskId, connection, cancelled: false, repo: args.repo };
        active.set(key, entry);
        let observed = await observation;
        if (!observed || !["completed", "idle", "failed", "cancelled"].includes(observed.status)) {
          timeout = true;
          const cancelled = await session.rpc.tasks.cancel({ id: hostTaskId });
          if (!cancelled.cancelled) throw new Error("Host timeout cancellation was not confirmed");
          observed = { id: hostTaskId, status: "cancelled", error: "WorkPacket time budget exceeded", budgetStop: "time" };
        }
        const text = String(observed.result || observed.latestResponse || observed.error || "").slice(0, 8192);
        connection.send({ hostTaskId, hostStatus: observed.status, text,
          reusedOwner: Boolean(args.owner_handle),
          requestedModel: args.model || null, effectiveModel: observed.effectiveModel || observed.resolvedModel || null,
          usageTotal: observed.usageTotal ?? null, totalToolCalls: observed.totalToolCalls ?? null,
          turnsObserved: observed.turnsObserved ?? null, budgetStop: observed.budgetStop ?? null });
        const candidate = await connection.next();
        if (!args.owner_handle) {
          if (observed.status === "idle") await session.rpc.tasks.cancel({ id: hostTaskId });
          await session.rpc.tasks.remove({ id: hostTaskId });
        }
        return result({ ...candidate, hostTaskId, timedOut: Boolean(timeout), effort: prepared.effort });
      } catch (error) {
        let cancellation;
        if (hostTaskId) cancellation = await session.rpc.tasks.cancel({ id: hostTaskId });
        connection.child.stdin.end();
        return result({ status: "failed", error: { code: "NATIVE_HOST_FAILED", message: String(error) },
          hostTaskId, hostCancellationConfirmed: cancellation?.cancelled ?? false });
      } finally {
        if (entry) active.delete(entry.key);
        observer?.close();
        await connection.close();
      }
    }),
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
      const observedTasks = await hostTasks();
      const input = { ...request(args, action, invocation), recipe: args.recipe, ciRunId: args.ci_run_id,
        checkpointId: args.checkpoint_id,
        hostWorkers: {
          visibility: "OBSERVED", source: "joined supported tasks RPC, this session only",
          observedAt: new Date().toISOString(),
          activeCount: observedTasks.filter(task => task.type === "agent" && task.status === "running").length,
          idleProven: false, allSessionsObserved: false,
        } };
      const connection = pipe(input);
      try { return result(await connection.next()); }
      finally { await connection.close(); }
    },
  })),
];

tools.push({
  name: "architrave_native_review",
  description: "Execute one fresh source-bound semantic review through the joined host and admit only its observed result/model receipt. No verdict import or model pin.",
  parameters: { type: "object", properties: { ...identitySchema,
    reviewer: { type: "string", enum: ["code-review", "rubber-duck"] },
  }, required: ["repo", "run_id", "task_id"], additionalProperties: false },
  handler: async (args, invocation) => withAdmission(async () => {
    if (Object.keys(args).some(key => !["repo", "run_id", "task_id", "reviewer"].includes(key))) {
      throw new Error("Semantic execution accepts no claimed verdict, producer, event or model");
    }
    const tasks = await hostTasks();
    if (semanticScope || pendingDispatches !== 1 || tasks.some(task => task.type === "agent" && task.status === "running")) {
      throw new Error("SEMANTIC_REVIEW_BUSY: frozen-source reviews run alone in this joined session");
    }
    const input = { ...request(args, "semantic-review", invocation),
      invocationId: invocation.toolCallId, reviewer: args.reviewer || "rubber-duck" };
    const connection = pipe(input);
    semanticScope = input.repo;
    let hostTaskId, observer, key;
    let abort;
    try {
      const prepared = await connection.next();
      if (prepared.status !== "prepared") return result(prepared);
      observer = observeTask(prepared.maxTurns, true);
      const admitted = await session.rpc.tasks.startAgent({
        agentType: prepared.agentType, prompt: prepared.prompt,
        name: `Architrave semantic ${args.task_id}`, description: "Independent frozen-source gate",
      });
      hostTaskId = admitted.agentId;
      key = `review:${args.run_id}:${args.task_id}:${invocation.toolCallId}`;
      active.set(key, { hostTaskId, connection, repo: args.repo });
      abort = () => { void session.rpc.tasks.cancel({ id: hostTaskId }); };
      invocation.signal?.addEventListener("abort", abort, { once: true });
      const observation = observer.wait(hostTaskId, Date.parse(prepared.expiresAt), () => true);
      observation.catch(() => {});
      connection.send({ status: "admitted", hostTaskId });
      const bound = await connection.next();
      if (bound.status !== "bound") throw new Error(bound.error?.message || "Semantic host binding failed");
      const observed = await observation;
      if (!observed || !observed.completionEvent) throw new Error("SEMANTIC_HOST_PROVENANCE: completion metadata unavailable within bound");
      connection.send({
        hostTaskId, hostStatus: observed.status,
        text: String(observed.result || observed.latestResponse || ""),
        completion: observed.completionEvent,
      });
      return result(await connection.next());
    } catch (error) {
      return result({ status: "failed", error: { code: "NATIVE_SEMANTIC_FAILED", message: String(error) }, hostTaskId });
    } finally {
      invocation.signal?.removeEventListener("abort", abort);
      if (key) active.delete(key);
      observer?.close();
      try {
        if (hostTaskId) {
          await session.rpc.tasks.cancel({ id: hostTaskId });
          await session.rpc.tasks.remove({ id: hostTaskId });
        }
      } finally {
        try { await connection.close(); }
        finally { semanticScope = undefined; }
      }
    }
  }),
});

tools.push({
  name: "architrave_native_batch",
  description: "Invoke two or three pre-decomposed independent canonical WorkPackets concurrently through the same native dispatch. No automatic decomposition or recursive spawning.",
  parameters: { type: "object", properties: {
    repo: identitySchema.repo, run_id: identitySchema.run_id,
    task_ids: { type: "array", items: { type: "string" }, minItems: 2, maxItems: 3, uniqueItems: true },
  }, required: ["repo", "run_id", "task_ids"], additionalProperties: false },
  handler: async (args, invocation) => {
    const results = await Promise.all(args.task_ids.map(task_id =>
      tools[0].handler({ repo: args.repo, run_id: args.run_id, task_id }, invocation)));
    return { textResultForLlm: JSON.stringify(results.map(item => JSON.parse(item.textResultForLlm))),
      resultType: results.some(item => item.resultType === "failure") ? "failure" : "success" };
  },
});

session = await joinSession({ tools, hooks: {
  onPreToolUse: (input, invocation) => {
    if (semanticScope) {
      if (["tool_search_tool", "functions.tool_search_tool"].includes(input.toolName)) return;
      if (["skill", "functions.skill"].includes(input.toolName) && input.toolArgs?.skill === "architrave-review") return;
      if (!["view", "rg", "glob", "functions.view", "functions.rg", "functions.glob"].includes(input.toolName)) {
        return { permissionDecision: "deny", permissionDecisionReason: "SEMANTIC_READ_ONLY: only scoped view/rg/glob; no execute, mutation, control-plane or child tools" };
      }
      const name = input.toolName.replace(/^functions\./, "");
      const args = input.toolArgs;
      if (!args || typeof args !== "object" || Array.isArray(args)) {
        return { permissionDecision: "deny", permissionDecisionReason: "SEMANTIC_READ_ONLY: malformed read arguments" };
      }
      try {
        const paths = name === "view" ? [args.path] :
          Array.isArray(args.paths) ? args.paths : [args.paths || semanticScope];
        if (!paths.length) throw new Error("no source paths");
        const safe = paths.map(path => {
          if (typeof path !== "string") throw new Error("invalid source path");
          const absolute = realpathSync(resolve(semanticScope, path));
          const suffix = relative(semanticScope, absolute);
          if (suffix.startsWith("..") || isAbsolute(suffix) ||
              suffix.split(/[\\/]/).some(part => [".git", ".architrave"].includes(part.toLowerCase()))) {
            throw new Error("private or out-of-scope source");
          }
          return absolute;
        });
        return { modifiedArgs: { ...args, ...(name === "view" ? { path: safe[0] } : { paths: safe }) } };
      } catch (error) {
        return { permissionDecision: "deny", permissionDecisionReason: `SEMANTIC_READ_ONLY: ${error.code || error.message}` };
      }
    }
    if ((active.size || pendingDispatches) && input.sessionId !== invocation.sessionId &&
        /(?:^|[./-])(?:task|create_session|open_pr_session|open_issue_session|fork_session|run_workflow|run_dynamic_workflow|architrave_native_dispatch|architrave_native_batch|architrave_native_review)$/.test(input.toolName)) {
      return { permissionDecision: "deny", permissionDecisionReason: "CHILD_DEPTH: a bounded Architrave child may not spawn descendants (max depth one)" };
    }
  },
} });
