#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

import architrave_runtime as runtime_module
from architrave_runtime import RunStore


def load_installer_module():
    path = ROOT / "tools" / "install_update.py"
    spec = importlib.util.spec_from_file_location("architrave_install_update_focus", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load install_update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FocusControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp.name).resolve()
        self.repo = self.temp_root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "architrave@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Architrave Test"], cwd=self.repo, check=True)
        (self.repo / "existing-login.txt").write_text("working\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.store = RunStore(self.repo)
        self.runtime = ROOT / "harness" / "architrave_runtime.py"
        self.home = self.temp_root / "home"
        self.home.mkdir()
        self.cli_env = {
            **os.environ,
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
        }
        self.installer = load_installer_module()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create(
        self,
        outcome: str = "Prove the current product objective.",
        *,
        policy_allow: list[dict[str, object]] | None = None,
    ) -> str:
        arguments = [
            "run", "--goal", outcome, "--outcome", outcome, "--autonomy", "approved-program",
            "--criterion", f"ACCEPT-001|{outcome}|product|R1|deterministic",
        ]
        for grant in policy_allow or []:
            arguments.extend(["--allow", f"{grant['scope']}:{','.join(grant['operations'])}"])
        return self.cli(*arguments)["runId"]

    def cli(self, *arguments: str, expected: int = 0) -> dict[str, object]:
        process = subprocess.run(
            [sys.executable, str(self.runtime), "--repo", str(self.repo), *arguments],
            text=True,
            capture_output=True,
            check=False,
            env=self.cli_env,
        )
        self.assertEqual(expected, process.returncode, process.stdout + process.stderr)
        payload = json.loads(process.stdout if process.stdout.strip() else process.stderr)
        return payload.get("result") or payload.get("error") or {}

    def trusted_cli(self, *arguments: str, expected: int = 0) -> dict[str, object]:
        self.assertEqual("target-attest", arguments[0])
        parser = runtime_module.build_parser()
        parsed = parser.parse_args(["--repo", str(self.repo), *arguments])
        with mock.patch.object(
            runtime_module.RunStore,
            "_executor_registry_path",
            return_value=self.home / ".architrave" / "executors.json",
        ), mock.patch.object(
            runtime_module,
            "trusted_user_state_root",
            return_value=self.home / ".architrave",
        ):
            try:
                state = self.store.attest_target_identity_checkpoint(
                    parsed.run_id,
                    checkpoint_id=parsed.checkpoint_id,
                    challenge=parsed.challenge,
                    actor=parsed.actor,
                )
            except runtime_module.RuntimeFailure as exc:
                self.assertEqual(expected, exc.exit_code)
                return {"code": exc.code, "message": exc.message, "details": exc.details}
        self.assertEqual(expected, 0)
        return runtime_module.state_summary(state)

    def trusted_start(self, run_id: str, task_id: str, worker_id: str, *, expected: int = 0) -> dict[str, object]:
        with mock.patch.object(
            runtime_module.RunStore,
            "_executor_registry_path",
            return_value=self.home / ".architrave" / "executors.json",
        ), mock.patch.object(
            runtime_module,
            "trusted_user_state_root",
            return_value=self.home / ".architrave",
        ):
            try:
                state = self.store.start_task(run_id, task_id, worker_id=worker_id)
            except runtime_module.RuntimeFailure as exc:
                self.assertEqual(expected, exc.exit_code)
                return {"code": exc.code, "message": exc.message, "details": exc.details}
        self.assertEqual(expected, 0)
        return runtime_module.state_summary(state)

    def evidence(self, run_id: str, artifact_id: str = "baseline-evidence") -> str:
        path = self.store.run_dir(run_id) / "evidence" / f"{artifact_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"status": "pass", "exitCode": 0, "command": "synthetic fixture"}) + "\n",
            encoding="utf-8",
        )
        self.store._record_deterministic_result(
            run_id,
            artifact_id=artifact_id,
            path=path.resolve().relative_to(self.store.repository).as_posix(),
            evidence_refs=[],
        )
        return f"artifact:{artifact_id}"

    def target_evidence(
        self,
        run_id: str,
        checkpoint_id: str,
        challenge: str,
        intended: dict[str, str],
        observed: dict[str, str],
        artifact_id: str,
    ) -> str:
        state = self.store.load(run_id)
        checkpoint = next(item for item in state["externalCheckpoints"] if item["id"] == checkpoint_id)
        path = self.store.run_dir(run_id) / "evidence" / f"{artifact_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "checkpointId": checkpoint_id,
                    "runId": run_id,
                    "objectiveVersion": state["objective"]["version"],
                    "taskId": checkpoint["taskId"],
                    "provider": checkpoint["provider"],
                    "principal": checkpoint["principal"],
                    "actor": checkpoint["principal"],
                    "challengeHash": hashlib.sha256(challenge.encode("utf-8")).hexdigest(),
                    "intended": intended,
                    "observed": observed,
                }
            ) + "\n",
            encoding="utf-8",
        )
        self.store._record_external_proof(
            run_id,
            artifact_id=artifact_id,
            path=path.resolve().relative_to(self.store.repository).as_posix(),
            evidence_refs=[],
        )
        return f"artifact:{artifact_id}"

    def add_task(self, run_id: str, task_id: str, **overrides: object) -> dict[str, object]:
        arguments = [
            "task-add", run_id, "--id", task_id, "--title", task_id,
            "--objective", f"Complete {task_id}.", "--criteria",
            ",".join(overrides.get("acceptanceCriteria", ["ACCEPT-001"])),
            "--worker", "shell",
        ]
        if overrides.get("workKind"):
            arguments.extend(["--work-kind", str(overrides["workKind"])])
        if overrides.get("lane"):
            arguments.extend(["--lane", str(overrides["lane"])])
        if overrides.get("changeKind"):
            arguments.extend(["--change-kind", str(overrides["changeKind"])])
        if overrides.get("isMinimalAcceptanceTest"):
            arguments.append("--minimal-test")
        if overrides.get("largeChange"):
            arguments.append("--large-change")
        if overrides.get("sideEffect"):
            side_effect = overrides["sideEffect"]
            arguments.extend(["--side-effect", f"{side_effect['operation']}@{side_effect['target']}"])
        if overrides.get("targetIdentity"):
            arguments.extend(["--target-json", json.dumps(overrides["targetIdentity"])])
        return self.cli(*arguments)

    def target_wait(
        self,
        *,
        provider: str = "provider-a",
        principal: str = "synthetic-user",
        suffix: str = "",
    ) -> tuple[str, str, dict[str, str], Path]:
        artifact = self.temp_root / f"target{suffix}.bin"
        artifact.write_bytes(f"trusted target {suffix}".encode("utf-8"))
        intended = {
            "provider": provider,
            "artifact": f"target{suffix}.bin",
            "version": "2",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "environment": "test",
            "workspace": str(self.temp_root / f"prefix{suffix}"),
            "acceptanceTarget": "exact local target",
        }
        run_id = self.create(
            "Verify an exact trusted target.",
            policy_allow=[{"scope": provider, "operations": ["launch"]}],
        )
        task_id = f"target-task{suffix}"
        self.add_task(
            run_id,
            task_id,
            sideEffect={"operation": "launch", "target": provider},
            targetIdentity=intended,
            isMinimalAcceptanceTest=True,
        )
        checkpoint_id = f"target-check{suffix}"
        wait = self.cli(
            "external-wait",
            run_id,
            "--id",
            checkpoint_id,
            "--task-id",
            task_id,
            "--type",
            "SAFE_WRITE_TARGET_REQUIRED",
            "--principal",
            principal,
            "--provider",
            provider,
            "--reason",
            "Observe exact target.",
        )
        return run_id, str(wait["resolutionChallenge"]), intended, artifact

    def install_executor(self, intended: dict[str, str], artifact: Path) -> None:
        args = argparse.Namespace(
            provider=intended["provider"],
            artifact=intended["artifact"],
            artifact_path=str(artifact),
            version=intended["version"],
            sha256=intended["sha256"],
            environment=intended["environment"],
            workspace=intended["workspace"],
            acceptance_target=intended["acceptanceTarget"],
            workspace_mode="absent-or-exact-directory",
            timeout_seconds=1,
            ssh_host=None,
            ssh_host_key_alias=None,
            ssh_port=22,
            ssh_user=None,
            ssh_executable=None,
            ssh_identity=None,
            ssh_known_hosts=None,
            ssh_remote_python=None,
            ssh_remote_adapter=None,
            ssh_remote_adapter_sha256=None,
            reconcile_run_id=None,
            reconcile_task_id=None,
            reconcile_operation=None,
            reconcile_target=None,
            reconcile_outcome=None,
            reconcile_process_id=None,
        )
        with mock.patch.object(
            self.installer,
            "trusted_user_state_root",
            return_value=self.home / ".architrave",
        ):
            self.assertEqual(0, self.installer.install_exact_target_executor(args, ROOT))

    def install_reconciliation(
        self,
        run_id: str,
        task_id: str,
        operation: str,
        target: str,
        outcome: str,
        artifact: Path,
        workspace: Path,
    ) -> None:
        intended = {
            "provider": f"reconciliation:{task_id}",
            "artifact": artifact.name,
            "version": outcome,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "environment": "historical-test",
            "workspace": str(workspace),
            "acceptanceTarget": f"{operation} {outcome}",
        }
        args = argparse.Namespace(
            provider=intended["provider"],
            artifact=intended["artifact"],
            artifact_path=str(artifact),
            version=intended["version"],
            sha256=intended["sha256"],
            environment=intended["environment"],
            workspace=intended["workspace"],
            acceptance_target=intended["acceptanceTarget"],
            workspace_mode="exact-directory",
            timeout_seconds=1,
            ssh_host=None,
            ssh_host_key_alias=None,
            ssh_port=22,
            ssh_user=None,
            ssh_executable=None,
            ssh_identity=None,
            ssh_known_hosts=None,
            ssh_remote_python=None,
            ssh_remote_adapter=None,
            ssh_remote_adapter_sha256=None,
            reconcile_run_id=run_id,
            reconcile_task_id=task_id,
            reconcile_operation=operation,
            reconcile_target=target,
            reconcile_outcome=outcome,
            reconcile_process_id=2147483647,
        )
        with mock.patch.object(
            self.installer,
            "trusted_user_state_root",
            return_value=self.home / ".architrave",
        ):
            self.assertEqual(0, self.installer.install_exact_target_executor(args, ROOT))

    def registry(self) -> tuple[Path, dict[str, object]]:
        path = self.home / ".architrave" / "executors.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def write_registry(self, path: Path, registry: dict[str, object]) -> None:
        path.write_text(json.dumps(registry, separators=(",", ":")) + "\n", encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)

    def test_existing_working_login_blocks_diagnostic_redesign(self) -> None:
        run_id = self.create("Keep the existing working login and verify the smallest difference.")
        error = self.cli(
            "task-add", run_id, "--id", "replacement", "--title", "replacement",
            "--objective", "Replace the existing login.", "--criteria", "ACCEPT-001",
            "--change-kind", "replacement-architecture", "--large-change",
            expected=1,
        )
        self.assertEqual("REUSE_FIRST_REQUIRED", error["code"])
        difference = "Compare the existing login response with the requested acceptance state."
        self.cli(
            "reuse-verify", run_id, "--path", "existing-login.txt",
            "--difference", difference, "--test-command", sys.executable, "-c",
            "from pathlib import Path; assert Path('existing-login.txt').read_text().strip() == 'working'",
        )
        self.add_task(
            run_id,
            "minimal-login-test",
            workKind="diagnostic",
            isMinimalAcceptanceTest=True,
            changeKind="replacement-architecture",
        )
        self.add_task(run_id, "diagnostic-framework", workKind="diagnostic", largeChange=True)
        state = self.store.load(run_id)
        framework = next(task for task in state["tasks"] if task["id"] == "diagnostic-framework")
        self.assertEqual("DEFERRED", framework["status"])

    def test_correction_keeps_product_objective_and_defers_bridge_lane(self) -> None:
        run_id = self.create("Run the requested free-engine game acceptance test.")
        self.add_task(run_id, "game-test", isMinimalAcceptanceTest=True)
        self.add_task(run_id, "communications-bridge", workKind="communications", lane="bridge")
        self.add_task(run_id, "bridge-on-product-lane", workKind="communications", lane="product")
        wait = self.cli(
            "external-wait", run_id, "--id", "objective-correction", "--task-id", "game-test",
            "--type", "HUMAN_JUDGMENT_REQUIRED", "--principal", "synthetic-user",
            "--provider", "user-direction", "--reason", "Replace the objective.",
        )
        self.cli(
            "objective-replace", run_id,
            "--outcome", "Run the requested free-engine game acceptance test on the intended build.",
            "--criterion", "GAME-001|The intended game build passes its minimal launch test.|game|R1|deterministic",
            "--correction", "Stay focused; you lost my ask and do not drift into bridge work.",
            "--next-test", "Launch the intended build once and record the result.",
            "--checkpoint-id", "objective-correction", "--challenge", str(wait["resolutionChallenge"]),
            "--actor", "human:synthetic-user",
        )
        state = self.store.load(run_id)
        self.assertEqual(2, state["objective"]["version"])
        self.assertEqual(["product"], [lane["id"] for lane in state["lanes"]["active"]])
        bridge = next(task for task in state["tasks"] if task["id"] == "communications-bridge")
        self.assertEqual("DEFERRED", bridge["status"])
        product_bridge = next(task for task in state["tasks"] if task["id"] == "bridge-on-product-lane")
        self.assertEqual("DEFERRED", product_bridge["status"])
        self.assertNotIn("product", {lane["id"] for lane in state["lanes"]["deferred"]})
        checkpoint = self.store.human_checkpoint(run_id)
        self.assertEqual("Launch the intended build once and record the result.", checkpoint["nextCheapestTest"])
        self.assertEqual({"product"}, set(checkpoint["activeLanes"]))

    def test_legacy_target_resolve_cannot_consume_private_external_proof(self) -> None:
        run_id = self.create(
            "Test the intended provider build.",
            policy_allow=[{"scope": "provider-a", "operations": ["launch"]}],
        )
        intended = {
            "provider": "provider-a",
            "artifact": "game.exe",
            "version": "2",
            "sha256": "a" * 64,
            "environment": "test",
            "workspace": "workspace-a",
            "acceptanceTarget": "provider-a game launch",
        }
        self.add_task(
            run_id,
            "launch-intended-build",
            sideEffect={"operation": "launch", "target": "provider-a"},
            targetIdentity=intended,
            isMinimalAcceptanceTest=True,
        )
        task = next(task for task in self.store.load(run_id)["tasks"] if task["id"] == "launch-intended-build")
        self.assertEqual(["launch"], task["operations"])
        wait = self.cli(
            "external-wait", run_id, "--id", "target-check", "--task-id", "launch-intended-build",
            "--type", "SAFE_WRITE_TARGET_REQUIRED", "--principal", "synthetic-user",
            "--provider", "provider-a", "--reason", "Confirm target identity.",
        )
        private_proof = self.target_evidence(
            run_id,
            "target-check",
            str(wait["resolutionChallenge"]),
            intended,
            intended,
            "private-target-proof",
        )
        rejected = self.cli(
            "target-resolve", run_id, "--checkpoint-id", "target-check",
            "--challenge", str(wait["resolutionChallenge"]), "--intended-json", json.dumps(intended),
            "--evidence", private_proof, "--actor", "human:synthetic-user", expected=1,
        )
        self.assertEqual("TRUSTED_EXECUTOR_REQUIRED", rejected["code"])
        state = self.store.load(run_id)
        checkpoint = next(item for item in state["externalCheckpoints"] if item["id"] == "target-check")
        self.assertEqual("PENDING", checkpoint["status"])
        blocked = self.cli(
            "task-start", run_id, "launch-intended-build", "--worker-id", "launcher",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_REQUIRED", blocked["code"])
        with mock.patch("architrave_runtime.secrets.token_urlsafe", return_value="-formerly-leading"):
            challenge = "arc_" + runtime_module.secrets.token_urlsafe(32)
        self.assertEqual("arc_-formerly-leading", challenge)

    def test_public_checkpoint_renew_rotates_unconsumed_target_challenge(self) -> None:
        run_id, old_challenge, intended, artifact = self.target_wait(suffix="-renew")
        self.install_executor(intended, artifact)
        before = self.store.load(run_id)
        old_checkpoint = next(
            item for item in before["externalCheckpoints"] if item["id"] == "target-check-renew"
        )
        with mock.patch("architrave_runtime.secrets.token_urlsafe", return_value="renewed"):
            renewed, new_challenge = self.store.renew_target_checkpoint(
                run_id,
                checkpoint_id="target-check-renew",
                actor="human:synthetic-user",
            )
        self.assertEqual("arc_renewed", new_challenge)
        new_checkpoint = next(
            item for item in renewed["externalCheckpoints"] if item["id"] == "target-check-renew"
        )
        self.assertNotEqual(old_checkpoint["challengeHash"], new_checkpoint["challengeHash"])
        self.assertNotEqual(old_checkpoint["targetBindingHash"], new_checkpoint["targetBindingHash"])
        old = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-renew",
            "--challenge",
            old_challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", old["code"])
        renewed_result = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-renew",
            "--challenge",
            new_challenge,
            "--actor",
            "human:synthetic-user",
        )
        self.assertEqual([], renewed_result["pendingExternal"])
        denied = self.cli(
            "checkpoint-renew",
            run_id,
            "target-check-renew",
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("CHECKPOINT_RENEWAL_DENIED", denied["code"])

    def test_public_target_attest_uses_pinned_external_executor_and_consumes_once(self) -> None:
        run_id, challenge, intended, artifact = self.target_wait(suffix="-valid")
        self.add_task(
            run_id,
            "same-target-other-task",
            sideEffect={"operation": "launch", "target": intended["provider"]},
            targetIdentity=intended,
        )
        self.install_executor(intended, artifact)
        result = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-valid",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
        )
        self.assertEqual("VERIFIED", self.store.load(run_id)["targetIdentity"]["status"])
        self.assertEqual([], result["pendingExternal"])
        proof = next(item for item in self.store.load(run_id)["artifacts"] if item["producer"] == "external-proof")
        self.assertEqual("target-task-valid", proof["consumedByTask"])
        wrong_task = self.cli(
            "task-start",
            run_id,
            "same-target-other-task",
            "--worker-id",
            "wrong-task-worker",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_REQUIRED", wrong_task["code"])
        self.trusted_start(run_id, "target-task-valid", "verified-worker")
        replay = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-valid",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", replay["code"])

    def test_public_target_attest_invalidates_on_transition_or_artifact_change(self) -> None:
        stale_run, stale_challenge, stale_intended, stale_artifact = self.target_wait(suffix="-stale")
        self.install_executor(stale_intended, stale_artifact)
        self.trusted_cli(
            "target-attest",
            stale_run,
            "--checkpoint-id",
            "target-check-stale",
            "--challenge",
            stale_challenge,
            "--actor",
            "human:synthetic-user",
        )
        self.add_task(stale_run, "intervening-task")
        stale = self.cli(
            "task-start",
            stale_run,
            "target-task-stale",
            "--worker-id",
            "stale-worker",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_REQUIRED", stale["code"])

        changed_run, changed_challenge, changed_intended, changed_artifact = self.target_wait(suffix="-changed")
        self.install_executor(changed_intended, changed_artifact)
        self.trusted_cli(
            "target-attest",
            changed_run,
            "--checkpoint-id",
            "target-check-changed",
            "--challenge",
            changed_challenge,
            "--actor",
            "human:synthetic-user",
        )
        changed_artifact.write_bytes(b"changed after attestation")
        changed = self.trusted_start(changed_run, "target-task-changed", "changed-worker", expected=1)
        self.assertEqual("EXECUTOR_FAILED", changed["code"])

        workspace_run, workspace_challenge, workspace_intended, workspace_artifact = self.target_wait(suffix="-workspace")
        self.install_executor(workspace_intended, workspace_artifact)
        self.trusted_cli(
            "target-attest",
            workspace_run,
            "--checkpoint-id",
            "target-check-workspace",
            "--challenge",
            workspace_challenge,
            "--actor",
            "human:synthetic-user",
        )
        workspace = Path(workspace_intended["workspace"])
        external = self.temp_root / "external-workspace"
        external.mkdir()
        if os.name == "nt":
            completed = subprocess.run(
                [os.environ.get("ComSpec", "cmd.exe"), "/c", "mklink", "/J", str(workspace), str(external)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                self.skipTest(f"directory junctions are unavailable: {completed.stderr!r}")
        else:
            os.symlink(external, workspace, target_is_directory=True)
        workspace_changed = self.trusted_start(
            workspace_run,
            "target-task-workspace",
            "workspace-worker",
            expected=1,
        )
        self.assertEqual("EXECUTOR_FAILED", workspace_changed["code"])

    def test_public_target_attest_rejects_forgery_modified_pin_and_binding_mismatches(self) -> None:
        run_id, challenge, intended, artifact = self.target_wait(suffix="-security")
        self.install_executor(intended, artifact)
        registry_path, registry = self.registry()
        exact = registry["exactTarget"]
        adapter = Path(exact["adapter"])

        forged = self.repo / "forged-observer.py"
        shutil.copyfile(adapter, forged)
        exact["adapter"] = str(forged)
        exact["adapterSha256"] = hashlib.sha256(forged.read_bytes()).hexdigest()
        self.write_registry(registry_path, registry)
        error = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_TRUST_ROOT_INVALID", error["code"])

        self.install_executor(intended, artifact)
        _, registry = self.registry()
        adapter = Path(registry["exactTarget"]["adapter"])
        adapter.write_text(adapter.read_text(encoding="utf-8") + "\n# modified\n", encoding="utf-8")
        error = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_PIN_MISMATCH", error["code"])

        self.install_executor(intended, artifact)
        wrong_actor = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:other-user",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", wrong_actor["code"])
        wrong_challenge = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            "arc_wrong",
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", wrong_challenge["code"])

        registry_path, registry = self.registry()
        registry["exactTarget"]["allowedProviders"] = ["provider-b"]
        self.write_registry(registry_path, registry)
        wrong_provider = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_NOT_ALLOWED", wrong_provider["code"])

        self.install_executor(intended, artifact)
        registry_path, registry = self.registry()
        registry["exactTarget"]["targets"][0]["identity"]["version"] = "stale"
        self.write_registry(registry_path, registry)
        wrong_identity = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_TARGET_NOT_TRUSTED", wrong_identity["code"])

        self.install_executor(intended, artifact)
        registry_path, registry = self.registry()
        adapter = self.home / ".architrave" / "executors" / "wrong-observation.py"
        adapter.write_text(
            "import hashlib,json,pathlib,sys\n"
            "request=json.load(sys.stdin)\n"
            "observed=dict(request['intended']); observed['version']='wrong'\n"
            "observation={'artifactPath':request['target']['artifactPath'],'artifactSha256':request['intended']['sha256'],"
            "'artifactSize':1,'workspacePath':request['intended']['workspace'],'workspaceState':'absent',"
            "'observerSha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'transport':'local'}\n"
            "print(json.dumps({'schema':'architrave.exact-target-result.v1','status':'observed',"
            "'binding':request['binding'],'observed':observed,'observation':observation}))\n",
            encoding="utf-8",
        )
        adapter.write_text(
            adapter.read_text(encoding="utf-8").replace(",'extra':'forged'", ""),
            encoding="utf-8",
        )
        adapter.write_text(
            adapter.read_text(encoding="utf-8").replace(",'extra':'forged'", ""),
            encoding="utf-8",
        )
        registry["exactTarget"]["adapter"] = str(adapter)
        registry["exactTarget"]["adapterSha256"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
        self.write_registry(registry_path, registry)
        wrong_observation = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_MISMATCH", wrong_observation["code"])
        checkpoint = next(
            item
            for item in self.store.load(run_id)["externalCheckpoints"]
            if item["id"] == "target-check-security"
        )
        self.assertEqual("PENDING", checkpoint["status"])

        adapter.write_text(adapter.read_text(encoding="utf-8").replace(
            "'transport':'local'",
            "'transport':'local','extra':'forged'",
        ), encoding="utf-8")
        registry["exactTarget"]["adapterSha256"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
        self.write_registry(registry_path, registry)
        extra_observation = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_RESULT_INVALID", extra_observation["code"])

        contradictory = self.home / ".architrave" / "executors" / "contradictory-observation.py"
        contradictory.write_text(
            "import hashlib,json,pathlib,sys\n"
            "request=json.load(sys.stdin)\n"
            "observation={'artifactPath':request['target']['artifactPath'],'artifactSha256':'0'*64,"
            "'artifactSize':1,'workspacePath':request['intended']['workspace'],'workspaceState':'absent',"
            "'observerSha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'transport':'local'}\n"
            "print(json.dumps({'schema':'architrave.exact-target-result.v1','status':'observed',"
            "'binding':request['binding'],'observed':request['intended'],'observation':observation}))\n",
            encoding="utf-8",
        )
        registry["exactTarget"]["adapter"] = str(contradictory)
        registry["exactTarget"]["adapterSha256"] = hashlib.sha256(contradictory.read_bytes()).hexdigest()
        self.write_registry(registry_path, registry)
        contradictory_observation = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_RESULT_INVALID", contradictory_observation["code"])

        adapter.write_text(
            adapter.read_text(encoding="utf-8").replace(",'extra':'forged'", ""),
            encoding="utf-8",
        )
        registry["exactTarget"]["adapter"] = str(adapter)
        registry["exactTarget"]["adapterSha256"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
        next(
            target
            for target in registry["exactTarget"]["targets"]
            if target["identity"] == intended
        )["workspaceMode"] = "exact-directory"
        self.write_registry(registry_path, registry)
        impossible_absent_workspace = self.trusted_cli(
            "target-attest",
            run_id,
            "--checkpoint-id",
            "target-check-security",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("EXECUTOR_RESULT_INVALID", impossible_absent_workspace["code"])

        other_run, other_challenge, other_intended, other_artifact = self.target_wait(suffix="-other")
        self.install_executor(other_intended, other_artifact)
        cross_task = self.trusted_cli(
            "target-attest",
            other_run,
            "--checkpoint-id",
            "target-check-other",
            "--challenge",
            challenge,
            "--actor",
            "human:synthetic-user",
            expected=1,
        )
        self.assertEqual("TARGET_IDENTITY_INVALID", cross_task["code"])
        self.assertNotEqual(challenge, other_challenge)

    def test_public_target_attest_rejects_timeout_malformed_and_oversize_output(self) -> None:
        cases = {
            "timeout": "import time; time.sleep(5)\n",
            "malformed": "print('not-json')\n",
            "oversize": "print('x' * 70000)\n",
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                run_id, challenge, intended, artifact = self.target_wait(suffix=f"-{name}")
                self.install_executor(intended, artifact)
                registry_path, registry = self.registry()
                adapter = self.home / ".architrave" / "executors" / f"{name}.py"
                adapter.write_text(source, encoding="utf-8")
                registry["exactTarget"]["adapter"] = str(adapter)
                registry["exactTarget"]["adapterSha256"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
                self.write_registry(registry_path, registry)
                error = self.trusted_cli(
                    "target-attest",
                    run_id,
                    "--checkpoint-id",
                    f"target-check-{name}",
                    "--challenge",
                    challenge,
                    "--actor",
                    "human:synthetic-user",
                    expected=1,
                )
                expected = {
                    "timeout": "EXECUTOR_TIMEOUT",
                    "malformed": "EXECUTOR_RESULT_INVALID",
                    "oversize": "EXECUTOR_OUTPUT_OVERSIZE",
                }[name]
                self.assertEqual(expected, error["code"])

    def test_public_reconcile_attest_preserves_applied_closed_and_closed_unknown(self) -> None:
        for suffix, outcome, expected_state in (
            ("applied", "applied-closed", "CONFIRMED"),
            ("unknown", "closed-unknown", "NONE"),
        ):
            with self.subTest(outcome=outcome):
                operation = "publish" if outcome == "applied-closed" else "input"
                run_id = self.create(
                    f"Reconcile historical side effect {outcome}.",
                    policy_allow=[{"scope": "historical-resource", "operations": [operation]}],
                )
                task_id = f"historical-{suffix}"
                self.add_task(
                    run_id,
                    task_id,
                    sideEffect={"operation": operation, "target": "historical-resource"},
                )
                self.cli("task-start", run_id, task_id, "--worker-id", f"worker-{suffix}")
                self.cli(
                    "worker-finish",
                    run_id,
                    task_id,
                    "--worker-id",
                    f"worker-{suffix}",
                    "--status",
                    "FAILED",
                )
                artifact = self.temp_root / f"{suffix}-history.json"
                artifact.write_text(json.dumps({"historical": outcome}) + "\n", encoding="utf-8")
                workspace = self.temp_root / f"{suffix}-workspace"
                workspace.mkdir()
                self.install_reconciliation(
                    run_id,
                    task_id,
                    operation,
                    "historical-resource",
                    outcome,
                    artifact,
                    workspace,
                )
                with mock.patch.object(
                    runtime_module.RunStore,
                    "_executor_registry_path",
                    return_value=self.home / ".architrave" / "executors.json",
                ), mock.patch.object(
                    runtime_module,
                    "trusted_user_state_root",
                    return_value=self.home / ".architrave",
                ):
                    state = self.store.attest_side_effect_reconciliation(run_id, task_id)
                task = next(item for item in state["tasks"] if item["id"] == task_id)
                self.assertEqual("FAILED", task["status"])
                self.assertEqual(expected_state, task["sideEffect"]["state"])
                receipt_ref = task["sideEffect"]["reconciliation"]
                receipt = next(
                    item
                    for item in state["artifacts"]
                    if f"artifact:{item['id']}" == receipt_ref
                )
                self.assertEqual("reconciliation", receipt["producer"])
                payload = json.loads((self.repo / receipt["path"]).read_text(encoding="utf-8"))
                self.assertEqual(outcome, payload["outcome"])
                self.assertEqual("closed", payload["observation"]["processState"])

    def test_correction_cancels_active_old_work_and_recomputes_next_test(self) -> None:
        run_id = self.create(
            "Old objective.",
            policy_allow=[{"scope": "sandbox:fixture", "operations": ["deploy"]}],
        )
        old_evidence = self.evidence(run_id, "old-gate-evidence")
        self.store.record_gate(
            run_id,
            gate_id="old-objective-gate",
            task_id=None,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[old_evidence],
            criteria=["ACCEPT-001"],
        )
        self.add_task(
            run_id,
            "old-worker-one",
            sideEffect={"operation": "deploy", "target": "sandbox:fixture"},
        )
        self.add_task(run_id, "old-worker-two")
        self.add_task(run_id, "correction-auth")
        self.cli("task-start", run_id, "old-worker-one", "--worker-id", "worker-one")
        self.cli("task-start", run_id, "old-worker-two", "--worker-id", "worker-two")
        wait = self.cli(
            "external-wait", run_id, "--id", "correction-checkpoint", "--task-id", "correction-auth",
            "--type", "HUMAN_JUDGMENT_REQUIRED", "--principal", "synthetic-user",
            "--provider", "user-direction", "--reason", "Replace objective.",
        )
        self.cli(
            "objective-replace", run_id, "--outcome", "Corrected product objective.",
            "--criterion", "ACCEPT-001|Corrected objective reaches acceptance.|product|R1|deterministic",
            "--correction", "Wrong target; use the existing working implementation.",
            "--next-test", "Diff and run the existing working path.",
            "--checkpoint-id", "correction-checkpoint", "--challenge", str(wait["resolutionChallenge"]),
            "--actor", "human:synthetic-user",
        )
        state = self.store.load(run_id)
        uncertain = next(task for task in state["tasks"] if task["id"] == "old-worker-one")
        deferred = next(task for task in state["tasks"] if task["id"] == "old-worker-two")
        self.assertEqual("UNCERTAIN", uncertain["sideEffect"]["state"])
        self.assertEqual("WAITING_RESOURCE", uncertain["status"])
        self.assertEqual("DEFERRED", deferred["status"])
        self.assertTrue(all(worker["status"] == "FAILED" for worker in state["workers"]))
        error = self.cli(
            "criterion-set", run_id, "ACCEPT-001", "--status", "PASS",
            "--evidence", "gate:old-objective-gate", expected=1,
        )
        self.assertEqual("EVIDENCE_SUPERSEDED", error["code"])
        verified = self.cli("verify", run_id, expected=1)
        self.assertEqual("WAITING_RESOURCE", verified["status"])
        self.add_task(
            run_id,
            "new-minimal-test",
            acceptanceCriteria=["ACCEPT-001"],
            isMinimalAcceptanceTest=True,
        )
        self.cli("task-start", run_id, "new-minimal-test", "--worker-id", "new-worker")
        state = self.store.load(run_id)
        self.assertEqual("RUNNING", next(task for task in state["tasks"] if task["id"] == "new-minimal-test")["status"])

    def test_repeated_micro_reviews_require_batch_and_reset(self) -> None:
        run_id = self.create("Prove a minimal product slice before review.")
        evidence = self.evidence(run_id)
        self.store.record_gate(
            run_id,
            gate_id="minimal-gate",
            task_id=None,
            gate_type="deterministic",
            status="PASS",
            evidence_refs=[evidence],
            criteria=["ACCEPT-001"],
        )
        self.store.set_criterion(run_id, "ACCEPT-001", "PASS", ["gate:minimal-gate"])
        self.add_task(run_id, "micro-review", workKind="review")
        self.cli("review-record", run_id, "--verdict", "REVISE")
        self.cli("review-record", run_id, "--verdict", "REVISE")
        state = self.store.load(run_id)
        review = next(task for task in state["tasks"] if task["id"] == "micro-review")
        self.assertEqual("DEFERRED", review["status"])
        self.assertEqual("review.batch_required", self.store.events(run_id)[-1]["type"])
        self.assertEqual(
            "repeated review without new product evidence",
            state["focus"]["lastResetReason"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
