#!/usr/bin/env python3
"""Focused tests for the canonical install/update implementation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "install_update.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("architrave_install_update", CLI)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load install_update.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> tuple[str, ...]:
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

    def setUp(self) -> None:
        self.workspace = ROOT / f".install-update-test-{uuid.uuid4().hex}"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace, ignore_errors=True)

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT,
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
        self.assertEqual(
            (application / ".github/hooks/design-guard.json").read_bytes(),
            (ROOT / "gates/hooks/design-guard.windows.json").read_bytes(),
        )

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
            5,
        )
        self.assertFalse((knowledge / ".github/agents/ui-visual.agent.md").exists())
        self.assertFalse(any(knowledge.glob("constitution-*.md")))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
