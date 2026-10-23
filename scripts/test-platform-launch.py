#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys
import os
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from platform_launch import LaunchError, configured_shell_command


class PlatformLaunchTests(unittest.TestCase):
    @staticmethod
    def mapping(values: dict[str, str]):
        return lambda name: values.get(name)

    def test_windows_without_posix_shell_uses_cmd(self) -> None:
        command = configured_shell_command(
            "echo ok",
            platform="windows",
            which=self.mapping({"cmd": "C:\\Windows\\System32\\cmd.exe", "powershell": "C:\\ps.exe"}),
        )
        self.assertEqual(["C:\\Windows\\System32\\cmd.exe", "/d", "/s", "/c", "echo ok"], command)

    def test_windows_never_selects_powershell(self) -> None:
        with mock.patch.dict(os.environ, {"COMSPEC": ""}), self.assertRaisesRegex(LaunchError, "no command shell"):
            configured_shell_command("echo ok", platform="windows",
                                     which=self.mapping({"pwsh": "C:\\pwsh.exe", "powershell": "C:\\ps.exe"}))

    def test_windows_falls_back_to_shell_for_repository_recipes(self) -> None:
        command = configured_shell_command(
            "echo ok",
            platform="windows",
            which=self.mapping({"sh": "C:\\Tools\\sh.exe"}),
        )
        self.assertEqual(["C:\\Tools\\sh.exe", "-c", "echo ok"], command)

    def test_missing_shell_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(LaunchError, "no POSIX shell"):
            configured_shell_command("true", platform="posix", which=self.mapping({}))

    def test_posix_prefers_bash_for_backward_compatible_recipes(self) -> None:
        command = configured_shell_command(
            "[[ -n value ]]",
            platform="posix",
            which=self.mapping({"bash": "/bin/bash", "sh": "/bin/sh"}),
        )
        self.assertEqual("/bin/bash", command[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
