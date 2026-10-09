#!/usr/bin/env python3
"""Focused tests for the canonical install/update implementation."""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import unittest
import uuid
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "install_update.py"


def legacy_hook_bytes(name: str = "design-guard.json") -> bytes:
    command = (
        "pwsh -NoProfile -File ./gates/quality-gate.ps1 -HookJson"
        if name == "design-guard.windows.json"
        else "./gates/quality-gate.sh --hook-json"
    )
    return json.dumps({
        "hooks": {"PostToolUse": [{"type": "command", "command": command, "timeout": 20}]}
    }).encode("utf-8")


def load_cli_module():
    spec = importlib.util.spec_from_file_location("architrave_install_update", CLI)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load install_update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_observer_module():
    path = ROOT / "trusted" / "exact_target_observer.py"
    spec = importlib.util.spec_from_file_location("architrave_exact_target_observer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load exact_target_observer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> tuple[str, ...]:
    root = Path(load_cli_module().ManagedTransaction._native_path(root))
    entries: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in (*directories, *files):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                entries.append(f"link {relative}")
            elif stat.S_ISDIR(info.st_mode):
                entries.append(f"dir {relative}")
            elif stat.S_ISREG(info.st_mode):
                entries.append(f"file {relative} {digest(path)} {stat.S_IMODE(info.st_mode):o}")
            else:
                entries.append(f"other {relative}")
    return tuple(entries)


class InstallUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_cli_module()
        cls.observer = load_observer_module()

    def setUp(self) -> None:
        self.workspace = ROOT / f".install-update-test-{uuid.uuid4().hex}"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.module.ManagedTransaction._native_path(self.workspace), ignore_errors=True)

    def run_cli(
        self,
        *arguments: str,
        expected: int = 0,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
            env={**os.environ, **(env or {})},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return completed

    def test_profiles_spaces_and_install_idempotency(self) -> None:
        application = self.workspace / "application repo with spaces"
        knowledge = self.workspace / "knowledge repo with spaces"
        application.mkdir()
        knowledge.mkdir()

        self.run_cli("install", "--entrypoint", "windows", str(application))
        application_first = snapshot(application)
        self.run_cli("install", "--entrypoint", "windows", str(application))
        self.assertEqual(snapshot(application), application_first)
        application_config = json.loads((application / "architrave.config.json").read_text())
        self.assertEqual(application_config["platform"], "web")
        self.assertNotIn("kind", application_config)
        self.assertTrue((application / "constitution-apple.md").is_file())
        self.assertTrue((application / ".github/agents/ui-visual.agent.md").is_file())
        self.assertFalse((application / ".github/hooks/design-guard.json").exists())
        self.assertFalse((application / "gates/hooks").exists())

        self.run_cli(
            "install",
            "--profile",
            "knowledge",
            "--entrypoint",
            "posix",
            str(knowledge),
        )
        knowledge_first = snapshot(knowledge)
        self.run_cli(
            "install",
            "--profile",
            "knowledge",
            "--entrypoint",
            "posix",
            str(knowledge),
        )
        self.assertEqual(snapshot(knowledge), knowledge_first)
        self.assertEqual(
            json.loads((knowledge / "architrave.config.json").read_text())["kind"],
            "knowledge",
        )
        self.assertEqual(
            len(list((knowledge / ".github/agents").glob("*.agent.md"))),
            6,
        )
        self.assertTrue((knowledge / ".github/agents/cto.agent.md").is_file())
        self.assertTrue((application / ".github/agents/cto.agent.md").is_file())
        self.assertFalse((knowledge / ".github/agents/ui-visual.agent.md").exists())
        self.assertFalse(any(knowledge.glob("constitution-*.md")))
        for relative in (
            "harness/architrave_runtime.py",
            "knowledge/execution-policy.md",
            "gates/gate_runner.py",
        ):
            self.assertTrue((knowledge / relative).is_file(), relative)

    def test_known_legacy_quality_hooks_are_retired_transactionally_and_idempotently(self) -> None:
        for source in ("design-guard.json", "design-guard.windows.json"):
            target = self.workspace / source
            target.mkdir()
            self.run_cli("install", "--profile", "knowledge", str(target))
            active = target / ".github/hooks/design-guard.json"
            active.parent.mkdir(parents=True)
            content = json.loads(legacy_hook_bytes(source))
            active.write_text(json.dumps(content))
            copied = target / "gates/hooks" / source
            copied.parent.mkdir(parents=True)
            copied.write_text(json.dumps(content))
            other = active.parent / "other-plugin.json"
            other.write_text('{"hooks":{"PreToolUse":[{"type":"command","command":"preserve-user-policy"}]}}')
            (target / "product.txt").write_text("preserve product")
            before_other = other.read_bytes()
            before_config = (target / "architrave.config.json").read_bytes()
            dry = self.run_cli("retire-hooks", "--dry-run", str(target))
            self.assertIn("remove-recognized", dry.stdout)
            self.assertTrue(active.exists())
            self.run_cli("update", str(target))
            self.assertFalse(active.exists())
            self.assertFalse(copied.exists())
            self.assertEqual(before_other, other.read_bytes())
            self.assertEqual(before_config, (target / "architrave.config.json").read_bytes())
            self.assertEqual("preserve product", (target / "product.txt").read_text())
            first = snapshot(target)
            self.run_cli("update", str(target))
            self.assertEqual(first, snapshot(target))

    def test_custom_quality_hook_is_preserved_with_explicit_manual_action(self) -> None:
        target = self.workspace / "custom hooks"
        target.mkdir()
        self.run_cli("install", "--profile", "knowledge", str(target))
        active = target / ".github/hooks/design-guard.json"
        active.parent.mkdir(parents=True)
        owned = json.loads(legacy_hook_bytes("design-guard.windows.json"))
        owned["hooks"]["PostToolUse"].append({"type": "command", "command": "user-check"})
        active.write_text(json.dumps(owned))
        original = active.read_bytes()
        result = self.run_cli("update", str(target), expected=2)
        self.assertIn("MANUAL_ACTION_REQUIRED", result.stderr)
        self.assertEqual(original, active.read_bytes())
        retired = self.run_cli("retire-hooks", str(target), expected=2)
        self.assertIn("MANUAL_ACTION_REQUIRED", retired.stderr)
        dry = self.run_cli("retire-hooks", "--dry-run", str(target), expected=2)
        self.assertIn("MANUAL_ACTION_REQUIRED", dry.stderr)
        self.assertEqual(original, active.read_bytes())
        active.write_text('{"hooks":{},"hooks":{"PostToolUse":[{"type":"command","command":"./gates/quality-gate.sh --hook-json","timeout":20}]}}')
        duplicate = active.read_bytes()
        retired = self.run_cli("retire-hooks", str(target), expected=2)
        self.assertIn("MANUAL_ACTION_REQUIRED", retired.stderr)
        self.assertEqual(duplicate, active.read_bytes())
        active.write_text("{malformed")
        malformed = active.read_bytes()
        retired = self.run_cli("retire-hooks", str(target), expected=2)
        self.assertIn("MANUAL_ACTION_REQUIRED", retired.stderr)
        self.assertEqual(malformed, active.read_bytes())

    def test_quality_retirement_conflicting_edit_rolls_back_without_deleting_custom_data(self) -> None:
        target = self.workspace / "hook race"
        target.mkdir()
        active = target / ".github/hooks/design-guard.json"
        active.parent.mkdir(parents=True)
        active.write_bytes(legacy_hook_bytes())
        managed = self.module.ManagedRoot(target, "fixture")
        plan = self.module.quality_hook_plan(managed, ROOT)
        custom = b'{"hooks":{"PostToolUse":[{"type":"command","command":"custom-changed"}]}}'
        with self.assertRaises(self.module.InstallerError):
            with self.module.ManagedTransaction(managed):
                self.module.apply_quality_hook_plan(managed, plan)
                active.write_bytes(custom)
        self.assertEqual(custom, active.read_bytes())
        self.assertFalse((target / ".architrave-install.lock").exists())
        self.assertFalse((target / ".architrave-install-transaction").exists())

    @unittest.skipIf(sys.version_info < (3, 11), "optional Codex role installation requires Python 3.11+")
    def test_update_agents_codex_and_idempotency(self) -> None:
        target = self.workspace / "codex knowledge"
        target.mkdir()
        self.run_cli(
            "install",
            "--profile",
            "knowledge",
            "--codex",
            str(target),
        )
        self.assertEqual(len(list((target / ".codex/agents").glob("*.toml"))), 2)
        custom = target / ".github/agents/custom.agent.md"
        legacy = target / ".github/agents/ui-visual.agent.md"
        custom.write_text("custom\n", encoding="utf-8")
        shutil.copy2(ROOT / "agents/ui-visual.agent.md", legacy)

        self.run_cli("update", "--codex", str(target))
        self.assertTrue(legacy.exists())
        self.run_cli("update", "--agents", "--codex", str(target))
        self.assertFalse(legacy.exists())
        self.assertEqual(custom.read_text(encoding="utf-8"), "custom\n")
        updated = snapshot(target)
        self.run_cli("update", "--agents", "--codex", str(target))
        self.assertEqual(snapshot(target), updated)

    def test_executor_install_uses_private_user_state_and_pins_exact_target(self) -> None:
        state = self.workspace / "user state" / ".architrave"
        state.parent.mkdir()
        artifact = self.workspace / "target.bin"
        artifact.write_bytes(b"exact target")
        workspace = self.workspace / "future prefix"
        args = argparse.Namespace(
            provider="provider-a",
            artifact="target.bin",
            artifact_path=str(artifact),
            version="2",
            sha256=digest(artifact),
            environment="test",
            workspace=str(workspace),
            acceptance_target="exact target smoke",
            workspace_mode="absent-or-exact-directory",
            timeout_seconds=3,
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
        )
        with mock.patch.object(self.module, "trusted_user_state_root", return_value=state):
            self.assertEqual(0, self.module.install_exact_target_executor(args, ROOT))
            self.assertEqual(0, self.module.install_exact_target_executor(args, ROOT))
        registry_path = state / "executors.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        exact = registry["exactTarget"]
        self.assertEqual("architrave.executor-registry.v1", registry["schema"])
        self.assertEqual(["provider-a"], exact["allowedProviders"])
        self.assertEqual(
            ["SAFE_WRITE_TARGET_REQUIRED", "SIDE_EFFECT_RECONCILIATION_REQUIRED"],
            exact["allowedCheckpointTypes"],
        )
        self.assertEqual(1, len(exact["targets"]))
        self.assertEqual(digest(Path(exact["adapter"])), exact["adapterSha256"])
        self.assertEqual(digest(Path(exact["executable"])), exact["executableSha256"])
        self.assertTrue(Path(exact["adapter"]).is_relative_to(state / "executors"))

    def test_executor_install_enrolls_pinned_ssh_relay_target(self) -> None:
        state = self.workspace / "remote user state" / ".architrave"
        state.parent.mkdir()
        identity_file = self.workspace / "id_ed25519"
        known_hosts = self.workspace / "known_hosts"
        identity_file.write_text("fixture identity\n", encoding="utf-8")
        known_hosts.write_text("fixture host key\n", encoding="utf-8")
        args = argparse.Namespace(
            provider="provider-remote",
            artifact="remote target",
            artifact_path="/srv/target.bin",
            version="3",
            sha256="a" * 64,
            environment="trusted-mac",
            workspace="/srv/future-prefix",
            acceptance_target="remote exact target",
            workspace_mode="absent-or-exact-directory",
            timeout_seconds=10,
            ssh_host="trusted-host",
            ssh_host_key_alias="trusted-key-alias",
            ssh_port=22,
            ssh_user="operator",
            ssh_executable=sys.executable,
            ssh_identity=str(identity_file),
            ssh_known_hosts=str(known_hosts),
            ssh_remote_python="/usr/bin/python3",
            ssh_remote_adapter="/Users/operator/.architrave/executors/exact-target-v1/observer.py",
            ssh_remote_adapter_sha256="b" * 64,
        )
        ssh_trust_root = self.workspace / "approved ssh"
        ssh_trust_root.mkdir()
        approved_identity = ssh_trust_root / "id_ed25519"
        approved_known_hosts = ssh_trust_root / "known_hosts"
        shutil.copyfile(identity_file, approved_identity)
        shutil.copyfile(known_hosts, approved_known_hosts)
        args.ssh_identity = str(approved_identity)
        args.ssh_known_hosts = str(approved_known_hosts)
        with mock.patch.object(self.module, "trusted_user_state_root", return_value=state):
            with mock.patch.object(self.module, "approved_ssh_trust_root", return_value=ssh_trust_root):
                self.assertEqual(0, self.module.install_exact_target_executor(args, ROOT))
                first_registry = json.loads((state / "executors.json").read_text(encoding="utf-8"))
                first_target = first_registry["exactTarget"]["targets"][0]
                identity_destination = Path(first_target["ssh"]["identityFile"])
                known_hosts_destination = Path(first_target["ssh"]["knownHosts"])
                if os.name == "nt":
                    self.assertEqual(approved_identity.resolve(), identity_destination)
                    self.assertEqual(approved_known_hosts.resolve(), known_hosts_destination)
                else:
                    external_identity = self.workspace / "external-identity"
                    external_known_hosts = self.workspace / "external-known-hosts"
                    external_identity.write_text("external identity sentinel\n", encoding="utf-8")
                    external_known_hosts.write_text("external hosts sentinel\n", encoding="utf-8")
                    identity_destination.unlink()
                    known_hosts_destination.unlink()
                    os.link(external_identity, identity_destination)
                    os.link(external_known_hosts, known_hosts_destination)
                    self.assertEqual(0, self.module.install_exact_target_executor(args, ROOT))
                    self.assertEqual("external identity sentinel\n", external_identity.read_text(encoding="utf-8"))
                    self.assertEqual("external hosts sentinel\n", external_known_hosts.read_text(encoding="utf-8"))
                second = argparse.Namespace(**vars(args))
                second.artifact = "second remote target"
                second.artifact_path = "/srv/second-target.bin"
                second.workspace = "/srv/second-prefix"
                second.sha256 = "c" * 64
                self.assertEqual(0, self.module.install_exact_target_executor(second, ROOT))
                before_invalid = snapshot(state)
                invalid = argparse.Namespace(**vars(args))
                invalid.ssh_user = "-operator"
                with self.assertRaises(self.module.InstallerError):
                    self.module.install_exact_target_executor(invalid, ROOT)
                self.assertEqual(before_invalid, snapshot(state))
        registry = json.loads((state / "executors.json").read_text(encoding="utf-8"))
        target, second_target = registry["exactTarget"]["targets"]
        self.assertEqual("ssh", target["transport"])
        self.assertEqual("/srv/target.bin", target["artifactPath"])
        self.assertEqual("trusted-host", target["ssh"]["host"])
        self.assertEqual("trusted-key-alias", target["ssh"]["hostKeyAlias"])
        self.assertEqual("b" * 64, target["ssh"]["remoteAdapterSha256"])
        if os.name == "nt":
            self.assertEqual(approved_identity.resolve(), Path(target["ssh"]["identityFile"]))
            self.assertEqual(approved_known_hosts.resolve(), Path(target["ssh"]["knownHosts"]))
        else:
            self.assertTrue(Path(target["ssh"]["identityFile"]).is_relative_to(state / "ssh"))
            self.assertTrue(Path(target["ssh"]["knownHosts"]).is_relative_to(state / "ssh"))
            self.assertNotEqual(
                Path(target["ssh"]["identityFile"]).parent,
                Path(second_target["ssh"]["identityFile"]).parent,
            )

    def test_ssh_relay_streams_fixed_helper_and_preserves_binding(self) -> None:
        identity_file = self.workspace / "relay_identity"
        known_hosts = self.workspace / "relay_known_hosts"
        identity_file.write_text("fixture identity\n", encoding="utf-8")
        known_hosts.write_text("fixture host key\n", encoding="utf-8")
        binding = {
            "runId": "run-a",
            "objectiveVersion": 1,
            "revision": 4,
            "taskId": "task-a",
            "checkpointId": "checkpoint-a",
            "checkpointType": "SAFE_WRITE_TARGET_REQUIRED",
            "provider": "provider-remote",
            "principal": "operator",
            "challengeHash": "a" * 64,
        }
        intended = {
            "provider": "provider-remote",
            "artifact": "remote target",
            "version": "3",
            "sha256": "b" * 64,
            "environment": "trusted-mac",
            "workspace": "/srv/future-prefix",
            "acceptanceTarget": "remote exact target",
        }
        request = {
            "schema": "architrave.exact-target-request.v1",
            "binding": binding,
            "intended": intended,
            "target": {
                "transport": "ssh",
                "artifactPath": "/srv/target.bin",
                "workspaceMode": "absent-or-exact-directory",
                "ssh": None,
                "reconciliation": None,
            },
        }
        remote_result = {
            "schema": "architrave.exact-target-result.v1",
            "status": "observed",
            "binding": binding,
            "observed": intended,
            "observation": {"transport": "ssh"},
        }
        captured: dict[str, object] = {}

        class Sink:
            def __init__(self) -> None:
                self.value = bytearray()

            def write(self, value: bytes) -> int:
                self.value.extend(value)
                return len(value)

            def close(self) -> None:
                captured["stdin"] = bytes(self.value)

        class Process:
            returncode = 0

            def __init__(self, argv: list[str]) -> None:
                captured["argv"] = argv
                self.stdin = Sink()
                self.stdout = io.BytesIO(json.dumps(remote_result).encode("utf-8"))
                self.stderr = io.BytesIO()

            def poll(self) -> int:
                return 0

            def wait(self) -> int:
                return 0

            def kill(self) -> None:
                self.returncode = -9

        def popen(argv: list[str], **kwargs: object) -> Process:
            captured["kwargs"] = kwargs
            return Process(argv)

        ssh = {
            "executable": str(Path(sys.executable).resolve()),
            "executableSha256": digest(Path(sys.executable).resolve()),
            "host": "trusted-host",
            "hostKeyAlias": "trusted-key-alias",
            "port": 22,
            "user": "operator",
            "identityFile": str(identity_file),
            "identityFileSha256": digest(identity_file),
            "knownHosts": str(known_hosts),
            "knownHostsSha256": digest(known_hosts),
            "remotePython": "/usr/bin/python3",
            "remoteAdapter": "/Users/operator/.architrave/executors/exact-target-v1/observer.py",
            "remoteAdapterSha256": "c" * 64,
        }
        with mock.patch.object(self.observer.subprocess, "Popen", side_effect=popen):
            result = self.observer.invoke_ssh(ssh, request)
        self.assertEqual(binding, result["binding"])
        expected_argv = [
            str(Path(sys.executable).resolve()),
            "-F",
            "NUL" if os.name == "nt" else "/dev/null",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-o",
            "HostKeyAlias=trusted-key-alias",
            "-i",
            str(identity_file),
            "-p",
            "22",
            "operator@trusted-host",
            "/usr/bin/python3 -I -S -",
        ]
        self.assertEqual(expected_argv, captured["argv"])
        kwargs = captured["kwargs"]
        self.assertEqual({"stdin", "stdout", "stderr", "shell", "env"}, set(kwargs))
        self.assertEqual(subprocess.PIPE, kwargs["stdin"])
        self.assertEqual(subprocess.PIPE, kwargs["stdout"])
        self.assertEqual(subprocess.PIPE, kwargs["stderr"])
        self.assertFalse(kwargs["shell"])
        self.assertEqual(
            {
                key: value
                for key, value in os.environ.items()
                if key.upper()
                in {
                    "SYSTEMROOT",
                    "WINDIR",
                    "TMP",
                    "TEMP",
                    "TMPDIR",
                    "USERPROFILE",
                    "HOMEDRIVE",
                    "HOMEPATH",
                    "PROGRAMDATA",
                }
            },
            kwargs["env"],
        )
        ast.parse(self.observer.REMOTE_HELPER, feature_version=(3, 9))
        ast.parse(
            (ROOT / "trusted" / "exact_target_observer.py").read_text(encoding="utf-8"),
            feature_version=(3, 9),
        )
        unsafe_user = dict(ssh)
        unsafe_user["user"] = "-operator"
        with self.assertRaises(ValueError):
            self.observer.invoke_ssh(unsafe_user, request)
        unsafe_digest = dict(ssh)
        unsafe_digest["remoteAdapterSha256"] = "z" * 64
        with self.assertRaises(ValueError):
            self.observer.invoke_ssh(unsafe_digest, request)

    def test_streamed_helper_independently_rejects_modified_remote_adapter(self) -> None:
        artifact = self.workspace / "remote-target.bin"
        artifact.write_bytes(b"remote target")
        adapter = self.workspace / "observer.py"
        shutil.copyfile(ROOT / "trusted" / "exact_target_observer.py", adapter)
        request = {
            "schema": "architrave.exact-target-request.v1",
            "binding": {
                "runId": "run-a",
                "objectiveVersion": 1,
                "revision": 4,
                "taskId": "task-a",
                "checkpointId": "checkpoint-a",
                "checkpointType": "SAFE_WRITE_TARGET_REQUIRED",
                "provider": "provider-remote",
                "principal": "operator",
                "challengeHash": "a" * 64,
            },
            "intended": {
                "provider": "provider-remote",
                "artifact": "remote target",
                "version": "3",
                "sha256": digest(artifact),
                "environment": "trusted-mac",
                "workspace": str(self.workspace / "future-prefix"),
                "acceptanceTarget": "remote exact target",
            },
            "target": {
                "transport": "local",
                "artifactPath": str(artifact),
                "workspaceMode": "absent-or-exact-directory",
                "ssh": None,
                "reconciliation": None,
            },
        }
        helper = self.observer.REMOTE_HELPER.replace(
            "__REQUEST__",
            self.observer.base64.b64encode(
                json.dumps(request, separators=(",", ":"), sort_keys=True).encode("utf-8")
            ).decode("ascii"),
        ).replace(
            "__ADAPTER__",
            adapter.as_posix(),
        ).replace(
            "__ADAPTER_SHA256__",
            digest(adapter),
        )
        passed = subprocess.run(
            [sys.executable, "-I", "-S", "-"],
            input=helper,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, passed.returncode, passed.stderr)
        adapter.write_text(adapter.read_text(encoding="utf-8") + "\n# modified\n", encoding="utf-8")
        rejected = subprocess.run(
            [sys.executable, "-I", "-S", "-"],
            input=helper,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("remote adapter SHA-256 does not match", rejected.stderr)

    def test_observer_rejects_linked_workspace_ancestor(self) -> None:
        artifact = self.workspace / "target.bin"
        artifact.write_bytes(b"target")
        linked_parent = self.workspace / "linked-parent"
        external = self.workspace / "external-workspace"
        external.mkdir()
        if os.name == "nt":
            completed = subprocess.run(
                [os.environ.get("ComSpec", "cmd.exe"), "/c", "mklink", "/J", str(linked_parent), str(external)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                self.skipTest(f"directory junctions are unavailable: {completed.stderr!r}")
        else:
            os.symlink(external, linked_parent, target_is_directory=True)
        request = {
            "binding": {
                "runId": "run-a",
                "objectiveVersion": 1,
                "revision": 1,
                "taskId": "task-a",
                "checkpointId": "checkpoint-a",
                "checkpointType": "SAFE_WRITE_TARGET_REQUIRED",
                "provider": "provider-a",
                "principal": "operator",
                "challengeHash": "a" * 64,
            },
            "intended": {
                "provider": "provider-a",
                "artifact": "target.bin",
                "version": "1",
                "sha256": digest(artifact),
                "environment": "test",
                "workspace": str(linked_parent / "future-prefix"),
                "acceptanceTarget": "exact target",
            },
            "target": {
                "transport": "local",
                "artifactPath": str(artifact),
                "workspaceMode": "absent-or-exact-directory",
                "ssh": None,
                "reconciliation": None,
            },
        }
        with self.assertRaisesRegex(ValueError, "workspace path contains"):
            self.observer.observe_local(request)

    def test_reconciliation_liveness_probe_never_terminates_owned_live_child(self) -> None:
        artifact = self.workspace / "process-proof.bin"
        artifact.write_bytes(b"owned liveness fixture")
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        request = {
            "binding": {"runId": "run-a", "objectiveVersion": 1, "revision": 1, "taskId": "task-a",
                        "checkpointId": "checkpoint-a", "checkpointType": "SIDE_EFFECT_RECONCILIATION_REQUIRED",
                        "provider": "provider-a", "principal": "operator", "challengeHash": "a" * 64},
            "intended": {"provider": "provider-a", "artifact": "process-proof.bin", "version": "1",
                         "sha256": digest(artifact), "environment": "test", "workspace": str(self.workspace.resolve()),
                         "acceptanceTarget": "owned fixture"},
            "target": {"transport": "local", "artifactPath": str(artifact.resolve()),
                       "workspaceMode": "exact-directory", "ssh": None,
                       "reconciliation": {"runId": "run-a", "taskId": "task-a", "operation": "input",
                                          "target": "owned fixture", "outcome": "closed-unknown",
                                          "processId": child.pid}},
        }
        try:
            self.assertEqual("ready\n", child.stdout.readline())
            with self.assertRaisesRegex(ValueError, "still running"):
                self.observer.observe_local(request)
            time.sleep(.1)
            self.assertIsNone(child.poll(), "Read-only probe terminated its exact owned child")
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()
        result = self.observer.observe_local(request)
        self.assertEqual("closed", result["observation"]["processState"])

    @unittest.skipUnless(os.name == "nt", "Windows non-mutating process query contract")
    def test_reconciliation_process_query_errors_fail_closed_without_signals(self) -> None:
        kernel = mock.Mock()
        kernel.OpenProcess.return_value = None
        with mock.patch("ctypes.WinDLL", return_value=kernel), \
                mock.patch("ctypes.get_last_error", return_value=5), \
                mock.patch.object(self.observer.os, "kill", side_effect=AssertionError("No Windows signals")):
            with self.assertRaisesRegex(ValueError, "cannot be observed"):
                self.observer.process_state(os.getpid())
            kernel.OpenProcess.return_value = 123
            kernel.WaitForSingleObject.return_value = 0xFFFFFFFF
            kernel.CloseHandle.return_value = 1
            with self.assertRaisesRegex(ValueError, "status query failed"):
                self.observer.process_state(os.getpid())
            kernel.CloseHandle.assert_called_once_with(123)

    def test_observer_self_installer_is_python39_compatible_and_pinned(self) -> None:
        state = self.workspace / "observer state" / ".architrave"
        state.parent.mkdir()
        source = ROOT / "trusted" / "exact_target_observer.py"
        destination_root = state / "executors" / "exact-target-v1" / digest(source)[:32]
        destination_root.mkdir(parents=True)
        if os.name != "nt":
            for path in (state, state / "executors", state / "executors" / "exact-target-v1", destination_root):
                path.chmod(0o700)
        external = self.workspace / "observer-temp-sentinel"
        external.write_text("unchanged\n", encoding="utf-8")
        os.link(external, destination_root / f".observer.{os.getpid()}.tmp")
        stdout = io.StringIO()
        with mock.patch.object(self.observer, "trusted_user_state_root", return_value=state):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(0, self.observer.install_self())
        installed = json.loads(stdout.getvalue())
        adapter = Path(installed["adapter"])
        self.assertEqual(digest(adapter), installed["sha256"])
        self.assertTrue(adapter.is_relative_to(state / "executors"))
        self.assertEqual("unchanged\n", external.read_text(encoding="utf-8"))

    def test_executor_and_observer_reject_linked_trust_root(self) -> None:
        home = self.workspace / "linked home"
        external = self.workspace / "external trust"
        home.mkdir()
        external.mkdir()
        sentinel = external / "sentinel.txt"
        sentinel.write_text("unchanged\n", encoding="utf-8")
        state = home / ".architrave"
        if os.name == "nt":
            completed = subprocess.run(
                [os.environ.get("ComSpec", "cmd.exe"), "/c", "mklink", "/J", str(state), str(external)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                self.skipTest(f"directory junctions are unavailable: {completed.stderr!r}")
        else:
            os.symlink(external, state, target_is_directory=True)
        artifact = self.workspace / "linked-target.bin"
        artifact.write_bytes(b"target")
        args = argparse.Namespace(
            provider="provider-a",
            artifact="target",
            artifact_path=str(artifact),
            version="1",
            sha256=digest(artifact),
            environment="test",
            workspace=str(self.workspace / "future-prefix"),
            acceptance_target="target",
            workspace_mode="absent-or-exact-directory",
            timeout_seconds=3,
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
        )
        with mock.patch.object(self.module, "trusted_user_state_root", return_value=state):
            with self.assertRaises(self.module.InstallerError):
                self.module.install_exact_target_executor(args, ROOT)
        with mock.patch.object(self.observer, "trusted_user_state_root", return_value=state):
            with self.assertRaises(OSError):
                self.observer.install_self()
        self.assertEqual("unchanged\n", sentinel.read_text(encoding="utf-8"))

    def test_executor_digest_failure_writes_nothing(self) -> None:
        state = self.workspace / "digest failure home" / ".architrave"
        state.parent.mkdir()
        artifact = self.workspace / "digest-target.bin"
        artifact.write_bytes(b"target")
        args = argparse.Namespace(
            provider="provider-a",
            artifact="target",
            artifact_path=str(artifact),
            version="1",
            sha256=digest(artifact),
            environment="test",
            workspace=str(self.workspace / "future-prefix"),
            acceptance_target="target",
            workspace_mode="absent-or-exact-directory",
            timeout_seconds=3,
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
        )
        original = self.module.sha256_file

        def fail_executable(path: Path) -> str:
            if path.resolve() == Path(sys.executable).resolve():
                raise OSError("injected executable read failure")
            return original(path)

        with mock.patch.object(self.module, "trusted_user_state_root", return_value=state):
            with mock.patch.object(self.module, "sha256_file", side_effect=fail_executable):
                with self.assertRaises(OSError):
                    self.module.install_exact_target_executor(args, ROOT)
        self.assertFalse(state.exists())

    def test_symlink_and_path_escape_fail_without_writes(self) -> None:
        target = self.workspace / "linked target"
        external = self.workspace / "external"
        target.mkdir()
        external.mkdir()
        (external / "sentinel.md").write_text("outside\n", encoding="utf-8")
        link = target / "knowledge"
        if os.name == "nt":
            completed = subprocess.run(
                [os.environ.get("ComSpec", "cmd.exe"), "/c", "mklink", "/J", str(link), str(external)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                self.skipTest(f"directory junctions are unavailable: {completed.stderr!r}")
        else:
            try:
                os.symlink(external, link, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

        target_before = snapshot(target)
        external_before = snapshot(external)
        self.run_cli("install", "--profile", "knowledge", str(target), expected=1)
        self.assertEqual(snapshot(target), target_before)
        self.assertEqual(snapshot(external), external_before)

        managed = self.module.ManagedRoot(target, "test")
        with self.assertRaises(self.module.InstallerError):
            managed.path("../escape")
        with self.assertRaises(self.module.InstallerError):
            managed.path("/absolute")
        self.assertFalse((self.workspace / "escape").exists())

    def test_hardlink_replacement_does_not_mutate_external_file(self) -> None:
        target = self.workspace / "hardlink target"
        target.mkdir()
        external = self.workspace / "external-gitignore"
        external.write_text("outside hard-link sentinel\n", encoding="utf-8")
        try:
            os.link(external, target / ".gitignore")
        except OSError as exc:
            self.skipTest(f"hard links are unavailable: {exc}")
        external_before = digest(external)

        self.run_cli("install", "--profile", "knowledge", str(target))
        self.assertEqual(digest(external), external_before)
        self.assertIn(
            ".architrave/runs/",
            (target / ".gitignore").read_text(encoding="utf-8").splitlines(),
        )
        self.assertNotEqual((target / ".gitignore").stat().st_ino, external.stat().st_ino)

    def test_invalid_update_and_unsafe_destination_do_not_write(self) -> None:
        invalid = self.workspace / "invalid update"
        invalid.mkdir()
        (invalid / "architrave.config.json").write_text(
            '{"kind":"application","kind":"knowledge"}\n',
            encoding="utf-8",
        )
        invalid_before = snapshot(invalid)
        self.run_cli("update", str(invalid), expected=2)
        self.assertEqual(snapshot(invalid), invalid_before)

        unsafe = self.workspace / "unsafe destination"
        (unsafe / ".github").mkdir(parents=True)
        (unsafe / ".github/hooks").write_text("not a directory\n", encoding="utf-8")
        (unsafe / "architrave.config.json").write_text(
            '{"kind":"knowledge","build":"true","test":"true"}\n',
            encoding="utf-8",
        )
        unsafe_before = snapshot(unsafe)
        self.run_cli("update", str(unsafe), expected=1)
        self.assertEqual(snapshot(unsafe), unsafe_before)

    def test_quality_retirement_edit_after_backup_preserves_custom_and_rolls_back_applied_write(self) -> None:
        target = self.workspace / "after backup"
        target.mkdir()
        active = target / ".github/hooks/design-guard.json"
        active.parent.mkdir(parents=True)
        active.write_bytes(legacy_hook_bytes())
        product = target / "managed.txt"
        product.write_bytes(b"before")
        managed = self.module.ManagedRoot(target, "fixture")
        plan = self.module.quality_hook_plan(managed, ROOT)
        custom = b'{"hooks":{"PostToolUse":[{"type":"command","command":"new-custom-after-backup"}]}}'
        original = self.module.ManagedTransaction._write_manifest
        edited = False
        def after_backup(transaction, value):
            nonlocal edited
            original(transaction, value)
            if not edited and value["status"] == "prepared" and value["applied"] == 0:
                active.write_bytes(custom)
                edited = True
        with mock.patch.object(self.module.ManagedTransaction, "_write_manifest", after_backup):
            with self.assertRaises(self.module.InstallerError):
                with self.module.ManagedTransaction(managed):
                    managed.replace_bytes("managed.txt", b"applied-new-value")
                    self.module.apply_quality_hook_plan(managed, plan)
        self.assertEqual(custom, active.read_bytes())
        self.assertEqual(b"before", product.read_bytes())
        self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_quality_retirement_post_journal_edit_preserves_actual_inode(self) -> None:
        target = self.workspace / "post journal race"
        target.mkdir()
        active = target / ".github/hooks/design-guard.json"
        active.parent.mkdir(parents=True)
        active.write_bytes(legacy_hook_bytes())
        managed = self.module.ManagedRoot(target, "fixture")
        plan = self.module.quality_hook_plan(managed, ROOT)
        custom = b'{"hooks":{"PostToolUse":[{"type":"command","command":"custom-after-journal"}]}}'
        original = self.module.ManagedTransaction._write_manifest
        edited = False
        def after_journal(transaction, value):
            nonlocal edited
            original(transaction, value)
            if not edited and value.get("inFlight") == 0:
                active.write_bytes(custom)
                edited = True
        with mock.patch.object(self.module.ManagedTransaction, "_write_manifest", after_journal):
            with self.assertRaises(self.module.InstallerError):
                with self.module.ManagedTransaction(managed):
                    self.module.apply_quality_hook_plan(managed, plan)
        self.assertEqual(custom, active.read_bytes())
        retained = list((target / ".architrave/install-retired-hooks").glob("*/design-guard.json"))
        self.assertEqual(1, len(retained))
        self.assertEqual(custom, retained[0].read_bytes())
        self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_quality_retirement_preserves_late_open_handle_write_and_new_target(self) -> None:
        for late_hash in (False, True):
            target = self.workspace / ("open handle late hash" if late_hash else "open handle mismatch")
            target.mkdir()
            active = target / ".github/hooks/design-guard.json"
            active.parent.mkdir(parents=True)
            active.write_bytes(legacy_hook_bytes())
            managed = self.module.ManagedRoot(target, "fixture")
            plan = self.module.quality_hook_plan(managed, ROOT)
            custom = b'{"hooks":{"PostToolUse":[{"type":"command","command":"open-handle-custom"}]}}'
            replacement = b'{"hooks":{"PostToolUse":[{"type":"command","command":"new-target-custom"}]}}'
            if os.name == "nt":
                import ctypes
                import msvcrt
                create = ctypes.windll.kernel32.CreateFileW
                create.restype = ctypes.c_void_p
                create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                   ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
                handle = create(str(active), 0xC0000000, 7, None, 3, 0, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise OSError("shared-delete fixture handle could not be opened")
                writer = os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDWR), "r+b")
            else:
                writer = active.open("r+b")
            original_replace = self.module.os.replace
            original_hash = self.module.sha256_file
            wrote = False
            def write_open_handle():
                nonlocal wrote
                writer.seek(0); writer.write(custom); writer.truncate(); writer.flush()
                wrote = True
            def quarantine_then_edit(source, destination):
                original_replace(source, destination)
                if Path(str(source).removeprefix("\\\\?\\")) == active:
                    if not late_hash:
                        write_open_handle()
                        active.write_bytes(replacement)
            def hash_then_late_write(path):
                value = original_hash(path)
                if late_hash and "install-retired-hooks" in Path(path).parts and not wrote:
                    write_open_handle()
                return value
            try:
                with mock.patch.object(self.module.os, "replace", quarantine_then_edit), \
                        mock.patch.object(self.module, "sha256_file", hash_then_late_write):
                    if late_hash:
                        with self.module.ManagedTransaction(managed):
                            self.module.apply_quality_hook_plan(managed, plan)
                        self.assertFalse(active.exists())
                    else:
                        with self.assertRaises(self.module.InstallerError):
                            with self.module.ManagedTransaction(managed):
                                self.module.apply_quality_hook_plan(managed, plan)
                        self.assertEqual(replacement, active.read_bytes())
            finally:
                writer.close()
            retained = list((target / ".architrave/install-retired-hooks").glob("*/design-guard.json"))
            self.assertTrue(wrote)
            self.assertEqual(1, len(retained))
            self.assertEqual(custom, retained[0].read_bytes())
            self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_quality_retirement_crash_after_quarantine_restores_actual_inode(self) -> None:
        target = self.workspace / "quarantine journal crash"
        target.mkdir()
        active = target / ".github/hooks/design-guard.json"
        active.parent.mkdir(parents=True)
        active.write_bytes(legacy_hook_bytes())
        original_bytes = active.read_bytes()
        managed = self.module.ManagedRoot(target, "fixture")
        plan = self.module.quality_hook_plan(managed, ROOT)
        original = self.module.ManagedTransaction._write_manifest
        def after_move(transaction, value):
            if value["applied"] == 1:
                raise OSError("injected post-quarantine journal failure")
            original(transaction, value)
        with mock.patch.object(self.module.ManagedTransaction, "_write_manifest", after_move):
            with self.assertRaises(OSError):
                with self.module.ManagedTransaction(managed):
                    self.module.apply_quality_hook_plan(managed, plan)
        self.assertEqual(original_bytes, active.read_bytes())
        retained = list((target / ".architrave/install-retired-hooks").glob("*/design-guard.json"))
        self.assertEqual(original_bytes, retained[0].read_bytes())
        self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_quality_retirement_private_guard_survives_rollback_and_custom_ignore_edits(self) -> None:
        for mode in ("success", "mismatch", "crash"):
            with self.subTest(mode=mode):
                target = self.workspace / mode
                target.mkdir()
                subprocess.run(["git", "init", "-q"], cwd=target, check=True, capture_output=True)
                ignore = target / ".gitignore"
                ignore.write_bytes(b"original-custom-rule\n")
                active = target / ".github/hooks/design-guard.json"
                active.parent.mkdir(parents=True)
                active.write_bytes(legacy_hook_bytes())
                changed_ignore = b"concurrent-custom-rule\n!.architrave/\n!.architrave/**\n"
                custom_hook = b'{"custom":"retained private contents"}'
                original_manifest = self.module.ManagedTransaction._write_manifest
                original_replace = self.module.os.replace
                edited = False
                witnessed_private = False

                def journal_then_edit(transaction, value):
                    nonlocal edited
                    if mode == "crash" and value.get("applied") == 1:
                        raise OSError("injected crash after private quarantine")
                    original_manifest(transaction, value)
                    if not edited and value.get("inFlight") == 0:
                        edited = True
                        ignore.write_bytes(changed_ignore)
                        if mode == "mismatch":
                            active.write_bytes(custom_hook)

                def assert_private_before_move(source, destination):
                    nonlocal witnessed_private
                    if Path(str(source).removeprefix("\\\\?\\")) == active:
                        relative = Path(str(destination).removeprefix("\\\\?\\")).relative_to(target).as_posix()
                        checked = subprocess.run(["git", "check-ignore", "--no-index", "--", relative],
                                                 cwd=target, capture_output=True)
                        self.assertEqual(0, checked.returncode)
                        witnessed_private = True
                    original_replace(source, destination)

                with mock.patch.object(self.module.ManagedTransaction, "_write_manifest", journal_then_edit), \
                        mock.patch.object(self.module.os, "replace", assert_private_before_move):
                    if mode == "success":
                        self.assertEqual(0, self.module.retire_quality_hooks(ROOT, target))
                    else:
                        error = OSError if mode == "crash" else self.module.InstallerError
                        with self.assertRaises(error):
                            self.module.retire_quality_hooks(ROOT, target)
                self.assertTrue(witnessed_private)
                self.assertEqual(changed_ignore, ignore.read_bytes())
                retained = list((target / ".architrave/install-retired-hooks").glob("*/design-guard.json"))
                self.assertEqual(1, len(retained))
                relative = retained[0].relative_to(target).as_posix()
                self.assertEqual(0, subprocess.run(["git", "check-ignore", "--no-index", "--", relative],
                                                 cwd=target, capture_output=True).returncode)
                self.assertEqual(b"*\n", (retained[0].parent / ".gitignore").read_bytes())
                status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                        cwd=target, capture_output=True, text=True, check=True).stdout
                self.assertNotIn("install-retired-hooks", status)
                if mode == "mismatch":
                    self.assertEqual(custom_hook, active.read_bytes())
                    self.assertEqual(custom_hook, retained[0].read_bytes())

    def test_quality_retirement_preserves_conflicting_archive_ignore_before_retention(self) -> None:
        target = self.workspace / "c"
        target.mkdir()
        active = target / ".github/hooks/design-guard.json"
        active.parent.mkdir(parents=True)
        original = legacy_hook_bytes()
        active.write_bytes(original)
        identifier = uuid.UUID("a" * 32)
        directory = target / ".architrave/install-retired-hooks" / identifier.hex
        guard = Path(self.module.ManagedTransaction._native_path(directory / ".gitignore"))
        guard.parent.mkdir(parents=True)
        custom = b"!design-guard.json\n"
        guard.write_bytes(custom)
        with mock.patch.object(self.module.uuid, "uuid4", return_value=identifier):
            with self.assertRaisesRegex(self.module.InstallerError, "custom quarantine ignore rules preserved"):
                self.module.retire_quality_hooks(ROOT, target)
        self.assertEqual(original, active.read_bytes())
        self.assertEqual(custom, guard.read_bytes())
        self.assertFalse((directory / active.name).exists())

    def test_quality_retirement_new_hook_after_absent_plan_requires_manual_action(self) -> None:
        for operation in ("install", "update", "retire-hooks"):
            with self.subTest(operation=operation):
                target = self.workspace / operation
                target.mkdir()
                if operation == "update":
                    self.run_cli("install", "--profile", "knowledge", str(target))
                active = target / ".github/hooks/design-guard.json"
                custom = b'{"hooks":{"PostToolUse":[{"type":"command","command":"new-custom-hook"}]}}'
                original = self.module.ManagedTransaction._write_manifest
                original_plan = self.module.quality_hook_plan
                created = False

                def journal_then_create(transaction, value):
                    nonlocal created
                    original(transaction, value)
                    if not created and "inFlight" in value:
                        created = True
                        active.parent.mkdir(parents=True, exist_ok=True)
                        active.write_bytes(custom)

                def plan_then_create(managed, kit):
                    nonlocal created
                    plan = original_plan(managed, kit)
                    if operation == "retire-hooks":
                        created = True
                        active.parent.mkdir(parents=True, exist_ok=True)
                        active.write_bytes(custom)
                    return plan

                output, errors = io.StringIO(), io.StringIO()
                with mock.patch.object(self.module.ManagedTransaction, "_write_manifest", journal_then_create), \
                        mock.patch.object(self.module, "quality_hook_plan", plan_then_create), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    arguments = [operation, str(target)]
                    if operation == "install":
                        arguments[1:1] = ["--profile", "knowledge"]
                    status = self.module.main(arguments)
                self.assertTrue(created)
                self.assertEqual(2, status)
                self.assertIn("MANUAL_ACTION_REQUIRED", errors.getvalue())
                self.assertEqual(custom, active.read_bytes())
                self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_quality_retirement_concurrent_removal_is_idempotent_but_replacement_is_preserved(self) -> None:
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                target = self.workspace / ("replaced" if replacement else "removed")
                target.mkdir()
                active = target / ".github/hooks/design-guard.json"
                active.parent.mkdir(parents=True)
                active.write_bytes(legacy_hook_bytes())
                custom = b'{"custom":"replacement after concurrent removal"}'
                original = self.module.os.replace

                def remove_before_move(source, destination):
                    if Path(str(source).removeprefix("\\\\?\\")) == active:
                        active.unlink()
                        if replacement:
                            active.write_bytes(custom)
                        raise FileNotFoundError("fixture concurrent removal before quarantine")
                    original(source, destination)

                output = io.StringIO()
                with mock.patch.object(self.module.os, "replace", remove_before_move), contextlib.redirect_stdout(output):
                    if replacement:
                        with self.assertRaises(FileNotFoundError):
                            self.module.retire_quality_hooks(ROOT, target)
                    else:
                        self.assertEqual(0, self.module.retire_quality_hooks(ROOT, target))
                if replacement:
                    self.assertEqual(custom, active.read_bytes())
                else:
                    self.assertFalse(active.exists())
                    self.assertIn("already absent at retirement", output.getvalue())
                    self.assertNotIn("retired hook inode retained", output.getvalue())
                self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_create_only_commit_never_clobbers_or_rolls_back_late_custom_file(self) -> None:
        for name in ("architrave.config.json", ".github/workflows/copilot-setup-steps.yml"):
            with self.subTest(name=name):
                target = self.workspace / uuid.uuid4().hex
                target.mkdir()
                destination = target / name
                custom = b"late custom contents"
                managed = self.module.ManagedRoot(target, "fixture")
                with self.assertRaises(FileExistsError):
                    with self.module.ManagedTransaction(managed):
                        managed.create_bytes(name, b"scaffold")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(custom)
                self.assertEqual(custom, destination.read_bytes())
                self.assertFalse((target / ".architrave-install-transaction").exists())


    def test_quality_retirement_absence_assertion_recovery_preserves_new_hook(self) -> None:
        target = self.workspace / "absence recovery"
        target.mkdir()
        active = target / ".github/hooks/design-guard.json"
        custom = b'{"custom":"new hook survives assertion recovery"}'
        product = target / "product.txt"
        product.write_bytes(b"before")
        managed = self.module.ManagedRoot(target, "fixture")
        plan = self.module.quality_hook_plan(managed, ROOT)
        original = self.module.ManagedTransaction._write_manifest

        def assertion_journal_failure(transaction, value):
            if value.get("applied") == 2:
                raise OSError("injected failure after absence assertion")
            original(transaction, value)
            if value.get("inFlight") == 1:
                active.parent.mkdir(parents=True, exist_ok=True)
                active.write_bytes(custom)

        with mock.patch.object(self.module.ManagedTransaction, "_write_manifest", assertion_journal_failure):
            with self.assertRaises(OSError):
                with self.module.ManagedTransaction(managed):
                    self.module.apply_quality_hook_plan(managed, plan)
                    managed.replace_bytes("product.txt", b"after")
        self.assertEqual(custom, active.read_bytes())
        self.assertEqual(b"before", product.read_bytes())
        self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_public_entrypoints_are_python_only_launch_shims(self) -> None:
        install_sh = (ROOT / "tools/install.sh").read_text(encoding="utf-8")
        update_sh = (ROOT / "tools/update.sh").read_text(encoding="utf-8")
        install_ps1 = (ROOT / "tools/install.ps1").read_text(encoding="utf-8")
        update_ps1 = (ROOT / "tools/update.ps1").read_text(encoding="utf-8")
        for content in (install_sh, update_sh, install_ps1, update_ps1):
            self.assertIn("install_update.py", content)
            self.assertIn("https://www.python.org/downloads/", content)
            self.assertNotIn("managed-paths", content.lower())
            self.assertNotIn("ManagedPaths", content)
            self.assertIn("sys.version_info", content)
        self.assertLess(len(install_sh.splitlines()), 20)
        self.assertLess(len(update_sh.splitlines()), 20)
        self.assertLess(len(install_ps1.splitlines()), 25)
        self.assertLess(len(update_ps1.splitlines()), 25)
        self.assertLess(
            install_sh.index("command -v python3"),
            install_sh.index("command -v python "),
        )
        self.assertLess(install_ps1.index("Get-Command py"), install_ps1.index("'python3'"))
        for removed in (
            "tools/managed-paths.sh",
            "tools/ManagedPaths.ps1",
            "scripts/test-managed-paths.ps1",
            "scripts/test-installers.sh",
            "scripts/test-installers.ps1",
        ):
            self.assertFalse((ROOT / removed).exists(), f"obsolete paired implementation remains: {removed}")

    def test_transaction_rolls_back_each_injected_replacement(self) -> None:
        target = self.workspace / "transaction target"
        target.mkdir()
        self.run_cli("install", "--profile", "knowledge", str(target))
        before = snapshot(target)
        for index in (0, 5, 10):
            self.run_cli(
                "update",
                str(target),
                expected=1,
                env={"ARCHITRAVE_INSTALL_FAIL_AFTER": str(index)},
            )
            self.assertEqual(before, snapshot(target))
            self.assertFalse((target / ".architrave-install.lock").exists())
            self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_fresh_install_failure_restores_exact_filesystem_shape(self) -> None:
        for index in (0, 8, 20):
            target = self.workspace / f"fresh failure {index}"
            target.mkdir()
            before = snapshot(target)
            self.run_cli(
                "install",
                "--profile",
                "knowledge",
                str(target),
                expected=1,
                env={"ARCHITRAVE_INSTALL_FAIL_AFTER": str(index)},
            )
            self.assertEqual(before, snapshot(target))

    def test_concurrent_lock_and_stale_transaction_recovery(self) -> None:
        target = self.workspace / "locked target"
        target.mkdir()
        self.run_cli("install", "--profile", "knowledge", str(target))
        before = snapshot(target)
        lock = target / ".architrave-install.lock"
        lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        self.run_cli("update", str(target), expected=1)
        self.assertTrue(lock.exists())
        lock.unlink()
        self.assertEqual(before, snapshot(target))

        transaction = target / ".architrave-install-transaction"
        (transaction / "backup").mkdir(parents=True)
        (transaction / "stage").mkdir()
        original = (target / ".gitignore").read_bytes()
        (transaction / "backup/0").write_bytes(original)
        (target / ".gitignore").write_text("corrupt\n", encoding="utf-8")
        (transaction / "manifest.json").write_text(
            json.dumps(
                {
                    "status": "prepared",
                    "applied": 0,
                    "operations": [
                        {
                            "kind": "write",
                            "relative": ".gitignore",
                            "stage": "stage/0",
                            "mode": 0o644,
                            "existed": True,
                            "backup": "backup/0",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        lock.write_text(json.dumps({"pid": 99999999}), encoding="utf-8")
        self.run_cli("update", str(target))
        self.assertFalse(lock.exists())
        self.assertFalse(transaction.exists())
        self.assertIn(".architrave/runs/", (target / ".gitignore").read_text(encoding="utf-8"))

    def test_empty_and_malformed_installer_lock_never_imply_dead_owner(self) -> None:
        for content in (b"", b"{partial", b'{"pid":null}', b'{"pid":true}'):
            with self.subTest(content=content):
                target = self.workspace / uuid.uuid4().hex
                target.mkdir()
                lock = target / ".architrave-install.lock"
                lock.write_bytes(content)
                with self.assertRaisesRegex(self.module.InstallerError, "ownership"):
                    with self.module.ManagedTransaction(self.module.ManagedRoot(target, "fixture")):
                        self.fail("Uncertain ownership was accepted")
                self.assertEqual(content, lock.read_bytes())
                self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_installer_peer_cannot_take_lock_before_owner_metadata_is_written(self) -> None:
        target = self.workspace / "initializing lock"
        target.mkdir()
        managed = self.module.ManagedRoot(target, "fixture")
        original = self.module.ManagedTransaction._lock_file
        checked = False

        def check_peer(transaction, descriptor, unlock=False):
            nonlocal checked
            original(transaction, descriptor, unlock)
            if not unlock and not checked:
                checked = True
                with self.assertRaises((self.module.InstallerError, OSError)):
                    with self.module.ManagedTransaction(self.module.ManagedRoot(target, "peer")):
                        self.fail("Peer entered before ownership publication")

        with mock.patch.object(self.module.ManagedTransaction, "_lock_file", check_peer):
            with self.module.ManagedTransaction(managed):
                self.assertTrue(checked)
        self.assertFalse((target / ".architrave-install.lock").exists())

    def test_stale_installer_lock_replacement_is_preserved_before_recovery(self) -> None:
        target = self.workspace / "replaced stale lock"
        target.mkdir()
        lock = target / ".architrave-install.lock"
        lock.write_text(json.dumps({"pid": 99999999}), encoding="utf-8")
        replacement = json.dumps({"pid": os.getpid(), "nonce": "b" * 32}).encode()

        def replace_before_recovery(_pid):
            new = target / "new-lock"
            new.write_bytes(replacement)
            os.replace(new, lock)
            return False

        with mock.patch.object(self.module, "_pid_alive", side_effect=replace_before_recovery):
            with self.assertRaises((self.module.InstallerError, PermissionError)):
                with self.module.ManagedTransaction(self.module.ManagedRoot(target, "fixture")):
                    self.fail("Replacement ownership was accepted")
        if os.name == "nt":
            self.assertEqual({"pid": 99999999}, json.loads(lock.read_text()))
            self.assertEqual(replacement, (target / "new-lock").read_bytes())
        else:
            self.assertEqual(replacement, lock.read_bytes())
        self.assertFalse((target / ".architrave-install-transaction").exists())

    def test_changed_installer_lock_is_not_unlinked_or_committed_on_exit(self) -> None:
        target = self.workspace / "changed owned lock"
        target.mkdir()
        lock = target / ".architrave-install.lock"
        product = target / "product.txt"
        product.write_bytes(b"before")
        replacement = b'{"custom":"owner data must survive"}'
        with self.assertRaises((self.module.InstallerError, PermissionError)):
            managed = self.module.ManagedRoot(target, "fixture")
            with self.module.ManagedTransaction(managed):
                managed.replace_bytes("product.txt", b"after")
                other = target / "replacement-lock"
                other.write_bytes(replacement)
                os.replace(other, lock)
        self.assertEqual(b"before", product.read_bytes())
        if os.name == "nt":
            self.assertEqual(replacement, other.read_bytes())
            self.assertFalse(lock.exists())
        else:
            self.assertEqual(replacement, lock.read_bytes())
            self.assertTrue((target / ".architrave-install-transaction").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
