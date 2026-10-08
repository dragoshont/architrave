import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, copyFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import vm from "node:vm";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const root = await mkdtemp(join(tmpdir(), "native-semantic-sdk-"));
const trust = join(root, "trust");
const repo = join(root, "repo");
const sha = value => createHash("sha256").update(value).digest("hex");
const command = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const executable = spawnSync(command, ["-c", "import sys;from pathlib import Path;print(Path(sys.executable).resolve())"], { encoding: "utf8" });
assert.equal(executable.status, 0, executable.stderr);
const python = executable.stdout.trim();
let definition, hooks, current, count = 0;
const listeners = new Set();
const tasks = new Map();
let assertions = 0;
const ok = value => { assert.ok(value); assertions++; };
try {
    const setup = spawnSync(python, ["-c", `
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'harness'))
from architrave_runtime import RunStore
import subprocess
r=Path(sys.argv[2]);r.mkdir()
def git(*args):subprocess.run(['git',*args],cwd=r,check=True,capture_output=True)
git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
(r/'.gitignore').write_text('.architrave/\\n')
(r/'README.md').write_text('Public synthetic source\\n')
(r/'architrave.config.json').write_text(json.dumps({'kind':'knowledge','build':'git diff --check','test':'git diff --check','review':{'crossFamily':True}}))
git('add','.');git('commit','-qm','fixture')
s=RunStore(r)
s.create(run_id='review',goal='Source',outcome='Reviewed',criteria=[{'id':'QUAL','description':'Review source','scope':'fixture','risk':'R3','verificationType':'semantic','blocking':True}])
s.add_task('review',{'id':'source','objective':'Review source','acceptanceCriteria':['QUAL'],'workerProfile':'native','risk':'R3','pushback':'KEEP:fixture','workPacket':{'budget':{'timeoutSeconds':120,'maxOutputBytes':8192,'maxTurns':20}}})
`, ROOT, repo], { encoding: "utf8" });
    assert.equal(setup.status, 0, setup.stderr);
    await mkdir(join(trust, "harness"), { recursive: true });
    const files = {};
    const { readdir } = await import("node:fs/promises");
    for (const name of await readdir(join(ROOT, "harness"))) if (name.endsWith(".py")) {
        const destination = join(trust, "harness", name);
        await copyFile(join(ROOT, "harness", name), destination);
        files[destination] = sha(await readFile(destination));
    }
    await mkdir(join(trust, "gates"));
    const gate = join(trust, "gates", "gate_runner.py");
    await copyFile(join(ROOT, "gates", "gate_runner.py"), gate);
    files[gate] = sha(await readFile(gate));
    const source = await readFile(join(ROOT, "extensions", "architrave-native", "bridge.mjs"), "utf8");
    const entry = join(trust, "extension.mjs");
    await writeFile(entry, source);
    await writeFile(join(trust, "installation.json"), JSON.stringify({
        root: trust, version: "fixture", python, pythonSha256: sha(await readFile(python)),
        extensionSha256: sha(Buffer.from(source)), files,
    }));
    const emit = event => { for (const listener of listeners) listener(event); };
    const sdk = {
        joinSession: async config => {
            hooks = config.hooks;
            definition = config.tools.find(tool => tool.name === "architrave_native_review");
            return {
                sessionId: "owner-one", on: callback => { listeners.add(callback); return () => listeners.delete(callback); },
                rpc: { tasks: {
                    list: async () => ({ tasks: [...tasks.values()] }),
                    startAgent: async args => {
                        ok(!Object.hasOwn(args, "model"));
                        count++;
                        const id = `agent-${count}`;
                        const subject = JSON.parse(args.prompt.split("Bound subject:\n")[1]);
                        const report = { verdict: "PASS", criteria: subject.criteria,
                            sourceCommit: subject.source.commit, sourceSha256: subject.source.sha256,
                            challenge: subject.challenge, summary: "SDK fixture, not live evidence.", findings: [] };
                        current = { id, type: "agent", status: "running", prompt: args.prompt };
                        tasks.set(id, current);
                        ok(hooks.onPreToolUse({ toolName: "functions.powershell", toolArgs: {}, sessionId: "child" }, { sessionId: "owner-one" }).permissionDecision === "deny");
                        ok(hooks.onPreToolUse({ toolName: "evil.view", toolArgs: { path: join(repo, "README.md") }, sessionId: "child" }, { sessionId: "owner-one" }).permissionDecision === "deny");
                        ok(hooks.onPreToolUse({ toolName: "functions.view", toolArgs: { path: join(repo, ".architrave", "runtime.key") }, sessionId: "child" }, { sessionId: "owner-one" }).permissionDecision === "deny");
                        ok(hooks.onPreToolUse({ toolName: "functions.view", toolArgs: { path: join(repo, "README.md") }, sessionId: "child" }, { sessionId: "owner-one" }).modifiedArgs.path.endsWith("README.md"));
                        setTimeout(() => {
                            current.status = "idle"; current.latestResponse = JSON.stringify(report);
                            emit({ type: "subagent.completed", id: `completion-${count}`, agentId: id,
                                timestamp: new Date().toISOString(),
                                data: { toolCallId: id, agentName: args.agentType, firstDispatchedModel: args.agentType === "rubber-duck" ? "claude-fixture" : "gpt-fixture",
                                    modelSelectionSource: "fixture", cancelled: false } });
                            emit({ type: "session.background_tasks_changed" });
                        }, 30);
                        return { agentId: id };
                    },
                    cancel: async ({ id }) => { if (tasks.has(id)) tasks.get(id).status = "cancelled"; return { cancelled: true }; },
                    remove: async ({ id }) => { tasks.delete(id); return { removed: true }; },
                } },
            };
        },
    };
    const context = vm.createContext({ Buffer, process, setTimeout, clearTimeout });
    const module = new vm.SourceTextModule(source, {
        context, identifier: entry, initializeImportMeta: meta => { meta.url = new URL(`file:///${entry.replaceAll("\\", "/")}`).href; },
    });
    await module.link(async name => {
        const values = name === "@github/copilot-sdk/extension" ? sdk : await import(name);
        return new vm.SyntheticModule(Object.keys(values), function () {
            for (const [key, value] of Object.entries(values)) this.setExport(key, value);
        }, { context });
    });
    await module.evaluate();
    const args = { repo, run_id: "review", task_id: "source", reviewer: "rubber-duck" };
    const invocation = { sessionId: "owner-one", toolCallId: "call-one" };
    await assert.rejects(() => definition.handler({ ...args, firstDispatchedModel: "caller-claimed" }, invocation)); assertions++;
    ok(count === 0);
    const first = JSON.parse((await definition.handler(args, invocation)).textResultForLlm);
    ok(first.status === "ok" && first.result.verdict === "PASS" && first.result.family === "anthropic");
    ok(tasks.size === 0 && listeners.size === 0);
    const second = JSON.parse((await definition.handler({ ...args, reviewer: "code-review" }, { ...invocation, toolCallId: "call-two" })).textResultForLlm);
    ok(second.status === "ok" && second.result.family === "openai");
    const repeated = JSON.parse((await definition.handler(args, { ...invocation, toolCallId: "call-three" })).textResultForLlm);
    ok(repeated.error.code === "SEMANTIC_ALREADY_OBSERVED" && count === 2);
    const state = JSON.parse(await readFile(join(repo, ".architrave", "runs", "review", "run.json"), "utf8"));
    ok(state.artifacts.every(artifact => artifact.producer === "semantic-judge" && artifact.consumedByTask === "source"));
    ok(state.gateResults.filter(gate => gate.status === "PASS").length === 2);
    ok(state.acceptanceCriteria[0].status === "UNTESTED");
    console.log(`PASS native semantic SDK fixtures: ${assertions} assertions; not live host qualification`);
} finally {
    await rm(root, { recursive: true });
}
