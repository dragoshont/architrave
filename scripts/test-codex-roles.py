#!/usr/bin/env python3
"""Focused tests for transactional Codex role delivery."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "tools/codex-roles.py"


def digest(root: Path) -> str:
    result = hashlib.sha256()
    for item in sorted(root.rglob("*")):
        if item.is_file() and not item.is_symlink():
            result.update(item.relative_to(root).as_posix().encode())
            result.update(item.read_bytes())
    return result.hexdigest()


def invoke(
    target: Path,
    expected: int = 0,
    env: dict[str, str] | None = None,
    *,
    preflight: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(HELPER), "--kit", str(ROOT), "--target", str(target)]
    if preflight:
        command.append("--preflight")
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"command timed out: {' '.join(command)}") from error
    if process.returncode != expected:
        raise AssertionError(f"expected {expected}, got {process.returncode}: {process.stderr}")
    return process


def config(target: Path, content: bytes) -> Path:
    path = target / ".codex/config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        fresh = base / "fresh"
        fresh.mkdir()
        invoke(fresh)
        parsed = tomllib.loads((fresh / ".codex/config.toml").read_text())
        assert set(parsed["agents"]) == {"architrave_tournament", "architrave_judge"}
        assert len(list((fresh / ".codex/agents").glob("*.toml"))) == 2
        assert not (fresh / ".agents/skills").exists()
        before = digest(fresh)
        invoke(fresh)
        assert digest(fresh) == before
        print("ok    fresh role install and idempotency")

        crlf = base / "crlf"
        crlf.mkdir()
        config(crlf, b'[user]\r\nname = "Scoala"\r\n')
        invoke(crlf)
        raw = (crlf / ".codex/config.toml").read_bytes()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
        print("ok    CRLF preservation")

        invalid = {
            "mixed": b"x = 1\r\ny = 2\n",
            "utf8": b'x = "\xff"\n',
            "collision": b'[agents.architrave_judge]\ndescription = "mine"\n',
            "marker": (BEGIN := "# BEGIN ARCHITRAVE MANAGED CODEX ROLES\n").encode(),
        }
        for name, content in invalid.items():
            target = base / name
            target.mkdir()
            config(target, content)
            original = digest(target)
            invoke(target, 2)
            assert digest(target) == original
        print("ok    malformed input fails without writes")

        symlink = base / "symlink"
        symlink.mkdir()
        outside = base / "outside"
        outside.mkdir()
        (symlink / ".codex").symlink_to(outside, target_is_directory=True)
        invoke(symlink, 2)
        assert not any(outside.iterdir())
        print("ok    symlink target rejected")

        unsafe_config = base / "unsafe-config"
        unsafe_config.mkdir()
        external_config = base / "external-config.toml"
        external_content = b'[user]\nname = "outside"\n'
        external_config.write_bytes(external_content)
        config_link = unsafe_config / ".codex/config.toml"
        config_link.parent.mkdir()
        config_link.symlink_to(external_config)
        invoke(unsafe_config, 2)
        invoke(unsafe_config, 2, preflight=True)
        assert external_config.read_bytes() == external_content
        assert not (unsafe_config / ".codex/agents").exists()
        print("ok    external config symlink rejected before apply and preflight")

        directory_config = base / "directory-config"
        directory_config.mkdir()
        config_path = directory_config / ".codex/config.toml"
        config_path.parent.mkdir()
        config_path.mkdir()
        invoke(directory_config, 2)
        invoke(directory_config, 2, preflight=True)
        print("ok    non-regular config rejected before apply and preflight")

        if os.name != "nt" and hasattr(os, "mkfifo"):
            fifo_config = base / "fifo-config"
            fifo_config.mkdir()
            config_path = fifo_config / ".codex/config.toml"
            config_path.parent.mkdir()
            os.mkfifo(config_path)
            invoke(fifo_config, 2)
            invoke(fifo_config, 2, preflight=True)
            print("ok    FIFO config rejected without blocking")

        rollback = base / "rollback"
        rollback.mkdir()
        config(rollback, b'[user]\nname = "before"\n')
        original = digest(rollback)
        for position in range(3):
            invoke(rollback, 1, {"ARCHITRAVE_CODEX_FAIL_AFTER": str(position)})
            assert digest(rollback) == original
            assert not (rollback / ".codex/agents").exists()
        print("ok    every replacement position rolls back and removes directories")

        rollback_failure = base / "rollback-failure"
        rollback_failure.mkdir()
        config(rollback_failure, b'[user]\nname = "before"\n')
        process = invoke(
            rollback_failure,
            1,
            {
                "ARCHITRAVE_CODEX_FAIL_AFTER": "2",
                "ARCHITRAVE_CODEX_FAIL_ROLLBACK_AT": "0",
            },
        )
        recovery = list(rollback_failure.glob(".architrave-codex-txn-*"))
        assert len(recovery) == 1 and "recovery data retained" in process.stderr
        assert any(recovery[0].iterdir())
        print("ok    rollback failure retains named recovery data")

        if os.name != "nt" and hasattr(os, "mkfifo"):
            race = base / "parent-race"
            race.mkdir()
            config(race, b'[user]\nname = "before"\n')
            original = digest(race)
            outside = base / "race-outside"
            outside.mkdir()
            ready = base / "race-ready"
            fifo = base / "race-fifo"
            os.mkfifo(fifo)
            environment = {
                **os.environ,
                "ARCHITRAVE_CODEX_HOOK_AT": "0",
                "ARCHITRAVE_CODEX_READY_FILE": str(ready),
                "ARCHITRAVE_CODEX_CONTINUE_FIFO": str(fifo),
            }
            process = subprocess.Popen(
                [sys.executable, str(HELPER), "--kit", str(ROOT), "--target", str(race)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            deadline = time.monotonic() + 10
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "transaction never reached parent-swap hook"
            original_codex = race / ".codex-original"
            (race / ".codex").rename(original_codex)
            (race / ".codex").symlink_to(outside, target_is_directory=True)
            with fifo.open("wb", buffering=0) as stream:
                stream.write(b"x")
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 1, (stdout, stderr)
            (race / ".codex").unlink()
            original_codex.rename(race / ".codex")
            assert not any(outside.iterdir())
            assert digest(race) == original
            assert not list(race.glob(".architrave-codex-txn-*"))
            print("ok    synchronized parent swap writes nothing outside target")

    print("CODEX-ROLES: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())