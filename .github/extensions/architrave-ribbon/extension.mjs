// Optional read-only projection. Python Run APIs remain the only authority.
import { createServer } from "node:http";
import { randomBytes, createHash } from "node:crypto";
import { mkdir, lstat, readFile, writeFile, rename, unlink, realpath } from "node:fs/promises";
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
    companion.activity = waiting.size ? [...waiting.values()][0] : activeTools.size ? "working" : activity;
    for (const entry of servers.values()) if (entry.domainKey === null)
        for (const response of entry.clients) {
            if (response.writableLength > 8192) response.destroy();
            else response.write("data: changed\n\n");
        }
}
function companionSnapshot() {
    return { ...companion, activeTools: [...activeTools.values()], subagents: [...subagents.values()] };
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
        companion.selectedModel = companion.observedModel = companion.observedEffort = companion.observedAt = companion.usage = null;
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
        if (compact(data.requestId) && waiting.size < 32) waiting.set(data.requestId, "blocked");
        break;
    case "user_input.requested":
    case "elicitation.requested":
        if (compact(data.requestId) && waiting.size < 32) waiting.set(data.requestId, "waiting");
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
    case "session.shutdown": resetActivity("stopped"); break;
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
    const allowed = global ? ["enabled"] : ["opened", "dismissed"];
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
        sessionPreferences = { ...await readPreferences(), ...sessionPreferences };
        if (!companion.autoOpen || sessionPreferences.dismissed || sessionPreferences.opened) return;
        if (typeof session.rpc?.canvas?.open !== "function" || typeof session.rpc.canvas.listOpen !== "function") {
            diagnostic("Automatic canvas opening unavailable on this host."); return;
        }
        const { openCanvases } = await session.rpc.canvas.listOpen();
        // Do not take focus from an existing panel, including on resume/reload.
        await serial("companion-session", async () => {
            sessionPreferences = { ...await readPreferences(), ...sessionPreferences, opened: true };
            await writePreferences(sessionPreferences);
        });
        if (openCanvases.length) return;
        companion.autoOpen = (await readPreferences(true)).enabled !== false;
        const latest = await session.rpc.canvas.listOpen();
        if (latest.openCanvases.length || displayRevision !== openingRevision || !companion.autoOpen ||
            sessionPreferences.dismissed) return;
        await session.rpc.canvas.open({ canvasId: "architrave-session",
            instanceId: "architrave-session-companion", input: {} });
    } catch (error) { diagnostic(`Automatic canvas opening unavailable or suppressed (${compact(String(error.code)) || "invalid preferences"}); inspect host extension support and preferences.`); }
}

export function renderCompanion(nonce) {
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Session companion</title><style nonce="${nonce}">
:root{color-scheme:light dark;--bg:var(--background-color-default,#171a1e);--ink:var(--text-color-default,#f0f2f4);--muted:var(--text-color-muted,#b8c0ca);--line:var(--border-color-default,#48515c);--accent:var(--true-color-blue,#92c7ff)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 var(--font-sans,system-ui,sans-serif)}main{max-width:800px;padding:24px;margin:auto}header{display:flex;align-items:center;justify-content:space-between;gap:16px}h1{font-size:18px;margin:0}h2{font-size:24px;font-weight:600;margin:28px 0 12px}p{color:var(--muted);overflow-wrap:anywhere}button{font:inherit;color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:5px;padding:8px 12px;min-height:40px;cursor:pointer}button:hover{border-color:var(--ink)}button:disabled{opacity:.6;cursor:wait}button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--color-focus-outline,#8db9ff);outline-offset:3px}
.track{height:8px;overflow:hidden;background:var(--line);border-radius:2px}.track span{display:block;height:100%;background:var(--accent);width:0}.track.active span{width:30%;animation:travel 2s ease-in-out infinite alternate}.track.paused span{width:100%;background:var(--muted)}@keyframes travel{to{transform:translateX(233%)}}@media(prefers-reduced-motion:reduce){.track.active span{animation:none;width:100%;background:repeating-linear-gradient(90deg,var(--accent) 0 12px,transparent 12px 18px)}}
dl{display:grid;grid-template-columns:minmax(100px,1fr) minmax(0,2fr);gap:8px 20px;margin:24px 0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}#context{margin-top:24px}meter{width:100%;height:10px;accent-color:var(--accent)}.small{font-size:12px}#lanes{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:8px}#lanes li{padding:4px 8px;border:1px solid var(--line);overflow-wrap:anywhere}details{border-top:1px solid var(--line);padding-top:16px;margin-top:24px}summary{cursor:pointer}label{display:flex;align-items:center;gap:10px;min-height:44px}#error{color:var(--true-color-red,#ffa7a7)}@media(max-width:420px){main{padding:16px}dl{grid-template-columns:1fr;gap:4px}dd{margin-bottom:10px}header{align-items:flex-start}}
</style></head><body><main>
<!-- THESIS: quiet session activity, never invented completion. OWN-WORLD: host tokens and ribbon line.
STORY: see state and settings, dismiss without changing work. FIRST VIEWPORT: state, activity, compact facts.
FORM: narrow extension of the existing read-only ribbon; no new visual system. -->
<header><h1>Session companion</h1><button id="close">Close this session</button></header>
<h2 id="activity" role="status">Activity unavailable</h2><div class="track" id="track" aria-hidden="true"><span></span></div>
<ul id="lanes" aria-label="Observed active tools"></ul>
<dl><dt>Selected model</dt><dd id="selected">Unavailable</dd><dt>Effort setting</dt><dd id="effort">Unavailable</dd>
<dt>Last observed model</dt><dd id="observed">Not observed</dd><dt>Observed effort</dt><dd id="observed-effort">Not observed</dd></dl>
<section id="context" aria-label="Host context usage"><p id="usage">Context usage unavailable</p><meter id="meter" min="0" max="1" value="0" hidden aria-label="Context used"></meter></section>
<section aria-label="Child visibility"><h2 style="font-size:16px">Session subagents</h2><p id="children-state" class="small">Host metadata unavailable</p><div id="children"></div>
<p class="small">App child sessions: unavailable through this extension API. Subagents are not project/chat child sessions.</p></section>
<p id="error" role="alert"></p><details><summary>Display preferences &amp; source</summary>
<label><input id="enabled" type="checkbox" checked>Automatically show in new sessions</label>
<p class="small">This preference follows this user. Closing affects only this session. Neither changes permissions or starts workers.</p>
<p class="small" id="source">Host events only; no task denominator, no completion percentage.</p><p class="small" id="diagnostic"></p>
</details></main><script nonce="${nonce}">
const el=id=>document.getElementById(id);const labels={unavailable:'Activity unavailable',ready:'Ready',working:'Working',blocked:'Waiting for permission',waiting:'Waiting for input',error:'Error reported',idle:'Idle',stopped:'Stopped'};
function item(tag,text){const n=document.createElement(tag);n.textContent=text;return n}
function children(data){
 const root=el('children'),opened=new Set([...root.querySelectorAll('details[open]')].map(n=>n.dataset.id));root.replaceChildren();
 el('children-state').textContent=data.subagentsDiagnostic||(data.subagentsStatus==='observed'?(data.subagents.length?'Host-tracked subagents; assigned slices are not completion.':'No subagents reported by this session.'):'Host task metadata unavailable');
 for(const child of data.subagents){
  const row=document.createElement('details');row.dataset.id=child.id;row.open=opened.has(child.id);row.style.marginTop='12px';
  const summary=item('summary',child.name+' / '+(child.role||'Role unavailable')+' / '+child.status);
  const slice=item('span','Assigned: '+(child.assignedSlice||'Unavailable'));slice.className='small';slice.style.display='block';summary.append(slice);row.append(summary);
  const facts=document.createElement('dl');
  for(const [label,value] of [['Role',child.role],['Requested model',child.requestedModel],['Resolved model',child.resolvedModel],['Observed model',child.observedModel],['Effort setting',child.configuredEffort],['Observed effort',child.observedEffort],['Current activity',child.currentActivity],['Context tier',child.contextTier]])
   facts.append(item('dt',label),item('dd',value||'Unavailable'));
  row.append(facts);
  if(child.usage)row.append(item('p',child.usage.currentTokens.toLocaleString()+' / '+child.usage.tokenLimit.toLocaleString()+' context tokens (host observed)'));
  root.append(row);
 }
}
function draw(data){
 el('activity').textContent=labels[data.activity]||labels.unavailable;
 el('track').className='track'+(data.activity==='working'?' active':['waiting','blocked','error'].includes(data.activity)?' paused':'');
 for(const [id,key,empty] of [['selected','selectedModel','Unavailable'],['effort','selectedEffort','Unavailable'],['observed','observedModel','Not observed'],['observed-effort','observedEffort','Not observed']])el(id).textContent=data[key]||empty;
 el('lanes').replaceChildren();for(const name of data.activeTools){const li=document.createElement('li');li.textContent=name;el('lanes').append(li)}
 const u=data.usage;el('meter').hidden=!u;
 el('usage').textContent=u?u.currentTokens.toLocaleString()+' / '+u.tokenLimit.toLocaleString()+' context tokens':'Context usage unavailable';
 if(u){el('meter').max=u.tokenLimit;el('meter').value=Math.min(u.currentTokens,u.tokenLimit);el('meter').setAttribute('aria-valuetext',el('usage').textContent)}
 el('enabled').checked=data.autoOpen;el('diagnostic').textContent=data.diagnostic||'';
 children(data);
 el('source').textContent='Host events only; no task denominator, no completion percentage.'+(u?.capturedAt?' Context observed '+u.capturedAt+'.':'')+(data.observedAt?' Last model call '+data.observedAt+'.':'')+(data.contextTier?' Context tier: '+data.contextTier+'.':'');
}
let refreshing=false,queued=false;
async function refresh(){if(refreshing){queued=true;return}refreshing=true;try{const r=await fetch('snapshot',{cache:'no-store'});if(!r.ok)throw Error('Session display unavailable. Reopen from the canvas catalog.');draw(await r.json());el('error').textContent=''}catch(e){el('error').textContent=e.message}finally{refreshing=false;if(queued){queued=false;refresh()}}}
async function action(name,body){const r=await fetch(name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error('Display preference could not be saved. Check extension support and storage.')}
el('enabled').onchange=async()=>{el('enabled').disabled=true;try{await action('preferences',{enabled:el('enabled').checked});await refresh()}catch(e){el('error').textContent=e.message}finally{el('enabled').disabled=false}};
el('close').onclick=async()=>{el('close').disabled=true;try{await action('dismiss',{});el('activity').textContent='Closed for this session'}catch(e){el('error').textContent=e.message;el('close').disabled=false}};
refresh();const events=new EventSource('events');events.onmessage=refresh;events.onerror=()=>{el('error').textContent='Display disconnected. Values may be stale; reopen from the canvas catalog.';el('track').className='track'};window.addEventListener('pagehide',()=>events.close());
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
        if (step.state === "verified" && step.streamId && streams.get(step.streamId).kind !== "delivery")
            fail("steps: investigation/reference completion is not product verified");
        for (const key of ["startedAt", "finishedAt"]) if (step[key]) timestamp(step[key], "owner span");
        if (step.finishedAt && (!step.startedAt || Date.parse(step.finishedAt) < Date.parse(step.startedAt)))
            fail("steps: invalid owner span order");
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
        if (relation.type === "informs" && relation.provenance !== "display-only annotation")
            fail("relations: INFORMS is display-only, not scheduling authority");
    }
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
async function saveSnapshot(value, expectedDigest) {
    validateSnapshot(value);
    return serial(value.domainKey, async () => {
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
    });
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
