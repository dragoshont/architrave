import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { get } from "node:http";
import { spawnSync, fork } from "node:child_process";

const source = await readFile(new URL("../.github/extensions/architrave-ribbon/extension.mjs", import.meta.url), "utf8");
const writer = process.argv[2] === "--writer";
const root = writer ? process.argv[3] : await mkdtemp(join(tmpdir(), "architrave-ribbon-"));
let writing = false, held = false;
const filename = fileURLToPath(new URL("../.github/extensions/architrave-ribbon/extension.mjs", import.meta.url));
async function load() {
    let canvas;
    const context = vm.createContext({ Buffer, console, process: { once() {}, stderr: process.stderr } });
    const main = new vm.SourceTextModule(source, { context, identifier: filename });
    await main.link(async specifier => {
        let exports;
        if (specifier === "@github/copilot-sdk/extension") {
            exports = {
                CanvasError: class extends Error { constructor(code, message) { super(message); this.code = code; } },
                createCanvas: value => value,
                joinSession: async config => { canvas = config.canvases[0]; return { workspacePath: root, log: async () => {} }; },
            };
        } else {
            exports = await import(specifier);
            if (writer && specifier === "node:fs/promises") {
                const original = exports.readFile;
                exports = { ...exports, readFile: async (...args) => {
                    const value = await original(...args);
                    if (writing && !held && String(args[0]).endsWith(".json")) {
                        held = true; process.send({ kind: "read" });
                        await new Promise(resolve => process.once("message", resolve));
                    }
                    return value;
                } };
            }
        }
        return new vm.SyntheticModule(Object.keys(exports), function () {
            for (const [key, value] of Object.entries(exports)) this.setExport(key, value);
        }, { context });
    });
    await main.evaluate();
    return { canvas, validate: main.namespace.validateSnapshot, html: main.namespace.renderHtml };
}
const fixture = {
    schema: "architrave.ribbon.v1", domainKey: "public-fixture:run", runId: "run", revision: 1,
    objectiveVersion: 1, title: "Generic release route", objective: "Qualify the actual requested product, not prerequisite counts.",
    capturedAt: "2026-10-08T05:00:00Z", startedAt: "2026-10-08T04:00:00Z", deadline: "2026-10-08T08:00:00Z",
    source: { commit: "fixture", sha256: "fixture", freshness: "unknown", provenance: "Public synthetic test fixture; not production evidence." },
    next: "Complete acceptance after the dependency clears.", milestone: null,
    steps: [
        { id: "scope", title: "Scope complete", state: "done", current: true, reason: "Scoped prerequisite only.", evidence: ["fixture:scoped"], dependencies: [], blocker: null, attempts: 1, retry: null, weightEstimate: 2 },
        { id: "bypass", title: "Alternate route", state: "bypassed", current: true, reason: "Explicitly bypassed, not done.", evidence: [], dependencies: ["scope"], blocker: null, attempts: 0, retry: null, weightEstimate: 1 },
        { id: "hold", title: "Product acceptance", state: "blocked", current: true, reason: "Wait for human observation.", evidence: [], dependencies: ["scope"], blocker: "human", attempts: 0, retry: null, weightEstimate: 3 },
    ],
};
let assertions = 0;
function ok(value) { assert.ok(value); assertions++; }
async function rejects(action, code) { await assert.rejects(action, error => error.code === code); assertions++; }
const providers = [];
const writers = [];
if (writer) {
    const provider = await load();
    const update = JSON.parse(process.argv[4]);
    await provider.canvas.open({ instanceId: "writer", input: { domainKey: update.domainKey } });
    process.send({ kind: "ready" });
    await new Promise(resolve => process.once("message", resolve));
    writing = true;
    try {
        const value = await provider.canvas.actions.find(entry => entry.name === "update_snapshot").handler({
            instanceId: "writer", input: { snapshot: update, expectedDigest: process.argv[5] } });
        process.send({ kind: "result", status: "saved", value });
    } catch (error) { process.send({ kind: "result", status: "rejected", code: error.code }); }
    await provider.canvas.onClose({ instanceId: "writer" });
    process.disconnect();
    process.exit(0);
}
function startWriter(update, digest) {
    const child = fork(fileURLToPath(import.meta.url), ["--writer", root, JSON.stringify(update), digest],
        { execArgv: ["--experimental-vm-modules"], stdio: ["ignore", "ignore", "pipe", "ipc"] });
    let ready, read, result, exited;
    const entry = { child, ready: new Promise(resolve => ready = resolve),
        read: new Promise(resolve => read = resolve), result: new Promise(resolve => result = resolve),
        exited: new Promise(resolve => exited = resolve) };
    child.on("message", value => {
        if (value.kind === "ready") ready(entry);
        if (value.kind === "read") read(entry);
        if (value.kind === "result") result(value);
    });
    child.on("exit", code => exited(code));
    writers.push(entry);
    return entry;
}
async function bounded(value) {
    let timer;
    try {
        return await Promise.race([value, new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error("Cross-process fixture exceeded its bound")), 15000);
        })]);
    } finally { clearTimeout(timer); }
}
try {
    const first = await load(); providers.push(first.canvas);
    first.validate(fixture);
    const maximum = structuredClone(fixture);
    maximum.runId = "r".repeat(128);
    maximum.domainKey = "a".repeat(24) + ":" + maximum.runId;
    first.validate(maximum); assertions++;
    const python = spawnSync(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
        ["-c", "import sys,json;sys.path.insert(0,'harness');from ribbon import compact;print(json.dumps(compact('\\U0001f680'*1201)))"],
        { cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8" });
    assert.equal(python.status, 0, python.stderr);
    const unicode = structuredClone(fixture); unicode.title = JSON.parse(python.stdout);
    first.validate(unicode);
    ok([...unicode.title].length === 1200 && unicode.title.length === 2400);
    const parallel = structuredClone(fixture);
    parallel.steps[0].streamId = "exploration";
    parallel.steps[1].streamId = "delivery";
    parallel.steps[2].streamId = "delivery";
    parallel.steps[2].dependencies = [];
    const sourceRef = { domainKey: fixture.domainKey, runId: fixture.runId, revision: 1,
        objectiveVersion: 1, capturedAt: fixture.capturedAt, commit: "fixture", sha256: "fixture", freshness: "unknown" };
    parallel.streams = [
        { id: "delivery", label: "Delivery / current slice", kind: "delivery",
            outcome: "Visible product outcome still unverified.", sourceRef: { ...sourceRef } },
        { id: "exploration", label: "Alternate approach feasibility", kind: "exploratory",
            outcome: "Scoped findings inform a decision, not product shipped.", sourceRef: { ...sourceRef } },
    ];
    parallel.relations = [{ fromStep: "scope", toStep: "hold", type: "informs",
        reason: "Feasibility findings inform funding, not an execution prerequisite.", provenance: "display-only annotation" }];
    first.validate(parallel); assertions++;
    const invalidParallel = structuredClone(parallel);
    invalidParallel.steps[0].state = "verified";
    assert.throws(() => first.validate(invalidParallel), error => error.code === "ribbon_input_invalid"); assertions++;
    delete invalidParallel.steps[0].streamId;
    assert.throws(() => first.validate(invalidParallel), error => error.code === "ribbon_input_invalid"); assertions++;
    const falseBlock = structuredClone(parallel);
    falseBlock.relations[0].type = "blocks"; falseBlock.relations[0].provenance = "canonical dependency";
    assert.throws(() => first.validate(falseBlock), error => error.code === "ribbon_input_invalid"); assertions++;
    falseBlock.relations[0].provenance = "display-only annotation";
    assert.throws(() => first.validate(falseBlock), error => error.code === "ribbon_input_invalid"); assertions++;
    const mutate = action => { const value = structuredClone(fixture); action(value); return value; };
    for (const action of [
        value => value.extra = "arbitrary",
        value => value.steps[0].state = "PASS",
        value => value.steps[0].dependencies = ["hold"],
        value => value.steps[0].dependencies = ["missing"],
        value => value.steps[1].id = "scope",
        value => value.steps[2].blocker = null,
        value => value.steps[0].evidence = [],
        value => value.steps[0].attempts = -1,
        value => value.deadline = "not a timestamp",
        value => value.domainKey = "../escape",
        value => value.startedAt = "2026-10-09T00:00:00Z",
        value => value.steps = Array.from({ length: 81 }, (_, index) => ({ ...value.steps[0], id: "step-" + index })),
        value => { value.steps = Array.from({ length: 60 }, (_, index) => ({ ...value.steps[0], id: "step-" + index, reason: "x".repeat(1200) })); },
        value => value.steps[0].retry = { fingerprint: "fixture", evidenceFingerprint: "fixture", repeated: 2, stopped: true, reason: "Explicit stop" },
    ]) {
        assert.throws(() => first.validate(mutate(action)), error => error.code === "ribbon_input_invalid"); assertions++;
    }
    const open = await first.canvas.open({ instanceId: "one", input: { domainKey: fixture.domainKey, snapshot: fixture } });
    const action = (provider, name, instanceId, input = {}) => provider.actions.find(entry => entry.name === name).handler({ instanceId, input });
    const saved = await action(first.canvas, "get_snapshot", "one");
    ok(JSON.stringify(saved.snapshot) === JSON.stringify(fixture));
    ok(saved.digest === createHash("sha256").update(JSON.stringify(fixture)).digest("hex"));
    const page = await fetch(open.url);
    ok(page.status === 200 && page.headers.get("content-security-policy").includes("default-src 'none'"));
    const html = await page.text();
    ok(html.includes('aria-label="Route steps"') && html.includes("d.source.sha256") && html.includes("textContent") && !html.includes("innerHTML"));
    const clientScript = html.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
    new vm.Script(clientScript); assertions++;
    ok((await fetch(new URL("snapshot", open.url))).status === 200);
    ok((await fetch(open.url, { headers: { Origin: "https://invalid.example" } })).status === 403);
    const hostStatus = await new Promise((resolve, reject) => {
        const request = get(open.url, { headers: { Host: "invalid.example" } }, response => {
            response.resume(); resolve(response.statusCode);
        });
        request.on("error", reject);
    });
    ok(hostStatus === 403);
    ok((await fetch(open.url, { method: "POST", body: "{}" })).status === 403);
    ok((await fetch(new URL("/", open.url))).status === 403);
    ok((await fetch(new URL("unknown", open.url))).status === 404);
    await rejects(() => first.canvas.open({ instanceId: "one", input: { domainKey: "another" } }), "ribbon_input_invalid");
    const refresh = structuredClone(fixture);
    refresh.capturedAt = "2026-10-08T05:01:00Z";
    refresh.source.sha256 = "refreshed-public-source";
    refresh.source.freshness = "stale";
    const refreshed = await action(first.canvas, "update_snapshot", "one", { snapshot: refresh, expectedDigest: saved.digest });
    ok(refreshed.revision === fixture.revision && refreshed.digest !== saved.digest);
    const competitor = structuredClone(refresh);
    competitor.capturedAt = "2026-10-08T05:02:00Z";
    competitor.steps[0].evidence = ["fixture:competing-observation"];
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: competitor, expectedDigest: saved.digest }), "ribbon_snapshot_conflict");
    ok((await action(first.canvas, "get_snapshot", "one")).digest === refreshed.digest);
    const left = structuredClone(competitor);
    left.steps[0].evidence = ["fixture:new-left-observation"];
    const right = structuredClone(competitor);
    right.steps[0].evidence = ["fixture:new-right-observation"];
    const competing = await Promise.allSettled([
        action(first.canvas, "update_snapshot", "one", { snapshot: left, expectedDigest: refreshed.digest }),
        action(first.canvas, "update_snapshot", "one", { snapshot: right, expectedDigest: refreshed.digest }),
    ]);
    ok(competing.filter(entry => entry.status === "fulfilled").length === 1);
    ok(competing.filter(entry => entry.status === "rejected" && entry.reason.code === "ribbon_snapshot_conflict").length === 1);
    const winner = await action(first.canvas, "get_snapshot", "one");
    ok(winner.snapshot.steps[0].evidence[0] === "fixture:new-left-observation");
    const olderCapture = structuredClone(winner.snapshot);
    olderCapture.capturedAt = fixture.capturedAt;
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: olderCapture, expectedDigest: winner.digest }), "ribbon_stale_snapshot");
    const olderObjective = structuredClone(winner.snapshot);
    olderObjective.objectiveVersion = 0;
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: olderObjective, expectedDigest: winner.digest }), "ribbon_stale_snapshot");
    const update = structuredClone(winner.snapshot); update.revision = 2;
    update.capturedAt = "2026-10-08T05:03:00Z";
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: update, expectedDigest: null }), "ribbon_snapshot_conflict");
    const result = await action(first.canvas, "update_snapshot", "one", { snapshot: update, expectedDigest: winner.digest });
    ok(result.revision === 2);
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: fixture, expectedDigest: result.digest }), "ribbon_stale_snapshot");
    const peer = await first.canvas.open({ instanceId: "two", input: { domainKey: fixture.domainKey } });
    ok((await fetch(new URL("snapshot", peer.url)).then(response => response.json())).revision === 2);
    await first.canvas.onClose({ instanceId: "one" }); await first.canvas.onClose({ instanceId: "two" });
    await assert.rejects(() => fetch(open.url)); assertions++;
    const second = await load(); providers.push(second.canvas);
    // Runtime rehydrate retains the original open input, not the last action payload.
    await second.canvas.open({ instanceId: "fresh-panel", input: { domainKey: fixture.domainKey, snapshot: fixture } });
    const restored = await action(second.canvas, "get_snapshot", "fresh-panel");
    ok(restored.snapshot.revision === 2 && restored.digest === result.digest);
    await rejects(() => action(second.canvas, "update_snapshot", "fresh-panel", { snapshot: competitor, expectedDigest: saved.digest }), "ribbon_snapshot_conflict");
    const artifacts = await readdir(join(root, "artifacts", "architrave-ribbon"));
    ok(artifacts.length === 1 && /^[a-f0-9]{64}\.json$/.test(artifacts[0]));
    const domainFile = join(root, "artifacts", "architrave-ribbon", createHash("sha256").update(fixture.domainKey).digest("hex") + ".json");
    await writeFile(domainFile, '{"malformed":true}');
    await rejects(() => action(second.canvas, "get_snapshot", "fresh-panel"), "ribbon_input_invalid");
    await second.canvas.onClose({ instanceId: "fresh-panel" });
    const maxPanel = await second.canvas.open({ instanceId: "maximum", input: { domainKey: maximum.domainKey, snapshot: maximum } });
    const maxSaved = await action(second.canvas, "get_snapshot", "maximum");
    ok(maxSaved.snapshot.domainKey.length === 153 && (await fetch(new URL("snapshot", maxPanel.url))).status === 200);
    const maxUpdate = structuredClone(maximum); maxUpdate.revision = 2;
    await action(second.canvas, "update_snapshot", "maximum", { snapshot: maxUpdate, expectedDigest: maxSaved.digest });
    ok((await action(second.canvas, "get_snapshot", "maximum")).snapshot.revision === 2);
    await second.canvas.onClose({ instanceId: "maximum" });
    const third = await load(); providers.push(third.canvas);
    await third.canvas.open({ instanceId: "maximum-reloaded", input: { domainKey: maximum.domainKey } });
    ok((await action(third.canvas, "get_snapshot", "maximum-reloaded")).snapshot.revision === 2);
    await third.canvas.onClose({ instanceId: "maximum-reloaded" });
    const shared = structuredClone(fixture); shared.domainKey = "cross-process";
    await third.canvas.open({ instanceId: "shared", input: { domainKey: shared.domainKey, snapshot: shared } });
    const sharedSaved = await action(third.canvas, "get_snapshot", "shared");
    const writerA = structuredClone(shared); writerA.revision = 2; writerA.title = "Writer A";
    const writerB = structuredClone(writerA); writerB.title = "Writer B";
    const a = startWriter(writerA, sharedSaved.digest), b = startWriter(writerB, sharedSaved.digest);
    await bounded(Promise.all([a.ready, b.ready]));
    a.child.send("start"); b.child.send("start");
    const firstRead = await bounded(Promise.race([a.read, b.read]));
    const lockPath = join(root, "artifacts", "architrave-ribbon", createHash("sha256").update(shared.domainKey).digest("hex") + ".json.lock");
    const owner = JSON.parse(await readFile(lockPath, "utf8"));
    ok([a.child.pid, b.child.pid].includes(owner.pid));
    firstRead.child.send("continue");
    const secondRead = await bounded(firstRead === a ? b.read : a.read);
    secondRead.child.send("continue");
    const results = await bounded(Promise.all([a.result, b.result]));
    ok(results.filter(value => value.status === "saved").length === 1);
    ok(results.filter(value => value.code === "ribbon_snapshot_conflict").length === 1);
    ok((await action(third.canvas, "get_snapshot", "shared")).snapshot.revision === 2);
    await bounded(Promise.all([a.exited, b.exited]));
    await writeFile(lockPath, JSON.stringify({ pid: a.child.pid, nonce: "a".repeat(32) }));
    const currentShared = await action(third.canvas, "get_snapshot", "shared");
    const afterCrash = structuredClone(currentShared.snapshot); afterCrash.revision = 3;
    await action(third.canvas, "update_snapshot", "shared", { snapshot: afterCrash, expectedDigest: currentShared.digest });
    ok((await action(third.canvas, "get_snapshot", "shared")).snapshot.revision === 3);
    await writeFile(lockPath, "{orphan");
    const orphanUpdate = structuredClone(afterCrash); orphanUpdate.revision = 4;
    const orphanSaved = await action(third.canvas, "get_snapshot", "shared");
    await rejects(() => action(third.canvas, "update_snapshot", "shared",
        { snapshot: orphanUpdate, expectedDigest: orphanSaved.digest }), "ribbon_lock_recovery_required");
    ok((await readFile(lockPath, "utf8")) === "{orphan");
    await rm(lockPath);
    await writeFile(lockPath, "");
    await rejects(() => action(third.canvas, "update_snapshot", "shared",
        { snapshot: orphanUpdate, expectedDigest: orphanSaved.digest }), "ribbon_lock_recovery_required");
    await rm(lockPath);
    await third.canvas.onClose({ instanceId: "shared" });
    console.log(`PASS Route Ribbon: ${assertions} assertions (SDK fixture, not native host proof)`);
} finally {
    for (const provider of providers) for (const instanceId of ["one", "two", "fresh-panel", "maximum", "maximum-reloaded", "shared"])
        await provider.onClose({ instanceId });
    for (const entry of writers) if (entry.child.exitCode === null) entry.child.kill();
    await rm(root, { recursive: true });
}
