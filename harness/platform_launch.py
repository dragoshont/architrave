#!/usr/bin/env python3
"""Minimal platform command selection for configured repository recipes."""

from __future__ import annotations

import os
import shutil
import re
from typing import Sequence
from typing import Callable, Optional


Which = Callable[[str], Optional[str]]


class LaunchError(RuntimeError):
    pass


def reject_agent_harness(command: str | Sequence[str]) -> None:
    text = command if isinstance(command, str) else " ".join(command)
    if re.search(r"""(?i)(?:^|[\s;&|('"\\/])(?:copilot|claude|codex)(?:\.(?:exe|cmd|bat))?(?=$|[\s;&|)'"])""", text):
        raise LaunchError("agent CLI recipes are prohibited; use host-native structured delegation")


def configured_shell_command(
    command: str,
    *,
    platform: str | None = None,
    which: Which = shutil.which,
) -> list[str]:
    reject_agent_harness(command)
    effective = platform or ("windows" if os.name == "nt" else "posix")
    shell = which("bash") or which("sh")
    if shell:
        return [shell, "-c", command]
    if effective == "windows":
        cmd = which("cmd") or os.environ.get("COMSPEC")
        if cmd:
            return [cmd, "/d", "/s", "/c", command]
        raise LaunchError("no command shell is available; install Git Bash or ensure cmd.exe is on PATH")
    raise LaunchError("no POSIX shell is available")
