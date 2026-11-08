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
const ok = (value, message) => { assert.ok(value, message || JSON.stringify(value)); assertions++; };
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
(r/'architrave.config.json').write_text(json.dumps({'kind':'knowledge','build':'git diff --check','test':'git diff --check','review':{'crossFamily':True},'workers':{'maxParallel':20}}))
git('add','.');git('commit','-qm','fixture')
s=RunStore(r)
s.create(run_id='review',goal='Source',outcome='Reviewed',criteria=[{'id':'QUAL','description':'Review source','scope':'fixture','risk':'R3','verificationType':'semantic','blocking':True}])
s.add_task('review',{'id':'source','objective':'Read source','acceptanceCriteria':['QUAL'],'workerProfile':'native','risk':'R3','pushback':'KEEP:fixture','workPacket':{'budget':{'timeoutSeconds':120,'maxOutputBytes':8192,'maxTurns':20}}})
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
                        current = { id, type: "agent", status: "running", prompt: args.prompt,
                            description: args.description };
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
    const context = vm.createContext({ Buffer, process, performance, setTimeout, clearTimeout });
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
    const alreadyAborted = new AbortController();
    alreadyAborted.abort();
    const neverStarted = JSON.parse((await definition.handler(args,
        { ...invocation, signal: alreadyAborted.signal })).textResultForLlm);
    ok(neverStarted.error?.code === "NATIVE_ABORTED" && count === 0 && tasks.size === 0);
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
    const startReviewer = taskRpc.startAgent;
    taskRpc.startAgent = async input => {
        await startReviewer(input);
        throw new Error("fixture: reviewer admission reply was lost");
    };
    const lostReviewer = JSON.parse((await definition.handler(args,
        { ...invocation, toolCallId: "lost-reviewer-admission" })).textResultForLlm);
    ok(lostReviewer.status === "failed" && lostReviewer.cleanup.confirmed === true && tasks.size === 0);
    taskRpc.startAgent = startReviewer;
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
    ok(count === 4);

    // REQ-97 bounded native dispatch. Fixture evidence only: the fake task RPC
    // simulates delayed, hung and lost host stages; this is not a live host.
    const dispatchRun = spawnSync(python, ["-c", `
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'harness'))
from architrave_runtime import RunStore
s=RunStore(Path(sys.argv[2]))
s.create(run_id='dispatch',goal='Bounded dispatch',outcome='Bounded',criteria=[{'id':'FIX','description':'d','scope':'fixture','risk':'R0','verificationType':'deterministic','blocking':True}])
for t in ['t1','t2','t3','t4','t5','t6','t7','t8','t9','t10','t11','t12','t13','t14','t15']:
    s.add_task('dispatch',{'id':t,'objective':'Read README','acceptanceCriteria':['FIX'],'workerProfile':'native','risk':'R0','pushback':'KEEP:fixture','maxAttempts':2,'workPacket':{'budget':{'timeoutSeconds':120 if t=='t15' else 3,'maxOutputBytes':800,'maxTurns':4}}})
`, ROOT, repo], { encoding: "utf8" });
    assert.equal(dispatchRun.status, 0, dispatchRun.stderr);
    const dispatchTool = options.tools.find(tool => tool.name === "architrave_native_dispatch");
    const batchTool = options.tools.find(tool => tool.name === "architrave_native_batch");
    const original = { ...taskRpc };
    const hang = () => new Promise(() => {});
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    // Preparation has its own 30 s bound; the 3 s worker lease does not include
    // checkout creation or the separate 5 s cancellation/persistence window.
    const dispatchBound = 30000 + 3000 + 5000;
    const call = async (tool, args, label, limit = dispatchBound + 2000, signal) => {
        const started = Date.now();
        let timer;
        const reply = await Promise.race([tool.handler(args, { sessionId: "owner-one", toolCallId: label, signal }),
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`TEST_TIMEOUT after ${limit}ms (${label})`)), limit); })])
            .finally(() => clearTimeout(timer));
        const value = JSON.parse(reply.textResultForLlm);
        return Array.isArray(value) ? { items: value, elapsed: Date.now() - started } : { ...value, elapsed: Date.now() - started };
    };
    const dispatch = async (task_id, label = task_id, extra = {}) => {
        return call(dispatchTool, { repo, run_id: "dispatch", task_id, ...extra }, label);
    };
    const retry = { retry_hypothesis: "Fixture: the previous host owner was reconciled, so a fresh start can complete." };
    const cancelPacket = async task_id => {
        return call(cancelDefinition, { repo, run_id: "dispatch", task_id }, `cancel-${task_id}`);
    };
    const blocked = value => value.status === "failed" && value.error?.code === "NATIVE_RECOVERY_PENDING";
    let agentNumber = 0;
    const running = async args => {
        const id = `dispatch-agent-${++agentNumber}`;
        tasks.set(id, { id, type: "agent", status: "running", prompt: args.prompt,
            name: args.name, description: args.description });
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
        try { await body(); } catch (error) { failures.push(`${name}: ${error.stack || error.message}`); }
        finally { Object.assign(taskRpc, original); }
    };
    const within = value => value.elapsed < dispatchBound + 1000;

    await scenario("fixture: hung startAgent is bounded at admission and retains recovery", async () => {
        let releaseStart;
        let attemptMarker;
        taskRpc.startAgent = args => {
            attemptMarker = args.description;
            return new Promise(resolve => { releaseStart = resolve; });
        };
        const first = await dispatch("t1");
        ok(first.status === "failed" && first.error?.stage === "admission" && within(first));
        ok(first.hostCancellationConfirmed === false);
        ok(blocked(await dispatch("t1", "t1-retry")));
        await assert.rejects(() => dispatchTool.handler(
            { repo, run_id: "dispatch", task_id: "t1" },
            { sessionId: "another-owner", toolCallId: "wrong-owner" }), /owner mismatch/); assertions++;
        await assert.rejects(() => dispatchTool.handler(
            { repo: join(root, "missing-repository"), run_id: "dispatch", task_id: "t1" },
            { sessionId: "owner-one", toolCallId: "wrong-repository" }), /ENOENT/); assertions++;
        const configPath = join(repo, "architrave.config.json");
        const config = JSON.parse(await readFile(configPath, "utf8"));
        config.workers.maxParallel = 1;
        await writeFile(configPath, JSON.stringify(config));
        let capacityError;
        try { await dispatch("t1-capacity-probe"); } catch (error) { capacityError = error; }
        ok(capacityError?.message.includes("CHILD_LIMIT"));
        tasks.set("late-t1", { id: "late-t1", type: "agent", status: "running", description: attemptMarker });
        releaseStart({ agentId: "late-t1" });
        taskRpc.startAgent = completing;
        let retried;
        for (let attempt = 0; attempt < 100; attempt++) {
            retried = await dispatch("t1", "t1-after-late-cleanup", retry);
            if (!blocked(retried)) break;
            await sleep(20);
        }
        ok(retried && !blocked(retried) && retried.hostTaskId, JSON.stringify(retried));
        ok(!tasks.has("late-t1"));
        config.workers.maxParallel = 20;
        await writeFile(configPath, JSON.stringify(config));
    });
    await scenario("fixture: late admission after an empty listing is retained and cleaned", async () => {
        let lateAdmitted;
        let attemptMarker;
        let cancelCalls = 0;
        let removeCalls = 0;
        let releaseCancel;
        let admissionStarted;
        const late = new Promise(resolve => { lateAdmitted = resolve; });
        const cancelGate = new Promise(resolve => { releaseCancel = resolve; });
        taskRpc.startAgent = args => {
            admissionStarted = Date.now();
            return new Promise(resolve => setTimeout(() => {
            attemptMarker = args.description;
            tasks.set("late-1", { id: "late-1", type: "agent", status: "running",
                prompt: args.prompt, description: args.description });
            resolve({ agentId: "late-1" });
            lateAdmitted();
            }, 5000));
        };
        const first = await dispatch("t2");
        ok(first.status === "failed" && first.error?.stage === "admission" &&
            Date.now() - admissionStarted < 4900, JSON.stringify(first));
        ok(!tasks.has("late-1") && first.hostCancellationConfirmed === false);
        ok(blocked(await dispatch("t2", "t2-retry")));
        taskRpc.cancel = async ({ id }) => {
            cancelCalls++;
            if (cancelCalls === 1) await cancelGate;
            if (tasks.has(id)) tasks.get(id).status = "cancelled";
            return { cancelled: true };
        };
        taskRpc.remove = async ({ id }) => {
            removeCalls++;
            tasks.delete(id);
            return { removed: true };
        };
        await Promise.race([late, sleep(15000).then(() => { throw new Error("TEST_TIMEOUT: late admission never fired"); })]);
        for (let attempt = 0; attempt < 100 && cancelCalls === 0; attempt++) await sleep(10);
        const lateCleanupStarted = Boolean(attemptMarker && cancelCalls === 1);
        const reconciliation = cancelPacket("t2");
        await sleep(50);
        const serialized = cancelCalls === 1 && removeCalls === 0;
        releaseCancel();
        const released = await reconciliation;
        ok(lateCleanupStarted && serialized);
        ok(released.status === "ok" && released.hostCancellationConfirmed && released.hostRemovalConfirmed);
        ok(cancelCalls === 1 && removeCalls === 1);
        ok(!tasks.has("late-1"));
        taskRpc.cancel = original.cancel;
        taskRpc.remove = original.remove;
        taskRpc.startAgent = completing;
        const retried = await dispatch("t2", "t2-after-late-cleanup", retry);
        ok(retried.hostTaskId && within(retried));
    });
    await scenario("fixture: overlapping dispatch and recovery retain exactly one lost-start owner", async () => {
        let starts = 0;
        let orphan;
        taskRpc.startAgent = async args => {
            starts++; ({ agentId: orphan } = await running(args)); throw new Error("fixture lost startAgent reply");
        };
        let listCalls = 0;
        let releaseLists;
        let bothListed;
        const listsGate = new Promise(resolve => { releaseLists = resolve; });
        const listed = new Promise(resolve => { bothListed = resolve; });
        taskRpc.list = async () => {
            if (++listCalls <= 2) {
                if (listCalls === 2) bothListed();
                await listsGate;
            }
            return original.list();
        };
        const calls = [dispatch("t3", "t3-first"), dispatch("t3", "t3-overlap")];
        await Promise.race([listed, sleep(2000).then(() => { throw new Error("TEST_TIMEOUT: overlapping listings never entered"); })]);
        releaseLists();
        const outcomes = await Promise.all(calls);
        taskRpc.list = original.list;
        const first = outcomes.find(value => value.error?.stage === "admission");
        ok(outcomes.filter(value => ["NATIVE_DISPATCH_ACTIVE", "NATIVE_RECOVERY_PENDING"].includes(value.error?.code)).length === 1,
            "overlapping dispatch must retain one owner instead of replacing its reservation");
        ok(first.status === "failed" && first.error?.stage === "admission" && first.hostCancellationConfirmed === false);
        ok(blocked(await dispatch("t3", "t3-retry")) && starts === 1 && tasks.has(orphan));
        const configPath = join(repo, "architrave.config.json");
        const config = JSON.parse(await readFile(configPath, "utf8"));
        config.workers.maxParallel = 1;
        await writeFile(configPath, JSON.stringify(config));
        taskRpc.list = async () => ({ tasks: [] });
        let capacityError;
        try { await dispatch("t3-capacity-probe"); } catch (error) { capacityError = error; }
        taskRpc.list = original.list;
        config.workers.maxParallel = 20;
        await writeFile(configPath, JSON.stringify(config));
        ok(capacityError?.message.includes("CHILD_LIMIT") && starts === 1);
        let cancelCalls = 0;
        let removeCalls = 0;
        let enteredCancel;
        let releaseCancel;
        const cancelEntered = new Promise(resolve => { enteredCancel = resolve; });
        const cancelGate = new Promise(resolve => { releaseCancel = resolve; });
        taskRpc.cancel = async args => {
            cancelCalls++;
            enteredCancel();
            await cancelGate;
            return original.cancel(args);
        };
        taskRpc.remove = async args => {
            removeCalls++;
            return original.remove(args);
        };
        const firstRecovery = cancelPacket("t3");
        await Promise.race([cancelEntered, sleep(2000).then(() => { throw new Error("TEST_TIMEOUT: recovery never reached cancel"); })]);
        const secondRecovery = cancelPacket("t3");
        releaseCancel();
        const [released, joined] = await Promise.all([firstRecovery, secondRecovery]);
        taskRpc.cancel = original.cancel;
        taskRpc.remove = original.remove;
        assert.equal(cancelCalls, 1, "concurrent reconciliations must share one cancellation"); assertions++;
        assert.equal(removeCalls, 1, "concurrent reconciliations must share one removal"); assertions++;
        ok(released.status === "ok" && released.ownerListing === "adopted" && released.recoveryOwner === orphan);
        ok(joined.status === "ok" && joined.ownerListing === "adopted" && joined.recoveryOwner === orphan);
        ok(joined.hostCancellationConfirmed && joined.hostRemovalConfirmed && joined.candidate);
        ok(released.hostCancellationConfirmed === true && released.cleanup?.confirmed === true && !tasks.has(orphan));
        taskRpc.startAgent = completing;
        const again = await dispatch("t3", "t3-again", retry);
        ok(!blocked(again) && again.hostTaskId && within(again), JSON.stringify(again));
    });
    await scenario("fixture: identical historical prompt is not adopted over attempt identity", async () => {
        let currentAttempt;
        const historical = { id: "historical-identical", type: "agent", status: "running",
            prompt: "same prompt", description: "older attempt" };
        tasks.set(historical.id, historical);
        taskRpc.startAgent = async args => {
            historical.status = "completed";
            historical.description = args.description;
            currentAttempt = "current-identical";
            tasks.set(currentAttempt, { id: currentAttempt, type: "agent", status: "running",
                prompt: args.prompt, description: args.description });
            throw new Error("fixture lost startAgent reply");
        };
        const first = await dispatch("t12");
        ok(first.error?.stage === "admission" && blocked(await dispatch("t12", "t12-retry")));
        const released = await cancelPacket("t12");
        ok(released.status === "ok" && released.recoveryOwner === currentAttempt);
        ok(released.hostCancellationConfirmed && released.hostRemovalConfirmed);
        ok(tasks.has("historical-identical") && !tasks.has(currentAttempt));
    });
    await scenario("fixture: empty reconcile listing does not prove a rejected start absent", async () => {
        let attemptMarker;
        taskRpc.startAgent = async args => { attemptMarker = args.description; throw new Error("fixture host rejected start"); };
        const first = await dispatch("t10");
        ok(first.status === "failed" && first.error?.stage === "admission" && first.cleanup?.confirmed === false);
        ok(blocked(await dispatch("t10", "t10-retry")));
        const released = await cancelPacket("t10");
        ok(blocked(released) && released.cleanup?.confirmed === false);
        ok(released.hostCancellationConfirmed === false && blocked(await dispatch("t10", "t10-again", retry)));
        tasks.set("late-t10", { id: "late-t10", type: "agent", status: "running", description: attemptMarker });
        const adopted = await cancelPacket("t10");
        ok(adopted.status === "ok" && adopted.recoveryOwner === "late-t10");
        ok(adopted.hostCancellationConfirmed && adopted.hostRemovalConfirmed);
    });
    await scenario("fixture: already aborted invocation never starts", async () => {
        let starts = 0;
        const controller = new AbortController();
        controller.abort();
        taskRpc.startAgent = async args => { starts++; return completing(args); };
        const stopped = await call(dispatchTool, { repo, run_id: "dispatch", task_id: "t13" },
            "aborted-before", 8000, controller.signal);
        ok(stopped.status === "failed" && starts === 0);
    });
    await scenario("fixture: abort during observation confirms cancel and remove separately", async () => {
        const controller = new AbortController();
        let owner;
        taskRpc.startAgent = async args => {
            ({ agentId: owner } = await running(args));
            setTimeout(() => controller.abort(), 150);
            return { agentId: owner };
        };
        const stopped = await call(dispatchTool, { repo, run_id: "dispatch", task_id: "t13" },
            "aborted-during", 20000, controller.signal);
        ok(stopped.status === "failed" && stopped.error?.code === "NATIVE_ABORTED");
        ok(stopped.hostCancellationConfirmed === true && stopped.hostRemovalConfirmed === true);
        ok(owner && !tasks.has(owner));
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
        taskRpc.startAgent = async () => ({ agentId: "ghost-t14" }); // Admitted id the host then cannot list.
        const first = await dispatch("t14");
        ok(first.status === "failed" && first.error?.code === "NATIVE_HOST_FAILED" && first.error?.stage === "observation");
        ok(first.hostCancellationConfirmed === true && first.cleanup?.confirmed === true && within(first));
        taskRpc.startAgent = completing;
        const again = await dispatch("t14", "t14-again", retry);
        ok(!blocked(again) && again.hostTaskId && within(again), JSON.stringify(again));
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
        ok(first.status === "failed" && first.error?.stage === "cleanup" && within(first), JSON.stringify(first));
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
    await scenario("fixture: hung remove defers persistence and preserves the observed result", async () => {
        taskRpc.startAgent = completing;
        taskRpc.remove = hang;
        const first = await dispatch("t6");
        ok(first.status === "failed" && first.error?.stage === "cleanup" && within(first), JSON.stringify(first));
        ok(!first.candidate && first.cleanup?.confirmed === false && first.recoveryOwner === first.hostTaskId);
        ok(first.hostCancellationConfirmed === true && first.hostRemovalConfirmed === false && tasks.has(first.hostTaskId));
        ok(blocked(await dispatch("t6", "t6-retry")));
        taskRpc.remove = original.remove;
        const adopted = await cancelPacket("t6");
        ok(adopted.adopted === true && adopted.candidate?.result?.status === "failed" &&
            adopted.candidate.result.observedHostStatus === "cancelled" && !tasks.has(first.hostTaskId),
            JSON.stringify(adopted));
        ok(adopted.candidate.result.summary === "Fixture result: README read." &&
            adopted.hostCancellationConfirmed === true && adopted.hostRemovalConfirmed === true);
    });
    await scenario("fixture: hung remove retains ownership and avoids redispatch before persistence", async () => {
        let starts = 0, cancels = 0, removals = 0;
        taskRpc.startAgent = async args => { starts++; return completing(args); };
        taskRpc.cancel = async args => { cancels++; return original.cancel(args); };
        taskRpc.remove = hang;
        const first = await dispatch("t7");
        ok(first.status === "failed" && first.error?.stage === "cleanup" && !first.candidate && within(first),
            JSON.stringify(first));
        ok(blocked(await dispatch("t7", "t7-retry")) && starts === 1 && cancels === 1);
        taskRpc.remove = async args => { removals++; return original.remove(args); };
        const adopted = await cancelPacket("t7");
        ok(adopted.adopted === true && adopted.candidate?.result?.status === "failed" &&
            adopted.candidate.result.observedHostStatus === "cancelled" &&
            adopted.cleanup?.confirmed === true && starts === 1 && cancels === 1 && removals === 1);
    });
    await scenario("fixture: one hung batch packet does not hold the other past the deadline", async () => {
        let releaseHung;
        let attemptMarker;
        taskRpc.startAgent = args => args.name.includes("t8") ?
            (attemptMarker = args.description, new Promise(resolve => { releaseHung = resolve; })) : completing(args);
        const batch = await call(batchTool, { repo, run_id: "dispatch", task_ids: ["t8", "t9"] }, "batch");
        ok(within(batch) && batch.items.length === 2, JSON.stringify(batch));
        ok(batch.items[0].status === "failed" && batch.items[0].error?.stage === "admission", JSON.stringify(batch));
        ok(batch.items[1].hostTaskId && batch.items[1].error?.stage !== "admission", JSON.stringify(batch));
        tasks.set("late-t8", { id: "late-t8", type: "agent", status: "running", description: attemptMarker });
        releaseHung({ agentId: "late-t8" });
        taskRpc.startAgent = completing;
        let retried;
        for (let attempt = 0; attempt < 100; attempt++) {
            retried = await dispatch("t8", "t8-after-late-cleanup", retry);
            if (!blocked(retried)) break;
            await sleep(20);
        }
        ok(retried && !blocked(retried) && retried.hostTaskId, JSON.stringify(retried));
        ok(!tasks.has("late-t8"));
    });
    await scenario("fixture: hung cleanup cannot borrow an unused long execution budget", async () => {
        let cleanupStarted;
        taskRpc.startAgent = completing;
        taskRpc.cancel = () => { cleanupStarted = Date.now(); return hang(); };
        const first = await dispatch("t15");
        ok(first.status === "failed" && first.error?.stage === "cleanup" &&
            cleanupStarted && Date.now() - cleanupStarted < 6500, JSON.stringify(first));
        ok(first.cleanup?.confirmed === false && first.hostCancellationConfirmed === false);
        taskRpc.cancel = original.cancel;
        const adopted = await cancelPacket("t15");
        ok(adopted.adopted === true && adopted.candidate?.result?.status === "candidate" &&
            adopted.candidate.result.observedHostStatus === "idle" &&
            adopted.cleanup?.confirmed === true && !tasks.has(first.hostTaskId), JSON.stringify(adopted));
    });
    for (const mode of ["abort", "deferred-abort", "timeout"]) {
        const deferred = mode === "deferred-abort";
        await scenario(`fixture: retained owner ${mode} persists cancellation without removal`, async () => {
            const run = `retained-${mode}`;
            const owner = `retained-owner-${mode}`;
            const seed = spawnSync(python, ["-c", `
import sys
sys.path.insert(0,sys.argv[1]+'/harness')
from architrave_runtime import RunStore
s=RunStore(sys.argv[2]);run=sys.argv[3];owner=sys.argv[4]
s.create(run_id=run,goal='Retained owner abort',outcome='Confirmed cancellation without removal',
 criteria=[{'id':'FIX','description':'d','scope':'fixture','risk':'R0','verificationType':'deterministic','blocking':True}])
s.add_task(run,{'id':'retained','objective':'Read README','acceptanceCriteria':['FIX'],'workerProfile':'native',
 'risk':'R0','pushback':'KEEP:fixture','maxAttempts':3,
 'workPacket':{'budget':{'timeoutSeconds':3,'maxOutputBytes':800,'maxTurns':4}}})
ticket=s.begin_native_worker(run,'retained',host_owner='owner-one')
s.bind_native_owner(ticket,owner)
s.accept_native_candidate(ticket,host_task_id=owner,host_status='cancelled',text='Previous retained turn cancelled')
`, ROOT, repo, run, owner], { encoding: "utf8" });
            assert.equal(seed.status, 0, seed.stderr);
            tasks.set(owner, { id: owner, type: "agent", status: "idle", prompt: "Previous retained turn" });
            const controller = new AbortController();
            let starts = 0, cancels = 0, removals = 0;
            taskRpc.startAgent = async args => { starts++; return completing(args); };
            taskRpc.sendMessage = async ({ id, message }) => {
                ok(id === owner);
                tasks.get(id).status = "running";
                tasks.get(id).prompt = message;
                return { sent: true };
            };
            taskRpc.list = async () => {
                const listing = await original.list();
                if (mode !== "timeout" && listing.tasks.some(task => task.id === owner && task.status === "running"))
                    queueMicrotask(() => controller.abort());
                return listing;
            };
            taskRpc.cancel = async args => {
                cancels++;
                return deferred ? { cancelled: false } : original.cancel(args);
            };
            taskRpc.remove = async args => { removals++; return original.remove(args); };
            const packet = { repo, run_id: run, task_id: "retained", owner_handle: owner, ...retry };
            const stopped = await call(dispatchTool, packet, run, dispatchBound + 2000, controller.signal);
            if (mode === "timeout") {
                ok(stopped.status === "failed" && stopped.timedOut === true && within(stopped), JSON.stringify(stopped));
                ok(stopped.result?.hostObservation.budgetStop === "time");
            } else {
                ok(stopped.error?.code === "NATIVE_ABORTED" && stopped.error?.stage === "observation" && within(stopped));
            }
            ok(stopped.hostCancellationConfirmed === !deferred && stopped.hostRemovalConfirmed === false);
            ok(tasks.has(owner) && removals === 0 && starts === 0);
            let receipt = mode === "timeout" ? stopped : stopped.candidate;
            if (deferred) {
                ok(stopped.cleanup?.confirmed === false && !receipt && tasks.get(owner).status === "running");
                ok(blocked(await call(dispatchTool, packet, `${run}-blocked`)));
                taskRpc.cancel = async args => { cancels++; return original.cancel(args); };
                const recovered = await call(cancelDefinition, { repo, run_id: run, task_id: "retained" }, `${run}-recover`);
                ok(recovered.status === "ok" && recovered.cleanup?.confirmed === true &&
                    recovered.hostCancellationConfirmed === true && recovered.hostRemovalConfirmed === false,
                    JSON.stringify(recovered));
                receipt = recovered.candidate;
            } else if (mode !== "timeout") {
                ok(stopped.cleanup?.confirmed === true, JSON.stringify(stopped));
            }
            ok(receipt?.result?.observedHostStatus === "cancelled" &&
                receipt.result.hostObservation.cancellationConfirmed === true &&
                receipt.result.hostObservation.removalConfirmed === false, JSON.stringify(receipt));
            ok(tasks.has(owner) && tasks.get(owner).status === "cancelled" &&
                starts === 0 && removals === 0 && cancels === (deferred ? 2 : 1));
            const canonical = spawnSync(python, ["-c", `
import sys
sys.path.insert(0,sys.argv[1]+'/harness')
from architrave_runtime import RunStore
s=RunStore(sys.argv[2]).load(sys.argv[3])
assert s['tasks'][0]['lease'] is None
expected='READY' if sys.argv[4]=='timeout' else 'FAILED'
assert s['tasks'][0]['status']==expected, s['tasks'][0]['status']
assert len(s['workers'])==2 and all(w['status']!='RUNNING' for w in s['workers'])
`, ROOT, repo, run, mode], { encoding: "utf8" });
            assert.equal(canonical.status, 0, canonical.stderr); assertions++;
            delete taskRpc.sendMessage;
        });
    }
    if (failures.length) {
        console.error(`FAIL native dispatch fixtures (${failures.length}); fixture root: ${root}\n${failures.join("\n")}`);
        process.exit(1);
    }
    console.log(`PASS native semantic SDK fixtures: ${assertions} assertions; not live host qualification`);
} catch (error) {
    console.error(error);
    throw error;
} finally {
    await rm(root, { recursive: true, maxRetries: 20, retryDelay: 100 });
}
