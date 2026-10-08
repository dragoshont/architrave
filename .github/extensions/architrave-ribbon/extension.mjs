// Optional read-only projection. Python Run APIs remain the only authority.
import { createServer } from "node:http";
import { randomBytes, createHash } from "node:crypto";
import { mkdir, lstat, readFile, writeFile, rename, unlink, realpath } from "node:fs/promises";
import { join } from "node:path";
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
        if (relation.provenance === "canonical dependency" &&
            (relation.type !== "blocks" || !byId.get(relation.toStep).dependencies.includes(relation.fromStep)))
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

async function startServer(domainKey) {
    const token = randomBytes(24).toString("hex");
    const nonce = randomBytes(18).toString("base64");
    const clients = new Set();
    const server = createServer(async (req, res) => {
        res.setHeader("Cache-Control", "no-store");
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.setHeader("Referrer-Policy", "no-referrer");
        const host = `127.0.0.1:${server.address().port}`;
        if (req.headers.host !== host || req.headers.origin && req.headers.origin !== `http://${host}` ||
            req.method !== "GET" || !req.url?.startsWith(`/${token}/`)) {
            res.writeHead(403); res.end("Forbidden"); return;
        }
        try {
            const route = req.url.slice(token.length + 2);
            if (route === "") {
                res.setHeader("Content-Type", "text/html; charset=utf-8");
                res.setHeader("Content-Security-Policy", `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'`);
                res.end(renderHtml(nonce));
            } else if (route === "snapshot") {
                res.setHeader("Content-Type", "application/json");
                res.end(JSON.stringify(await readSnapshot(domainKey)));
            } else if (route === "events") {
                if (clients.size >= 16) { res.writeHead(429); res.end("Too many observers"); return; }
                res.writeHead(200, { "Content-Type": "text/event-stream", Connection: "keep-alive" });
                res.write(": snapshot notifications\n\n"); clients.add(res);
                res.on("close", () => clients.delete(res));
            } else { res.writeHead(404); res.end("Not found"); }
        } catch (error) {
            await session.log(`Ribbon snapshot read failed: ${error.code || "invalid artifact"}`, { level: "error" });
            res.writeHead(500); res.end("Snapshot unavailable; check extension logs");
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
const session = await joinSession({ canvases: [createCanvas({
    id: "architrave-ribbon", displayName: "Route Ribbon",
    description: "Read-only Architrave route, blockers, bypasses and retry evidence from durable agent-fed snapshots.",
    inputSchema: openSchema,
    open: async ctx => {
        check(ctx.input, openSchema, "input");
        if (!storageRoot) {
            if (!session.workspacePath) throw new CanvasError("ribbon_storage_unavailable", "Host did not supply workspace artifact storage");
            storageRoot = await realpath(session.workspacePath);
        }
        if (ctx.input.snapshot) {
            if (ctx.input.snapshot.domainKey !== ctx.input.domainKey) fail("Open snapshot domain mismatch");
            const prior = await readSnapshot(ctx.input.domainKey);
            if (!prior) await saveSnapshot(ctx.input.snapshot, null);
        }
        const existing = servers.get(ctx.instanceId);
        if (existing && existing.domainKey !== ctx.input.domainKey) fail("Panel domain cannot change; open a fresh instance");
        if (!existing) {
            if (servers.size >= 8) throw new CanvasError("ribbon_limit", "Close an existing ribbon before opening another");
            servers.set(ctx.instanceId, await startServer(ctx.input.domainKey));
        }
        return { url: servers.get(ctx.instanceId).url, title: "Architrave / Route Ribbon", status: "Read-only snapshot" };
    },
    actions: [
        { name: "get_snapshot", description: "Read saved snapshot and its display digest; no canonical mutations.",
            inputSchema: object({}), handler: async ctx => {
                const entry = servers.get(ctx.instanceId);
                if (!entry) throw new CanvasError("ribbon_not_open", "Reopen this ribbon after provider reload");
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
    onClose: ctx => close(ctx.instanceId),
})] });
for (const signal of ["SIGTERM", "SIGINT"]) process.once(signal, () => {
    Promise.all([...servers.keys()].map(close)).then(() => process.exit(0), error => {
        process.stderr.write(`Ribbon cleanup failed: ${error.message}\n`); process.exit(1);
    });
});
