// Optional read-only projection. Python Run APIs remain the only authority.
import { createServer } from "node:http";
import { randomBytes, createHash } from "node:crypto";
import { mkdir, lstat, readFile, writeFile, rename, unlink, realpath, open } from "node:fs/promises";
import { pid, kill } from "node:process";
import { setTimeout as delay } from "node:timers/promises";
import { join } from "node:path";
import { homedir } from "node:os";
import { joinSession, createCanvas, CanvasError } from "@github/copilot-sdk/extension";

const LIMIT = 65536;
const states = {
    done: "Scoped done", verified: "Product verified", active: "Active",
    blocked: "Blocked", deferred: "Deferred", bypassed: "Bypassed",
    stopped: "Dead end / stop", planned: "Planned",
};
const text = { type: "string", minLength: 1, maxLength: 1200 };
const id = { type: "string", pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$" };
const domain = { type: "string", minLength: 1, maxLength: 256, pattern: "^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$" };
const nullableText = { anyOf: [text, { type: "null" }] };
const count = { type: "integer", minimum: 0, maximum: 1000000000 };
const object = (properties, required = Object.keys(properties)) =>
    ({ type: "object", additionalProperties: false, properties, required });
export const snapshotSchema = object({
    schema: { const: "architrave.ribbon.v1" }, domainKey: domain, runId: id,
    revision: count, objectiveVersion: count, title: text, objective: text,
    capturedAt: text, startedAt: text, deadline: nullableText,
    source: object({ commit: text, sha256: text, freshness: { enum: ["current", "stale", "unknown"] }, provenance: text }),
    next: nullableText, milestone: nullableText,
    steps: { type: "array", maxItems: 80, items: object({
        id, title: text, state: { enum: Object.keys(states) }, current: { type: "boolean" }, reason: text,
        evidence: { type: "array", maxItems: 12, items: text },
        dependencies: { type: "array", maxItems: 80, uniqueItems: true, items: id },
        blocker: { enum: [null, "human", "resource", "dependency"] },
        attempts: count, retry: { anyOf: [{ type: "null" }, object({
            fingerprint: text, evidenceFingerprint: text, repeated: { type: "integer", minimum: 1, maximum: 1000000000 },
            stopped: { type: "boolean" }, reason: text,
        })] },
        weightEstimate: { type: "number", minimum: 1, maximum: 10 },
        streamId: id, workKind: text, owner: nullableText, hostOwner: nullableText, hostTaskId: nullableText,
        startedAt: nullableText, finishedAt: nullableText,
    }, ["id", "title", "state", "current", "reason", "evidence", "dependencies", "blocker", "attempts", "retry", "weightEstimate"]) },
    streams: { type: "array", maxItems: 80, items: object({
        id, label: text, kind: { enum: ["delivery", "exploratory", "reference", "review", "operations", "unassigned"] },
        outcome: text, sourceRef: object({
            domainKey: domain, runId: id, revision: count, objectiveVersion: count, capturedAt: text, commit: text, sha256: text,
            freshness: { enum: ["current", "stale", "unknown"] },
        }),
    }) },
    relations: { type: "array", maxItems: 160, items: object({
        fromStep: id, toStep: id, type: { enum: ["blocks", "informs"] }, reason: text,
        provenance: { enum: ["canonical dependency", "display-only annotation"] },
    }) },
}, ["schema", "domainKey", "runId", "revision", "objectiveVersion", "title", "objective",
    "capturedAt", "startedAt", "deadline", "source", "next", "milestone", "steps"]);
const openSchema = object({ domainKey: domain, snapshot: snapshotSchema }, ["domainKey"]);
const updateSchema = object({ snapshot: snapshotSchema, expectedDigest: { anyOf: [
    { type: "string", minLength: 64, maxLength: 64, pattern: "^[a-f0-9]{64}$" }, { type: "null" },
] } });
const servers = new Map();
const queues = new Map();
let storageRoot;
const companion = {
    activity: "unavailable", selectedModel: null, selectedEffort: null,
    observedModel: null, observedEffort: null, contextTier: null, usage: null,
    observedAt: null, diagnostic: null, autoOpen: true,
    subagentsStatus: "unavailable", subagentsDiagnostic: null,
};
const activeTools = new Map();
const waiting = new Map();
let waitingOverflow = false;
const subagents = new Map();
const pendingSubagents = new Map();
const childVersions = new Map();
let childRevision = 0, displayRevision = 0;
let tasksRefreshing = false, tasksQueued = false;
let activity = "unavailable", selectionRevision = 0, sessionPreferences;
const compact = value => typeof value === "string" && value.length <= 120 ? value : null;
const caption = value => typeof value === "string" ? value.replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, 240) : null;
const validCount = value => Number.isSafeInteger(value) && value >= 0;

async function refreshSubagents() {
    if (tasksRefreshing) { tasksQueued = true; return; }
    if (typeof session.rpc?.tasks?.list !== "function") return;
    tasksRefreshing = true;
    try {
        do {
            tasksQueued = false;
            const requestedAt = childRevision;
            const result = await session.rpc.tasks.list();
            if (!Array.isArray(result.tasks)) throw new CanvasError("companion_tasks_invalid", "Invalid host task list");
            const agents = result.tasks.filter(task => task.type === "agent");
            const next = new Map();
            for (const task of agents.slice(0, 32)) {
                if (!compact(task.id)) continue;
                const pending = !subagents.has(task.id) && pendingSubagents.get(task.id);
                const previous = subagents.get(task.id) || pending;
                const versions = childVersions.get(task.id) || {};
                const status = versions.status > requestedAt || pending?.status ? previous?.status :
                    ["running", "idle", "completed", "failed", "cancelled"].includes(task.status) ? task.status : "unknown";
                next.set(task.id, { id: task.id, toolCallId: compact(task.toolCallId),
                    name: caption(task.displayName) || caption(task.description) || "Unnamed subagent",
                    role: compact(task.agentType), assignedSlice: caption(task.description),
                    status,
                    requestedModel: compact(task.model), resolvedModel: versions.model > requestedAt || pending?.resolvedModel
                        ? previous?.resolvedModel : compact(task.resolvedModel),
                    observedModel: previous?.observedModel || null, observedEffort: previous?.observedEffort || null,
                    configuredEffort: previous?.configuredEffort || null, contextTier: previous?.contextTier || null,
                    usage: previous?.usage || null, currentActivity: status === "running" ? previous?.currentActivity || null : null,
                });
            }
            subagents.clear();
            for (const [key, value] of next) subagents.set(key, value);
            for (const key of next.keys()) pendingSubagents.delete(key);
            if (!tasksQueued) pendingSubagents.clear();
            for (const key of childVersions.keys())
                if (!subagents.has(key) && !pendingSubagents.has(key)) childVersions.delete(key);
            companion.subagentsStatus = "observed";
            companion.subagentsDiagnostic = agents.length > 32 ? "Showing the first 32 host-tracked subagents." : null;
            notifyCompanion();
        } while (tasksQueued);
    } catch (error) {
        pendingSubagents.clear();
        for (const key of childVersions.keys()) if (!subagents.has(key)) childVersions.delete(key);
        companion.subagentsStatus = "unavailable";
        companion.subagentsDiagnostic = "Host task metadata unavailable; any displayed rows are last observed, not current.";
        process.stderr.write(`Architrave companion task metadata unavailable: ${compact(error.code) || "unsupported"}\n`);
        notifyCompanion();
    } finally { tasksRefreshing = false; }
}
function observeSubagent(event) {
    if (!["assistant.usage", "subagent.configured", "session.usage_info", "tool.execution_start",
        "tool.execution_complete", "subagent.completed", "subagent.failed", "session.model_change",
        "session.context_cleared"].includes(event.type)) return;
    const data = event.data || {};
    let child = subagents.get(event.agentId) ||
        (["subagent.completed", "subagent.failed"].includes(event.type)
            ? [...subagents.values()].find(item => item.toolCallId === data.toolCallId) : null);
    // Keep only field-level observations while an ownership read is pending.
    // Unconfirmed IDs never render and are discarded when that read settles.
    if (!child && tasksRefreshing && compact(event.agentId)) {
        child = pendingSubagents.get(event.agentId);
        if (!child && pendingSubagents.size < 32) {
            child = { id: event.agentId };
            pendingSubagents.set(event.agentId, child);
        }
    }
    if (!child) return;
    const versions = childVersions.get(child.id) || {};
    switch (event.type) {
    case "assistant.usage":
        if (data.initiator && data.initiator !== "sub-agent") return;
        child.observedModel = compact(data.model); child.observedEffort = compact(data.reasoningEffort); break;
    case "subagent.configured":
        child.resolvedModel = compact(data.model); child.configuredEffort = compact(data.reasoningEffort);
        child.contextTier = compact(data.contextTier); versions.model = ++childRevision; break;
    case "session.usage_info":
        child.usage = validCount(data.currentTokens) && validCount(data.tokenLimit) && data.tokenLimit > 0
            ? { currentTokens: data.currentTokens, tokenLimit: data.tokenLimit, capturedAt: compact(event.timestamp) } : null;
        break;
    case "tool.execution_start": child.currentActivity = compact(data.toolName); break;
    case "tool.execution_complete": child.currentActivity = null; break;
    case "subagent.completed":
    case "subagent.failed":
        child.observedModel ||= compact(data.firstDispatchedModel);
        child.status = data.cancelled ? "cancelled" : event.type === "subagent.failed" ? "failed" : "completed";
        child.currentActivity = null; versions.status = ++childRevision; break;
    case "session.model_change":
        child.resolvedModel = compact(data.newModel); child.configuredEffort = compact(data.reasoningEffort);
        child.observedModel = child.observedEffort = child.usage = null; versions.model = ++childRevision; break;
    case "session.context_cleared": child.usage = null; break;
    default: return;
    }
    childVersions.set(child.id, versions);
    notifyCompanion();
}
function notifyCompanion() {
    companion.activity = waitingOverflow ? "waiting" : waiting.size ? [...waiting.values()][0] : activeTools.size ? "working" : activity;
    for (const entry of servers.values()) if (entry.domainKey === null)
        for (const response of entry.clients) {
            if (response.writableLength > 8192) response.destroy();
            else response.write("data: changed\n\n");
        }
}
function companionSnapshot() {
    return { ...companion, pendingRequestsStatus: waitingOverflow ? "overflow-unreconciled" : "observed",
        diagnostic: waitingOverflow ? "Pending request limit reached; waiting state is unreconciled until host shutdown." : companion.diagnostic,
        activeTools: [...activeTools.values()], subagents: [...subagents.values()] };
}
function resetActivity(state) {
    activeTools.clear(); waiting.clear(); activity = state;
}
export function observeSession(event) {
    if (["session.canvas.opened", "session.canvas.closed"].includes(event.type)) { displayRevision++; return; }
    if (event.type === "session.background_tasks_changed" && !event.agentId) { void refreshSubagents(); return; }
    if (event.agentId || event.type.startsWith("subagent.")) { observeSubagent(event); return; }
    if (event.agentId || event.data?.parentToolCallId) return;
    const data = event.data || {};
    switch (event.type) {
    case "session.model_change":
        selectionRevision++;
        companion.selectedModel = compact(data.newModel);
        companion.selectedEffort = compact(data.reasoningEffort);
        companion.contextTier = compact(data.contextTier);
        companion.observedModel = companion.observedEffort = companion.observedAt = companion.usage = null;
        break;
    case "session.model_deselected":
        selectionRevision++;
        companion.selectedModel = companion.selectedEffort = companion.contextTier =
            companion.observedModel = companion.observedEffort = companion.observedAt = companion.usage = null;
        break;
    case "assistant.usage":
        if (data.initiator || data.interactionType && data.interactionType !== "conversation-agent") return;
        companion.observedModel = compact(data.model);
        companion.observedEffort = compact(data.reasoningEffort);
        companion.observedAt = compact(event.timestamp);
        break;
    case "session.usage_info":
        if (!validCount(data.currentTokens) || !validCount(data.tokenLimit) || data.tokenLimit === 0 ||
            !validCount(data.messagesLength)) {
            companion.usage = null; companion.diagnostic = "Host sent invalid context counts.";
            break;
        }
        companion.usage = { currentTokens: data.currentTokens, tokenLimit: data.tokenLimit,
            capturedAt: compact(event.timestamp) };
        for (const key of ["systemTokens", "conversationTokens", "toolDefinitionsTokens"])
            if (validCount(data[key])) companion.usage[key] = data[key];
        break;
    case "session.context_cleared":
        companion.usage = companion.observedModel = companion.observedEffort = companion.observedAt = null;
        resetActivity("ready");
        break;
    case "assistant.turn_start": activity = "working"; break;
    case "tool.execution_start":
        if (compact(data.toolCallId) && activeTools.size < 32)
            activeTools.set(data.toolCallId, compact(data.toolName) || "Tool");
        else companion.diagnostic = "Activity detail limit reached; showing bounded tool lanes.";
        activity = "working";
        break;
    case "tool.execution_complete":
        activeTools.delete(data.toolCallId);
        if (data.success === false) activity = "error";
        break;
    case "permission.requested":
        if (data.resolvedByHook) return;
        if (compact(data.requestId) && (waiting.has(data.requestId) || waiting.size < 32))
            waiting.set(data.requestId, "blocked");
        else waitingOverflow = true;
        break;
    case "user_input.requested":
    case "elicitation.requested":
        if (compact(data.requestId) && (waiting.has(data.requestId) || waiting.size < 32))
            waiting.set(data.requestId, "waiting");
        else waitingOverflow = true;
        break;
    case "permission.completed":
    case "user_input.completed":
    case "elicitation.completed":
        waiting.delete(data.requestId);
        break;
    case "session.error": resetActivity("error"); break;
    case "session.idle":
        activeTools.clear();
        if (activity !== "error") activity = "idle";
        break;
    case "session.shutdown": waitingOverflow = false; resetActivity("stopped"); break;
    default: return;
    }
    notifyCompanion();
}

async function preferencePath(global = false) {
    const root = global ? (process.env.COPILOT_HOME || join(homedir(), ".copilot")) : session.workspacePath;
    if (!root) throw new CanvasError("companion_storage_unavailable", "Host did not supply session artifact storage");
    // Never create global storage on startup. Only an explicit preference change writes it.
    return global ? join(root, "extensions", "architrave-ribbon", "artifacts", "preferences.json")
        : join(root, "artifacts", "architrave-ribbon", "session.json");
}
async function readPreferences(global = false) {
    const path = await preferencePath(global);
    const root = global ? (process.env.COPILOT_HOME || join(homedir(), ".copilot")) : session.workspacePath;
    let parent = root;
    for (const part of ["", ...(global ? ["extensions", "architrave-ribbon", "artifacts"] : ["artifacts", "architrave-ribbon"])]) {
        if (part) parent = join(parent, part);
        let info;
        try { info = await lstat(parent); } catch (error) { if (error.code === "ENOENT") return {}; throw error; }
        if (!info.isDirectory() || info.isSymbolicLink())
            throw new CanvasError("companion_storage_unsafe", "Companion preference directory is not a real directory");
    }
    let info;
    try { info = await lstat(path); } catch (error) { if (error.code === "ENOENT") return {}; throw error; }
    if (!info.isFile() || info.isSymbolicLink() || info.size > 1024)
        throw new CanvasError("companion_storage_unsafe", "Companion preferences must be a bounded regular file");
    const value = JSON.parse(await readFile(path, "utf8"));
    const allowed = global ? ["enabled"] : ["opened", "dismissed", "autoOpenSuppressed"];
    if (!value || typeof value !== "object" || Array.isArray(value) ||
        Object.entries(value).some(([key, entry]) => !allowed.includes(key) || typeof entry !== "boolean"))
        throw new CanvasError("companion_preferences_invalid", "Invalid companion preferences; auto-open is suppressed");
    return value;
}
async function writePreferences(value, global = false) {
    const root = global ? (process.env.COPILOT_HOME || join(homedir(), ".copilot")) : session.workspacePath;
    const parts = global ? ["extensions", "architrave-ribbon", "artifacts"] : ["artifacts", "architrave-ribbon"];
    await directory(root);
    let parent = root;
    for (const part of parts) { parent = join(parent, part); await directory(parent); }
    const path = await preferencePath(global);
    await readPreferences(global);
    const temporary = path + "." + randomBytes(16).toString("hex") + ".tmp";
    try {
        await writeFile(temporary, JSON.stringify(value), { flag: "wx", mode: 0o600 });
        await rename(temporary, path);
    } finally {
        try { await unlink(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
    }
}
function diagnostic(code) {
    companion.diagnostic = code;
    process.stderr.write(`Architrave companion: ${code}\n`);
    notifyCompanion();
}
async function startCompanion() {
    if (typeof session.on !== "function") return;
    const openingRevision = displayRevision;
    session.on(observeSession);
    void refreshSubagents();
    const revision = selectionRevision;
    if (typeof session.rpc?.model?.getCurrent === "function") {
        try {
            const current = await session.rpc.model.getCurrent();
            if (revision === selectionRevision) {
                companion.selectedModel = compact(current.modelId);
                companion.selectedEffort = compact(current.reasoningEffort);
                companion.contextTier = compact(current.contextTier);
            }
        } catch (error) { diagnostic(`Model settings unavailable from this host connection (${compact(String(error.code)) || "unsupported"}).`); }
    }
    notifyCompanion();
    try {
        companion.autoOpen = (await readPreferences(true)).enabled !== false;
        sessionPreferences = { ...sessionPreferences, ...await readPreferences() };
        if (!companion.autoOpen || sessionPreferences.dismissed || sessionPreferences.opened
            || sessionPreferences.autoOpenSuppressed) return;
        if (typeof session.rpc?.canvas?.open !== "function" || typeof session.rpc.canvas.listOpen !== "function"
            || typeof session.rpc.extensions?.list !== "function") {
            diagnostic("Automatic canvas opening unavailable on this host."); return;
        }
        const own = (await session.rpc.extensions.list()).extensions.filter(entry => entry.pid === pid);
        if (own.length !== 1 || typeof own[0].id !== "string") {
            diagnostic("Automatic canvas opening unavailable: host did not identify this provider."); return;
        }
        if (!session.workspacePath) throw new CanvasError("companion_storage_unavailable", "Host workspace storage is unavailable");
        const sessionStorage = await realpath(session.workspacePath);
        await directory(join(sessionStorage, "artifacts"));
        await directory(join(sessionStorage, "artifacts", "architrave-ribbon"));
        await serial("companion-start", async () => displayLock(
            join(sessionStorage, "artifacts", "architrave-ribbon", "session-open"), async () => {
                sessionPreferences = { ...sessionPreferences, ...await readPreferences() };
                companion.autoOpen = (await readPreferences(true)).enabled !== false;
                if (!companion.autoOpen || sessionPreferences.dismissed || sessionPreferences.opened
                    || sessionPreferences.autoOpenSuppressed) return;
                const latest = await session.rpc.canvas.listOpen();
                if (latest.openCanvases.length || displayRevision !== openingRevision) {
                    sessionPreferences.autoOpenSuppressed = true;
                    await writePreferences(sessionPreferences);
                    return;
                }
                const confirmedEmpty = await session.rpc.canvas.listOpen();
                if (confirmedEmpty.openCanvases.length || displayRevision !== openingRevision) {
                    sessionPreferences.autoOpenSuppressed = true;
                    await writePreferences(sessionPreferences);
                    return;
                }
                const opened = await session.rpc.canvas.open({ extensionId: own[0].id,
                    canvasId: "architrave-session", instanceId: "architrave-session-companion", input: {} });
                if (opened.extensionId !== own[0].id || opened.canvasId !== "architrave-session"
                    || opened.instanceId !== "architrave-session-companion")
                    throw new CanvasError("companion_provider_mismatch", "Host did not confirm the requested companion provider");
                sessionPreferences = { ...sessionPreferences, ...await readPreferences(), opened: true };
                await writePreferences(sessionPreferences);
            }));
    } catch (error) { diagnostic(`Automatic canvas opening unavailable or suppressed (${compact(String(error.code)) || "invalid preferences"}); inspect host extension support and preferences.`); }
}

export function renderCompanion(nonce) {
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Architrave / Session instrument</title><style nonce="${nonce}">
:root{color-scheme:light dark;--surface-tone:white;--surface-lift:75%;--fallback-paper:#f6f7f9;--fallback-ink:#202124;--fallback-muted:#626973;--fallback-line:#d9dde3;--fallback-blue:#1264cd;--fallback-green:#237c51;--fallback-amber:#875b00;--fallback-red:#b52b3a}
@media(prefers-color-scheme:dark){:root{--surface-tone:#f1f2f5;--surface-lift:3%;--fallback-paper:#18191c;--fallback-ink:#f1f2f5;--fallback-muted:#a9afb9;--fallback-line:#3b3e46;--fallback-blue:#7db6ff;--fallback-green:#8bd5ab;--fallback-amber:#e8c077;--fallback-red:#ffa7a7}}
:root[data-color-mode=dark],body[data-color-mode=dark]{color-scheme:dark;--surface-tone:#f1f2f5;--surface-lift:3%;--fallback-paper:#18191c;--fallback-ink:#f1f2f5;--fallback-muted:#a9afb9;--fallback-line:#3b3e46;--fallback-blue:#7db6ff;--fallback-green:#8bd5ab;--fallback-amber:#e8c077;--fallback-red:#ffa7a7}
:root[data-color-mode=light],body[data-color-mode=light]{color-scheme:light;--surface-tone:white;--surface-lift:75%;--fallback-paper:#f6f7f9;--fallback-ink:#202124;--fallback-muted:#626973;--fallback-line:#d9dde3;--fallback-blue:#1264cd;--fallback-green:#237c51;--fallback-amber:#875b00;--fallback-red:#b52b3a}
*{box-sizing:border-box}[hidden]{display:none!important}
body{--paper:var(--background-color-default,var(--fallback-paper));--ink:var(--text-color-default,var(--fallback-ink));--muted:var(--text-color-muted,var(--fallback-muted));--line:var(--border-color-default,var(--fallback-line));--blue:var(--true-color-blue,var(--fallback-blue));--green:var(--fallback-green);--amber:var(--fallback-amber);--red:var(--true-color-red,var(--fallback-red));--surface:color-mix(in srgb,var(--paper),var(--surface-tone) var(--surface-lift));--soft:color-mix(in srgb,var(--paper),var(--ink) 8%);margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 var(--font-sans,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif)}
main{max-width:740px;margin:0 auto;padding:28px}.mast{display:flex;align-items:center;gap:12px;margin-bottom:28px}.mark{width:27px;height:27px;color:var(--blue);flex:none}h1{font-size:20px;letter-spacing:-.025em;margin:0;font-weight:650}h2{font-size:22px;letter-spacing:-.025em;font-weight:600;margin:0}h3{font-size:13px;font-weight:600;margin:0}p{color:var(--muted);overflow-wrap:anywhere}button,summary,input{font:inherit}button{color:inherit;cursor:pointer}button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--color-focus-outline,var(--blue));outline-offset:3px;border-radius:7px}.close{margin-left:auto;display:grid;place-items:center;width:44px;height:44px;flex:none;border:0;border-radius:11px;background:transparent;color:var(--muted)}.close:hover{background:var(--soft);color:var(--ink)}.close svg{width:18px;height:18px}.close:disabled{opacity:.6;cursor:default}
.telemetry{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,.8fr) minmax(0,1.15fr);gap:16px;margin:0 0 28px}.telemetry>div{min-width:0}.telemetry>div+div{border-inline-start:1px solid var(--line);padding-inline-start:16px}dt,.caption{display:block;color:var(--muted);font-size:12px}dd{margin:4px 0 0;font-weight:550;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.context-value{display:flex;flex-wrap:wrap;column-gap:5px}.context-value .capacity{color:var(--muted);font-weight:400}.context-value .unknown{color:var(--muted);font-weight:400}meter{display:block;width:100%;height:5px;margin-top:9px;background:var(--soft);border:0;border-radius:4px}meter::-webkit-meter-bar{height:5px;border:0;background:var(--soft)}meter::-webkit-meter-optimum-value,meter::-webkit-meter-suboptimum-value,meter::-webkit-meter-even-less-good-value{background:var(--blue)}meter::-moz-meter-bar{background:var(--blue)}
.workspace{background:var(--surface);border:1px solid var(--line);border-radius:17px;padding:23px 23px 0}.heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.state,.lane-status{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);flex-shrink:0}.dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}.state[data-state=working],.lane-status[data-state=running]{color:var(--blue)}.state[data-state=waiting],.state[data-state=blocked],.lane-status[data-state=idle]{color:var(--amber)}.state[data-state=error],.lane-status[data-state=failed]{color:var(--red)}.lane-status[data-state=completed]{color:var(--green)}
.goal{font-size:13px;margin:8px 0 24px}.track{height:7px;background:var(--soft);border-radius:4px;overflow:hidden}.track span{display:block;height:100%;width:0;background:var(--blue);border-radius:4px}.track[data-state=working] span{width:30%;animation:travel 2.2s ease-in-out infinite alternate}.track[data-state=waiting] span,.track[data-state=blocked] span,.track[data-state=error] span{width:100%;background:repeating-linear-gradient(90deg,var(--amber) 0 6px,transparent 6px 10px)}.track[data-state=error] span{background:repeating-linear-gradient(90deg,var(--red) 0 6px,transparent 6px 10px)}@keyframes travel{to{transform:translateX(233%)}}
.activity-note{display:flex;justify-content:space-between;gap:12px;margin:12px 0 0;color:var(--muted);font-size:11px}.activity-note strong{color:var(--ink);font-weight:500}.tools{list-style:none;display:flex;flex-wrap:wrap;column-gap:16px;row-gap:4px;padding:0;margin:10px 0 0;font-size:12px;color:var(--muted)}.tools:empty{display:none}.tools li{min-width:0;overflow-wrap:anywhere}.tools li:before{content:"";display:inline-block;width:4px;height:4px;border-radius:50%;background:var(--blue);margin-right:6px;vertical-align:middle}
.children-header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:20px;margin:23px 0 0}.count{font-size:11px;color:var(--muted)}.empty{padding:24px 0 20px;display:flex;align-items:center;gap:12px;color:var(--muted);font-size:13px;margin:0}.empty svg{width:25px;height:25px;flex:none;color:var(--muted)}.empty p{margin:0}.lane{border-bottom:1px solid var(--line)}.lane:last-child{border-bottom:0}summary{cursor:pointer}.lane summary{list-style:none;display:grid;grid-template-columns:20px minmax(0,1fr) auto 12px;align-items:center;gap:11px;padding:17px 0;min-height:68px}.lane summary::-webkit-details-marker{display:none}.lane summary:hover .name{color:var(--blue)}.lane-icon{width:20px;height:20px;color:var(--muted)}.chevron{width:12px;height:12px;color:var(--muted);transition:transform .16s ease-out}.lane[open] .chevron{transform:rotate(90deg)}.identity{min-width:0}.name{font-size:13px;font-weight:550;overflow-wrap:anywhere}.role{font-size:11px;color:var(--muted);margin-left:6px;overflow-wrap:anywhere}.slice{font-size:12px;color:var(--muted);margin-top:3px;overflow-wrap:anywhere}.lane-model{font-size:11px;color:var(--muted);margin-top:5px;overflow-wrap:anywhere}.lane-status{font-size:11px}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:22px;row-gap:14px;margin:0;padding:0 0 18px 31px}.facts dt{font-size:11px}.facts dd{font-size:12px;font-weight:500}.lane-context{margin:0 0 16px 31px;font-size:11px}.boundary{font-size:11px;margin:0;padding:17px 0 20px;border-top:1px solid var(--line)}#children-state{font-size:12px;margin:12px 0}#error,#diagnostic{font-size:12px;color:var(--red);margin:16px 0;overflow-wrap:anywhere}#error:empty,#diagnostic:empty{display:none}
.source{margin-top:16px;color:var(--muted);font-size:12px}.source>summary{min-height:44px;display:flex;align-items:center;gap:7px;list-style:none}.source>summary::-webkit-details-marker{display:none}.source[open]>summary .chevron{transform:rotate(90deg)}.source .facts{padding:12px 0 8px}.source label{display:flex;align-items:center;gap:10px;min-height:44px;color:var(--ink)}input{accent-color:var(--blue);width:16px;height:16px;flex:none}.source p{font-size:11px;margin:8px 0 16px}.source-content{border-top:1px solid var(--line);padding-top:10px}body[data-disconnected=true] .telemetry,body[data-disconnected=true] .children{opacity:.65}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important}.track[data-state=working] span{width:100%;background:repeating-linear-gradient(90deg,var(--blue) 0 8px,transparent 8px 13px)}}
@media(max-width:440px){main{padding:20px 16px}.mast{margin-bottom:22px}.telemetry{gap:10px;margin-bottom:24px}.telemetry>div+div{padding-inline-start:10px}.telemetry dt{font-size:11px}.telemetry dd{font-size:12px}.workspace{padding:19px 17px 0}h2{font-size:20px}.heading{align-items:flex-start;flex-wrap:wrap;gap:8px}.goal{margin-bottom:20px}.lane summary{grid-template-columns:18px minmax(0,1fr) 12px;gap:8px}.lane-icon{width:18px;height:18px}.lane-status{grid-column:2;grid-row:2;margin-top:-3px}.lane summary>.chevron{grid-column:3;grid-row:1}.role{display:block;margin:2px 0 0}.facts{padding-left:26px;column-gap:14px}.lane-context{margin-left:26px}.activity-note{flex-wrap:wrap;gap:4px}.source .facts{padding-left:0}}
</style></head><body><main>
<!-- THESIS: a quiet session instrument, never a synthetic completion dashboard.
OWN-WORLD: system type, neutral host surfaces, fine dividers, blue for observed activity.
STORY: read available context, locate current activity and inspect owned assignments.
FIRST VIEWPORT: compact telemetry rail, one indeterminate ribbon, expandable subagent lanes.
FORM: user-approved Apple-like Session instrument; all values come from supported host observations. -->
<header class="mast"><svg class="mark" viewBox="0 0 28 28" fill="none" aria-hidden="true"><path d="M5 23V9L14 4l9 5v14M5 13h18M10 23V13m8 10V13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg><h1>Architrave</h1><button id="close" class="close" aria-label="Close this session" title="Close this session"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button></header>
<dl class="telemetry" aria-label="Host session settings"><div><dt>Selected model</dt><dd id="selected">Unavailable</dd></div><div><dt>Effort setting</dt><dd id="effort">Unavailable</dd></div><div id="context"><dt>Context tokens</dt><dd id="usage" class="context-value">Unavailable</dd><meter id="meter" min="0" max="1" value="0" hidden aria-label="Context used"></meter></div></dl>
<section class="workspace" aria-label="Session activity"><div class="heading"><h2>Your session</h2><div class="state" id="state" data-state="unavailable"><span class="dot" aria-hidden="true"></span><span id="activity" role="status">Unavailable</span></div></div><p class="goal" id="goal">Waiting for host activity.</p>
<div class="track" id="track" data-state="unavailable" aria-hidden="true"><span></span></div>
<div class="activity-note"><strong id="activity-detail">No activity observed yet</strong><span>Activity, not completion</span></div><ul class="tools" id="lanes" aria-label="Observed active tools"></ul>
<section aria-label="Session subagents"><div class="children-header"><h3>Parallel work</h3><span class="count" id="child-count">Unavailable</span></div><p id="children-state" hidden></p><div id="children" class="children"></div>
<div id="children-empty" class="empty"><svg viewBox="0 0 28 28" fill="none" aria-hidden="true"><path d="M14 4v7M6 23v-7h16v7M14 16v7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="14" cy="6" r="3" fill="var(--surface)" stroke="currentColor" stroke-width="1.5"/></svg><p id="empty-text">Subagent metadata unavailable.</p></div>
<p class="boundary">App child sessions unavailable here. These lanes show session subagents only.</p></section>
</section><p id="error" role="alert"></p><p id="diagnostic" role="status"></p>
<details class="source" id="source-details"><summary><svg class="chevron" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m4 2 4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>Display preferences &amp; source</summary><div class="source-content">
<label><input id="enabled" type="checkbox" checked>Automatically show in new sessions</label><p>Saved for this user. Closing affects only this session, never its work or permissions.</p>
<dl class="facts"><div><dt>Last observed model</dt><dd id="observed">Not observed</dd></div><div><dt>Observed effort</dt><dd id="observed-effort">Not observed</dd></div></dl>
<p id="source">Host events only. No task denominator or completion percentage.</p></div></details>
<template id="child-template"><details class="lane"><summary><svg class="lane-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3" stroke="currentColor" stroke-width="1.5"/><path d="m8 9 3 3-3 3m5 0h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg><div class="identity"><span class="name"></span><span class="role"></span><div class="slice"></div><div class="lane-model"></div></div><span class="lane-status"><span class="dot" aria-hidden="true"></span><span class="status-label"></span></span><svg class="chevron" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m4 2 4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></summary><dl class="facts"></dl><p class="lane-context" hidden></p></details></template>
</main><script nonce="${nonce}">
const el=id=>document.getElementById(id);const labels={unavailable:'Activity unavailable',ready:'Ready',working:'Working',blocked:'Waiting for permission',waiting:'Waiting for input',error:'Error reported',idle:'Idle',stopped:'Stopped'};
const goals={unavailable:'Waiting for host activity.',ready:'Ready when you are.',working:'Activity from your host session.',blocked:'A permission decision is needed in the host.',waiting:'An answer is needed in the host.',error:'The host reported an error. Check the conversation.',idle:'No foreground activity reported.',stopped:'The host session has stopped.'};
const childLabels={running:'Running',idle:'Idle',completed:'Completed',failed:'Failed',cancelled:'Cancelled',unknown:'Unknown'};
let closed=false;
function item(tag,text){const n=document.createElement(tag);n.textContent=text;return n}
function facts(root,entries){root.replaceChildren();for(const [label,value] of entries){const pair=document.createElement('div');pair.append(item('dt',label),item('dd',value||'Unavailable'));root.append(pair)}}
function children(data){
 const root=el('children'),rows=new Map([...root.children].map(n=>[n.dataset.id,n])),current=new Set(data.subagents.map(child=>child.id));
 for(const [id,row] of rows)if(!current.has(id))row.remove();
 el('children-state').textContent=data.subagentsDiagnostic||'';el('children-state').hidden=!data.subagentsDiagnostic;
 el('child-count').textContent=data.subagentsStatus==='observed'?data.subagents.length+' subagent'+(data.subagents.length===1?'':'s'):'Unavailable';
 el('children-empty').hidden=data.subagents.length>0;
 el('empty-text').textContent=data.subagentsStatus==='observed'?'No subagents in this session.':'Subagent metadata unavailable.';
 for(const child of data.subagents){
  let row=rows.get(child.id);if(!row){row=el('child-template').content.firstElementChild.cloneNode(true);row.dataset.id=child.id;root.append(row)}
  row.querySelector('.name').textContent=child.name;row.querySelector('.role').textContent=child.role||'Role unavailable';
  row.querySelector('.slice').textContent='Assigned: '+(child.assignedSlice||'Unavailable');
  row.querySelector('.lane-model').textContent=child.observedModel?'Observed model: '+child.observedModel:child.resolvedModel?'Resolved model: '+child.resolvedModel:child.requestedModel?'Requested model: '+child.requestedModel:'Model not observed';
  row.querySelector('.lane-status').dataset.state=child.status;row.querySelector('.status-label').textContent=childLabels[child.status]||'Unknown';
  facts(row.querySelector('.facts'),[['Requested model',child.requestedModel],['Resolved model',child.resolvedModel],['Observed model',child.observedModel],['Effort setting',child.configuredEffort],['Observed effort',child.observedEffort],['Current activity',child.currentActivity],['Context tier',child.contextTier]]);
  const usage=row.querySelector('.lane-context');usage.hidden=!child.usage;usage.textContent=child.usage?child.usage.currentTokens.toLocaleString()+' / '+child.usage.tokenLimit.toLocaleString()+' context tokens. Observed '+(child.usage.capturedAt||'at an unavailable time')+'.':'';
 }
}
function draw(data){
 if(closed)return;
 document.body.dataset.disconnected='false';el('state').dataset.state=data.activity;el('track').dataset.state=data.activity;
 el('activity').textContent=labels[data.activity]||labels.unavailable;
 el('goal').textContent=goals[data.activity]||goals.unavailable;
 el('activity-detail').textContent=data.activeTools.length?data.activeTools.length+' active tool'+(data.activeTools.length===1?'':'s'):data.activity==='working'?'Host activity in progress':data.activity==='unavailable'?'No activity observed yet':'Host-reported state';
 for(const [id,key,empty] of [['selected','selectedModel','Unavailable'],['effort','selectedEffort','Unavailable'],['observed','observedModel','Not observed'],['observed-effort','observedEffort','Not observed']])el(id).textContent=data[key]||empty;
 el('lanes').replaceChildren();for(const name of data.activeTools){const li=document.createElement('li');li.textContent=name;el('lanes').append(li)}
 const u=data.usage;el('meter').hidden=!u;
 el('usage').replaceChildren();
 if(u){const used=item('span',u.currentTokens.toLocaleString()),capacity=item('span','/ '+u.tokenLimit.toLocaleString());capacity.className='capacity';el('usage').append(used,capacity);el('meter').max=u.tokenLimit;el('meter').value=Math.min(u.currentTokens,u.tokenLimit);el('meter').setAttribute('aria-valuetext',u.currentTokens.toLocaleString()+' of '+u.tokenLimit.toLocaleString()+' context tokens');el('usage').title=el('meter').getAttribute('aria-valuetext')}
 else{el('usage').textContent='Unavailable';el('usage').removeAttribute('title')}
 el('enabled').checked=data.autoOpen;el('diagnostic').textContent=data.diagnostic||'';
 children(data);
 el('source').textContent='Host events only. No task denominator or completion percentage.'+(u?.capturedAt?' Context observed '+u.capturedAt+'.':'')+(data.observedAt?' Last model call '+data.observedAt+'.':'')+(data.contextTier?' Context tier: '+data.contextTier+'.':'');
}
function disconnect(message){if(closed)return;document.body.dataset.disconnected='true';el('error').textContent=message;el('activity').textContent='Disconnected';el('state').dataset.state='unavailable';el('track').dataset.state='unavailable';el('goal').textContent='Displayed values are last observed, not current.'}
let refreshing=false,queued=false;
async function refresh(){if(closed)return;if(refreshing){queued=true;return}refreshing=true;try{const r=await fetch('snapshot',{cache:'no-store'});if(!r.ok)throw Error('Session display unavailable. Reopen from the canvas catalog.');draw(await r.json());if(!closed)el('error').textContent=''}catch(e){disconnect(e.message)}finally{refreshing=false;if(queued){queued=false;refresh()}}}
async function action(name,body){const r=await fetch(name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error('Display preference could not be saved. Check extension support and storage.')}
el('enabled').onchange=async()=>{el('enabled').disabled=true;try{await action('preferences',{enabled:el('enabled').checked});await refresh()}catch(e){el('error').textContent=e.message}finally{el('enabled').disabled=false}};
el('close').onclick=async()=>{el('close').disabled=true;try{await action('dismiss',{});closed=true;events.close();el('enabled').disabled=true;el('error').textContent='';el('activity').textContent='Closed';el('state').dataset.state='idle';el('track').dataset.state='idle';el('goal').textContent='Hidden for this session. Your work is unchanged.';el('activity-detail').textContent='Automatic reopening suppressed';el('lanes').replaceChildren()}catch(e){el('error').textContent=e.message;el('close').disabled=false}};
refresh();const events=new EventSource('events');events.onmessage=refresh;events.onerror=()=>disconnect('Display disconnected. Reopen from the canvas catalog.');window.addEventListener('pagehide',()=>events.close());
</script></body></html>`;
}

function fail(message) { throw new CanvasError("ribbon_input_invalid", message); }
function timestamp(value, label) {
    if (!/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value)))
        fail(`${label}: expected timestamp with timezone`);
}
function check(value, schema, path = "snapshot") {
    if (schema.anyOf) {
        if (!schema.anyOf.some(option => { try { check(value, option, path); return true; } catch (error) {
            if (error.code !== "ribbon_input_invalid") throw error;
            return false;
        } })) fail(`${path}: invalid value`);
        return;
    }
    if (schema.const !== undefined && value !== schema.const) fail(`${path}: unsupported schema`);
    if (schema.enum && !schema.enum.includes(value)) fail(`${path}: invalid choice`);
    if (schema.type === "null" && value !== null) fail(`${path}: expected null`);
    if (schema.type === "object") {
        if (!value || typeof value !== "object" || Array.isArray(value)) fail(`${path}: expected object`);
        if (Object.keys(value).some(key => !Object.hasOwn(schema.properties, key))) fail(`${path}: unexpected field`);
        for (const key of schema.required) if (!Object.hasOwn(value, key)) fail(`${path}.${key}: required`);
        for (const [key, entry] of Object.entries(value)) check(entry, schema.properties[key], `${path}.${key}`);
    }
    if (schema.type === "array") {
        if (!Array.isArray(value) || value.length > schema.maxItems) fail(`${path}: invalid array`);
        if (schema.uniqueItems && new Set(value).size !== value.length) fail(`${path}: duplicate item`);
        value.forEach((entry, index) => check(entry, schema.items, `${path}[${index}]`));
    }
    if (schema.type === "string" && (typeof value !== "string" ||
        [...value].length < (schema.minLength || 1) || [...value].length > (schema.maxLength || 128) ||
        schema.pattern && !new RegExp(schema.pattern).test(value))) fail(`${path}: invalid text`);
    if (["number", "integer"].includes(schema.type) && (typeof value !== "number" ||
        !Number.isFinite(value) || schema.type === "integer" && !Number.isSafeInteger(value) ||
        value < schema.minimum || value > schema.maximum)) fail(`${path}: invalid number`);
    if (schema.type === "boolean" && typeof value !== "boolean") fail(`${path}: expected boolean`);
}
export function validateSnapshot(value) {
    check(value, snapshotSchema);
    if (Buffer.byteLength(JSON.stringify(value)) > LIMIT) fail("snapshot: exceeds 64 KiB");
    for (const key of ["capturedAt", "startedAt", "deadline"]) {
        if (value[key] !== null) timestamp(value[key], key);
    }
    if (Date.parse(value.startedAt) > Date.parse(value.capturedAt) ||
        value.deadline && Date.parse(value.deadline) < Date.parse(value.startedAt)) fail("snapshot: invalid time order");
    const byId = new Map(value.steps.map(step => [step.id, step]));
    if (byId.size !== value.steps.length) fail("steps: duplicate ID");
    const visited = new Set();
    function visit(step, chain = new Set()) {
        if (chain.has(step.id)) fail("steps: dependency cycle; retries are not dependencies");
        if (visited.has(step.id)) return;
        const next = new Set([...chain, step.id]);
        for (const parent of step.dependencies) {
            if (!byId.has(parent)) fail("steps: missing dependency");
            visit(byId.get(parent), next);
        }
        visited.add(step.id);
        if (step.state === "blocked" && !step.blocker) fail("steps: blocked step requires blocker kind");
        if (["done", "verified"].includes(step.state) && !step.evidence.length) fail("steps: completed step requires evidence");
        if (step.retry?.stopped && step.state !== "stopped") fail("steps: stopped retry must retain stop state");
    }
    value.steps.forEach(step => visit(step));
    const streams = new Map((value.streams || []).map(stream => [stream.id, stream]));
    if (streams.size !== (value.streams || []).length) fail("streams: duplicate ID");
    for (const stream of streams.values()) timestamp(stream.sourceRef.capturedAt, "stream capture");
    for (const step of value.steps) {
        if (step.streamId && !streams.has(step.streamId)) fail("steps: missing workstream");
        if (step.state === "verified" && (!step.streamId || streams.get(step.streamId)?.kind !== "delivery"))
            fail("steps: product verification requires an existing delivery workstream");
        for (const key of ["startedAt", "finishedAt"]) if (step[key]) timestamp(step[key], "owner span");
        if (step.finishedAt && (!step.startedAt || Date.parse(step.finishedAt) < Date.parse(step.startedAt)))
            fail("steps: invalid owner span order");
    }
    const requiredBlocks = new Set();
    for (const step of value.steps) for (const dependency of step.dependencies) {
        const parent = byId.get(dependency);
        if (step.streamId && parent.streamId && step.streamId !== parent.streamId)
            requiredBlocks.add(JSON.stringify([dependency, step.id]));
    }
    const relationships = new Set();
    for (const relation of value.relations || []) {
        if (!byId.has(relation.fromStep) || !byId.has(relation.toStep) || relation.fromStep === relation.toStep)
            fail("relations: invalid step reference");
        const key = relation.fromStep + ":" + relation.toStep + ":" + relation.type;
        if (relationships.has(key)) fail("relations: duplicate relationship");
        relationships.add(key);
        if (relation.type === "blocks" &&
            (relation.provenance !== "canonical dependency" ||
             !byId.get(relation.toStep).dependencies.includes(relation.fromStep)))
            fail("relations: canonical BLOCKS must match a real prerequisite");
        if (relation.type === "blocks" && !requiredBlocks.delete(JSON.stringify([relation.fromStep, relation.toStep])))
            fail("relations: BLOCKS must be exactly the canonical cross-stream prerequisites");
        if (relation.type === "informs" && relation.provenance !== "display-only annotation")
            fail("relations: INFORMS is display-only, not scheduling authority");
    }
    if (requiredBlocks.size) fail("relations: missing canonical cross-stream BLOCKS");
    return value;
}

async function directory(path) {
    try { await mkdir(path, { mode: 0o700 }); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
    const info = await lstat(path);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new CanvasError("ribbon_storage_unsafe", "Ribbon artifact directory is not a real directory");
}
async function statePath(domainKey) {
    if (!storageRoot) throw new CanvasError("ribbon_storage_unavailable", "Host workspace artifact storage is unavailable");
    check(domainKey, domain, "domainKey");
    await directory(join(storageRoot, "artifacts"));
    await directory(join(storageRoot, "artifacts", "architrave-ribbon"));
    return join(storageRoot, "artifacts", "architrave-ribbon", createHash("sha256").update(domainKey).digest("hex") + ".json");
}
async function readSnapshot(domainKey) {
    const path = await statePath(domainKey);
    let info;
    try { info = await lstat(path); }
    catch (error) { if (error.code === "ENOENT") return null; throw error; }
    if (!info.isFile() || info.isSymbolicLink() || info.size > LIMIT)
        throw new CanvasError("ribbon_storage_unsafe", "Ribbon snapshot is not a bounded regular file");
    let value;
    try { value = JSON.parse(await readFile(path, "utf8")); }
    catch (error) {
        if (!(error instanceof SyntaxError)) throw error;
        throw new CanvasError("ribbon_storage_invalid", "Stored ribbon artifact is invalid JSON; inspect the display artifact, not canonical Run files");
    }
    validateSnapshot(value);
    if (value.domainKey !== domainKey) fail("Stored snapshot domain mismatch");
    return value;
}
async function serial(domainKey, action) {
    const previous = queues.get(domainKey) || Promise.resolve();
    const work = previous.catch(() => {}).then(action);
    queues.set(domainKey, work);
    try { return await work; } finally { if (queues.get(domainKey) === work) queues.delete(domainKey); }
}
function snapshotDigest(value) {
    return value === null ? null : createHash("sha256").update(JSON.stringify(value)).digest("hex");
}
async function lockOwner(path) {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink() || info.size > 1024)
        throw new CanvasError("ribbon_storage_unsafe", "Display lock is not a bounded regular file");
    let owner;
    try { owner = JSON.parse(await readFile(path, "utf8")); }
    catch (error) {
        if (error instanceof SyntaxError) {
            if (!info.size && Date.now() - info.mtimeMs < 200) return null;
            throw new CanvasError("ribbon_lock_recovery_required", "Display lock owner is unreadable; inspect the orphan display lock before removing it");
        }
        throw error;
    }
    if (!owner || typeof owner !== "object" || !Number.isInteger(owner.pid) || owner.pid < 1 ||
        owner.pid > 2147483647 || !/^[a-f0-9]{32}$/.test(owner.nonce))
        throw new CanvasError("ribbon_storage_unsafe", "Display lock ownership is invalid");
    return owner;
}
function ownerAlive(owner) {
    try { kill(owner.pid, 0); return true; }
    catch (error) { if (error.code === "ESRCH") return false; if (error.code === "EPERM") return true; throw error; }
}
async function displayLock(path, action) {
    const lock = path + ".lock";
    const recovery = path + ".recovery";
    const owner = { pid, nonce: randomBytes(16).toString("hex") };
    let acquired = false;
    for (let attempt = 0; attempt < 40 && !acquired; attempt++) {
        try {
            const file = await open(lock, "wx", 0o600);
            try { await file.writeFile(JSON.stringify(owner)); acquired = true; }
            catch (error) { await unlink(lock); throw error; }
            finally { await file.close(); }
        } catch (error) {
            if (error.code !== "EEXIST") throw error;
            try {
                const prior = await lockOwner(lock);
                if (prior && !ownerAlive(prior)) {
                    let guard;
                    try { guard = await open(recovery, "wx", 0o600); }
                    catch (error) {
                        if (error.code !== "EEXIST") throw error;
                        throw new CanvasError("ribbon_lock_recovery_required", "Display lock recovery is already owned; inspect an orphan recovery guard before removing it");
                    }
                    try {
                        await guard.writeFile(JSON.stringify(owner));
                        const current = await lockOwner(lock);
                        if (current && !ownerAlive(current)) await unlink(lock);
                    } finally { await guard.close(); await unlink(recovery); }
                }
            } catch (error) { if (error.code !== "ENOENT") throw error; }
            if (!acquired) await delay(25);
        }
    }
    if (!acquired) throw new CanvasError("ribbon_snapshot_busy", "Another provider owns this domain; retry after its snapshot write finishes");
    try { return await action(); }
    finally {
        const current = await lockOwner(lock);
        if (current?.nonce !== owner.nonce) throw new CanvasError("ribbon_storage_unsafe", "Display lock ownership changed");
        await unlink(lock);
    }
}
async function saveSnapshot(value, expectedDigest) {
    validateSnapshot(value);
    return serial(value.domainKey, async () => displayLock(await statePath(value.domainKey), async () => {
        const prior = await readSnapshot(value.domainKey);
        if (snapshotDigest(prior) !== expectedDigest)
            throw new CanvasError("ribbon_snapshot_conflict", "Saved display snapshot changed; read it again before replacing it");
        if (prior && (value.runId !== prior.runId || value.revision < prior.revision ||
            value.objectiveVersion < prior.objectiveVersion || Date.parse(value.capturedAt) < Date.parse(prior.capturedAt)))
            throw new CanvasError("ribbon_stale_snapshot", "Snapshot cannot rewind domain history");
        for (const stream of value.streams || []) {
            const previous = (prior?.streams || []).find(item => item.id === stream.id)?.sourceRef;
            const current = stream.sourceRef;
            if (previous && (previous.domainKey !== current.domainKey || previous.runId !== current.runId ||
                current.revision < previous.revision || current.objectiveVersion < previous.objectiveVersion ||
                Date.parse(current.capturedAt) < Date.parse(previous.capturedAt)))
                throw new CanvasError("ribbon_stale_snapshot", "A workstream cannot rewind or silently change source identity");
        }
        const path = await statePath(value.domainKey);
        const temporary = path + "." + randomBytes(16).toString("hex") + ".tmp";
        try {
            await writeFile(temporary, JSON.stringify(value), { flag: "wx", mode: 0o600 });
            await rename(temporary, path);
        } finally {
            try { await unlink(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
        }
        for (const entry of servers.values()) if (entry.domainKey === value.domainKey)
            for (const response of entry.clients) response.write("data: changed\n\n");
        return { domainKey: value.domainKey, revision: value.revision, digest: snapshotDigest(value),
            mode: "agent-fed snapshot; not live" };
    }));
}

export function renderHtml(nonce) {
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Architrave / Route Ribbon</title><style nonce="${nonce}">
:root{color-scheme:light dark;--bg:var(--background-color-default,#171a1e);--ink:var(--text-color-default,#f0f2f4);--muted:var(--text-color-muted,#b8c0ca);--line:var(--border-color-default,#48515c);--done:#88d3a0;--verified:#a6ddff;--active:#f1cb7c;--blocked:#f2a392;--deferred:#b9c5d5;--bypassed:#b9c5d5;--stopped:#efaeb9;--planned:#b0bac7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--font-sans,system-ui,sans-serif)}main{max-width:1180px;margin:auto;padding:24px}h1{font-size:21px;margin:0 0 24px}h2{font-size:clamp(24px,4vw,36px);line-height:1.2;margin:22px 0 12px}h3{font-size:16px;margin:20px 0 8px}p{max-width:75ch;color:var(--muted);margin:8px 0;overflow-wrap:anywhere}button{font:inherit;cursor:pointer;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:8px 10px}button:focus-visible{outline:3px solid var(--color-focus-outline,#8db9ff);outline-offset:3px}button:hover{border-color:var(--ink)}button[aria-pressed=true]{outline:2px solid var(--ink);outline-offset:2px}.context{border-block:1px solid var(--line);padding:12px 0;margin:18px 0}.small{font-size:12px}.strip{display:flex;gap:6px;overflow-x:auto;padding:5px 3px 10px;margin:20px 0}.segment{flex:var(--weight);min-width:38px;min-height:54px;background:var(--c);color:#171a1e;border:0;font-weight:700}.segment.bypassed,.segment.deferred{background:repeating-linear-gradient(135deg,#26303b 0px,#26303b 5px,var(--c) 5px,var(--c) 7px);color:#fff}.segment.planned,.segment.stopped{background:transparent;border:2px dashed var(--c);color:var(--c)}.work{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:26px}.rows{min-width:0}.row{display:grid;grid-template-columns:1fr auto;gap:10px;border-bottom:1px solid var(--line);padding:14px 0}.row button{text-align:left;border:0;padding:0;overflow-wrap:anywhere}.state{color:var(--c);font-size:12px}.row p{grid-column:1/-1;font-size:13px}.inspect{border:1px solid var(--line);padding:16px;align-self:start;position:sticky;top:12px;min-width:0;overflow-wrap:anywhere}.inspect h3:first-child{margin-top:0}.inspect p{font-size:13px}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px}.legend span{color:var(--c)}#error{color:var(--blocked)}footer{margin-top:24px;border-top:1px solid var(--line);padding-top:12px}
@media(max-width:720px){main{padding:18px}.work{grid-template-columns:1fr}.inspect{position:static;order:-1}.row{grid-template-columns:1fr}.strip{gap:5px}body{font-size:16px}}
.stream{border-top:1px solid var(--line);padding:14px 0}.stream h3{margin:0 0 6px}.stream .strip{margin:8px 0}.stream p{font-size:13px}.relations{padding:8px 0 16px}
[data-color-mode=light]{--done:#256b3d;--verified:#245f87;--active:#735000;--blocked:#983a23;--deferred:#485a70;--bypassed:#485a70;--stopped:#993343;--planned:#485a70}[data-color-mode=light] .segment:not(.planned):not(.stopped){color:#fff}
</style></head><body><main><h1>Architrave / Route Ribbon</h1><p id="error" role="alert"></p><div id="summary"></div><div class="legend" id="legend" aria-label="Step states"></div><nav class="strip" id="ribbon" aria-label="Route steps"></nav><p class="small">Overview order is display only, not a serial schedule. Widths are estimated relative weights, not time, tokens or overall completion. Bypassed and deferred steps are not done.</p><section id="lanes" aria-label="Workstreams" hidden></section><div class="work"><section class="rows" id="rows" aria-label="Step details"></section><aside class="inspect" id="inspector" aria-live="polite">Select a step to inspect its reason and evidence.</aside></div><footer><p class="small">Read-only, agent-fed snapshot. Refresh reads the latest saved projection; no Run, policy, hold or acceptance mutations.</p><button id="refresh">Refresh snapshot</button></footer></main><script nonce="${nonce}">
const labels=${JSON.stringify(states)};const el=id=>document.getElementById(id);let snapshot=null,selected=null;
function make(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function tint(n,state){n.style.setProperty('--c','var(--'+state+')');return n}
function label(step){return labels[step.state]+(step.current?'':' / historical')+(step.blocker?' / '+step.blocker:'')}
function relationshipText(relation,data){
 const from=data.steps.find(s=>s.id===relation.fromStep),to=data.steps.find(s=>s.id===relation.toStep);
 return (from.current&&to.current?'':'Historical / not current: ')+from.title+' '+relation.type.toUpperCase()+' '+to.title+' / '+relation.provenance+': '+relation.reason;
}
function inspect(step){
 selected=step.id;const root=el('inspector');
 root.replaceChildren(make('h3',step.title),tint(make('p',label(step)),step.state),make('p',step.reason),make('h3','Evidence / provenance'));
 const stream=(snapshot.streams||[]).find(s=>s.id===step.streamId);
 if(stream){const ref=stream.sourceRef;root.append(make('h3',stream.label),make('p',stream.kind+' / '+stream.outcome),make('p','Run '+ref.runId+' / revision '+ref.revision+' / '+ref.freshness+' at '+ref.capturedAt),make('p','Source '+ref.commit+' / SHA-256 '+ref.sha256))}
 root.append(make('p','Owner: '+(step.owner||'Unassigned')+' / joined owner: '+(step.hostOwner||'Unknown')+' / host task: '+(step.hostTaskId||'Unknown')),
  make('p','Canonical owner span: '+(step.startedAt||'Unknown')+' → '+(step.finishedAt||'Unknown')+'. Includes waits; not active effort or a measured concurrency claim.'));
 for(const ref of step.evidence)root.append(make('p',ref));
 if(!step.evidence.length)root.append(make('p','No qualifying evidence recorded.'));
 root.append(make('h3','Dependencies'));
 for(const id of step.dependencies){const parent=snapshot.steps.find(s=>s.id===id);const b=make('button',parent.title);b.onclick=()=>inspect(parent);root.append(b)}
 if(!step.dependencies.length)root.append(make('p','No prerequisite recorded.'));
 for(const relation of snapshot.relations||[])if(relation.fromStep===step.id||relation.toStep===step.id){
  root.append(make('p',relationshipText(relation,snapshot)));
 }
 root.append(make('p','Attempts: '+step.attempts+'. Estimated weight: '+step.weightEstimate+'.'));
 if(step.retry)root.append(make('h3',step.retry.stopped?'Explicit repeated-failure stop':'Retry evidence'),make('p',step.retry.reason),make('p','Failure fingerprint: '+step.retry.fingerprint),make('p','Evidence fingerprint: '+step.retry.evidenceFingerprint+' / repetitions: '+step.retry.repeated));
 for(const b of document.querySelectorAll('.segment[data-id]'))b.setAttribute('aria-pressed',String(b.dataset.id===step.id));
}
function streamLanes(data){
 const root=el('lanes');root.replaceChildren();root.hidden=(data.streams||[]).length<2;
 if(root.hidden)return;
 root.append(make('h3','Workstreams'),make('p','Independent scoped lanes, not a measured concurrency timeline. Two active labels do not prove overlapping execution. Timing/effort stays Unknown without recorded spans.','small'));
 for(const stream of data.streams){
  const group=data.steps.filter(step=>step.streamId===stream.id),lane=make('section',undefined,'stream');
  lane.dataset.stream=stream.id;
  const statuses=[...new Set(group.filter(step=>step.current).map(step=>label(step)))];
  lane.append(make('h3',stream.label),make('p',stream.kind+' / '+(statuses.join(' · ')||'Historical / no current slice')),make('p',stream.outcome));
  const strip=make('nav',undefined,'strip');strip.setAttribute('aria-label',stream.label+' slices');
  for(const step of group){const b=tint(make('button',String(data.steps.indexOf(step)+1),'segment '+step.state),step.state);b.style.setProperty('--weight',step.weightEstimate);b.dataset.id=step.id;b.setAttribute('aria-label',step.title+' / '+label(step));b.onclick=()=>inspect(step);strip.append(b)}
  lane.append(strip);root.append(lane);
 }
 const relations=make('div',undefined,'relations');
 for(const relation of data.relations||[])relations.append(make('p',relationshipText(relation,data)));
 root.append(relations);
}
function draw(data){
 snapshot=data;el('error').textContent='';for(const id of ['summary','ribbon','rows','legend'])el(id).replaceChildren();
 if(!data){el('lanes').hidden=true;el('lanes').replaceChildren();el('summary').append(make('h2','No snapshot yet'),make('p','Supply a validated Run projection with update_snapshot. Opening a panel does not invent progress.'));el('inspector').textContent='No steps to inspect.';return}
 const d=data;el('summary').append(make('h2',d.title),make('p',d.objective));const context=make('div',undefined,'context');
 const age=Math.max(0,Math.floor((Date.now()-Date.parse(d.capturedAt))/60000));
 context.append(make('p','Snapshot '+d.capturedAt+' / '+age+' min old / '+d.source.freshness+' at capture'),make('p','Source '+d.source.commit+' / SHA-256 '+d.source.sha256+' / revision '+d.revision+' / objective '+d.objectiveVersion,'small'),make('p',d.source.provenance,'small'));
 if(d.next)context.append(make('p','Next: '+d.next));
 context.append(make('p','Current milestone: '+(d.milestone||'No current source-bound product observation.')));
 const elapsed=((Date.parse(d.capturedAt)-Date.parse(d.startedAt))/3600000).toFixed(1);
 context.append(make('p','Wall elapsed at snapshot: '+elapsed+' h (includes waits). Earliest current lane deadline: '+(d.deadline||'Unknown')+'. Active effort / wait duration / tokens / cost: Unknown.'));
 el('summary').append(context);
 for(const [state,title] of Object.entries(labels))el('legend').append(tint(make('span',title),state));
 d.steps.forEach((step,index)=>{
  const b=tint(make('button',String(index+1),'segment '+step.state),step.state);b.style.setProperty('--weight',step.weightEstimate);b.dataset.id=step.id;b.setAttribute('aria-label',step.title+' / '+label(step));b.onclick=()=>inspect(step);el('ribbon').append(b);
  const row=make('div',undefined,'row');const title=make('button',step.title);title.onclick=()=>inspect(step);
  row.append(title,tint(make('span',label(step)+(step.retry?' / retry':''),'state'),step.state),make('p',step.reason));el('rows').append(row);
 });
 streamLanes(d);
 const current=d.steps.find(s=>s.id===selected)||d.steps.find(s=>s.current&&(s.state==='active'||s.state==='blocked'))||d.steps[0];
 if(current)inspect(current);else el('inspector').textContent='No steps recorded.';
}
async function refresh(){try{const response=await fetch('snapshot',{cache:'no-store'});if(!response.ok)throw new Error('Snapshot read failed ('+response.status+'). Reopen the canvas or check extension logs.');draw(await response.json())}catch(error){el('error').textContent=error.message}}
el('refresh').onclick=refresh;refresh();const events=new EventSource('events');events.onmessage=refresh;events.onerror=()=>{el('error').textContent='Snapshot notification connection unavailable. Displayed data may be stale; refresh or reopen the canvas.'};window.addEventListener('pagehide',()=>events.close());
</script></body></html>`;
}

async function startServer(domainKey, instanceId) {
    const token = randomBytes(24).toString("hex");
    const nonce = randomBytes(18).toString("base64");
    const clients = new Set();
    const server = createServer(async (req, res) => {
        res.setHeader("Cache-Control", "no-store");
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.setHeader("Referrer-Policy", "no-referrer");
        const host = `127.0.0.1:${server.address().port}`;
        if (req.headers.host !== host || req.headers.origin && req.headers.origin !== `http://${host}` ||
            !["GET", "POST"].includes(req.method) || !req.url?.startsWith(`/${token}/`) ||
            req.method === "POST" && (domainKey !== null || req.headers.origin !== `http://${host}` ||
                req.headers["content-type"] !== "application/json")) {
            res.writeHead(403); res.end("Forbidden"); return;
        }
        try {
            const route = req.url.slice(token.length + 2);
            if (req.method === "POST") {
                if (!["preferences", "dismiss"].includes(route)) { res.writeHead(404); res.end("Not found"); return; }
                let body = "";
                for await (const chunk of req) {
                    body += chunk.toString("utf8");
                    if (Buffer.byteLength(body) > 256) { res.writeHead(413); res.end("Request too large"); return; }
                }
                let value;
                try { value = JSON.parse(body); }
                catch { res.writeHead(400); res.end("Invalid JSON"); return; }
                if (route === "preferences") {
                    check(value, object({ enabled: { type: "boolean" } }), "preferences");
                    displayRevision++;
                    await serial("companion-preferences", () => writePreferences(value, true));
                    companion.autoOpen = value.enabled;
                    notifyCompanion();
                } else {
                    check(value, object({}), "dismiss");
                    displayRevision++;
                    sessionPreferences = { ...(sessionPreferences || {}), dismissed: true };
                    await serial("companion-session", () => writePreferences(sessionPreferences));
                    res.end("{}");
                    try {
                        if (typeof session.rpc?.canvas?.close !== "function")
                            throw new CanvasError("companion_close_unavailable", "Use the host panel close control");
                        await session.rpc.canvas.close({ instanceId });
                    } catch (error) { diagnostic(`Session auto-open suppressed; host close unavailable (${compact(String(error.code)) || "unsupported"}).`); }
                    return;
                }
                res.setHeader("Content-Type", "application/json"); res.end("{}");
            } else if (route === "") {
                res.setHeader("Content-Type", "text/html; charset=utf-8");
                res.setHeader("Content-Security-Policy", `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'`);
                res.end(domainKey === null ? renderCompanion(nonce) : renderHtml(nonce));
            } else if (route === "snapshot") {
                res.setHeader("Content-Type", "application/json");
                res.end(JSON.stringify(domainKey === null ? companionSnapshot() : await readSnapshot(domainKey)));
            } else if (route === "events") {
                if (clients.size >= 16) { res.writeHead(429); res.end("Too many observers"); return; }
                res.writeHead(200, { "Content-Type": "text/event-stream", Connection: "keep-alive" });
                res.write(": snapshot notifications\n\n"); clients.add(res);
                res.on("close", () => clients.delete(res));
            } else { res.writeHead(404); res.end("Not found"); }
        } catch (error) {
            process.stderr.write(`Ribbon display request failed: ${error.code || "invalid artifact"}\n`);
            res.writeHead(error.code === "ribbon_input_invalid" ? 400 : 500); res.end("Display request failed; check extension logs");
        }
    });
    server.requestTimeout = 5000;
    server.headersTimeout = 5000;
    await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
    return { server, clients, domainKey, url: `http://127.0.0.1:${server.address().port}/${token}/` };
}
async function close(instanceId) {
    const entry = servers.get(instanceId);
    if (!entry) return;
    servers.delete(instanceId);
    for (const response of entry.clients) response.end();
    const closed = new Promise((resolve, reject) => entry.server.close(error => error ? reject(error) : resolve()));
    entry.server.closeAllConnections();
    await closed;
}
async function openPanel(ctx) {
        displayRevision++;
        const input = ctx.input ?? {};
        const domainKey = input.domainKey || null;
        if (input.snapshot && !domainKey) fail("Snapshot requires domainKey");
        if (domainKey && !storageRoot) {
            if (!session.workspacePath) throw new CanvasError("ribbon_storage_unavailable", "Host did not supply workspace artifact storage");
            storageRoot = await realpath(session.workspacePath);
        }
        if (input.snapshot) {
            if (input.snapshot.domainKey !== domainKey) fail("Open snapshot domain mismatch");
            const prior = await readSnapshot(domainKey);
            if (!prior) await saveSnapshot(input.snapshot, null);
        }
        const existing = servers.get(ctx.instanceId);
        if (existing && existing.domainKey !== domainKey) fail("Panel domain cannot change; open a fresh instance");
        if (!existing) {
            if (servers.size >= 8) throw new CanvasError("ribbon_limit", "Close an existing ribbon before opening another");
            servers.set(ctx.instanceId, await startServer(domainKey, ctx.instanceId));
        }
        return { url: servers.get(ctx.instanceId).url, title: domainKey ? "Architrave / Route Ribbon" : "Session companion",
            status: domainKey ? "Read-only snapshot" : "Passive host events" };
}
async function closePanel(ctx) {
    displayRevision++;
    if (servers.get(ctx.instanceId)?.domainKey === null) {
        try {
            sessionPreferences = { ...(sessionPreferences || {}), dismissed: true };
            await serial("companion-session", () => writePreferences(sessionPreferences));
        } finally { await close(ctx.instanceId); }
    } else await close(ctx.instanceId);
}
const session = await joinSession({ canvases: [createCanvas({
    id: "architrave-ribbon", displayName: "Route Ribbon",
    description: "Read-only Run route, blockers and evidence from explicit canonical snapshots.",
    inputSchema: openSchema,
    open: async ctx => {
        check(ctx.input, openSchema, "input");
        return openPanel(ctx);
    },
    actions: [
        { name: "get_snapshot", description: "Read saved snapshot and its display digest; no canonical mutations.",
            inputSchema: object({}), handler: async ctx => {
                const entry = servers.get(ctx.instanceId);
                if (!entry) throw new CanvasError("ribbon_not_open", "Reopen this ribbon after provider reload");
                if (entry.domainKey === null) throw new CanvasError("ribbon_domain_required", "Open a Run domain to read its projection; session telemetry stays outside model context");
                const snapshot = await readSnapshot(entry.domainKey);
                return { snapshot, digest: snapshotDigest(snapshot) };
            } },
        { name: "update_snapshot", description: "Compare-and-swap the display projection using the digest from get_snapshot.",
            inputSchema: updateSchema, handler: async ctx => {
                check(ctx.input, updateSchema, "input");
                const entry = servers.get(ctx.instanceId);
                if (!entry) throw new CanvasError("ribbon_not_open", "Reopen this ribbon after provider reload");
                if (entry.domainKey !== ctx.input.snapshot.domainKey) fail("Snapshot must match the open domain");
                return saveSnapshot(ctx.input.snapshot, ctx.input.expectedDigest);
            } },
    ],
    onClose: closePanel,
}), createCanvas({
    id: "architrave-session", displayName: "Session companion",
    description: "Passive session activity, model, effort and host-reported context usage.",
    inputSchema: object({}),
    open: async ctx => {
        check(ctx.input ?? {}, object({}), "input");
        return openPanel(ctx);
    },
    onClose: closePanel,
})] });
await startCompanion();
for (const signal of ["SIGTERM", "SIGINT"]) process.once(signal, () => {
    Promise.all([...servers.keys()].map(close)).then(() => process.exit(0), error => {
        process.stderr.write(`Ribbon cleanup failed: ${error.message}\n`); process.exit(1);
    });
});
