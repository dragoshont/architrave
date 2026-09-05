#!/usr/bin/env python3
"""Install Architrave Codex roles without touching provider or skill config."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path


BEGIN = "# BEGIN ARCHITRAVE MANAGED CODEX ROLES"
END = "# END ARCHITRAVE MANAGED CODEX ROLES"
ROLE_NAMES = {"architrave_tournament", "architrave_judge"}
ROLE_FILES = (
    "architrave-tournament.toml",
    "architrave-judge.toml",
)


class PreflightError(Exception):
    pass


@dataclass(frozen=True)
class Fingerprint:
    device: int
    inode: int
    mode: int
    attributes: int = 0


def fingerprint(path: Path) -> Fingerprint | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return Fingerprint(info.st_dev, info.st_ino, info.st_mode, getattr(info, "st_file_attributes", 0))


def require_directory(path: Path, label: str) -> Fingerprint:
    current = fingerprint(path)
    if current is None or not stat.S_ISDIR(current.mode) or stat.S_ISLNK(current.mode) or current.attributes & 0x400:
        raise PreflightError(f"{label} must be a real directory: {path}")
    return current


def validate_existing(path: Path, *, directory: bool) -> Fingerprint | None:
    current = fingerprint(path)
    if current is None:
        return None
    valid = stat.S_ISDIR(current.mode) if directory else stat.S_ISREG(current.mode)
    if not valid or stat.S_ISLNK(current.mode) or current.attributes & 0x400:
        kind = "directory" if directory else "regular file"
        raise PreflightError(f"target must be a non-symlink {kind}: {path}")
    return current


def ensure_contained(path: Path, root: Path) -> None:
    resolved_parent = path.parent.resolve(strict=True)
    try:
        resolved_parent.relative_to(root)
    except ValueError as error:
        raise PreflightError(f"target escaped repository root: {path}") from error


def revalidate(path: Path, expected: Fingerprint | None, *, directory: bool) -> None:
    actual = validate_existing(path, directory=directory)
    if actual != expected:
        raise RuntimeError(f"target changed after preflight: {path}")


def from_stat(info: os.stat_result) -> Fingerprint:
    return Fingerprint(info.st_dev, info.st_ino, info.st_mode, getattr(info, "st_file_attributes", 0))


def open_directory(root_fd: int, parts: tuple[str, ...], *, create: bool, created: list[tuple[str, ...]]) -> int:
    current_fd = os.dup(root_fd)
    walked: tuple[str, ...] = ()
    try:
        for part in parts:
            walked += (part,)
            try:
                before = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise PreflightError(f"directory disappeared after preflight: {'/'.join(walked)}")
                os.mkdir(part, mode=0o755, dir_fd=current_fd)
                created.append(walked)
                before = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
                raise PreflightError(f"directory path is not a real directory: {'/'.join(walked)}")
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            next_fd = os.open(part, flags, dir_fd=current_fd)
            if from_stat(os.fstat(next_fd)) != from_stat(before):
                os.close(next_fd)
                raise RuntimeError(f"directory changed while opening: {'/'.join(walked)}")
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def entry_fingerprint(parent_fd: int, name: str) -> Fingerprint | None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PreflightError(f"target must be a non-symlink regular file: {name}")
    return from_stat(info)


def read_entry(parent_fd: int, name: str, expected: Fingerprint) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        if from_stat(os.fstat(descriptor)) != expected:
            raise RuntimeError(f"file changed while opening: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def write_entry(parent_fd: int, name: str, content: bytes) -> None:
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
    finally:
        os.close(descriptor)


def same_open_directory(root_fd: int, parts: tuple[str, ...], opened_fd: int) -> bool:
    current_fd = open_directory(root_fd, parts, create=False, created=[])
    try:
        return from_stat(os.fstat(current_fd)) == from_stat(os.fstat(opened_fd))
    finally:
        os.close(current_fd)


def run_test_hook(index: int) -> None:
    if os.environ.get("ARCHITRAVE_CODEX_HOOK_AT") != str(index):
        return
    ready = os.environ.get("ARCHITRAVE_CODEX_READY_FILE")
    fifo = os.environ.get("ARCHITRAVE_CODEX_CONTINUE_FIFO")
    if not ready or not fifo:
        raise RuntimeError("transaction test hook is incomplete")
    Path(ready).write_text("ready\n", encoding="ascii")
    with open(fifo, "rb", buffering=0) as stream:
        stream.read(1)


def mkdir_checked_windows(path: Path, root: Path, created: list[Path]) -> None:
    if path == root:
        return
    if path.exists():
        validate_existing(path, directory=True)
        ensure_contained(path / ".containment-probe", root)
        return
    mkdir_checked_windows(path.parent, root, created)
    parent_before = require_directory(path.parent, "parent")
    ensure_contained(path, root)
    path.mkdir()
    revalidate(path.parent, parent_before, directory=True)
    validate_existing(path, directory=True)
    created.append(path)


def lock_windows_directory(path: Path) -> object:
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80,  # FILE_READ_ATTRIBUTES
        0x1 | 0x2,  # FILE_SHARE_READ | FILE_SHARE_WRITE; deliberately no DELETE
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), f"cannot lock directory: {path}")
    return handle


def close_windows_handle(handle: object) -> None:
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


def marker_indices(text: str) -> tuple[list[str], list[int], list[int]]:
    lines = text.splitlines(keepends=True)
    begins: list[int] = []
    ends: list[int] = []
    state = "normal"
    escaped = False
    for line_index, raw_line in enumerate(lines):
        line = raw_line.rstrip("\r\n")
        if state == "normal":
            if line.strip() == BEGIN:
                begins.append(line_index)
            elif line.strip() == END:
                ends.append(line_index)
        offset = 0
        while offset < len(line):
            if state == "normal":
                if line[offset] == "#":
                    break
                if line.startswith('"""', offset):
                    state, offset = "multiline-basic", offset + 3
                    continue
                if line.startswith("'''", offset):
                    state, offset = "multiline-literal", offset + 3
                    continue
                if line[offset] == '"':
                    state = "basic"
                elif line[offset] == "'":
                    state = "literal"
                offset += 1
            elif state == "basic":
                if escaped:
                    escaped = False
                elif line[offset] == "\\":
                    escaped = True
                elif line[offset] == '"':
                    state = "normal"
                offset += 1
            elif state == "literal":
                if line[offset] == "'":
                    state = "normal"
                offset += 1
            elif state == "multiline-basic":
                if escaped:
                    escaped, offset = False, offset + 1
                elif line[offset] == "\\":
                    escaped, offset = True, offset + 1
                elif line.startswith('"""', offset):
                    state, offset = "normal", offset + 3
                else:
                    offset += 1
            elif line.startswith("'''", offset):
                state, offset = "normal", offset + 3
            else:
                offset += 1
        if state in {"basic", "literal"}:
            state, escaped = "normal", False
    return lines, begins, ends


def read_regular_file(path: Path, expected: Fingerprint, parent: Fingerprint) -> bytes:
    parent_fd: int | None = None
    descriptor: int | None = None
    try:
        if os.name == "nt":
            # os.O_NONBLOCK does not exist on Windows (no FIFO semantics to
            # guard against there), so it must not be referenced in this
            # branch's flags.
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
        else:
            flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
            parent_fd = os.open(
                path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            if from_stat(os.fstat(parent_fd)) != parent:
                raise PreflightError(f"config parent changed while opening: {path.parent}")
            descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        actual = from_stat(os.fstat(descriptor))
        if actual != expected or not stat.S_ISREG(actual.mode) or stat.S_ISLNK(actual.mode):
            raise PreflightError(f"config changed or is not a non-symlink regular file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as error:
        raise PreflightError(f"cannot safely read config: {path}: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def decode_config(path: Path) -> tuple[str, str, bool]:
    parent = validate_existing(path.parent, directory=True)
    if parent is None:
        return "", "\n", True
    expected = validate_existing(path, directory=False)
    if expected is None:
        return "", "\n", True
    raw = read_regular_file(path, expected, parent)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PreflightError(f"config is not valid UTF-8: {path}") from error
    without_crlf = raw.replace(b"\r\n", b"")
    has_crlf = b"\r\n" in raw
    if b"\r" in without_crlf or (has_crlf and b"\n" in without_crlf):
        raise PreflightError(f"config has mixed newline styles: {path}")
    return text, "\r\n" if has_crlf else "\n", text.endswith(("\n", "\r"))


def parse_toml(text: str, label: str) -> dict[str, object]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PreflightError(f"invalid TOML in {label}: {error}") from error


def canonical_block(kit: Path, newline: str) -> str:
    text = (kit / ".codex/config.toml").read_text(encoding="utf-8")
    _, begins, ends = marker_indices(text)
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        raise PreflightError("canonical config must contain one managed block")
    return text.strip("\r\n").replace("\r\n", "\n").replace("\n", newline)


def build_config(kit: Path, path: Path) -> bytes:
    text, newline, final_newline = decode_config(path)
    parse_toml(text, str(path))
    lines, begins, ends = marker_indices(text)
    if not begins and not ends:
        start = end = None
        unmanaged = text
    elif len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        start, end = begins[0], ends[0]
        unmanaged = "".join(lines[:start] + lines[end + 1 :])
    else:
        raise PreflightError("duplicate, unmatched, or reversed managed markers")
    data = parse_toml(unmanaged, "unmanaged config")
    agents = data.get("agents", {})
    if isinstance(agents, dict) and ROLE_NAMES.intersection(agents):
        raise PreflightError("unmanaged Architrave role collision")
    block = canonical_block(kit, newline)
    if start is not None and end is not None:
        candidate = "".join(lines[:start]) + block
        suffix = "".join(lines[end + 1 :])
        if suffix:
            candidate += newline + suffix
        elif final_newline:
            candidate += newline
    elif not text:
        candidate = block + newline
    else:
        base = text[: -len(newline)] if final_newline else text
        candidate = base + newline + newline + block + (newline if final_newline else "")
    parse_toml(candidate, "candidate config")
    return candidate.encode("utf-8")


def planned_outputs(kit: Path, target: Path) -> list[tuple[Path, bytes]]:
    output: list[tuple[Path, bytes]] = []
    for filename in ROLE_FILES:
        source = kit / ".codex/agents" / filename
        if not source.is_file():
            raise PreflightError(f"missing generated role: {source}")
        output.append((target / ".codex/agents" / filename, source.read_bytes()))
    config = target / ".codex/config.toml"
    output.append((config, build_config(kit, config)))
    return output


def apply_outputs_windows(outputs: list[tuple[Path, bytes]], target: Path) -> None:
    root = target.resolve(strict=True)
    root_fingerprint = require_directory(root, "target")
    expected: dict[Path, Fingerprint | None] = {}
    for destination, _ in outputs:
        validate_existing(destination.parent, directory=True)
        expected[destination] = validate_existing(destination, directory=False)
    transaction = Path(tempfile.mkdtemp(prefix=".architrave-codex-txn-", dir=root))
    records: list[tuple[Path, Path, Path | None]] = []
    created_dirs: list[Path] = []
    directory_handles: list[object] = [lock_windows_directory(root)]
    keep_recovery = False
    try:
        for index, (destination, content) in enumerate(outputs):
            stage = transaction / f"stage-{index}"
            stage.write_bytes(content)
            backup = None
            if expected[destination] is not None:
                revalidate(destination, expected[destination], directory=False)
                backup = transaction / f"backup-{index}"
                shutil.copy2(destination, backup, follow_symlinks=False)
            records.append((destination, stage, backup))
        committed: list[tuple[Path, Path | None]] = []
        fail_after = os.environ.get("ARCHITRAVE_CODEX_FAIL_AFTER")
        try:
            for index, (destination, stage, backup) in enumerate(records):
                if fail_after is not None and int(fail_after) == index:
                    raise OSError(f"injected failure before replacement {index}")
                revalidate(root, root_fingerprint, directory=True)
                mkdir_checked_windows(destination.parent, root, created_dirs)
                directory_handles.append(lock_windows_directory(destination.parent))
                ensure_contained(destination, root)
                if validate_existing(destination, directory=False) != expected[destination]:
                    raise OSError(f"destination changed after preflight: {destination}")
                os.replace(stage, destination)
                committed.append((destination, backup))
        except Exception as error:
            rollback_errors: list[str] = []
            fail_rollback = os.environ.get("ARCHITRAVE_CODEX_FAIL_ROLLBACK_AT")
            for rollback_index, (destination, backup) in enumerate(reversed(committed)):
                try:
                    if fail_rollback is not None and int(fail_rollback) == rollback_index:
                        raise OSError(f"injected rollback failure {rollback_index}")
                    if backup is None:
                        destination.unlink(missing_ok=True)
                    else:
                        shutil.copy2(backup, destination, follow_symlinks=False)
                except OSError as rollback_error:
                    rollback_errors.append(f"{destination}: {rollback_error}")
            for handle in reversed(directory_handles[1:]):
                close_windows_handle(handle)
            directory_handles = directory_handles[:1]
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_errors:
                keep_recovery = True
                print(f"codex-roles: recovery data retained at {transaction}", file=sys.stderr)
                raise RuntimeError("rollback incomplete: " + "; ".join(rollback_errors)) from error
            raise RuntimeError(f"transaction rolled back: {error}") from error
    finally:
        for handle in reversed(directory_handles):
            close_windows_handle(handle)
        if not keep_recovery:
            shutil.rmtree(transaction, ignore_errors=True)


def apply_outputs(outputs: list[tuple[Path, bytes]], target: Path) -> None:
    if os.name == "nt":
        apply_outputs_windows(outputs, target)
        return
    root = target.resolve(strict=True)
    root_fingerprint = require_directory(root, "target")
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    transaction_name = f".architrave-codex-txn-{uuid.uuid4().hex}"
    os.mkdir(transaction_name, mode=0o700, dir_fd=root_fd)
    transaction_fd = os.open(
        transaction_name,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_fd,
    )
    created_dirs: list[tuple[str, ...]] = []
    records: list[tuple[tuple[str, ...], str, str | None, Fingerprint | None]] = []
    keep_recovery = False
    try:
        for index, (destination, content) in enumerate(outputs):
            relative = destination.relative_to(root).parts
            try:
                parent_fd = open_directory(root_fd, relative[:-1], create=False, created=[])
            except PreflightError:
                if fingerprint(destination.parent) is not None:
                    raise
                expected = None
                backup_name = None
            else:
                try:
                    expected = entry_fingerprint(parent_fd, relative[-1])
                    backup_name = None
                    if expected is not None:
                        backup_name = f"backup-{index}"
                        write_entry(transaction_fd, backup_name, read_entry(parent_fd, relative[-1], expected))
                finally:
                    os.close(parent_fd)
            stage_name = f"stage-{index}"
            write_entry(transaction_fd, stage_name, content)
            records.append((relative, stage_name, backup_name, expected))
        committed: list[tuple[tuple[str, ...], int, str | None]] = []
        fail_after = os.environ.get("ARCHITRAVE_CODEX_FAIL_AFTER")
        try:
            for index, (relative, stage_name, backup_name, expected) in enumerate(records):
                if fail_after is not None and int(fail_after) == index:
                    raise OSError(f"injected failure before replacement {index}")
                run_test_hook(index)
                if from_stat(os.fstat(root_fd)) != root_fingerprint or fingerprint(root) != root_fingerprint:
                    raise OSError("target root changed after preflight")
                parent_fd = open_directory(root_fd, relative[:-1], create=True, created=created_dirs)
                current = entry_fingerprint(parent_fd, relative[-1])
                if current != expected:
                    os.close(parent_fd)
                    raise OSError(f"destination changed after preflight: {'/'.join(relative)}")
                os.replace(stage_name, relative[-1], src_dir_fd=transaction_fd, dst_dir_fd=parent_fd)
                committed.append((relative, parent_fd, backup_name))
                if not same_open_directory(root_fd, relative[:-1], parent_fd):
                    raise OSError(f"parent moved outside target during commit: {'/'.join(relative[:-1])}")
        except Exception as error:
            rollback_errors: list[str] = []
            fail_rollback = os.environ.get("ARCHITRAVE_CODEX_FAIL_ROLLBACK_AT")
            for rollback_index, (relative, parent_fd, backup_name) in enumerate(reversed(committed)):
                try:
                    if fail_rollback is not None and int(fail_rollback) == rollback_index:
                        raise OSError(f"injected rollback failure {rollback_index}")
                    if backup_name is None:
                        os.unlink(relative[-1], dir_fd=parent_fd)
                    else:
                        os.replace(backup_name, relative[-1], src_dir_fd=transaction_fd, dst_dir_fd=parent_fd)
                except OSError as rollback_error:
                    rollback_errors.append(f"{'/'.join(relative)}: {rollback_error}")
                finally:
                    os.close(parent_fd)
            for directory in sorted(created_dirs, key=len, reverse=True):
                try:
                    parent_fd = open_directory(root_fd, directory[:-1], create=False, created=[])
                    try:
                        os.rmdir(directory[-1], dir_fd=parent_fd)
                    finally:
                        os.close(parent_fd)
                except OSError:
                    pass
            if rollback_errors:
                keep_recovery = True
                print(f"codex-roles: recovery data retained at {root / transaction_name}", file=sys.stderr)
                raise RuntimeError("rollback incomplete: " + "; ".join(rollback_errors)) from error
            raise RuntimeError(f"transaction rolled back: {error}") from error
        for _, parent_fd, _ in committed:
            os.close(parent_fd)
    finally:
        if not keep_recovery:
            for name in os.listdir(transaction_fd):
                os.unlink(name, dir_fd=transaction_fd)
            os.close(transaction_fd)
            os.rmdir(transaction_name, dir_fd=root_fd)
        else:
            os.close(transaction_fd)
        os.close(root_fd)


def main() -> int:
    if sys.version_info < (3, 11):
        print("codex-roles: Python 3.11+ is required", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        kit = args.kit.resolve(strict=True)
        target = args.target.resolve(strict=True)
        outputs = planned_outputs(kit, target)
        if not args.preflight:
            apply_outputs(outputs, target)
    except PreflightError as error:
        print(f"codex-roles: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"codex-roles: {error}", file=sys.stderr)
        return 1
    if not args.preflight:
        # Plain ASCII only: Windows stdout falls back to the legacy ANSI
        # codepage (e.g. cp1252) once redirected, which cannot encode
        # non-ASCII symbols such as U+2713 and would crash after the
        # transaction already succeeded.
        print("  ok Codex roles installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())