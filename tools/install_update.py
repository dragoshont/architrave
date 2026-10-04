#!/usr/bin/env python3
"""Canonical, stdlib-only Architrave repository installer and updater."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import uuid


BEGIN = "<!-- architrave:begin -->"
END = "<!-- architrave:end -->"
KNOWLEDGE_AGENTS = (
    "architrave",
    "adversarial-judge",
    "tournament-analyst",
    "product-research",
    "runtime-observer",
)
GATE_FILES = (
    "checks.sh",
    "checks.ps1",
    "reconcile.sh",
    "reconcile.ps1",
    "quality-gate.sh",
    "quality-gate.ps1",
    "backend-checks.sh",
    "backend-checks.ps1",
    "gate_runner.py",
    "rubric.md",
)
IGNORE_RULES = (
    ".architrave/runs/",
    ".architrave/worktrees/",
    ".architrave/runtime.key",
    ".architrave/resources.lock",
)
APPLICATION_CONFIG = """{
  "platform": "web",
  "stack": "react",
  "designSource": { "type": "storybook", "path": ".storybook", "url": "http://localhost:6006" },
  "designMap": "docs/design/ui-map.json",
  "tokens": "tokens/tokens.json",
  "applyTo": ["src/**"],
  "build": "npm run build",
  "test": "npm test",
  "learning": {
    "runArtifactsPath": ".architrave/runs",
    "repoProfilePath": ".architrave/learning/repo-profile.md",
    "lessonsPath": ".architrave/learning/repo-lessons.md",
    "capture": ["run-artifacts", "gate-results", "judge-verdicts", "runtime-evidence", "repo-profile", "lessons"],
    "redactionPolicy": "no-secrets",
    "staleFactPolicy": "validate-before-use",
    "promotionPolicy": "approval-required",
    "promoteAfterOccurrences": 2,
    "promoteTargets": ["architrave.config.json", "AGENTS.md", ".github/instructions", "docs"]
  }
}
"""


class InstallerError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _is_real_dir(info: os.stat_result) -> bool:
    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _is_reparse(info)


def _is_regular_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _is_reparse(info)


def require_source_file(path: Path, label: str) -> None:
    info = _lstat(path)
    if info is None or not _is_regular_file(info):
        raise InstallerError(f"{label}: packaged source is not a regular non-link file: {path}")
    try:
        with path.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        raise InstallerError(f"{label}: packaged source is not readable: {path}") from exc


def require_source_tree(path: Path, label: str) -> None:
    info = _lstat(path)
    if info is None or not _is_real_dir(info):
        raise InstallerError(f"{label}: packaged source is not a real directory: {path}")
    for current, directories, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            entry = current_path / name
            entry_info = _lstat(entry)
            if entry_info is None:
                raise InstallerError(f"{label}: packaged source disappeared: {entry}")
            if name in directories:
                valid = _is_real_dir(entry_info)
            else:
                valid = _is_regular_file(entry_info)
            if not valid:
                raise InstallerError(f"{label}: packaged source tree contains an unsafe entry: {entry}")
            if name in files:
                require_source_file(entry, label)


class ManagedRoot:
    """Fail-closed writes confined to one canonical repository root."""

    def __init__(self, root: Path, label: str) -> None:
        try:
            resolved = root.expanduser().resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise InstallerError(f"{label}: target dir not found: {root}") from exc
        info = _lstat(resolved)
        if info is None or not _is_real_dir(info):
            raise InstallerError(f"{label}: target root must resolve to a real directory")
        self.root = resolved
        self.label = label

    def path(self, relative: str) -> Path:
        pure = PurePosixPath(relative)
        raw_parts = relative.split("/")
        if (
            not relative
            or pure.is_absolute()
            or "\\" in relative
            or any(part in ("", ".", "..") for part in raw_parts)
        ):
            raise InstallerError(f"{self.label}: unsafe managed path '{relative}'")
        candidate = self.root.joinpath(*pure.parts)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise InstallerError(f"{self.label}: managed path escapes target root: {relative}") from exc
        return candidate

    def preflight_dir(self, relative: str) -> None:
        path = self.path(relative)
        current = self.root
        for part in path.relative_to(self.root).parts:
            current /= part
            info = _lstat(current)
            if info is None:
                return
            if not _is_real_dir(info):
                raise InstallerError(
                    f"{self.label}: unsafe managed path '{relative}': "
                    f"component '{part}' is not a real directory"
                )

    def require_dir(self, relative: str) -> Path:
        self.preflight_dir(relative)
        path = self.path(relative)
        info = _lstat(path)
        if info is None or not _is_real_dir(info):
            raise InstallerError(
                f"{self.label}: unsafe managed path '{relative}': directory is missing or unsafe"
            )
        return path

    def ensure_dir(self, relative: str) -> Path:
        path = self.path(relative)
        current = self.root
        built: list[str] = []
        for part in path.relative_to(self.root).parts:
            current /= part
            built.append(part)
            info = _lstat(current)
            if info is None:
                current.mkdir()
            elif not _is_real_dir(info):
                raise InstallerError(
                    f"{self.label}: unsafe managed path '{relative}': "
                    f"component '{part}' is not a real directory"
                )
            self.require_dir("/".join(built))
        return path

    def preflight_file(self, relative: str) -> None:
        path = self.path(relative)
        parent = path.parent
        if parent != self.root:
            self.preflight_dir(parent.relative_to(self.root).as_posix())
        info = _lstat(path)
        if info is not None and not _is_regular_file(info):
            raise InstallerError(
                f"{self.label}: unsafe managed path '{relative}': "
                "destination is not a regular non-link file"
            )

    def require_file(self, relative: str) -> Path:
        self.preflight_file(relative)
        path = self.path(relative)
        info = _lstat(path)
        if info is None or not _is_regular_file(info):
            raise InstallerError(
                f"{self.label}: unsafe managed path '{relative}': regular file is missing or unsafe"
            )
        return path

    def preflight_tree(self, relative: str) -> None:
        self.preflight_dir(relative)
        path = self.path(relative)
        info = _lstat(path)
        if info is None:
            return
        if not _is_real_dir(info):
            raise InstallerError(f"{self.label}: unsafe managed tree '{relative}'")
        for current, directories, files in os.walk(path, followlinks=False):
            current_path = Path(current)
            for name in (*directories, *files):
                entry = current_path / name
                entry_info = _lstat(entry)
                if entry_info is None:
                    raise InstallerError(f"{self.label}: managed entry disappeared: {entry}")
                if name in directories:
                    valid = _is_real_dir(entry_info)
                else:
                    valid = _is_regular_file(entry_info)
                if not valid:
                    raise InstallerError(
                        f"{self.label}: unsafe managed tree '{relative}': unsafe entry '{entry}'"
                    )

    def _write_temp(self, parent: Path, data: bytes, mode: int) -> Path:
        if parent != self.root:
            self.require_dir(parent.relative_to(self.root).as_posix())
        temp = parent / f".architrave.tmp.{uuid.uuid4().hex}"
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp, stat.S_IMODE(mode))
            return temp
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temp.unlink(missing_ok=True)
            raise

    def replace_bytes(self, relative: str, data: bytes, mode: int = 0o644) -> None:
        self.preflight_file(relative)
        path = self.path(relative)
        parent_relative = path.parent.relative_to(self.root).as_posix()
        parent = self.root if path.parent == self.root else self.require_dir(parent_relative)
        temp = self._write_temp(parent, data, mode)
        try:
            self.preflight_file(relative)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        self.require_file(relative)

    def create_bytes(self, relative: str, data: bytes, mode: int = 0o644) -> None:
        self.preflight_file(relative)
        path = self.path(relative)
        if _lstat(path) is not None:
            raise InstallerError(f"{self.label}: managed destination already exists: {relative}")
        parent_relative = path.parent.relative_to(self.root).as_posix()
        if path.parent != self.root:
            self.require_dir(parent_relative)
        try:
            self.preflight_file(relative)
            if _lstat(path) is not None:
                raise InstallerError(f"{self.label}: managed destination appeared before create: {relative}")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IMODE(mode))
        except FileExistsError as exc:
            raise InstallerError(
                f"{self.label}: managed destination appeared before create: {relative}"
            ) from exc
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(path, stat.S_IMODE(mode))
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            path.unlink(missing_ok=True)
            raise
        self.require_file(relative)

    def replace_file(self, source: Path, relative: str) -> None:
        require_source_file(source, self.label)
        source_info = source.stat(follow_symlinks=False)
        self.replace_bytes(relative, source.read_bytes(), stat.S_IMODE(source_info.st_mode))

    def create_file(self, source: Path, relative: str) -> None:
        require_source_file(source, self.label)
        source_info = source.stat(follow_symlinks=False)
        self.create_bytes(relative, source.read_bytes(), stat.S_IMODE(source_info.st_mode))

    def remove_file(self, relative: str) -> None:
        self.preflight_file(relative)
        path = self.path(relative)
        if _lstat(path) is None:
            return
        self.require_file(relative)
        path.unlink()
        if _lstat(path) is not None:
            raise InstallerError(f"{self.label}: managed file remains after removal: {relative}")

    def copy_tree(self, source: Path, relative: str) -> None:
        require_source_tree(source, self.label)
        self.preflight_tree(relative)
        self.ensure_dir(relative)
        for current, directories, files in os.walk(source, followlinks=False):
            directories[:] = sorted(name for name in directories if name != "__pycache__")
            files = sorted(name for name in files if not name.endswith(".pyc"))
            current_path = Path(current)
            suffix = current_path.relative_to(source)
            destination_dir = PurePosixPath(relative, *suffix.parts).as_posix()
            self.ensure_dir(destination_dir)
            for name in files:
                destination = PurePosixPath(destination_dir, name).as_posix()
                self.replace_file(current_path / name, destination)
        self.preflight_tree(relative)


class JsonObject(list[tuple[str, object]]):
    pass


def read_update_profile(config_path: Path) -> str:
    try:
        parsed = json.loads(
            config_path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=lambda pairs: JsonObject(pairs),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallerError(f"update: invalid architrave.config.json ({exc})", 2) from exc
    if not isinstance(parsed, JsonObject):
        raise InstallerError("update: invalid architrave.config.json (root must be a JSON object)", 2)
    kind_like = [key for key, _ in parsed if key.lower() == "kind"]
    if any(key != "kind" for key in kind_like):
        raise InstallerError(
            "update: invalid architrave.config.json (kind property is case-sensitive)", 2
        )
    kinds = [value for key, value in parsed if key == "kind"]
    if len(kinds) > 1:
        raise InstallerError(
            "update: invalid architrave.config.json (kind must occur at most once)", 2
        )
    if not kinds:
        return "application"
    if kinds[0] != "knowledge" or not isinstance(kinds[0], str):
        raise InstallerError(
            "update: invalid architrave.config.json (kind must be absent or 'knowledge')", 2
        )
    return "knowledge"


def plugin_version(kit: Path, label: str) -> str:
    try:
        manifest = json.loads((kit / "plugin.json").read_text(encoding="utf-8"))
        version = manifest["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InstallerError(f"{label}: plugin version is invalid") from exc
    if not isinstance(version, str) or not version:
        raise InstallerError(f"{label}: plugin version is invalid")
    return version


def preflight_common(
    managed: ManagedRoot,
    kit: Path,
    *,
    source_trees: tuple[str, ...],
    destination_trees: tuple[str, ...],
    destination_files: tuple[str, ...],
    source_files: tuple[str, ...],
) -> None:
    for source_tree in source_trees:
        require_source_tree(kit / source_tree, managed.label)
    for source_file in source_files:
        require_source_file(kit / source_file, managed.label)
    for destination_tree in destination_trees:
        managed.preflight_tree(destination_tree)
    for destination_file in destination_files:
        managed.preflight_file(destination_file)


def preflight_text(managed: ManagedRoot, relative: str) -> None:
    path = managed.path(relative)
    if _lstat(path) is None:
        return
    try:
        managed.require_file(relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallerError(f"{managed.label}: managed text file is not readable UTF-8: {relative}") from exc


def run_codex(kit: Path, target: Path, *, preflight: bool, label: str) -> None:
    if sys.version_info < (3, 11):
        raise InstallerError(f"{label}: --codex requires Python 3.11+", 2)
    command = [
        sys.executable,
        str(kit / "tools" / "codex-roles.py"),
        "--kit",
        str(kit),
        "--target",
        str(target),
    ]
    if preflight:
        command.append("--preflight")
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise InstallerError("", completed.returncode)


def install_agents(managed: ManagedRoot, kit: Path, profile: str) -> None:
    managed.ensure_dir(".github/agents")
    if profile == "knowledge":
        for name in KNOWLEDGE_AGENTS:
            managed.replace_file(kit / "agents" / f"{name}.agent.md", f".github/agents/{name}.agent.md")
        print("  ok agents -> .github/agents/ (knowledge crew)")
        return
    for source in sorted((kit / "agents").glob("*.agent.md")):
        managed.replace_file(source, f".github/agents/{source.name}")
    print("  ok agents -> .github/agents/")


def update_agents(managed: ManagedRoot, kit: Path, profile: str) -> None:
    managed.ensure_dir(".github/agents")
    if profile == "knowledge":
        retained = {f"{name}.agent.md" for name in KNOWLEDGE_AGENTS}
        for source in sorted((kit / "agents").glob("*.agent.md")):
            if source.name not in retained:
                managed.remove_file(f".github/agents/{source.name}")
        for name in KNOWLEDGE_AGENTS:
            managed.replace_file(kit / "agents" / f"{name}.agent.md", f".github/agents/{name}.agent.md")
        print("  ok agents refreshed (knowledge crew)")
        return
    for source in sorted((kit / "agents").glob("*.agent.md")):
        managed.replace_file(source, f".github/agents/{source.name}")
    print("  ok agents refreshed")


def copy_shared_assets(managed: ManagedRoot, kit: Path) -> None:
    managed.ensure_dir("gates/hooks")
    for name in GATE_FILES:
        managed.replace_file(kit / "gates" / name, f"gates/{name}")
    managed.copy_tree(kit / "gates" / "hooks", "gates/hooks")
    print("  ok gates")
    managed.ensure_dir("knowledge")
    managed.copy_tree(kit / "knowledge", "knowledge")
    print("  ok knowledge")
    managed.ensure_dir("harness")
    managed.copy_tree(kit / "harness", "harness")
    print("  ok harness")


def active_hook(kit: Path, entrypoint: str) -> Path:
    name = "design-guard.windows.json" if entrypoint == "windows" else "design-guard.json"
    return kit / "gates" / "hooks" / name


def update_gitignore(managed: ManagedRoot) -> None:
    path = managed.path(".gitignore")
    if _lstat(path) is None:
        content = ""
    else:
        content = managed.require_file(".gitignore").read_text(encoding="utf-8")
    existing = set(content.splitlines())
    missing = [rule for rule in IGNORE_RULES if rule not in existing]
    if not missing:
        print("  - .gitignore already ignores Architrave private runtime files")
        return
    content += "\n# Architrave: private run evidence and isolated worker trees stay local.\n"
    content += "".join(f"{rule}\n" for rule in missing)
    managed.replace_bytes(".gitignore", content.encode("utf-8"))
    print("  ok .gitignore updated")


def update_agents_stanza(managed: ManagedRoot, kit: Path) -> None:
    path = managed.path("AGENTS.md")
    if _lstat(path) is None:
        content = "# AGENTS.md\n"
    else:
        content = managed.require_file("AGENTS.md").read_text(encoding="utf-8")
    while True:
        begin = content.find(BEGIN)
        if begin < 0:
            break
        end = content.find(END, begin + len(BEGIN))
        if end < 0:
            content = content[:begin]
            break
        content = content[:begin] + content[end + len(END) :]
    stanza = (kit / "templates" / "AGENTS.stanza.md").read_text(encoding="utf-8").rstrip()
    refreshed = f"{content.rstrip()}\n\n{BEGIN}\n{stanza}\n{END}\n"
    managed.replace_bytes("AGENTS.md", refreshed.encode("utf-8"))
    print("  ok AGENTS.md stanza refreshed")


def install(args: argparse.Namespace, kit: Path) -> int:
    managed = ManagedRoot(Path(args.target or os.getcwd()), "install")
    if managed.root == kit:
        raise InstallerError("install: refusing to install the kit into itself")
    constitutions = tuple(sorted(kit.glob("constitution-*.md")))
    source_files = (
        "templates/AGENTS.stanza.md",
        "templates/copilot-setup-steps.yml",
        "plugin.json",
        "gates/hooks/design-guard.json",
        "gates/hooks/design-guard.windows.json",
    )
    if args.profile == "knowledge":
        source_files += ("kit/examples/knowledge.architrave.json",)
    elif not constitutions:
        raise InstallerError("install: packaged constitutions are missing")
    preflight_common(
        managed,
        kit,
        source_trees=("agents", "gates", "knowledge", "harness"),
        destination_trees=(
            ".github/agents",
            ".github/hooks",
            ".github/workflows",
            "gates",
            "gates/hooks",
            "knowledge",
            "harness",
        ),
        destination_files=(
            "architrave.config.json",
            ".gitignore",
            "AGENTS.md",
            "constitution-apple.md",
            "constitution-windows.md",
            ".github/hooks/design-guard.json",
            ".github/workflows/copilot-setup-steps.yml",
            "gates/.kit-version",
        ),
        source_files=source_files,
    )
    for source in constitutions:
        require_source_file(source, "install")
    for relative in (".gitignore", "AGENTS.md"):
        preflight_text(managed, relative)
    try:
        (kit / "templates" / "AGENTS.stanza.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallerError("install: packaged AGENTS stanza is not readable UTF-8") from exc
    version = plugin_version(kit, "install")
    if args.codex:
        run_codex(kit, managed.root, preflight=True, label="install")

    print(f"Architrave -> installing into: {managed.root}")
    for directory in (".github/agents", ".github/hooks", ".github/workflows", "gates/hooks", "knowledge", "harness"):
        managed.ensure_dir(directory)
    install_agents(managed, kit, args.profile)
    copy_shared_assets(managed, kit)
    if args.profile == "application":
        for source in constitutions:
            managed.replace_file(source, source.name)
        print("  ok constitution -> constitution-*.md")
    else:
        print("  - constitution-*.md skipped (knowledge profile)")

    config = managed.path("architrave.config.json")
    if _lstat(config) is None:
        if args.profile == "knowledge":
            managed.create_file(kit / "kit" / "examples" / "knowledge.architrave.json", "architrave.config.json")
        else:
            managed.create_bytes("architrave.config.json", APPLICATION_CONFIG.encode("utf-8"))
        print(f"  ok scaffolded architrave.config.json (profile: {args.profile})")
    else:
        print("  - architrave.config.json present - left as-is")

    update_gitignore(managed)
    update_agents_stanza(managed, kit)
    managed.replace_file(active_hook(kit, args.entrypoint), ".github/hooks/design-guard.json")
    print("  ok .github/hooks/design-guard.json")
    setup = managed.path(".github/workflows/copilot-setup-steps.yml")
    if _lstat(setup) is None:
        managed.create_file(
            kit / "templates" / "copilot-setup-steps.yml",
            ".github/workflows/copilot-setup-steps.yml",
        )
        print("  ok .github/workflows/copilot-setup-steps.yml")
    else:
        print("  - copilot-setup-steps.yml present - merge jq install manually")
    if args.codex:
        run_codex(kit, managed.root, preflight=False, label="install")
    managed.replace_bytes("gates/.kit-version", f"{version}\n".encode("utf-8"))
    print(f"  ok stamped gates/.kit-version = {version}")
    print(f"\nDone. Edit architrave.config.json to match this repo (profile: {args.profile}).")
    return 0


def update(args: argparse.Namespace, kit: Path) -> int:
    managed = ManagedRoot(Path(args.target or os.getcwd()), "update")
    if managed.root == kit:
        raise InstallerError("update: refusing to update the kit into itself")
    managed.preflight_file("architrave.config.json")
    config = managed.path("architrave.config.json")
    if _lstat(config) is None:
        raise InstallerError(
            f"update: {managed.root} has no safe architrave.config.json - run tools/install first"
        )
    profile = read_update_profile(managed.require_file("architrave.config.json"))
    constitutions = tuple(sorted(kit.glob("constitution-*.md")))
    if profile == "application" and not constitutions:
        raise InstallerError("update: packaged constitutions are missing")
    source_trees = ("gates", "knowledge", "harness") + (("agents",) if args.agents else ())
    destination_trees = (".github/hooks", "gates", "gates/hooks", "knowledge", "harness")
    if args.agents:
        destination_trees += (".github/agents",)
    preflight_common(
        managed,
        kit,
        source_trees=source_trees,
        destination_trees=destination_trees,
        destination_files=(
            "architrave.config.json",
            ".gitignore",
            "AGENTS.md",
            "constitution-apple.md",
            "constitution-windows.md",
            ".github/hooks/design-guard.json",
            "gates/.kit-version",
        ),
        source_files=(
            "templates/AGENTS.stanza.md",
            "plugin.json",
            "gates/hooks/design-guard.json",
            "gates/hooks/design-guard.windows.json",
        ),
    )
    for source in constitutions:
        require_source_file(source, "update")
    for relative in (".gitignore", "AGENTS.md"):
        preflight_text(managed, relative)
    try:
        (kit / "templates" / "AGENTS.stanza.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InstallerError("update: packaged AGENTS stanza is not readable UTF-8") from exc
    if args.codex:
        run_codex(kit, managed.root, preflight=True, label="update")
    version = plugin_version(kit, "update")

    print(f"Architrave -> refreshing assets in: {managed.root} (kit v{version})")
    for directory in (".github/hooks", "gates/hooks", "knowledge", "harness"):
        managed.ensure_dir(directory)
    if args.agents:
        update_agents(managed, kit, profile)
    else:
        print("  - agents left unchanged (use --agents to refresh .github/agents/)")
    copy_shared_assets(managed, kit)
    managed.replace_file(active_hook(kit, args.entrypoint), ".github/hooks/design-guard.json")
    print("  ok active workspace hook refreshed")
    if profile == "knowledge":
        for name in ("constitution-apple.md", "constitution-windows.md"):
            managed.remove_file(name)
        print("  ok constitution removed/skipped (knowledge profile)")
    else:
        for source in constitutions:
            managed.replace_file(source, source.name)
        print("  ok constitution refreshed")
    update_gitignore(managed)
    update_agents_stanza(managed, kit)
    if args.codex:
        run_codex(kit, managed.root, preflight=False, label="update")
    managed.replace_bytes("gates/.kit-version", f"{version}\n".encode("utf-8"))
    print(f"  ok stamped gates/.kit-version = {version}")
    print("Done. (architrave.config.json left untouched.)")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="install_update.py")
    subcommands = result.add_subparsers(dest="command", required=True)
    default_entrypoint = "windows" if os.name == "nt" else "posix"

    install_parser = subcommands.add_parser("install", add_help=False)
    install_parser.add_argument("-h", "--help", "-Help", action="help")
    install_parser.add_argument("--profile", "-Profile", choices=("application", "knowledge"), default="application")
    install_parser.add_argument("--codex", "-Codex", action="store_true")
    install_parser.add_argument("--entrypoint", choices=("posix", "windows"), default=default_entrypoint)
    install_parser.add_argument("target", nargs="?")

    update_parser = subcommands.add_parser("update", add_help=False)
    update_parser.add_argument("-h", "--help", "-Help", action="help")
    update_parser.add_argument("--agents", "-Agents", action="store_true")
    update_parser.add_argument("--codex", "-Codex", action="store_true")
    update_parser.add_argument("--entrypoint", choices=("posix", "windows"), default=default_entrypoint)
    update_parser.add_argument("target", nargs="?")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    kit = Path(__file__).resolve().parents[1]
    try:
        return install(args, kit) if args.command == "install" else update(args, kit)
    except InstallerError as exc:
        if str(exc):
            print(str(exc), file=sys.stderr)
        return exc.code
    except (OSError, UnicodeError) as exc:
        print(f"{args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
