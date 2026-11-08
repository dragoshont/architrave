import { joinSession } from "@github/copilot-sdk/extension";
import { spawn } from "node:child_process";
import { readFileSync, lstatSync, realpathSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, resolve, relative, isAbsolute, sep } from "node:path";
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

export function semanticReviewPrompt(prompt, files) {
  const value = prompt +
    "\nTracked regular source inventory (no recursive glob or directory view; search only these files):\n" +
    JSON.stringify(files);
  if (Buffer.byteLength(value, "utf8") > 65536)
    throw new Error("SEMANTIC_PROMPT_TOO_LARGE: declared implementation inventory exceeds the bounded host prompt");
  return value;
}

function pipe(request) {
  const firstLine = JSON.stringify(request) + "\n";
  if (Buffer.byteLength(firstLine) > 65536) throw new Error("Architrave bridge input exceeded bound");
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
    queue.length = 0;
    while (waiting.length) waiting.shift().reject(error);
  }
  lines.on("line", line => {
    if (failure) return;
    try {
      if (Buffer.byteLength(line) > 65536) throw new Error("Architrave bridge output exceeded bound");
      const value = JSON.parse(line);
      const waiter = waiting.shift();
      if (waiter) waiter.resolve(value);
      else queue.push(value);
    } catch (error) { fail(error); child.kill(); }
  });
  child.stderr.on("data", data => { stderr = (stderr + data.toString()).slice(-8192); });
  child.stdin.on("error", fail);
  child.stdout.on("error", fail);
  child.on("error", fail);
  const closed = new Promise(resolve => child.on("close", resolve));
  child.on("close", code => {
    failure ||= new Error(`Architrave bridge closed (${code}): ${stderr}`);
    if (waiting.length) fail(new Error(`Architrave bridge closed (${code}): ${stderr}`));
  });
  const next = () => queue.length ? Promise.resolve(queue.shift()) :
    failure ? Promise.reject(failure) : new Promise((resolve, reject) => waiting.push({ resolve, reject }));
  const send = value => {
    if (failure) throw failure;
    const line = JSON.stringify(value) + "\n";
    if (Buffer.byteLength(line) > 65536) throw new Error("Architrave bridge input exceeded bound");
    child.stdin.write(line);
  };
  child.stdin.write(firstLine);
  return { child, next, send, close: async () => { child.stdin.end(); await closed; lines.close(); } };
}

async function hostTasks() {
  if (!session.rpc.tasks?.startAgent || !session.rpc.tasks?.list || !session.rpc.tasks?.cancel) {
    throw new Error("NATIVE_HOST_REQUIRED: this Copilot host lacks structured tasks RPC; no shell fallback");
  }
  const tasks = (await session.rpc.tasks.list()).tasks;
  if (!Array.isArray(tasks)) throw new Error("NATIVE_HOST_FAILED: joined host task listing was invalid");
  return tasks;
}

function hostTaskInventory(tasks) {
  return tasks.filter(task => task.type === "agent").map(task => ({
    id: task.id, type: task.type, status: task.status,
    description: typeof task.description === "string" ? task.description : "",
  }));
}

function observeTask(maxTurns, requireCompletion = false) {
  const records = new Map();
  let id, fresh, resolve, reject, timer, outcome;
    let reading = false;
    let dirty = false;
    let done = false;
    let cancellationRequested = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      outcome = { error, value };
      unsubscribe();
      clearTimeout(timer);
      if (error && reject) reject(error);
      else if (resolve) resolve(value);
    };
    const enforceTurns = () => {
      if (!id || cancellationRequested || (records.get(id)?.turns || 0) < maxTurns) return;
      cancellationRequested = true;
      void Promise.resolve().then(() => session.rpc.tasks.cancel({ id })).then(outcome => {
        if (!outcome.cancelled) finish(new Error("Host turn-budget cancellation was not confirmed"));
      }).catch(error => finish(error));
    };
    const inspect = async () => {
      if (done || !id) return;
      if (reading) { dirty = true; return; }
      reading = true;
      try {
        if (records.get(id)?.error) throw records.get(id).error;
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
        const data = event.data && typeof event.data === "object" ? event.data : {};
        const completionEvent = {
          id: event.id, type: event.type, agentId: event.agentId, timestamp: event.timestamp,
          ephemeral: Boolean(event.ephemeral), cancelled: Boolean(data.cancelled),
          toolCallId: data.toolCallId, agentName: data.agentName,
          firstDispatchedModel: data.firstDispatchedModel || null,
          modelSelectionSource: data.modelSelectionSource || null,
        };
        const previous = records.get(event.agentId)?.completionEvent;
        if (previous && JSON.stringify(previous) !== JSON.stringify(completionEvent)) {
          const error = new Error("Conflicting host completion provenance");
          records.set(event.agentId, { ...records.get(event.agentId), error });
          if (id === event.agentId) finish(error);
          return;
        }
        records.set(event.agentId, { ...records.get(event.agentId),
          usageTotal: data.totalTokens ?? null,
          totalToolCalls: data.totalToolCalls ?? null,
          effectiveModel: data.firstDispatchedModel || data.model || null, completionEvent });
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
        if (done) {
          if (outcome.error) no(outcome.error);
          else yes(outcome.value);
          return;
        }
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

const HARD_CHILD_CAP = 20;
// workers.maxParallel in the target repository's architrave.config.json; default 3, never above 20.
function childCap(repo) {
  let value;
  try {
    value = JSON.parse(readFileSync(join(repo, "architrave.config.json"), "utf8")).workers?.maxParallel;
  } catch (error) {
    if (error.code === "ENOENT") return 3;
    throw new Error("NATIVE_CONFIG_INVALID: cannot read workers.maxParallel", { cause: error });
  }
  if (value === undefined) return 3;
  if (!Number.isInteger(value) || value < 1)
    throw new Error("NATIVE_CONFIG_INVALID: workers.maxParallel must be a positive integer");
  return Math.min(HARD_CHILD_CAP, value);
}

// REQ-97: every dispatch await is bounded. Preflight precedes the lease deadline, so it has a fixed bound.
const PREFLIGHT_MS = 30000;
const RECOVERY_MS = 5000;
function staged(stage, error) {
  return Object.assign(new Error(String(error?.message ?? error)),
    { stage: error?.stage || stage, timedOut: Boolean(error?.timedOut), aborted: Boolean(error?.aborted) });
}
function bounded(work, stage, until, { signal, clock = Date.now } = {}) {
  let timer;
  const pending = Promise.resolve().then(() => work);
  pending.catch(() => {});
  let abort;
  const races = [pending, new Promise((_, reject) => {
    timer = setTimeout(() => reject(Object.assign(
      new Error(`NATIVE_STAGE_TIMEOUT: ${stage} did not settle within the dispatch deadline`), { stage, timedOut: true })),
    Math.max(0, until - clock()));
    timer.unref?.();
  })];
  if (signal) races.push(new Promise((_, reject) => {
    abort = () => reject(Object.assign(new Error(`NATIVE_ABORTED: ${stage} was aborted`), { stage, aborted: true }));
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  }));
  return Promise.race(races).catch(error => { throw staged(stage, error); }).finally(() => {
    clearTimeout(timer);
    if (abort) signal.removeEventListener("abort", abort);
  });
}

// Cancel/remove the dispatch host owner. Confirmation is only what the host returned within the bound.
async function settleDispatch(entry, until, { stop, remove, closeBridge = true }) {
  const errors = [];
  if (!entry.hostTaskId) {
    if (entry.admissionPending) errors.push("admission: host start is unresolved; owner unknown, host-side admission may still complete");
  } else {
    try {
      if (stop && !entry.stopped) {
        const outcome = await bounded(session.rpc.tasks.cancel({ id: entry.hostTaskId }), "cleanup", until);
        if (!outcome?.cancelled) throw staged("cleanup", "Host cancellation was not confirmed");
        entry.cancelled = entry.stopped = true;
      }
      if (remove && !entry.hostRemoved) {
        const removed = await bounded(session.rpc.tasks.remove({ id: entry.hostTaskId }), "cleanup", until);
        if (!removed?.removed) throw staged("cleanup", "Host removal was not confirmed");
        entry.hostRemoved = true;
      }
    } catch (error) { errors.push(`host cleanup: ${error.message}`); }
  }
  if (closeBridge && !entry.bridgeClosed) {
    try {
      await bounded(entry.connection.close(), "cleanup", until);
      entry.bridgeClosed = true;
    } catch (error) {
      entry.connection.child.kill();
      errors.push(`bridge cleanup: ${error.message}`);
    }
  }
  return errors;
}

async function finishLateAdmission(entry, hostTaskId) {
  if (entry.lateCleanup) return entry.lateCleanup;
  entry.lateCleanup = (async () => {
    const until = Date.now() + RECOVERY_MS;
    try {
      entry.hostTaskId = hostTaskId;
      entry.unknownOwner = false;
      entry.connection.send({ status: "admitted", hostTaskId });
      const bound = await bounded(entry.connection.next(), "binding", until);
      if (bound.status !== "bound") throw new Error(bound.error?.message || "Run did not bind the late host owner");
      entry.nativeBound = true;
      const errors = await settleDispatch(entry, until,
        { stop: true, remove: !entry.ownerHandle, closeBridge: false });
      if (errors.length || !entry.cancelled) throw new Error(errors.join("; ") || "late owner cancellation was not confirmed");
      entry.connection.send({ hostTaskId, hostStatus: "cancelled", text: "Admission resolved after abort",
        cancellationConfirmed: true, removalConfirmed: Boolean(entry.hostRemoved), reusedOwner: Boolean(entry.ownerHandle) });
      entry.candidate = await bounded(entry.connection.next(), "persistence", until);
      await bounded(entry.connection.close(), "cleanup", until);
      entry.bridgeClosed = true;
      if (active.get(entry.key) === entry) active.delete(entry.key);
    } catch (error) {
      entry.recoveryPending = true;
      entry.recoveryError = String(error.message ?? error);
    }
  })();
  return entry.lateCleanup;
}

function reconcileDispatch(entry) {
  if (!entry.reconciliation) {
    entry.reconciliation = reconcileDispatchOnce(entry).finally(() => {
      entry.reconciliation = undefined;
    });
  }
  return entry.reconciliation;
}

async function reconcileDispatchOnce(entry) {
  if (entry.lateCleanup) {
    const cleanup = entry.lateCleanup;
    await cleanup;
    if (entry.lateCleanup === cleanup) entry.lateCleanup = undefined;
    if (entry.recoveryError) return { status: "failed", cancelled: false,
      hostCancellationConfirmed: Boolean(entry.cancelled), hostRemovalConfirmed: Boolean(entry.hostRemoved),
      hostTaskId: entry.hostTaskId, recoveryOwner: entry.hostTaskId,
      error: { code: "NATIVE_RECOVERY_PENDING", stage: entry.stage || "cleanup", message: entry.recoveryError },
      cleanup: { confirmed: false, errors: [entry.recoveryError] } };
    return { status: "ok", cancelled: Boolean(entry.cancelled),
      hostCancellationConfirmed: Boolean(entry.cancelled), hostRemovalConfirmed: Boolean(entry.hostRemoved),
      hostTaskId: entry.hostTaskId, recoveryOwner: entry.hostTaskId,
      cleanup: { confirmed: true, errors: [] },
      ...(entry.candidate ? { adopted: true, candidate: entry.candidate } : {}) };
  }
  const until = Date.now() + RECOVERY_MS;
  const errors = [];
  if (entry.bindingPromise && !entry.nativeBound) {
    try {
      const bound = await bounded(entry.bindingPromise, "binding", until);
      if (bound.status !== "bound") throw new Error(bound.error?.message || "Run owner binding was not confirmed");
      entry.nativeBound = true;
    } catch (error) {
      return { status: "failed", cancelled: false, hostCancellationConfirmed: Boolean(entry.cancelled),
        hostRemovalConfirmed: Boolean(entry.hostRemoved), recoveryOwner: entry.hostTaskId,
        error: { code: "NATIVE_RECOVERY_PENDING", stage: "binding", message: String(error.message ?? error) },
        cleanup: { confirmed: false, errors: [String(error.message ?? error)] } };
    }
  }
  let ownerListing;
  // The host listing is not authoritative absence. Adopt only by the attempt marker sent with startAgent.
  if (entry.unknownOwner && !entry.hostTaskId && !entry.admissionPending) {
    try {
      const tasks = await bounded(hostTasks(), "cleanup", until);
      const others = new Set([...active.values()].filter(other => other !== entry).map(other => other.hostTaskId));
      const matches = tasks.filter(task => task.type === "agent" && entry.attemptMarker &&
        !entry.preflightHostTaskIds?.has(task.id) &&
        task.description === entry.attemptMarker && !others.has(task.id));
      if (matches.length === 1) {
        entry.hostTaskId = matches[0].id;
        entry.unknownOwner = false;
        ownerListing = "adopted";
      } else {
        ownerListing = matches.length ? "ambiguous" : "unresolved";
        errors.push(matches.length ?
          "host cleanup listing: multiple tasks carry this attempt identity" :
          `host cleanup listing: no task carries attempt ${entry.attemptId}; absence is unconfirmed`);
      }
    } catch (error) { errors.push(`host cleanup listing: ${error.message}`); }
  }
  errors.push(...await settleDispatch(entry, until, { stop: true, remove: !entry.ownerHandle,
    closeBridge: !(entry.unknownOwner || entry.nativeBound && !entry.candidate ||
      ownerListing === "adopted" && !entry.nativeBound) }));
  if (entry.unknownOwner && !entry.hostTaskId && !errors.length) {
    errors.push("admission: host start failed; any created owner is unknown");
  }
  if (errors.length) return { status: "failed", cancelled: false, hostCancellationConfirmed: Boolean(entry.cancelled),
    hostRemovalConfirmed: Boolean(entry.hostRemoved),
    error: { code: "NATIVE_RECOVERY_PENDING", stage: entry.hostTaskId || entry.unknownOwner ? "cleanup" : "admission",
      message: errors.join("; ") },
    ...(entry.hostTaskId ? { hostTaskId: entry.hostTaskId, recoveryOwner: entry.hostTaskId } : {}),
    cleanup: { confirmed: false, errors } };
  if (entry.nativeBound && entry.hostTaskId && entry.cancelled &&
      (entry.hostRemoved || entry.ownerHandle) && !entry.candidate) {
    try {
      if (!entry.observationSent) {
        entry.connection.send({
          ...(entry.pendingObservation || {
            hostTaskId: entry.hostTaskId, hostStatus: "cancelled", text: "Native owner reconciled",
            reusedOwner: Boolean(entry.ownerHandle),
          }),
          ...(entry.pendingObservation && Date.now() >= entry.deadline ? { hostStatus: "cancelled" } : {}),
          cancellationConfirmed: Boolean(entry.cancelled), removalConfirmed: Boolean(entry.hostRemoved),
        });
        entry.observationSent = true;
        entry.persistencePromise = entry.connection.next();
      }
      entry.candidate = await bounded(entry.persistencePromise, "persistence", until);
    } catch (error) {
      return { status: "failed", cancelled: false, hostCancellationConfirmed: Boolean(entry.cancelled),
        hostRemovalConfirmed: Boolean(entry.hostRemoved), hostTaskId: entry.hostTaskId,
        recoveryOwner: entry.hostTaskId,
        error: { code: "NATIVE_RECOVERY_PENDING", stage: error.stage || "persistence",
          message: String(error.message ?? error) },
        cleanup: { confirmed: false, errors: [String(error.message ?? error)] } };
    }
  }
  if (ownerListing === "adopted" && !entry.nativeBound) {
    try {
    entry.connection.send({ status: "admitted", hostTaskId: entry.hostTaskId });
    const bound = await bounded(entry.connection.next(), "binding", until);
    if (bound.status !== "bound") throw new Error(bound.error?.message || "Run did not bind the reconciled host owner");
    entry.nativeBound = true;
    entry.connection.send({ hostTaskId: entry.hostTaskId, hostStatus: "cancelled", text: "Reconciled native owner",
      cancellationConfirmed: true, removalConfirmed: Boolean(entry.hostRemoved),
      reusedOwner: Boolean(entry.ownerHandle) });
    entry.observationSent = true;
    entry.persistencePromise = entry.connection.next();
    entry.candidate = await bounded(entry.persistencePromise, "persistence", until);
    } catch (error) {
    return { status: "failed", cancelled: false, hostCancellationConfirmed: Boolean(entry.cancelled),
      hostRemovalConfirmed: Boolean(entry.hostRemoved), recoveryOwner: entry.hostTaskId,
      error: { code: "NATIVE_RECOVERY_PENDING", stage: error.stage || "persistence", message: String(error.message ?? error) },
      cleanup: { confirmed: false, errors: [String(error.message ?? error)] } };
    }
  }
  if (!entry.bridgeClosed) {
    try { await bounded(entry.connection.close(), "cleanup", until); entry.bridgeClosed = true; }
    catch (error) {
      entry.connection.child.kill();
      entry.recoveryPending = true;
      return { status: "failed", cancelled: false, hostCancellationConfirmed: Boolean(entry.cancelled),
        hostRemovalConfirmed: Boolean(entry.hostRemoved), recoveryOwner: entry.hostTaskId,
        error: { code: "NATIVE_RECOVERY_PENDING", stage: "cleanup", message: String(error.message ?? error) },
        cleanup: { confirmed: false, errors: [String(error.message ?? error)] } };
    }
  }
  if (active.get(entry.key) === entry) active.delete(entry.key);
  return { status: "ok", cancelled: Boolean(entry.cancelled), hostCancellationConfirmed: Boolean(entry.cancelled),
    hostRemovalConfirmed: Boolean(entry.hostRemoved),
    hostTaskId: entry.hostTaskId, recoveryOwner: entry.hostTaskId, cleanup: { confirmed: true, errors: [] },
    ...(ownerListing ? { ownerListing } : {}),
    ...(entry.candidate ? { adopted: true, candidate: entry.candidate } : {}) };
}

async function withAdmission(operation) {
  if (pendingDispatches >= HARD_CHILD_CAP) throw new Error(`CHILD_LIMIT: ${HARD_CHILD_CAP} dispatches already admitted`);
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
  if (inside(repo, installed.root)) {
    throw new Error("Trusted native installation cannot be inside the target repository");
  }
  return { repo, action, runId: args.run_id, taskId: args.task_id, owner: session.sessionId,
    nativeInstallation: { version: installed.version, extensionSha256: installed.extensionSha256,
      provenance: "executing user-installed extension manifest; pinned files rechecked" } };
}

function inside(root, path) {
  const suffix = relative(root, path);
  return suffix !== ".." && !suffix.startsWith(`..${sep}`) && !isAbsolute(suffix);
}

function workKey(input) {
  return JSON.stringify([input.repo, input.runId, input.taskId]);
}

async function nativeCapacity(args, invocation, tasks, until) {
  const connection = pipe({ ...request(args, "capacity", invocation), hostTasks: hostTaskInventory(tasks) });
  try {
    const response = await bounded(connection.next(), "preflight", until,
      { signal: invocation.signal, clock: () => performance.now() });
    if (response.status !== "ok" || !Array.isArray(response.result?.unresolvedAttemptIds))
      throw staged("preflight", response.error?.message || "canonical native capacity could not be read");
    return response.result.unresolvedAttemptIds;
  } finally {
    const remaining = Math.max(0, until - performance.now());
    try { await bounded(connection.close(), "cleanup", Date.now() + remaining); }
    catch { connection.child.kill(); }
  }
}

async function reconcileNativeRequest(args, action, invocation, extra = {}) {
  const until = Date.now() + RECOVERY_MS;
  const tasks = await bounded(hostTasks(), "preflight", until, { signal: invocation.signal });
  const hostWorkers = {
    visibility: "OBSERVED", source: "joined supported tasks RPC, this session only",
    observedAt: new Date().toISOString(),
    activeCount: tasks.filter(task => task.type === "agent" && task.status === "running").length,
    idleProven: false, allSessionsObserved: false,
  };
  const connection = pipe({ ...request(args, action, invocation), ...extra,
    ...(action === "recover" ? { hostWorkers } : {}), hostTasks: hostTaskInventory(tasks) });
  try {
    const response = await bounded(connection.next(), "preflight", until, { signal: invocation.signal });
    if (response.status !== "recovery-required") return response;
    const cleanupUntil = until;
    const owners = [];
    for (const target of response.targets) {
      const owner = { attemptId: target.attemptId, hostTaskId: target.hostTaskId,
        cancellationConfirmed: false, removalConfirmed: false, error: null };
      try {
        const cancelled = await bounded(session.rpc.tasks.cancel({ id: target.hostTaskId }), "cleanup", cleanupUntil);
        owner.cancellationConfirmed = cancelled?.cancelled === true;
        if (owner.cancellationConfirmed && target.removeRequired) {
          const removed = await bounded(session.rpc.tasks.remove({ id: target.hostTaskId }), "cleanup", cleanupUntil);
          owner.removalConfirmed = removed?.removed === true;
          if (!owner.removalConfirmed) owner.error = removed?.error || "Host removal was not confirmed";
        }
        if (!owner.cancellationConfirmed) owner.error = cancelled?.error || "Host cancellation was not confirmed";
      } catch (error) { owner.error = String(error.message ?? error); }
      owners.push(owner);
    }
    connection.send({ status: "reconciled", owners });
    return await bounded(connection.next(), "persistence", cleanupUntil, { signal: invocation.signal });
  } finally {
    try { await bounded(connection.close(), "cleanup", Date.now() + RECOVERY_MS); }
    catch { connection.child.kill(); }
  }
}

function dispatchConflict(entry) {
  return result({ status: "failed", hostCancellationConfirmed: Boolean(entry.cancelled),
    hostRemovalConfirmed: Boolean(entry.hostRemoved),
    error: entry.recoveryPending ? { code: "NATIVE_RECOVERY_PENDING", stage: entry.stage,
      message: "An earlier dispatch of this WorkPacket has unresolved admission or cleanup; reconcile it with architrave_native_cancel instead of redispatching" } :
      { code: "NATIVE_DISPATCH_ACTIVE", stage: entry.stage, message: "This WorkPacket is already being dispatched by this bridge" },
    ...(entry.hostTaskId ? { hostTaskId: entry.hostTaskId, recoveryOwner: entry.hostTaskId } : {}) });
}

const tools = [
  {
    name: "architrave_native_dispatch",
    description: "Dispatch one bounded canonical WorkPacket through the joined host. Candidate only; independent gates required. Model pin only when explicitly supplied by the user; otherwise host inheritance.",
    parameters: { type: "object", properties: { ...identitySchema,
      reqs: { type: "array", items: { type: "string", pattern: "^REQ-[A-Za-z0-9_.-]+$" }, minItems: 1, uniqueItems: true, description: "Canonical task REQ ids; required when repository requirements are configured" },
      owner_handle: { type: "string", description: "Optional retained idle owner already bound to this same canonical task/objective; never repurpose another task's context" },
      model: { type: "string", description: "Optional explicit USER-requested host model pin; omit to inherit host settings" },
      retry_hypothesis: { type: "string", description: "New bounded hypothesis required for an intentional retry without new observed evidence" },
    }, required: ["repo", "run_id", "task_id"], additionalProperties: false },
    handler: async (args, invocation) => {
      if (invocation.signal?.aborted) return result({ status: "failed",
        error: { code: "NATIVE_ABORTED", stage: "preflight", message: "Dispatch was aborted before preflight" },
        hostCancellationConfirmed: false, hostRemovalConfirmed: false });
      let dispatchStage = "preflight";
      try { return await withAdmission(async () => {
      const input = request(args, "dispatch", invocation);
      if (typeof session.rpc.tasks?.[args.owner_handle ? "sendMessage" : "remove"] !== "function")
        throw new Error(`NATIVE_HOST_REQUIRED: dispatch requires tasks.${args.owner_handle ? "sendMessage" : "remove"} before admission`);
      const key = workKey(input);
      const retained = active.get(key);
      if (retained?.dispatch) return dispatchConflict(retained);
      const preflightUntil = performance.now() + PREFLIGHT_MS;
      let tasks;
      try { tasks = await bounded(hostTasks(), "preflight", preflightUntil,
        { signal: invocation.signal, clock: () => performance.now() }); }
      catch (error) {
        if (!error.timedOut && String(error.message).startsWith("NATIVE_HOST_REQUIRED")) throw error;
        return result({ status: "failed", hostCancellationConfirmed: false,
          error: { code: error.aborted ? "NATIVE_ABORTED" : "NATIVE_HOST_FAILED",
            stage: "preflight", message: String(error.message) } });
      }
      let unresolvedAttemptIds;
      try { unresolvedAttemptIds = await nativeCapacity(args, invocation, tasks, preflightUntil); }
      catch (error) {
        return result({ status: "failed", hostCancellationConfirmed: false,
          error: { code: error.aborted ? "NATIVE_ABORTED" : "NATIVE_HOST_FAILED",
            stage: "preflight", message: String(error.message ?? error) } });
      }
      const concurrent = active.get(key);
      if (concurrent?.dispatch) return dispatchConflict(concurrent);
      if (semanticScope) throw new Error("SEMANTIC_REVIEW_BUSY: frozen review owns this joined session");
      const owned = new Set([...active.values()].map(entry => entry.hostTaskId));
      const outside = tasks.filter(task => task.type === "agent" && task.status === "running" && !owned.has(task.id)).length;
      const currentAttempts = new Set([...active.values()].map(entry => entry.attemptId).filter(Boolean));
      const retainedReservations = [...active.values()].filter(entry => entry.dispatch && entry.recoveryPending).length;
      const unseenReservations = unresolvedAttemptIds.filter(attemptId => !currentAttempts.has(attemptId)).length;
      const cap = childCap(input.repo);
      if (outside + retainedReservations + unseenReservations + pendingDispatches > cap) {
        throw new Error(`CHILD_LIMIT: ${cap} active host children already exist, including child-originated work (workers.maxParallel)`);
      }
      if (args.owner_handle && !tasks.some(task => task.id === args.owner_handle && task.type === "agent" && task.status === "idle")) {
        throw new Error("Existing owner must be an idle native agent in the current joined host session");
      }
      const connection = pipe({ ...input, reqs: args.reqs, retryHypothesis: args.retry_hypothesis,
        ownerHandle: args.owner_handle });
      // REQ-97: the entry (recovery identity) is registered before preflight and kept until reconciled
      // whenever admission was attempted, so a late or lost host result is adopted rather than redispatched.
      const entry = { key, dispatch: true, connection, repo: input.repo, ownerHandle: args.owner_handle,
        stage: "preflight", cancelled: false,
        preflightHostTaskIds: new Set(tasks.filter(task => task.type === "agent" && typeof task.id === "string")
          .map(task => task.id)) };
      active.set(key, entry);
      let timeout;
      let cleanupUntil;
      let observer;
      try {
        const prepared = await bounded(connection.next(), "preflight", preflightUntil,
          { signal: invocation.signal, clock: () => performance.now() });
        if (prepared.status !== "prepared") {
          if (active.get(key) === entry) active.delete(key);
          await bounded(connection.close(), "cleanup", Date.now() + RECOVERY_MS).catch(() => connection.child.kill());
          entry.bridgeClosed = true;
          return result(prepared);
        }
        // The lease expiry bounds every stage after preflight (which has its own fixed bound); the main
        // stages stop early to reserve a cleanup budget.
        entry.prompt = prepared.prompt;
        entry.attemptId = prepared.binding?.workerId;
        if (typeof entry.attemptId !== "string" || !entry.attemptId) {
          throw staged("preflight", "Run did not provide a persisted native attempt identity");
        }
        entry.attemptMarker = `Architrave native attempt:${entry.attemptId}`;
        const dispatchedAt = Date.now();
        const deadline = Date.parse(prepared.expiresAt);
        entry.deadline = deadline;
        const reserve = Math.min(5000, Math.max(1000, 0.2 * (deadline - Date.now())));
        const mainUntil = deadline - reserve;
        cleanupUntil = Math.max(deadline, Date.now()) + RECOVERY_MS;
        observer = observeTask(prepared.maxTurns);
        if (invocation.signal?.aborted) throw Object.assign(
          staged("admission", "Dispatch was aborted before admission"), { aborted: true });
        if (!Number.isFinite(deadline) || Date.now() >= mainUntil)
          throw staged("admission", "WorkPacket lease expired before host admission");
        entry.stage = "admission";
        dispatchStage = entry.stage;
        entry.admissionStarted = entry.admissionPending = true;
        if (!args.owner_handle) entry.unknownOwner = true;
        if (args.owner_handle) entry.hostTaskId = args.owner_handle;
        connection.send({ status: "starting", attemptId: entry.attemptId });
        const start = (async () => {
          if (args.owner_handle) {
            const sent = await session.rpc.tasks.sendMessage({ id: args.owner_handle, message: prepared.prompt });
            if (!sent?.sent) throw new Error(sent?.error || "Host rejected WorkPacket delivery");
            return args.owner_handle;
          }
          const admitted = await session.rpc.tasks.startAgent({
            agentType: prepared.agentType, prompt: prepared.prompt,
            name: `Architrave ${args.task_id} ${entry.attemptId}`,
            description: entry.attemptMarker,
            ...(args.model ? { model: args.model } : {}),
          });
          return admitted.agentId;
        })();
        start.then(id => {
          if (typeof id !== "string" || !id) {
            entry.admissionPending = false;
            return;
          }
          entry.hostTaskId = id;
          entry.unknownOwner = false;
          entry.admissionPending = false;
          if (entry.abandoned) void finishLateAdmission(entry, id);
        }, () => {
          entry.admissionPending = false;
          if (!args.owner_handle) entry.unknownOwner = true; // The start may have created a host child anyway.
        });
        const hostTaskId = await bounded(start, "admission", mainUntil, { signal: invocation.signal });
        if (typeof hostTaskId !== "string" || !hostTaskId) throw staged("admission", "Host returned no owner identity");
        connection.send({ status: "admitted", hostTaskId });
        entry.stage = "binding";
        dispatchStage = entry.stage;
        const bindingReply = connection.next();
        entry.bindingPromise = bindingReply;
        entry.bindingPending = true;
        bindingReply.finally(() => { entry.bindingPending = false; }).catch(() => {});
        bindingReply.then(bound => { entry.nativeBound = bound.status === "bound"; }, () => {});
        const bound = await bounded(bindingReply, "binding", mainUntil, { signal: invocation.signal });
        if (bound.status !== "bound") throw staged("binding", bound.error?.message || "Run rejected host admission");
        entry.nativeBound = true;
        entry.stage = "observation";
        dispatchStage = entry.stage;
        const observation = observer.wait(hostTaskId, mainUntil, task => !args.owner_handle ||
          task.prompt === prepared.prompt && Date.parse(task.idleSince || task.completedAt || "") >= dispatchedAt);
        let observed = await bounded(observation, "observation", deadline, { signal: invocation.signal });
        if (!observed || !["completed", "idle", "failed", "cancelled"].includes(observed.status)) {
          timeout = true;
          observed = { id: hostTaskId, status: "cancelled", error: "WorkPacket time budget exceeded", budgetStop: "time" };
        }
        const text = String(observed.result || observed.latestResponse || observed.error || "").slice(0, 8192);
        entry.pendingObservation = {
          hostTaskId, hostStatus: observed.status, text, reusedOwner: Boolean(args.owner_handle),
          requestedModel: args.model || null, effectiveModel: observed.effectiveModel || observed.resolvedModel || null,
          usageTotal: observed.usageTotal ?? null, totalToolCalls: observed.totalToolCalls ?? null,
          turnsObserved: observed.turnsObserved ?? null, budgetStop: observed.budgetStop ?? null,
        };
        entry.stage = "cleanup";
        dispatchStage = entry.stage;
        cleanupUntil = Date.now() + RECOVERY_MS;
        const errors = await settleDispatch(entry, cleanupUntil,
          { stop: !args.owner_handle || timeout, remove: !args.owner_handle, closeBridge: false });
        if (errors.length) throw staged("cleanup", errors.join("; "));
        connection.send({ ...entry.pendingObservation,
          cancellationConfirmed: Boolean(entry.cancelled), removalConfirmed: Boolean(entry.hostRemoved) });
        entry.observationSent = true;
        entry.stage = "persistence";
        dispatchStage = entry.stage;
        const persisted = connection.next();
        entry.persistencePromise = persisted;
        persisted.then(candidate => { entry.candidate = candidate; }, () => {}); // A late reply is still adopted.
        const candidate = await bounded(persisted, "persistence", cleanupUntil);
        entry.candidate = candidate;
        entry.stage = "cleanup";
        dispatchStage = entry.stage;
        await bounded(connection.close(), "cleanup", cleanupUntil);
        entry.bridgeClosed = true;
        if (active.get(key) === entry) active.delete(key);
        return result({ ...candidate, hostTaskId, hostCancellationConfirmed: Boolean(entry.cancelled),
          hostRemovalConfirmed: Boolean(entry.hostRemoved), timedOut: Boolean(timeout), effort: prepared.effort });
      } catch (error) {
        const stage = error.stage || entry.stage;
        cleanupUntil = Math.min(cleanupUntil ?? Infinity, Date.now() + RECOVERY_MS);
        entry.abandoned = entry.recoveryPending = true;
        entry.stage = stage;
        if (error.aborted && stage === "admission" && entry.hostTaskId && !entry.nativeBound) {
          await finishLateAdmission(entry, entry.hostTaskId);
        }
        if (stage === "binding" && entry.bindingPromise) {
          try {
            const bound = await bounded(entry.bindingPromise, "binding", cleanupUntil);
            entry.nativeBound = bound.status === "bound";
          } catch (bindingError) {
            entry.recoveryError = String(bindingError.message ?? bindingError);
          }
        }
        const errors = entry.lateCleanup ? (entry.recoveryError ? [entry.recoveryError] : []) :
          await settleDispatch(entry, cleanupUntil ?? Date.now() + RECOVERY_MS,
            { stop: true, remove: !args.owner_handle && (!entry.bindingPromise || entry.nativeBound),
              closeBridge: false });
        if (entry.bindingPromise && !entry.nativeBound)
          errors.push("Run owner binding is unresolved; retain this attempt for reconciliation");
        if (entry.unknownOwner && !entry.hostTaskId) errors.push("admission: host start failed; any created owner is unknown");
        if (entry.hostTaskId && entry.nativeBound && entry.cancelled &&
            (entry.hostRemoved || entry.ownerHandle) && !entry.observationSent && !entry.pendingObservation) {
          try {
            connection.send({ hostTaskId: entry.hostTaskId, hostStatus: "cancelled",
              text: error.aborted ? "Dispatch aborted" : "Dispatch stopped after host failure",
              cancellationConfirmed: true, removalConfirmed: Boolean(entry.hostRemoved),
              reusedOwner: Boolean(entry.ownerHandle) });
            entry.observationSent = true;
            entry.persistencePromise = connection.next();
            entry.candidate = await bounded(entry.persistencePromise, "persistence", cleanupUntil ?? Date.now() + RECOVERY_MS);
          } catch (reportError) { errors.push(`Run cancellation receipt: ${String(reportError.message ?? reportError)}`); }
        }
        if (entry.nativeBound && !entry.candidate &&
            (entry.pendingObservation || entry.observationSent)) {
          errors.push("Run observation persistence is unresolved; retain this attempt for reconciliation");
        }
        if (!entry.admissionPending && !entry.lateCleanup && !entry.unknownOwner && !errors.length) {
          try { await bounded(connection.close(), "cleanup", cleanupUntil); entry.bridgeClosed = true; }
          catch (closeError) {
            connection.child.kill();
            errors.push(`bridge cleanup: ${String(closeError.message ?? closeError)}`);
          }
        }
        // Retain the identity only while something is unresolved; a confirmed-clean failure lets the Run retry.
        if (!errors.length && !entry.admissionPending && !entry.unknownOwner && active.get(key) === entry) active.delete(key);
        return result({ status: "failed", error: { code: error.aborted ? "NATIVE_ABORTED" : "NATIVE_HOST_FAILED",
          stage, message: String(error.message ?? error) },
          hostTaskId: entry.hostTaskId, hostCancellationConfirmed: Boolean(entry.cancelled),
          hostRemovalConfirmed: Boolean(entry.hostRemoved),
          ...(entry.hostTaskId ? { recoveryOwner: entry.hostTaskId } : {}),
          ...(entry.candidate ? { candidate: entry.candidate } : {}),
          cleanup: { confirmed: !errors.length && !entry.admissionPending && !entry.unknownOwner, errors } });
      } finally {
        observer?.close();
      }
      }); } catch (error) {
        if (error && typeof error === "object" && !error.stage) error.stage = dispatchStage;
        throw error;
      }
    },
  },
  {
    name: "architrave_native_cancel",
    description: "Cancel an active native WorkPacket through its actual joined host owner; no fabricated result.",
    parameters: { type: "object", properties: identitySchema,
      required: ["repo", "run_id", "task_id"], additionalProperties: false },
    handler: async (args, invocation) => {
      const input = request(args, "status", invocation);
      const scopeKey = workKey(input);
      const recoveries = [...active.values()].filter(value => value.semantic && value.scopeKey === scopeKey);
      const entry = active.get(scopeKey) || (recoveries.length === 1 ? recoveries[0] : null);
      if (!entry) return result(await reconcileNativeRequest(args, "native-cancel", invocation));
      if (entry.repo !== input.repo) throw new Error("No live native bridge owns this WorkPacket");
      if (entry.dispatch && entry.recoveryPending) return result(await reconcileDispatch(entry));
      if (!entry.hostTaskId && !entry.recoveryPending) return result({ status: "failed", cancelled: false,
        hostCancellationConfirmed: false, error: { code: "NATIVE_RECOVERY_PENDING", stage: entry.stage,
          message: "Host admission has not returned an owner yet; nothing confirmed to cancel" } });
      if (entry.recoveryPending) {
        const errors = await cleanupSemanticOwner(entry.hostTaskId, entry.connection, entry);
        if (errors.length) return result({ status: "failed", cancelled: false,
          recoveryOwner: entry.hostTaskId, cleanup: { confirmed: false, errors } });
        active.delete(entry.key);
        if (semanticScope === entry.repo) semanticScope = undefined;
        return result({ status: "ok", cancelled: true, hostTaskId: entry.hostTaskId });
      }
      let outcome;
      try { outcome = await bounded(session.rpc.tasks.cancel({ id: entry.hostTaskId }), "cleanup", Date.now() + RECOVERY_MS); }
      catch (error) { outcome = { error: error.message }; }
      if (!outcome?.cancelled) return result({ status: "failed", cancelled: false, hostCancellationConfirmed: false,
        hostRemovalConfirmed: Boolean(entry.hostRemoved),
        hostTaskId: entry.hostTaskId, recoveryOwner: entry.hostTaskId,
        error: { code: "NATIVE_HOST_FAILED", stage: "cleanup", message: outcome?.error || "Host cancellation was not confirmed" } });
      entry.cancelled = entry.stopped = true;
      return result({ status: "ok", cancelled: true, hostCancellationConfirmed: true,
        hostRemovalConfirmed: Boolean(entry.hostRemoved), hostTaskId: entry.hostTaskId });
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
      if (action === "recover") return result(await reconcileNativeRequest(args, "recover", invocation, {
        checkpointId: args.checkpoint_id,
      }));
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
    if (invocation.signal?.aborted) return result({ status: "failed",
      error: { code: "NATIVE_ABORTED", stage: "preflight", message: "Review was aborted before preflight" } });
    if (Object.keys(args).some(key => !["repo", "run_id", "task_id", "reviewer"].includes(key))) {
      throw new Error("Semantic execution accepts no claimed verdict, producer, event or model");
    }
    const preflightUntil = performance.now() + PREFLIGHT_MS;
    const tasks = await bounded(hostTasks(), "preflight", preflightUntil,
      { signal: invocation.signal, clock: () => performance.now() });
    if (typeof session.rpc.tasks.remove !== "function") {
      throw new Error("NATIVE_HOST_REQUIRED: semantic review requires tasks.remove before reviewer admission");
    }
    if (semanticScope || pendingDispatches !== 1 || tasks.some(task => task.type === "agent" && task.status === "running")) {
      throw new Error("SEMANTIC_REVIEW_BUSY: frozen-source reviews run alone in this joined session");
    }
    const input = { ...request(args, "semantic-review", invocation),
      invocationId: invocation.toolCallId, reviewer: args.reviewer || "rubber-duck" };
    const connection = pipe(input);
    semanticScope = input.repo;
    const scopeKey = workKey(input);
    const key = `review:${scopeKey}:${invocation.toolCallId}`;
    const entry = { key, scopeKey, connection, repo: input.repo, semantic: true,
      attemptMarker: `Architrave semantic attempt:${invocation.toolCallId}`,
      preflightHostTaskIds: new Set(tasks.map(task => task.id)) };
    active.set(key, entry);
    let hostTaskId, observer, cleanupAttempted = false;
    try {
      const prepared = await bounded(connection.next(), "preflight", preflightUntil,
        { signal: invocation.signal, clock: () => performance.now() });
      if (prepared.status !== "prepared") return result(prepared);
      if (!Number.isInteger(prepared.sourceFileCount) || prepared.sourceFileCount < 0 || prepared.sourceFileCount > 4096)
        throw new Error("Native source inventory count is invalid");
      const inventory = [];
      while (inventory.length < prepared.sourceFileCount) {
        const chunk = await bounded(connection.next(), "preflight", preflightUntil,
          { signal: invocation.signal, clock: () => performance.now() });
        if (chunk.status !== "source-inventory" || !Array.isArray(chunk.files) || !chunk.files.length ||
            chunk.files.some(path => typeof path !== "string") ||
            inventory.length + chunk.files.length > prepared.sourceFileCount)
          throw new Error("Native source inventory frame is invalid");
        inventory.push(...chunk.files);
      }
      const semanticFiles = inventory.map(path => {
        const file = resolve(input.repo, path);
        const suffix = relative(input.repo, file);
        const info = lstatSync(file);
        if (!inside(input.repo, file) ||
            suffix.split(/[\\/]/).some(part => [".git", ".architrave"].includes(part.toLowerCase())) ||
            !info.isFile() || info.isSymbolicLink() || realpathSync(file) !== file)
          throw new Error("SEMANTIC_SOURCE_UNSUPPORTED: full advertised source inventory contains a private, aliased or non-regular entry");
        return file;
      });
      const deadline = Date.parse(prepared.expiresAt);
      if (!Number.isFinite(deadline)) throw new Error("Native semantic deadline is invalid");
      const prompt = semanticReviewPrompt(prepared.prompt, semanticFiles);
      observer = observeTask(prepared.maxTurns, true);
      if (invocation.signal?.aborted) throw staged("admission",
        Object.assign(new Error("Review was aborted before admission"), { aborted: true }));
      if (Date.now() >= deadline) throw staged("admission", "Review lease expired before host admission");
      entry.admissionPending = entry.unknownOwner = true;
      const admission = Promise.resolve().then(() => session.rpc.tasks.startAgent({
        agentType: prepared.agentType, prompt,
        name: `Architrave semantic ${args.task_id}`, description: entry.attemptMarker,
      }));
      admission.then(admitted => {
        entry.admissionPending = false;
        if (typeof admitted?.agentId !== "string" || !admitted.agentId) return;
        entry.hostTaskId = admitted.agentId;
        entry.unknownOwner = false;
        if (entry.recoveryPending) void cleanupSemanticOwner(entry.hostTaskId, connection, entry).then(errors => {
          if (!errors.length && active.get(key) === entry) {
            active.delete(key);
            semanticScope = undefined;
          }
        });
      }, () => { entry.admissionPending = false; });
      const admitted = await bounded(admission, "admission", deadline, { signal: invocation.signal });
      if (typeof admitted?.agentId !== "string" || !admitted.agentId)
        throw new Error("Native semantic host admission returned no owner identity");
      hostTaskId = admitted.agentId;
      connection.send({ status: "admitted", hostTaskId });
      const bound = await bounded(connection.next(), "binding", deadline, { signal: invocation.signal });
      if (bound.status !== "bound") throw new Error(bound.error?.message || "Semantic host binding failed");
      const observed = await bounded(observer.wait(hostTaskId, deadline, () => true),
        "observation", deadline, { signal: invocation.signal });
      if (!observed || !observed.completionEvent) throw new Error("SEMANTIC_HOST_PROVENANCE: completion metadata unavailable within bound");
      connection.send({
        hostTaskId, hostStatus: observed.status,
        text: String(observed.result || observed.latestResponse || ""),
        completion: observed.completionEvent,
      });
      const outcome = await bounded(connection.next(), "persistence", Math.max(deadline, Date.now()) + RECOVERY_MS,
        { signal: invocation.signal });
      cleanupAttempted = true;
      const cleanupErrors = await cleanupSemanticOwner(hostTaskId, connection, entry);
      if (cleanupErrors.length && entry) entry.recoveryPending = true;
      else if (key) active.delete(key);
      return result({ ...outcome, cleanup: { confirmed: !cleanupErrors.length, errors: cleanupErrors },
        ...(cleanupErrors.length ? { recoveryOwner: hostTaskId } : {}) });
    } catch (error) {
      cleanupAttempted = true;
      entry.recoveryPending = true;
      const cleanupErrors = await cleanupSemanticOwner(hostTaskId, connection, entry);
      if (cleanupErrors.length && entry) entry.recoveryPending = true;
      else if (key) active.delete(key);
      return result({ status: "failed", error: { code: "NATIVE_SEMANTIC_FAILED", stage: error.stage,
        message: String(error) }, hostTaskId: entry.hostTaskId || hostTaskId,
        cleanup: { confirmed: !cleanupErrors.length, errors: cleanupErrors },
        ...(cleanupErrors.length && entry.hostTaskId ? { recoveryOwner: entry.hostTaskId } : {}) });
    } finally {
      try { observer?.close(); }
      catch (error) { process.stderr.write(`Native semantic observer cleanup failed: ${String(error)}\n`); }
      if (!cleanupAttempted) {
        const errors = await cleanupSemanticOwner(hostTaskId, connection, entry);
        if (errors.length) {
          if (entry) entry.recoveryPending = true;
          process.stderr.write(`Native semantic cleanup needs recovery: ${errors.join("; ")}\n`);
        } else if (key) active.delete(key);
      }
      const pending = active.get(key);
      if (!pending || pending.hostRemoved) semanticScope = undefined;
    }
  }),
});

async function cleanupSemanticOwner(owner, connection, progress = {}) {
  if (progress.cleanupPromise) return progress.cleanupPromise;
  progress.cleanupPromise = cleanupSemanticOwnerOnce(owner, connection, progress).finally(() => {
    progress.cleanupPromise = undefined;
  });
  return progress.cleanupPromise;
}

async function cleanupSemanticOwnerOnce(owner, connection, progress) {
  const errors = [];
  const until = Date.now() + RECOVERY_MS;
  if (!owner && (progress.admissionPending || progress.unknownOwner)) {
    if (!progress.admissionPending) {
      try {
        const tasks = await bounded(hostTasks(), "cleanup", until);
        const matches = tasks.filter(task => task.type === "agent" &&
          task.description === progress.attemptMarker && !progress.preflightHostTaskIds.has(task.id));
        if (matches.length === 1) {
          owner = progress.hostTaskId = matches[0].id;
          progress.unknownOwner = false;
        }
      } catch (error) { errors.push(`host listing: ${String(error)}`); }
    }
    if (!owner) {
      errors.push("Host reviewer admission is unresolved; retain ownership until its exact owner is reconciled");
      return errors;
    }
  }
  if (owner && !progress.hostRemoved) {
    try {
      if (!progress.cancelled) {
        const outcome = await bounded(session.rpc.tasks.cancel({ id: owner }), "cleanup", until);
        if (!outcome.cancelled) throw new Error("Host cancellation was not confirmed");
        progress.cancelled = true;
      }
      const removed = await bounded(session.rpc.tasks.remove({ id: owner }), "cleanup", until);
      if (!removed.removed) throw new Error("Host removal was not confirmed");
      progress.hostRemoved = true;
    } catch (error) { errors.push(`host cleanup: ${String(error)}`); }
  }
  try {
    if (!progress.bridgeClosed) {
      await bounded(connection.close(), "cleanup", until);
      progress.bridgeClosed = true;
    }
  }
  catch (error) { connection.child.kill(); errors.push(`bridge cleanup: ${String(error)}`); }
  return errors;
}

tools.push({
  name: "architrave_native_batch",
  description: "Invoke two to twenty (within workers.maxParallel) pre-decomposed independent canonical WorkPackets concurrently through the same native dispatch. No automatic decomposition or recursive spawning.",
  parameters: { type: "object", properties: {
    repo: identitySchema.repo, run_id: identitySchema.run_id,
    task_ids: { type: "array", items: { type: "string" }, minItems: 2, maxItems: 20, uniqueItems: true },
    reqs: { type: "object", additionalProperties: { type: "array", items: { type: "string", pattern: "^REQ-[A-Za-z0-9_.-]+$" }, minItems: 1, uniqueItems: true }, description: "REQ ids keyed by task id; each task needs an entry when requirements are configured" },
  }, required: ["repo", "run_id", "task_ids"], additionalProperties: false },
  handler: async (args, invocation) => {
    const results = await Promise.all(args.task_ids.map(task_id =>
      Promise.resolve().then(() => tools[0].handler({ repo: args.repo, run_id: args.run_id, task_id, reqs: args.reqs?.[task_id] }, invocation))
        .catch(error => result({ status: "failed", error: { code: "NATIVE_HOST_FAILED",
          stage: error.stage || "preflight", message: String(error.message ?? error) } }))));
    return { textResultForLlm: JSON.stringify(results.map(item => JSON.parse(item.textResultForLlm))),
      resultType: results.some(item => item.resultType === "failure") ? "failure" : "success" };
  },
});

session = await joinSession({ tools });
