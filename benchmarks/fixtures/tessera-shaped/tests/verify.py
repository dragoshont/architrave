import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EXPECTED_RELEASE = "fixture-2026.08.13"
EXPECTED_ENDPOINT = "/api/v1/release-status"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_backend() -> None:
    module = importlib.import_module("server.release_status")
    status = module.read_status()
    expected = json.loads((ROOT / "runtime" / "release-state.json").read_text())
    require(status == expected, "backend must read the persistent release state")
    child = subprocess.run(
        [sys.executable, "-c", "from server.release_status import read_status; print(read_status()['releaseId'])"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    require(child.stdout.strip() == EXPECTED_RELEASE, "release state must survive process restart")


def verify_web() -> None:
    source = (ROOT / "web" / "release-status.js").read_text()
    require(EXPECTED_ENDPOINT in source, "Web must use the release-status contract endpoint")
    require("blocked_external" in source and "provider_auth_required" in source, "Web must render the blocked reason honestly")
    require('href="#"' not in source, "Web controls must not be dead placeholders")


def verify_electron() -> None:
    source = (ROOT / "electron" / "release-status.js").read_text()
    require(EXPECTED_ENDPOINT in source, "Electron must use its own release-status contract integration")
    require("blocked_external" in source and "provider_auth_required" in source, "Electron must expose the blocked reason")


def verify_ios() -> None:
    source = (ROOT / "ios" / "ReleaseStatusView.swift").read_text()
    require(EXPECTED_ENDPOINT in source, "iOS must use the release-status contract endpoint")
    require("blocked_external" in source and "provider_auth_required" in source, "iOS must render the blocked reason")
    require("Release unavailable" not in source, "iOS must not keep the placeholder screen")


def verify_plugin() -> None:
    provider = importlib.import_module("plugin.provider").authentication_state()
    require(provider["type"] == "AUTH_REQUIRED", "provider auth must remain an external checkpoint")
    require(provider["principal"] == "fixture-user", "external checkpoint principal drift")
    require(provider["provider"] == "fixture-mail", "external checkpoint provider drift")
    require(provider["resolutionRef"] == "evidence:fixture-auth-resolved", "synthetic resolution evidence drift")


def verify_deployment() -> None:
    desired = json.loads((ROOT / "deploy" / "release.json").read_text())
    live = json.loads((ROOT / "deploy" / "live.json").read_text())
    require(desired["releaseId"] == EXPECTED_RELEASE, "desired deployment release is stale")
    require(desired["digest"] == "sha256:fixture-2026.08.13", "desired deployment digest is stale")
    require(live == desired, "sandbox deployment does not match the intended release")


parser = argparse.ArgumentParser()
parser.add_argument("--surface", choices=["backend", "web", "electron", "ios"])
args = parser.parse_args()
checks = {
    "backend": verify_backend,
    "web": verify_web,
    "electron": verify_electron,
    "ios": verify_ios,
}
if args.surface:
    checks[args.surface]()
else:
    verify_backend()
    verify_web()
    verify_electron()
    verify_ios()
    verify_plugin()
    verify_deployment()
print("fixture verification passed")