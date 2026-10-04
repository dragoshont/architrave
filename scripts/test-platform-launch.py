#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from platform_launch import LaunchError, configured_shell_command


class PlatformLaunchTests(unittest.TestCase):
    @staticmethod
    def mapping(values: dict[str, str]):
        return lambda name: values.get(name)

    def test_windows_uses_available_powershell(self) -> None:
        command = configured_shell_command(
            "Write-Output ok",
            platform="windows",
            which=self.mapping({"powershell": "C:\\Power Shell\\powershell.exe"}),
        )
        self.assertEqual("C:\\Power Shell\\powershell.exe", command[0])
        self.assertEqual("Write-Output ok", command[-1])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
