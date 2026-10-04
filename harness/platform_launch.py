#!/usr/bin/env python3
"""Minimal platform command selection for configured repository recipes."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Callable


Which = Callable[[str], str | None]


class LaunchError(RuntimeError):
    pass


def configured_shell_command(
    command: str,
    *,
    platform: str | None = None,
    which: Which = shutil.which,
) -> list[str]:
    effective = platform or ("windows" if os.name == "nt" else "posix")
    if effective == "windows":
        executable = which("pwsh") or which("powershell")
        if executable:
            prefix = [executable, "-NoProfile"]
            if Path(executable).name.lower().startswith("powershell"):
                prefix.extend(["-ExecutionPolicy", "Bypass"])
            return [*prefix, "-Command", command]
        shell = which("sh") or which("bash")
        if shell:
            return [shell, "-c", command]
        raise LaunchError(
            "no command shell is available; install PowerShell or a POSIX shell"
        )
    shell = which("sh") or which("bash")
    if shell:
        return [shell, "-c", command]
    raise LaunchError("no POSIX shell is available")
