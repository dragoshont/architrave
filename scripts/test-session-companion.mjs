import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, mkdir, writeFile, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const filename = fileURLToPath(new URL("../.github/extensions/architrave-ribbon/extension.mjs", import.meta.url));
const source = await readFile(filename, "utf8");
const root = await mkdtemp(join(tmpdir(), "companion-contract-"));
const home = join(root, "home");
await mkdir(home);
const providers = [];
let checks = 0;
const equal = (a, b) => { assert.deepEqual(a, b); checks++; };

async function load(name, options = {}) {
    let canvas, listener, declaration;
    const opens = [], panels = new Map(), logs = [];
    let taskReads = 0;
    const taskRows = options.tasks || [];
    const workspacePath = options.workspacePath || join(root, name);
    await mkdir(workspacePath, { recursive: true });
    const context = vm.createContext({ Buffer, process: { env: { COPILOT_HOME: home }, once() {},
        stderr: { write: value => logs.push(value) } } });
    const rpc = {
        extensions: { list: async () => ({ extensions: [
            { id: options.providerId || "project:architrave-ribbon", pid: process.pid },
            { id: "user:architrave-ribbon", pid: process.pid + 1 },
        ] }) },
        model: { getCurrent: async () => {
            if (options.modelDenied) throw Object.assign(Error("denied"), { code: "forbidden" });
            return { modelId: "auto", reasoningEffort: "high", contextTier: "default" };
        } },
        canvas: {
            listOpen: async () => {
                if (options.beforeListOpen) await options.beforeListOpen({ canvas, listener });
                return { openCanvases: options.sharedPanels || (options.existing ? [{ instanceId: "other" }] : []) };
            },
            open: async input => {
                opens.push(input);
                if (options.openDenied) throw Object.assign(Error("denied"), { code: "forbidden" });
                const result = await canvas.open(input); panels.set(input.instanceId, result);
                const confirmed = { ...input, ...result, extensionId: input.extensionId };
                options.sharedPanels?.push(confirmed);
                return confirmed;
            },
            close: async ({ instanceId }) => {
                if (options.closeDenied) throw Object.assign(Error("denied"), { code: "forbidden" });
                await canvas.onClose({ instanceId }); panels.delete(instanceId);
            },
        },
        tasks: { list: async () => { taskReads++; return options.readTasks ? options.readTasks() : { tasks: taskRows }; } },
    };
    const session = { sessionId: name, workspacePath, on: fn => listener = fn, rpc };
    if (options.noRpc) delete session.rpc;
    const main = new vm.SourceTextModule(source, { context, identifier: filename });
    await main.link(async specifier => {
        const exports = specifier === "@github/copilot-sdk/extension" ? {
            CanvasError: class extends Error { constructor(code, message) { super(message); this.code = code; } },
            createCanvas: value => value,
            joinSession: async config => { declaration = config; canvas = config.canvases.find(c => c.id === "architrave-session"); return session; },
        } : await import(specifier);
        return new vm.SyntheticModule(Object.keys(exports), function () {
            for (const [key, value] of Object.entries(exports)) this.setExport(key, value);
        }, { context });
    });
    await main.evaluate();
    const result = {
        canvas, rpc, opens, panels, logs, declaration, workspacePath, taskRows,
        get taskReads() { return taskReads; },
        emit(type, data = {}, extra = {}) { listener({ type, data, timestamp: "2026-10-08T12:00:00Z", ...extra }); },
        async manual(id = "manual") {
            const result = await canvas.open({ instanceId: id }); panels.set(id, result); return result.url;
        },
        async close() { for (const instanceId of panels.keys()) await canvas.onClose({ instanceId }); panels.clear(); },
    };
    providers.push(result);
    return result;
}
async function state(url) { return fetch(new URL("snapshot", url)).then(r => r.json()); }
async function post(url, action, value, headers = {}) {
    return fetch(new URL(action, url), { method: "POST", body: JSON.stringify(value),
        headers: { "Content-Type": "application/json", Origin: new URL(url).origin, ...headers } });
}

try {
    const one = await load("fresh");
    equal(Object.keys(one.declaration), ["canvases"]);
    equal(Object.keys(one.canvas.inputSchema.properties).length, 0);
    equal(one.canvas.actions, undefined);
    assert.equal(one.opens.length, 1, one.logs.join(";")); checks++;
    equal(one.opens[0].extensionId, "project:architrave-ribbon");
    const url = one.panels.get("architrave-session-companion").url;
    let view = await state(url);
    equal(view.selectedModel, "auto");
    equal(view.selectedEffort, "high");
    equal(view.observedModel, null);
    equal(view.usage, null);
    equal(view.activity, "unavailable");
    equal(view.subagentsStatus, "observed");
    equal(view.subagents, []);
    equal(one.taskReads, 1);
    equal(await readdir(home), []); // Startup never creates user-global files.
    const html = await fetch(url).then(r => r.text());
    new vm.Script(html.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1]); checks++;
    equal(html.includes("prefers-reduced-motion"), true);
    equal(html.includes("innerHTML"), false);
    one.emit("assistant.turn_start");
    one.emit("tool.execution_start", { toolCallId: "a", toolName: "read", arguments: { secret: "DO_NOT_RETAIN" } });
    one.emit("tool.execution_start", { toolCallId: "b", toolName: "test" });
    view = await state(url);
    equal(view.activity, "working");
    equal(view.activeTools, ["read", "test"]);
    equal(JSON.stringify(view).includes("DO_NOT_RETAIN"), false);
    equal(one.taskReads, 1); // Ordinary tool/activity events do not poll tasks.
    one.emit("permission.requested", { requestId: "permission", permissionRequest: { fullCommandText: "DO_NOT_RETAIN" } });
    one.emit("permission.requested", { requestId: "auto-approved", resolvedByHook: true });
    equal((await state(url)).activity, "blocked");
    one.emit("permission.completed", { requestId: "permission" });
    equal((await state(url)).activity, "working");
    one.emit("user_input.requested", { requestId: "input", question: "DO_NOT_RETAIN" });
    equal((await state(url)).activity, "waiting");
    one.emit("session.idle");
    equal((await state(url)).activity, "waiting");
    one.emit("user_input.completed", { requestId: "input", answer: "DO_NOT_RETAIN" });
    for (const kind of ["permission", "user_input", "elicitation"]) {
        one.emit(kind + ".requested", { requestId: "ordinary-" + kind });
        const expected = kind === "permission" ? "blocked" : "waiting";
        one.emit("session.context_cleared");
        equal((await state(url)).activity, expected);
        one.emit("session.error");
        equal((await state(url)).activity, expected);
        one.emit("session.idle");
        one.emit("assistant.turn_start");
        equal((await state(url)).activity, expected);
        one.emit(kind + ".completed", { requestId: "unrelated-completion" });
        equal((await state(url)).activity, expected);
        one.emit(kind + ".completed", { requestId: "ordinary-" + kind });
        equal((await state(url)).activity, "working");
    }
    for (let i = 0; i < 33; i++) one.emit("user_input.requested", { requestId: "overflow-" + i });
    for (let i = 0; i < 32; i++) one.emit("user_input.completed", { requestId: "overflow-" + i });
    equal((await state(url)).activity, "waiting");
    equal((await state(url)).pendingRequestsStatus, "overflow-unreconciled");
    one.emit("session.idle");
    one.emit("assistant.turn_start");
    equal((await state(url)).activity, "waiting");
    one.emit("session.context_cleared");
    equal((await state(url)).activity, "waiting");
    one.emit("session.error");
    equal((await state(url)).activity, "waiting");
    one.emit("user_input.completed", { requestId: "overflow-32" });
    equal((await state(url)).activity, "waiting");
    one.emit("session.shutdown");
    equal((await state(url)).activity, "stopped");
    equal((await state(url)).pendingRequestsStatus, "observed");
    for (const kind of ["permission", "elicitation"]) {
        for (let i = 0; i < 33; i++) one.emit(kind + ".requested", { requestId: kind + "-" + i });
        for (let i = 0; i < 32; i++) one.emit(kind + ".completed", { requestId: kind + "-" + i });
        equal((await state(url)).activity, "waiting");
        equal((await state(url)).pendingRequestsStatus, "overflow-unreconciled");
        one.emit("session.shutdown");
        equal((await state(url)).activity, "stopped");
    }
    one.emit("assistant.usage", { model: "model-observed", reasoningEffort: "medium" });
    one.emit("session.usage_info", { currentTokens: 1234, tokenLimit: 32768, messagesLength: 3,
        systemTokens: 100, toolDefinitionsTokens: 222, conversationTokens: 912 });
    view = await state(url);
    equal(view.selectedModel, "auto");
    equal(view.observedModel, "model-observed");
    equal(view.observedEffort, "medium");
    equal(view.usage.tokenLimit, 32768);
    equal(view.usage.currentTokens, 1234);
    one.emit("session.usage_info", { currentTokens: 999, tokenLimit: 9999, messagesLength: 2 }, { agentId: "child" });
    one.emit("assistant.usage", { model: "compaction-model", initiator: "compaction" });
    equal((await state(url)).observedModel, "model-observed");
    equal((await state(url)).usage.currentTokens, 1234);
    one.emit("session.model_change", { newModel: "new-selection", reasoningEffort: "high", contextTier: "long_context" });
    view = await state(url);
    equal(view.selectedModel, "new-selection");
    one.emit("session.model_deselected");
    view = await state(url);
    equal(view.selectedModel, null);
    equal(view.selectedEffort, null);
    equal(view.contextTier, null);
    equal(view.selectedEffort, null);
    equal(view.observedModel, null);
    equal(view.usage, null);
    one.emit("session.usage_info", { currentTokens: -1, tokenLimit: 0, messagesLength: 1 });
    equal((await state(url)).usage, null);
    one.emit("session.context_cleared");
    equal((await state(url)).activity, "ready");
    equal((await state(url)).activeTools, []);
    equal(one.opens.length, 1);
    for (let i = 0; i < 100; i++) one.emit("tool.execution_start", { toolCallId: "bounded-" + i, toolName: "read" });
    equal((await state(url)).activeTools.length, 32);
    one.emit("session.error", { message: "DO_NOT_RETAIN" });
    equal((await state(url)).activity, "error");
    one.emit("session.idle");
    equal((await state(url)).activity, "error");
    one.emit("assistant.turn_start");
    one.emit("session.idle");
    equal((await state(url)).activity, "idle");
    const reload = await load("fresh");
    equal(reload.opens.length, 0);
    await reload.manual();
    equal((await state(reload.panels.get("manual").url)).usage, null);
    equal((await post(url, "preferences", { enabled: false }, { Origin: "https://invalid.example" })).status, 403);
    equal((await post(url, "preferences", { enabled: false, extra: true })).status, 400);
    equal((await post(url, "preferences", { enabled: false })).status, 200);
    equal((await state(url)).autoOpen, false);
    for (const unsupported of [false, true]) {
        const denied = await load("close-denied-" + unsupported, { closeDenied: !unsupported });
        const deniedUrl = await denied.manual();
        if (unsupported) delete denied.rpc.canvas.close;
        equal((await post(deniedUrl, "dismiss", {})).status, 500);
        equal(denied.panels.size, 1);
        equal((await state(deniedUrl)).diagnostic.includes("host close unavailable"), true);
    }
    const optedOut = await load("opted-out");
    equal(optedOut.opens.length, 0);
    const optUrl = await optedOut.manual();
    equal((await state(optUrl)).autoOpen, false);
    equal((await post(optUrl, "preferences", { enabled: true })).status, 200);
    equal(optedOut.opens.length, 0); // Enabling doesn't take focus or reopen.
    const fresh = await load("enabled-next");
    equal(fresh.opens.length, 1);
    await fresh.close();
    equal((await load("enabled-next")).opens.length, 0);
    const dismissed = await load("dismissed");
    const dismissUrl = dismissed.panels.get("architrave-session-companion").url;
    equal((await post(dismissUrl, "dismiss", {})).status, 200);
    equal((await load("dismissed")).opens.length, 0);
    equal((await load("existing-panel", { existing: true })).opens.length, 0);
    equal((await load("existing-panel")).opens.length, 0);
    let interrupted = false;
    const startupClose = await load("startup-close", { beforeListOpen: async ({ canvas }) => {
        if (interrupted) return;
        interrupted = true;
        await canvas.open({ instanceId: "manual-during-startup" });
        await canvas.onClose({ instanceId: "manual-during-startup" });
    } });
    equal(startupClose.opens.length, 0);
    equal((await load("startup-close")).opens.length, 0);
    let discoveryCount = 0;
    const startupOther = await load("startup-other", { beforeListOpen: async ({ listener }) => {
        if (++discoveryCount === 2) listener({ type: "session.canvas.opened", data: { instanceId: "another" } });
    } });
    equal(startupOther.opens.length, 0);
    const denied = await load("denied", { modelDenied: true, openDenied: true });
    equal(denied.opens.length, 1);
    equal(denied.logs.length, 2);
    const deniedPreferences = JSON.parse(await readFile(join(denied.workspacePath,
        "artifacts", "architrave-ribbon", "session.json"), "utf8").catch(error => {
            if (error.code === "ENOENT") return "{}"; throw error;
        }));
    equal(deniedPreferences.opened, undefined);
    equal((await load("denied")).opens.length, 1);
    const sharedPanels = [];
    const sharedWorkspace = join(root, "coexistence");
    const [projectCopy, pluginCopy] = await Promise.all([
        load("project-copy", { workspacePath: sharedWorkspace, sharedPanels,
            providerId: "project:architrave-ribbon" }),
        load("plugin-copy", { workspacePath: sharedWorkspace, sharedPanels,
            providerId: "plugin:architrave:architrave-ribbon" }),
    ]);
    equal(projectCopy.opens.length + pluginCopy.opens.length, 1);
    equal(sharedPanels.length, 1);
    equal(["project:architrave-ribbon", "plugin:architrave:architrave-ribbon"]
        .includes(sharedPanels[0].extensionId), true);
    const unsupported = await load("unsupported", { noRpc: true });
    equal(unsupported.opens.length, 0);
    equal((await state(await unsupported.manual())).selectedModel, null);
    const family = await load("subagents", { tasks: [
        { type: "agent", id: "owned", toolCallId: "spawn", displayName: "Companion implementation",
            description: "Startup implementation", agentType: "general-purpose", status: "running",
            model: "requested", resolvedModel: "configured", prompt: "DO_NOT_RETAIN",
            latestResponse: "DO_NOT_RETAIN", result: "DO_NOT_RETAIN" },
        { type: "shell", id: "shell", command: "DO_NOT_RETAIN" },
        { type: "client", id: "client", description: "Not proof of app child ownership" },
    ] });
    const familyUrl = family.panels.get("architrave-session-companion").url;
    let child = (await state(familyUrl)).subagents[0];
    equal((await state(familyUrl)).subagents.length, 1);
    equal(child.assignedSlice, "Startup implementation");
    equal(child.role, "general-purpose");
    equal(child.requestedModel, "requested");
    equal(child.resolvedModel, "configured");
    equal(child.observedModel, null);
    equal(JSON.stringify(await state(familyUrl)).includes("DO_NOT_RETAIN"), false);
    family.emit("subagent.configured", { model: "resolved-new", reasoningEffort: "high", contextTier: "long_context" }, { agentId: "owned" });
    family.emit("assistant.usage", { model: "effective", reasoningEffort: "medium", initiator: "sub-agent" }, { agentId: "owned" });
    family.emit("session.usage_info", { currentTokens: 800, tokenLimit: 64000, messagesLength: 1 }, { agentId: "owned" });
    family.emit("tool.execution_start", { toolName: "test", toolCallId: "child-tool" }, { agentId: "owned" });
    child = (await state(familyUrl)).subagents[0];
    equal(child.resolvedModel, "resolved-new");
    equal(child.observedModel, "effective");
    equal(child.configuredEffort, "high");
    equal(child.observedEffort, "medium");
    equal(child.currentActivity, "test");
    equal(child.usage.currentTokens, 800);
    equal((await state(familyUrl)).observedModel, null);
    equal((await state(familyUrl)).usage, null);
    family.emit("assistant.usage", { model: "not-owned" }, { agentId: "unrelated" });
    equal((await state(familyUrl)).subagents.length, 1);
    family.taskRows[0].status = "idle";
    family.emit("session.background_tasks_changed");
    await new Promise(resolve => setImmediate(resolve));
    child = (await state(familyUrl)).subagents[0];
    equal(child.status, "idle");
    equal(child.currentActivity, null);
    equal(child.observedModel, "effective");
    equal(family.taskReads, 2);
    family.emit("subagent.completed", { toolCallId: "spawn", firstDispatchedModel: "dispatch-proof" });
    equal((await state(familyUrl)).subagents[0].observedModel, "effective");
    family.rpc.tasks.list = async () => { throw Object.assign(Error("denied"), { code: "forbidden" }); };
    family.emit("session.background_tasks_changed");
    await new Promise(resolve => setImmediate(resolve));
    equal((await state(familyUrl)).subagentsStatus, "unavailable");
    let settle;
    const deferred = await load("child-discovery-race", { readTasks: () => new Promise(resolve => { settle = resolve; }) });
    const raceUrl = deferred.panels.get("architrave-session-companion").url;
    deferred.emit("subagent.configured", { model: "actual-config", reasoningEffort: "high", contextTier: "long_context" }, { agentId: "new-child" });
    deferred.emit("assistant.usage", { model: "actual-call", initiator: "sub-agent" }, { agentId: "new-child" });
    deferred.emit("assistant.usage", { model: "unowned" }, { agentId: "not-owned" });
    equal((await state(raceUrl)).subagents.length, 0);
    const task = { type: "agent", id: "new-child", toolCallId: "new-spawn", description: "Composition feasibility",
        agentType: "research", status: "running", resolvedModel: "old-list-config" };
    settle({ tasks: [task] });
    await new Promise(resolve => setImmediate(resolve));
    child = (await state(raceUrl)).subagents[0];
    equal((await state(raceUrl)).subagents.length, 1);
    equal(child.resolvedModel, "actual-config");
    equal(child.configuredEffort, "high");
    equal(child.contextTier, "long_context");
    equal(child.observedModel, "actual-call");
    deferred.emit("session.background_tasks_changed");
    deferred.emit("session.model_change", { newModel: "newer-model", reasoningEffort: "medium" }, { agentId: "new-child" });
    deferred.emit("subagent.completed", { toolCallId: "new-spawn", firstDispatchedModel: "verified-dispatch" });
    settle({ tasks: [task] });
    await new Promise(resolve => setImmediate(resolve));
    child = (await state(raceUrl)).subagents[0];
    equal(child.status, "completed");
    equal(child.resolvedModel, "newer-model");
    equal(child.observedModel, "verified-dispatch");
    let settleQueued;
    const queuedChild = await load("queued-child-race", { readTasks: () => new Promise(resolve => { settleQueued = resolve; }) });
    const queuedUrl = queuedChild.panels.get("architrave-session-companion").url;
    queuedChild.emit("subagent.configured", { model: "pending-config", reasoningEffort: "high" }, { agentId: "new-child" });
    queuedChild.emit("assistant.usage", { model: "pending-call", initiator: "sub-agent" }, { agentId: "new-child" });
    queuedChild.emit("session.background_tasks_changed");
    settleQueued({ tasks: [] });
    await new Promise(resolve => setImmediate(resolve));
    equal((await state(queuedUrl)).subagents.length, 0);
    equal(queuedChild.taskReads, 2);
    settleQueued({ tasks: [task] });
    await new Promise(resolve => setImmediate(resolve));
    child = (await state(queuedUrl)).subagents[0];
    equal(child.resolvedModel, "pending-config");
    equal(child.observedModel, "pending-call");
    equal(child.configuredEffort, "high");
    const prefs = join(home, "extensions", "architrave-ribbon", "artifacts", "preferences.json");
    await writeFile(prefs, '{"enabled":"not boolean"}');
    equal((await load("malformed-prefs")).opens.length, 0);
    await writeFile(prefs, " ".repeat(1025));
    equal((await load("oversized-prefs")).opens.length, 0);
    // Optional scoped renderer proof: synthetic host events, never represented as native telemetry.
    if (process.env.COMPANION_PREVIEW === "1" || process.env.COMPANION_VISUAL_OUTPUT) {
        await writeFile(prefs, '{"enabled":true}');
        const preview = await load("preview");
        preview.emit("assistant.turn_start");
        preview.emit("assistant.usage", { model: "Fixture model", reasoningEffort: "high" });
        preview.emit("session.usage_info", { currentTokens: 4200, tokenLimit: 32768, messagesLength: 4 });
        const previewUrl = preview.panels.get("architrave-session-companion").url;
        console.log("FIXTURE_PREVIEW=" + previewUrl);
        if (process.env.COMPANION_VISUAL_OUTPUT) {
            const args = [fileURLToPath(new URL("test-session-instrument.py", import.meta.url)),
                previewUrl, process.env.COMPANION_VISUAL_OUTPUT];
            if (process.env.COMPANION_BROWSER) args.push("--browser", process.env.COMPANION_BROWSER);
            const result = await new Promise((resolve, reject) => {
                const child = spawn(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
                    args, { stdio: "inherit" });
                child.once("error", reject); child.once("exit", resolve);
            });
            equal(result, 0);
        } else await new Promise(resolve => setTimeout(resolve, 180000));
    }
    console.log(`PASS session companion: ${checks} assertions (SDK fixture, not native-host proof)`);
} finally {
    for (const provider of providers) await provider.close();
    await rm(root, { recursive: true, force: true });
}
