import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, copyFile, rm, realpath } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import vm from "node:vm";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const root = await realpath(await mkdtemp(join(tmpdir(), "native-semantic-sdk-")));
const trust = join(root, "trust");
const repo = join(root, "repo");
const sha = value => createHash("sha256").update(value).digest("hex");
const command = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const executable = spawnSync(command, ["-c", "import sys;from pathlib import Path;print(Path(sys.executable).resolve())"], { encoding: "utf8" });
assert.equal(executable.status, 0, executable.stderr);
const python = executable.stdout.trim();
let definition, cancelDefinition, options, current, taskRpc, count = 0, failCleanup = true;
let conflictCompletion = false;
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
(r/'public').mkdir();(r/'public'/'example.md').write_text('Public tracked nested source\\n')
(r/'src').mkdir();(r/'src'/'sk-abcdefgh.py').write_text('Public filename fixture, not a credential\\n')
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
            options = config;
            ok(!Object.hasOwn(options, "hooks"));
            definition = config.tools.find(tool => tool.name === "architrave_native_review");
            cancelDefinition = config.tools.find(tool => tool.name === "architrave_native_cancel");
            return {
                sessionId: "owner-one", on: callback => { listeners.add(callback); return () => listeners.delete(callback); },
                rpc: { tasks: taskRpc = {
                    list: async () => ({ tasks: [...tasks.values()] }),
                    startAgent: async args => {
                        ok(!Object.hasOwn(args, "model"));
                        count++;
                        const id = `agent-${count}`;
                        const subject = JSON.parse(args.prompt.split("Bound subject:\n")[1].split("\nTracked regular source inventory")[0]);
                        const report = { verdict: "PASS", criteria: subject.criteria,
                            sourceCommit: subject.source.commit, sourceSha256: subject.source.sha256,
                            challenge: subject.challenge, summary: "SDK fixture, not live evidence.", findings: [] };
                        current = { id, type: "agent", status: "running", prompt: args.prompt };
                        tasks.set(id, current);
                        ok(!Object.hasOwn(options, "hooks"));
                        const inventory = JSON.parse(args.prompt.split(
                            "Tracked regular source inventory (no recursive glob or directory view; search only these files):\n")[1]);
                        ok(inventory.includes(join(repo, "README.md")));
                        ok(inventory.includes(join(repo, "src", "sk-abcdefgh.py")));
                        ok(inventory.every(path => !path.startsWith(join(repo, ".architrave") + sep) &&
                            !path.startsWith(join(repo, ".git") + sep)));
                        setTimeout(() => {
                            current.status = "idle"; current.latestResponse = JSON.stringify(report);
                            if (conflictCompletion) {
                                for (const suffix of ["one", "two"]) emit({ type: "subagent.completed",
                                    id: "conflict-" + suffix, agentId: id, timestamp: new Date().toISOString(),
                                    data: { toolCallId: id, agentName: args.agentType, firstDispatchedModel: "claude-fixture" } });
                                return;
                            }
                            emit({ type: "subagent.completed", id: `completion-${count}`, agentId: id,
                                timestamp: new Date().toISOString(),
                                data: { toolCallId: id, agentName: args.agentType, firstDispatchedModel: args.agentType === "rubber-duck" ? "claude-fixture" : "gpt-fixture",
                                    modelSelectionSource: "fixture", cancelled: false } });
                            emit({ type: "session.background_tasks_changed" });
                        }, 30);
                        return { agentId: id };
                    },
                    cancel: async ({ id }) => {
                        if (failCleanup) {
                            failCleanup = false;
                            tasks.get(id).status = "running";
                            throw new Error("fixture cleanup transport failure");
                        }
                        if (tasks.has(id)) tasks.get(id).status = "cancelled"; return { cancelled: true };
                    },
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
    assert.throws(() => module.namespace.semanticReviewPrompt("Bound subject", Array.from({ length: 4096 },
        (_, index) => join(repo, "source-" + index + "-" + "x".repeat(120) + ".py"))),
        error => error.message.includes("SEMANTIC_PROMPT_TOO_LARGE")); assertions++;
    ok(module.namespace.semanticReviewPrompt("Bound subject", [join(repo, "README.md")]).includes("README.md"));
    const args = { repo, run_id: "review", task_id: "source", reviewer: "rubber-duck" };
    const invocation = { sessionId: "owner-one", toolCallId: "call-one" };
    const remove = taskRpc.remove;
    delete taskRpc.remove;
    await assert.rejects(() => definition.handler(args, invocation),
        error => error.message.includes("tasks.remove")); assertions++;
    ok(count === 0 && tasks.size === 0 && listeners.size === 0);
    ok(!Object.hasOwn(options, "hooks"));
    taskRpc.remove = remove;
    await assert.rejects(() => definition.handler({ ...args, firstDispatchedModel: "caller-claimed" }, invocation)); assertions++;
    ok(count === 0);
    const first = JSON.parse((await definition.handler(args, invocation)).textResultForLlm);
    ok(first.status === "ok" && first.result.verdict === "PASS" && first.result.family === "anthropic");
    ok(first.cleanup.confirmed === false && first.recoveryOwner === "agent-1");
    ok(tasks.get("agent-1").status === "running");
    ok(!Object.hasOwn(options, "hooks"));
    const recovered = JSON.parse((await cancelDefinition.handler(args, invocation)).textResultForLlm);
    ok(recovered.cancelled === true);
    ok(!Object.hasOwn(options, "hooks"));
    ok(tasks.size === 0 && listeners.size === 0);
    const second = JSON.parse((await definition.handler({ ...args, reviewer: "code-review" }, { ...invocation, toolCallId: "call-two" })).textResultForLlm);
    ok(second.status === "ok" && second.result.family === "openai");
    const repeated = JSON.parse((await definition.handler(args, { ...invocation, toolCallId: "call-three" })).textResultForLlm);
    ok(repeated.error.code === "SEMANTIC_ALREADY_OBSERVED" && count === 2);
    const state = JSON.parse(await readFile(join(repo, ".architrave", "runs", "review", "run.json"), "utf8"));
    ok(state.artifacts.every(artifact => artifact.producer === "semantic-judge" && artifact.consumedByTask === "source"));
    ok(state.gateResults.filter(gate => gate.status === "PASS").length === 2);
    ok(state.acceptanceCriteria[0].status === "UNTESTED");
    const correction = spawnSync(python, ["-c", `
import sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/harness')
from architrave_runtime import RunStore
r=Path(sys.argv[2]); (r/'README.md').write_text('New frozen candidate\\n')
for args in [('add','README.md'),('commit','-qm','new candidate')]:
 subprocess.run(['git',*args],cwd=r,check=True,capture_output=True)
RunStore(r).resume('review',accept_commit=True)
`, ROOT, repo], { encoding: "utf8" });
    assert.equal(correction.status, 0, correction.stderr);
    conflictCompletion = true; failCleanup = true;
    const exceptional = JSON.parse((await definition.handler(args,
        { ...invocation, toolCallId: "exceptional-cleanup" })).textResultForLlm);
    ok(exceptional.error.code === "NATIVE_SEMANTIC_FAILED" && exceptional.cleanup.confirmed === false);
    ok(exceptional.recoveryOwner === "agent-3");
    ok(!Object.hasOwn(options, "hooks"));
    const exceptionRecovery = JSON.parse((await cancelDefinition.handler(args, invocation)).textResultForLlm);
    ok(exceptionRecovery.cancelled === true && tasks.size === 0);
    conflictCompletion = false;
    await mkdir(join(repo, "public", ".architrave"));
    await writeFile(join(repo, "public", ".architrave", "advertised-source.md"), "Synthetic unsupported public source fixture");
    const advertise = spawnSync(python, ["-c", `
import sys,subprocess
sys.path.insert(0,sys.argv[1]+'/harness')
from architrave_runtime import RunStore
r=sys.argv[2]
for args in [('add','-f','public/.architrave/advertised-source.md'),('commit','-qm','unsupported tracked fixture')]:
 subprocess.run(['git',*args],cwd=r,check=True,capture_output=True)
RunStore(r).resume('review',accept_commit=True)
`, ROOT, repo], { encoding: "utf8" });
    assert.equal(advertise.status, 0, advertise.stderr);
    const unsupported = JSON.parse((await definition.handler(args,
        { ...invocation, toolCallId: "unsupported-inventory" })).textResultForLlm);
    assert.ok(unsupported.status === "failed" && unsupported.error?.message.includes("SEMANTIC_SOURCE_UNSUPPORTED"),
        JSON.stringify(unsupported)); assertions++;
    ok(count === 3);

    // REQ-97 bounded native dispatch. Fixture evidence only: the fake task RPC
    // simulates delayed, hung and lost host stages; this is not a live host.
    const dispatchRun = spawnSync(python, ["-c", `
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'harness'))
from architrave_runtime import RunStore
s=RunStore(Path(sys.argv[2]))
s.create(run_id='dispatch',goal='Bounded dispatch',outcome='Bounded',criteria=[{'id':'FIX','description':'d','scope':'fixture','risk':'R0','verificationType':'deterministic','blocking':True}])
for t in ['t1','t2','t3','t4','t5','t6','t7','t8','t9','t10','t11','t12','t13']:
    s.add_task('dispatch',{'id':t,'objective':'Read README','acceptanceCriteria':['FIX'],'workerProfile':'native','risk':'R0','pushback':'KEEP:fixture','maxAttempts':2,'workPacket':{'budget':{'timeoutSeconds':3,'maxOutputBytes':800,'maxTurns':4}}})
`, ROOT, repo], { encoding: "utf8" });
    assert.equal(dispatchRun.status, 0, dispatchRun.stderr);
    const dispatchTool = options.tools.find(tool => tool.name === "architrave_native_dispatch");
    const batchTool = options.tools.find(tool => tool.name === "architrave_native_batch");
    const original = { ...taskRpc };
    const hang = () => new Promise(() => {});
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const call = async (tool, args, label, limit = 20000) => {
        const started = Date.now();
        let timer;
        const reply = await Promise.race([tool.handler(args, { sessionId: "owner-one", toolCallId: label }),
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`TEST_TIMEOUT after ${limit}ms (${label})`)), limit); })])
            .finally(() => clearTimeout(timer));
        const value = JSON.parse(reply.textResultForLlm);
        return Array.isArray(value) ? { items: value, elapsed: Date.now() - started } : { ...value, elapsed: Date.now() - started };
    };
    const dispatch = (task_id, label = task_id, extra = {}) => call(dispatchTool, { repo, run_id: "dispatch", task_id, ...extra }, label);
    const retry = { retry_hypothesis: "Fixture: the previous host owner was reconciled, so a fresh start can complete." };
    const cancelPacket = task_id => call(cancelDefinition, { repo, run_id: "dispatch", task_id }, `cancel-${task_id}`);
    const blocked = value => value.status === "failed" && value.error?.code === "NATIVE_RECOVERY_PENDING";
    let agentNumber = 0;
    const running = async args => {
        const id = `dispatch-agent-${++agentNumber}`;
        tasks.set(id, { id, type: "agent", status: "running", prompt: args.prompt });
        return { agentId: id };
    };
    const completing = async args => {
        const { agentId: id } = await running(args);
        setTimeout(() => {
            const task = tasks.get(id);
            if (!task) return;
            task.status = "idle"; task.latestResponse = "Fixture result: README read.";
            emit({ type: "subagent.completed", id: `completion-${id}`, agentId: id, timestamp: new Date().toISOString(),
                data: { toolCallId: id, agentName: args.agentType, firstDispatchedModel: "gpt-fixture", modelSelectionSource: "fixture", cancelled: false } });
            emit({ type: "session.background_tasks_changed" });
        }, 30);
        return { agentId: id };
    };
    const failures = [];
    const scenario = async (name, body) => {
        Object.assign(taskRpc, original);
        try { await body(); } catch (error) { failures.push(`${name}: ${error.message}`); }
        finally { Object.assign(taskRpc, original); }
    };
    const within = value => value.elapsed < 8000;

    await scenario("fixture: hung startAgent is bounded at admission and retains recovery", async () => {
        taskRpc.startAgent = hang;
        const first = await dispatch("t1");
        ok(first.status === "failed" && first.error?.stage === "admission" && within(first));
        ok(first.hostCancellationConfirmed === false);
        ok(blocked(await dispatch("t1", "t1-retry")));
    });
    await scenario("fixture: late admission after an empty listing is retained and cleaned", async () => {
        let lateAdmitted;
        const late = new Promise(resolve => { lateAdmitted = resolve; });
        taskRpc.startAgent = args => new Promise(resolve => setTimeout(() => {
            tasks.set("late-1", { id: "late-1", type: "agent", status: "running", prompt: args.prompt });
            resolve({ agentId: "late-1" });
            lateAdmitted();
        }, 5000));
        const first = await dispatch("t2");
        ok(first.status === "failed" && first.error?.stage === "admission" && first.elapsed < 4900);
        ok(!tasks.has("late-1") && first.hostCancellationConfirmed === false);
        ok(blocked(await dispatch("t2", "t2-retry")));
        await Promise.race([late, sleep(15000).then(() => { throw new Error("TEST_TIMEOUT: late admission never fired"); })]);
        await sleep(300); // Let the bridge's background settle cancel and remove the late owner.
        ok(!tasks.has("late-1"));
        const cancelled = await cancelPacket("t2");
        ok(cancelled.recoveryOwner === "late-1" && cancelled.cleanup?.confirmed === true);
    });
    await scenario("fixture: abort before binding adopts the orphan, then unblocks redispatch", async () => {
        let starts = 0;
        let orphan;
        taskRpc.startAgent = async args => {
            starts++; ({ agentId: orphan } = await running(args)); throw new Error("fixture lost startAgent reply");
        };
        const first = await dispatch("t3");
        ok(first.status === "failed" && first.error?.stage === "admission" && first.hostCancellationConfirmed === false);
        ok(blocked(await dispatch("t3", "t3-retry")) && starts === 1 && tasks.has(orphan));
        const released = await cancelPacket("t3");
        ok(released.status === "ok" && released.ownerListing === "adopted" && released.recoveryOwner === orphan);
        ok(released.hostCancellationConfirmed === true && released.cleanup?.confirmed === true && !tasks.has(orphan));
        taskRpc.startAgent = completing;
        const again = await dispatch("t3", "t3-again", retry);
        ok(!blocked(again) && again.hostTaskId && within(again));
    });
    await scenario("fixture: clean startAgent rejection is released by an empty reconcile listing", async () => {
        taskRpc.startAgent = async () => { throw new Error("fixture host rejected start"); };
        const first = await dispatch("t10");
        ok(first.status === "failed" && first.error?.stage === "admission" && first.cleanup?.confirmed === false);
        ok(blocked(await dispatch("t10", "t10-retry")));
        const released = await cancelPacket("t10");
        ok(released.status === "ok" && released.ownerListing === "empty" && released.cleanup?.confirmed === true);
        ok(released.hostCancellationConfirmed === false);
        taskRpc.startAgent = completing;
        const again = await dispatch("t10", "t10-again", retry);
        ok(!blocked(again) && again.hostTaskId && within(again));
    });
    await scenario("fixture: hung reconcile listing stays unconfirmed and blocked", async () => {
        taskRpc.startAgent = async args => { await running(args); throw new Error("fixture lost startAgent reply"); };
        const first = await dispatch("t11");
        ok(first.status === "failed" && first.error?.stage === "admission");
        taskRpc.list = hang;
        const stuck = await cancelPacket("t11");
        ok(blocked(stuck) && stuck.error?.stage === "cleanup" && stuck.cleanup?.confirmed === false && within(stuck));
        ok(stuck.hostCancellationConfirmed === false && /listing/.test(stuck.error?.message));
        ok(blocked(await dispatch("t11", "t11-retry")));
        taskRpc.list = original.list;
        const released = await cancelPacket("t11"); // Leave no fixture orphan behind.
        ok(released.status === "ok" && released.cleanup?.confirmed === true);
    });
    await scenario("fixture: a failure with confirmed cancel and remove releases the identity", async () => {
        taskRpc.startAgent = async () => ({ agentId: "ghost-t12" }); // Admitted id the host then cannot list.
        const first = await dispatch("t12");
        ok(first.status === "failed" && first.error?.code === "NATIVE_HOST_FAILED" && first.error?.stage === "observation");
        ok(first.hostCancellationConfirmed === true && first.cleanup?.confirmed === true && within(first));
        taskRpc.startAgent = completing;
        const again = await dispatch("t12", "t12-again", retry);
        ok(!blocked(again) && again.hostTaskId && within(again));
    });
    await scenario("fixture: hung preflight listing returns a preflight failure without retained identity", async () => {
        taskRpc.list = hang;
        const first = await call(dispatchTool, { repo, run_id: "dispatch", task_id: "t13" }, "t13", 40000);
        ok(first.status === "failed" && first.error?.code === "NATIVE_HOST_FAILED" && first.error?.stage === "preflight");
        ok(first.hostCancellationConfirmed === false && first.elapsed < 35000);
        taskRpc.list = original.list;
        taskRpc.startAgent = completing;
        const again = await dispatch("t13", "t13-again", retry);
        ok(!blocked(again) && again.hostTaskId && within(again));
    });
    await scenario("fixture: hung cancel after observation timeout is unconfirmed", async () => {
        taskRpc.startAgent = running;
        taskRpc.cancel = hang;
        const first = await dispatch("t4");
        ok(first.status === "failed" && first.error?.stage === "cleanup" && within(first));
        ok(first.hostCancellationConfirmed === false && first.recoveryOwner?.startsWith("dispatch-agent-"));
        ok(blocked(await dispatch("t4", "t4-retry")));
        taskRpc.cancel = original.cancel;
        const released = await cancelPacket("t4");
        ok(released.status === "ok" && released.hostCancellationConfirmed === true && released.cleanup?.confirmed === true);
    });
    await scenario("fixture: unconfirmed cancel is never reported as cancelled", async () => {
        taskRpc.startAgent = running;
        taskRpc.cancel = async () => ({ cancelled: false });
        const first = await dispatch("t5");
        ok(first.status === "failed" && first.hostCancellationConfirmed === false && within(first));
        ok(first.recoveryOwner?.startsWith("dispatch-agent-"));
        ok(blocked(await dispatch("t5", "t5-retry")));
        taskRpc.cancel = original.cancel;
        const released = await cancelPacket("t5");
        ok(released.status === "ok" && released.hostCancellationConfirmed === true && released.cleanup?.confirmed === true);
    });
    await scenario("fixture: hung remove after persistence retains and adopts the candidate", async () => {
        taskRpc.startAgent = completing;
        taskRpc.remove = hang;
        const first = await dispatch("t6");
        ok(first.status === "failed" && first.error?.stage === "cleanup" && within(first));
        ok(first.candidate && first.cleanup?.confirmed === false && first.recoveryOwner === first.hostTaskId);
        ok(blocked(await dispatch("t6", "t6-retry")));
        taskRpc.remove = original.remove;
        const adopted = await cancelPacket("t6");
        ok(adopted.adopted === true && adopted.candidate && !tasks.has(first.hostTaskId));
    });
    await scenario("fixture: hung persistence reply is bounded and adoption avoids redispatch", async () => {
        let starts = 0;
        taskRpc.startAgent = async args => { starts++; return completing(args); };
        taskRpc.remove = hang;
        const first = await dispatch("t7");
        ok(first.status === "failed" && within(first));
        taskRpc.remove = original.remove;
        const adopted = await cancelPacket("t7");
        ok(adopted.adopted === true && starts === 1);
    });
    await scenario("fixture: one hung batch packet does not hold the other past the deadline", async () => {
        taskRpc.startAgent = args => args.name.endsWith("t8") ? hang() : completing(args);
        const batch = await call(batchTool, { repo, run_id: "dispatch", task_ids: ["t8", "t9"] }, "batch");
        // Python per-packet preparation (worktree creation) runs one packet after the other in this fixture,
        // about 10 s for two packets with or without the hang, so the bound is one `within` window per packet.
        ok(batch.elapsed < 2 * 8000 && batch.items.length === 2);
        ok(batch.items[0].status === "failed" && batch.items[0].error?.stage === "admission");
        ok(batch.items[1].hostTaskId && batch.items[1].error?.stage !== "admission");
    });
    if (failures.length) {
        console.error(`FAIL native dispatch fixtures (${failures.length}):\n${failures.join("\n")}`);
        process.exit(1);
    }
    console.log(`PASS native semantic SDK fixtures: ${assertions} assertions; not live host qualification`);
} finally {
    await rm(root, { recursive: true });
}
