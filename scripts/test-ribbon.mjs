import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { get } from "node:http";
import { spawnSync } from "node:child_process";

const source = await readFile(new URL("../.github/extensions/architrave-ribbon/extension.mjs", import.meta.url), "utf8");
const root = await mkdtemp(join(tmpdir(), "architrave-ribbon-"));
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
        } else exports = await import(specifier);
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
try {
    const first = await load(); providers.push(first.canvas);
    first.validate(fixture);
    const python = spawnSync(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
        ["-c", "import sys,json;sys.path.insert(0,'harness');from ribbon import compact;print(json.dumps(compact('\\U0001f680'*1201)))"],
        { cwd: fileURLToPath(new URL("../", import.meta.url)), encoding: "utf8" });
    assert.equal(python.status, 0, python.stderr);
    const unicode = structuredClone(fixture); unicode.title = JSON.parse(python.stdout);
    first.validate(unicode);
    ok([...unicode.title].length === 1200 && unicode.title.length === 2400);
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
    const snapshot = await action(first.canvas, "get_snapshot", "one");
    ok(JSON.stringify(snapshot) === JSON.stringify(fixture));
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
    const update = structuredClone(fixture); update.revision = 2;
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: update, expectedRevision: null }), "ribbon_revision_conflict");
    const result = await action(first.canvas, "update_snapshot", "one", { snapshot: update, expectedRevision: 1 });
    ok(result.revision === 2);
    await rejects(() => action(first.canvas, "update_snapshot", "one", { snapshot: fixture, expectedRevision: 2 }), "ribbon_stale_snapshot");
    const peer = await first.canvas.open({ instanceId: "two", input: { domainKey: fixture.domainKey } });
    ok((await fetch(new URL("snapshot", peer.url)).then(response => response.json())).revision === 2);
    await first.canvas.onClose({ instanceId: "one" }); await first.canvas.onClose({ instanceId: "two" });
    await assert.rejects(() => fetch(open.url)); assertions++;
    const second = await load(); providers.push(second.canvas);
    // Runtime rehydrate retains the original open input, not the last action payload.
    await second.canvas.open({ instanceId: "fresh-panel", input: { domainKey: fixture.domainKey, snapshot: fixture } });
    ok((await action(second.canvas, "get_snapshot", "fresh-panel")).revision === 2);
    const artifacts = await readdir(join(root, "artifacts", "architrave-ribbon"));
    ok(artifacts.length === 1 && /^[a-f0-9]{64}\.json$/.test(artifacts[0]));
    const domainFile = join(root, "artifacts", "architrave-ribbon", createHash("sha256").update(fixture.domainKey).digest("hex") + ".json");
    await writeFile(domainFile, '{"malformed":true}');
    await rejects(() => action(second.canvas, "get_snapshot", "fresh-panel"), "ribbon_input_invalid");
    await second.canvas.onClose({ instanceId: "fresh-panel" });
    console.log(`PASS Route Ribbon: ${assertions} assertions (SDK fixture, not native host proof)`);
} finally {
    for (const provider of providers) for (const instanceId of ["one", "two", "fresh-panel"])
        await provider.onClose({ instanceId });
    await rm(root, { recursive: true });
}
