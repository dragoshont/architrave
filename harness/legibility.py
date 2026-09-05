#!/usr/bin/env python3
"""Application, runtime, and deployment legibility for durable Runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid
import zlib
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit

from architrave_runtime import RunStore, RuntimeFailure, redact, utc_now
from worker_adapters import run_bounded


def load_config(repository: Path) -> dict[str, Any]:
    path = repository / "architrave.config.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeFailure("CONFIG_NOT_FOUND", f"config not found: {path}", exit_code=2) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeFailure("CONFIG_INVALID", f"invalid JSON config: {exc}", exit_code=2) from exc
    if not isinstance(value, dict):
        raise RuntimeFailure("CONFIG_INVALID", "config must be a JSON object", exit_code=2)
    return value


def shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return ["pwsh", "-NoProfile", "-Command", command]
    return ["/bin/sh", "-lc", command]


def paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    left_distance = abs(prediction - left)
    above_distance = abs(prediction - above)
    upper_left_distance = abs(prediction - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def png_luminance_range(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeFailure("SCREENSHOT_FORMAT", "screenshotPath must be an 8-bit non-interlaced PNG")
    offset = 8
    width = height = bit_depth = color_type = interlace = 0
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if not width or not height or bit_depth != 8 or interlace != 0 or channels is None:
        raise RuntimeFailure("SCREENSHOT_FORMAT", "unsupported PNG dimensions, color type, bit depth, or interlace")
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise RuntimeFailure("SCREENSHOT_FORMAT", "PNG scanline size does not match IHDR")
    previous = bytearray(stride)
    luminance: list[int] = []
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        encoded = raw[cursor:cursor + stride]
        cursor += stride
        decoded = bytearray(stride)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            predictor = 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = paeth(left, above, upper_left)
            elif filter_type != 0:
                raise RuntimeFailure("SCREENSHOT_FORMAT", f"unsupported PNG filter: {filter_type}")
            decoded[index] = (value + predictor) & 0xFF
        for index in range(0, stride, channels):
            if color_type == 0:
                red = green = blue = decoded[index]
                alpha = 255
            elif color_type == 2:
                red, green, blue = decoded[index:index + 3]
                alpha = 255
            elif color_type == 4:
                red = green = blue = decoded[index]
                alpha = decoded[index + 1]
            else:
                red, green, blue, alpha = decoded[index:index + 4]
            if alpha:
                luminance.append((299 * red + 587 * green + 114 * blue) // 1000)
        previous = decoded
    if not luminance:
        return 0, 0, 0
    return min(luminance), max(luminance), len(luminance)


class LegibilityRunner:
    def __init__(self, repository: Path | str, run_id: str):
        self.repository = Path(repository).resolve()
        self.store = RunStore(self.repository)
        self.run_id = run_id
        self.config = load_config(self.repository)
        self.runtime = self.config.get("runtime") or {}
        self.evidence_dir = self.store.run_dir(run_id) / "legibility"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def recipe(
        self,
        name: str,
        command: str | None,
        *,
        required: bool = False,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        safe_name = name.replace("/", "-").replace(".", "-")
        stdout_path = self.evidence_dir / f"{safe_name}.stdout.log"
        stderr_path = self.evidence_dir / f"{safe_name}.stderr.log"
        if not command:
            return {
                "name": name,
                "status": "missing" if required else "skipped",
                "exitCode": None,
                "durationMs": 0,
                "stdout": "",
                "artifacts": [],
            }
        execution = run_bounded(
            shell_command(command),
            cwd=self.repository,
            environment={
                name: value
                for name, value in os.environ.items()
                if name in {"PATH", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
            },
            timeout_seconds=timeout_seconds,
            max_output_bytes=1024 * 1024,
        )
        stdout = str(redact(execution["stdout"]))
        stderr = str(redact(execution["stderr"]))
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        return {
            "name": name,
            "status": "pass" if execution["exitCode"] == 0 and not execution["timedOut"] else "fail",
            "exitCode": execution["exitCode"],
            "timedOut": execution["timedOut"],
            "durationMs": execution["durationMs"],
            "stdout": stdout[:2000],
            "stdoutSha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "artifacts": [
                stdout_path.relative_to(self.repository).as_posix(),
                stderr_path.relative_to(self.repository).as_posix(),
            ],
        }

    def structured_recipe(
        self,
        name: str,
        command: str | None,
        validator: Callable[[dict[str, Any]], list[str]],
        evidence_started_ns: int | None = None,
    ) -> dict[str, Any]:
        evidence_started_ns = evidence_started_ns or time.time_ns()
        result = self.recipe(name, command, required=True)
        if result["status"] != "pass":
            return result
        try:
            stdout_path = self.repository / result["artifacts"][0]
            payload = json.loads(stdout_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result["status"] = "fail"
            result["exitCode"] = 1
            result["stdout"] = "structured evidence is not valid JSON"
            return result
        if not isinstance(payload, dict):
            errors = ["structured evidence must be an object"]
        else:
            errors = validator(payload)
        for field in ("domSnapshot", "accessibilityTree", "screenshot"):
            value = payload.get(field) if isinstance(payload, dict) else None
            if not value:
                continue
            path = Path(str(value))
            if path.is_absolute() or ".." in path.parts or not (self.repository / path).is_file():
                errors.append(f"{field} must reference an existing repository-relative artifact")
            else:
                absolute = self.repository / path
                if absolute.stat().st_mtime_ns < evidence_started_ns:
                    errors.append(f"{field} was not created or refreshed during this verification")
                if field == "screenshot":
                    try:
                        minimum, maximum, visible_pixels = png_luminance_range(absolute)
                    except RuntimeFailure as exc:
                        errors.append(exc.message)
                    else:
                        if visible_pixels == 0 or maximum - minimum < 8:
                            errors.append("screenshot is blank or visually flat")
                result["artifacts"].append(path.as_posix())
        if errors:
            result["status"] = "fail"
            result["exitCode"] = 1
            result["stdout"] = json.dumps({"errors": errors, "evidence": payload}, sort_keys=True)
        else:
            result["stdout"] = json.dumps(payload, sort_keys=True)
        return result

    @staticmethod
    def validate_web_evidence(payload: dict[str, Any], configured_url: str | None = None) -> list[str]:
        errors: list[str] = []
        for field in ("url", "domSnapshot", "accessibilityTree", "screenshot"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                errors.append(f"{field} is required")
        if not configured_url:
            errors.append("config.runtime.web.url is required")
        elif isinstance(payload.get("url"), str) and payload["url"]:
            expected = urlsplit(configured_url)
            actual = urlsplit(payload["url"])
            if (
                not expected.scheme
                or not expected.netloc
                or not actual.scheme
                or not actual.netloc
                or (expected.scheme, expected.netloc, expected.path or "/")
                != (actual.scheme, actual.netloc, actual.path or "/")
            ):
                errors.append("url must match config.runtime.web.url origin and route")
        if payload.get("workflowPassed") is not True:
            errors.append("workflowPassed must be true")
        for field in ("consoleErrors", "networkFailures"):
            if payload.get(field) != []:
                errors.append(f"{field} must be an empty array")
        return errors

    @staticmethod
    def validate_electron_evidence(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload.get("windowCount"), int) or payload["windowCount"] < 1:
            errors.append("windowCount must be at least one")
        for field in ("route", "screenshot"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                errors.append(f"{field} is required")
        if payload.get("workflowPassed") is not True or payload.get("crashed") is not False:
            errors.append("Electron must complete its workflow without crashing")
        for field in ("consoleErrors", "ipcErrors"):
            if payload.get(field) != []:
                errors.append(f"{field} must be an empty array")
        return errors

    @staticmethod
    def validate_ios_evidence(payload: dict[str, Any], bundle_id: str, screenshot_path: str) -> list[str]:
        errors: list[str] = []
        if payload.get("bundleId") != bundle_id:
            errors.append("bundleId does not match config")
        for field in ("installed", "launched", "terminated", "relaunched", "navigationPassed"):
            if payload.get(field) is not True:
                errors.append(f"{field} must be true")
        if payload.get("crashed") is not False:
            errors.append("crashed must be false")
        if payload.get("screenshot") != screenshot_path:
            errors.append("screenshot does not match config.runtime.ios.screenshotPath")
        return errors

    def _finalize_gate(
        self,
        surface: str,
        results: Sequence[dict[str, Any]],
        *,
        task_id: str | None,
    ) -> dict[str, Any]:
        failed = [result["name"] for result in results if result["status"] in {"fail", "missing"}]
        receipt_path = self.evidence_dir / f"{surface}-{uuid.uuid4().hex}.receipt.json"
        receipt = {
            "surface": surface,
            "status": "pass" if not failed else "fail",
            "failed": failed,
            "results": [
                {
                    "name": result["name"],
                    "status": result["status"],
                    "exitCode": result.get("exitCode"),
                    "stdoutSha256": result.get("stdoutSha256"),
                    "artifacts": [
                        {
                            "path": artifact,
                            "sha256": hashlib.sha256((self.repository / artifact).read_bytes()).hexdigest(),
                        }
                        for artifact in result.get("artifacts", [])
                        if (self.repository / artifact).is_file()
                    ],
                }
                for result in results
            ],
        }
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        evidence_refs: list[str] = []
        if not failed:
            artifact_id = f"{surface}-legibility-{uuid.uuid4().hex}"
            self.store._record_legibility_result(
                self.run_id,
                artifact_id=artifact_id,
                kind=f"{surface}-legibility",
                path=receipt_path.relative_to(self.repository).as_posix(),
                evidence_refs=[f"task:{task_id}"] if task_id else [],
            )
            evidence_refs = [f"artifact:{artifact_id}"]
        gate_id = f"reality-{surface}-{uuid.uuid4().hex[:10]}"
        status = "PASS" if not failed else "FAIL"
        if status == "PASS":
            self.store.record_gate(
                self.run_id,
                gate_id=gate_id,
                task_id=task_id,
                gate_type="reality",
                status=status,
                evidence_refs=evidence_refs,
                surface=surface,
            )
        return {
            "surface": surface,
            "status": "pass" if not failed else "fail",
            "failed": failed,
            "gateId": gate_id,
            "results": list(results),
        }

    def analyze_ios_screenshot(self, screenshot_path: str | None) -> dict[str, Any]:
        if not screenshot_path:
            return self.recipe("ios.blank-screen", None, required=True)
        relative = Path(screenshot_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeFailure("PATH_ESCAPE", "runtime.ios.screenshotPath must be repository-relative")
        path = (self.repository / relative).resolve()
        if not path.is_file():
            return {
                "name": "ios.blank-screen",
                "status": "fail",
                "exitCode": None,
                "durationMs": 0,
                "stdout": "configured screenshot artifact is missing",
                "artifacts": [],
            }
        minimum, maximum, visible_pixels = png_luminance_range(path)
        luminance_range = maximum - minimum
        return {
            "name": "ios.blank-screen",
            "status": "pass" if visible_pixels > 0 and luminance_range >= 8 else "fail",
            "exitCode": 0 if visible_pixels > 0 and luminance_range >= 8 else 1,
            "durationMs": 0,
            "stdout": json.dumps(
                {
                    "visiblePixels": visible_pixels,
                    "minimumLuminance": minimum,
                    "maximumLuminance": maximum,
                    "luminanceRange": luminance_range,
                },
                sort_keys=True,
            ),
            "artifacts": [relative.as_posix()],
        }

    def verify_surface(self, surface: str, *, task_id: str | None = None) -> dict[str, Any]:
        evidence_started_ns = time.time_ns()
        if surface == "web":
            config = self.runtime.get("web") or {}
            results = [self.recipe("runtime.health", self.runtime.get("health"), required=True)]
            results.extend(
                [
                    self.structured_recipe(
                        "web.e2e",
                        config.get("e2e"),
                        lambda payload: self.validate_web_evidence(payload, str(config.get("url") or "")),
                        evidence_started_ns,
                    ),
                    self.recipe("web.dom", config.get("dom")),
                    self.recipe("web.accessibility", config.get("accessibility")),
                    self.recipe("web.screenshot", config.get("screenshot")),
                    self.recipe("web.console", config.get("console")),
                    self.recipe("web.network", config.get("network")),
                ]
            )
            return self._finalize_gate(surface, results, task_id=task_id)

        if surface == "electron":
            config = self.runtime.get("electron") or {}
            results = [
                self.structured_recipe("electron.launch", config.get("launch"), self.validate_electron_evidence, evidence_started_ns),
                self.recipe("electron.health", config.get("health"), required=True),
                self.recipe("electron.logs", config.get("logs")),
                self.recipe("electron.screenshot", config.get("screenshot"), required=True),
            ]
            return self._finalize_gate(surface, results, task_id=task_id)

        if surface == "ios":
            config = self.runtime.get("ios") or {}
            screenshot_path = config.get("screenshotPath")
            build = self.recipe("ios.build", config.get("build"), required=True, timeout_seconds=1800)
            install = self.recipe("ios.install", config.get("install"), required=True)
            launch = self.structured_recipe(
                "ios.launch",
                config.get("launch"),
                lambda payload: self.validate_ios_evidence(
                    payload,
                    str(config.get("bundleId") or ""),
                    str(screenshot_path or ""),
                ),
                evidence_started_ns,
            )
            screenshot = self.recipe("ios.screenshot", config.get("screenshot"), required=True)
            blank_check = (
                self.analyze_ios_screenshot(config.get("screenshotPath"))
                if config.get("screenshotPath")
                else self.recipe("ios.blank-screen", config.get("blankScreenCheck"), required=True)
            )
            logs = self.recipe("ios.logs", config.get("logs"))
            results = [build, install, launch, screenshot, blank_check, logs]
            return self._finalize_gate(surface, results, task_id=task_id)
        raise RuntimeFailure("SURFACE_INVALID", f"unknown application surface: {surface}", exit_code=2)

    def observe_deployment(self) -> dict[str, Any]:
        deployment = self.runtime.get("deployment") or {}
        results = [
            self.recipe("deployment.current", deployment.get("current"), required=True),
            self.recipe("deployment.health", deployment.get("health"), required=True),
            self.recipe("deployment.version", deployment.get("version")),
            self.recipe("deployment.digest", deployment.get("digest")),
        ]
        failed = [result["name"] for result in results if result["status"] in {"fail", "missing"}]
        return {"status": "pass" if not failed else "fail", "failed": failed, "results": results}

    def apply_deployment(
        self,
        *,
        confirmed: bool,
        expected_version: str | None = None,
        expected_digest: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        deployment = self.runtime.get("deployment") or {}
        target = deployment.get("target")
        if not target:
            raise RuntimeFailure("DEPLOYMENT_CONFIG", "runtime.deployment.target is required")
        if not task_id:
            raise RuntimeFailure("DEPLOYMENT_TASK", "deployment apply requires a task-bound side effect")
        decision = self.store.policy_check(self.run_id, target, "deploy", confirmed=confirmed)
        if decision["status"] != "allowed":
            raise RuntimeFailure("MUTATION_DENIED", f"deployment is {decision['status']}", details=decision)
        if expected_version is None or expected_digest is None:
            raise RuntimeFailure("DEPLOYMENT_EXPECTATION", "authorized deployment requires expected version and digest")
        if not deployment.get("version") or not deployment.get("digest"):
            raise RuntimeFailure("DEPLOYMENT_CONFIG", "deployment version and digest commands are required")
        before = self.recipe("deployment.before", deployment.get("current"), required=True)
        if before["status"] != "pass":
            raise RuntimeFailure("DEPLOYMENT_PREFLIGHT", "deployment preflight failed before apply")
        diff = self.recipe("deployment.diff", deployment.get("diff"))
        if diff["status"] in {"fail", "missing"}:
            raise RuntimeFailure("DEPLOYMENT_PREFLIGHT", "deployment diff failed before apply")
        precondition = self.recipe("deployment.precondition", deployment.get("current"), required=True)
        if precondition["status"] != "pass":
            raise RuntimeFailure("DEPLOYMENT_PREFLIGHT", "deployment preflight failed before apply")
        if precondition["stdoutSha256"] != before["stdoutSha256"]:
            raise RuntimeFailure("DEPLOYMENT_DRIFT", "deployment current state changed before apply")
        self.store.prepare_side_effect(
            self.run_id,
            task_id,
            operation="deploy",
            target=target,
            confirmed=confirmed,
        )
        apply = self.recipe("deployment.apply", deployment.get("apply"), required=True, timeout_seconds=1800)
        after = self.recipe("deployment.after", deployment.get("current"), required=True)
        health = self.recipe("deployment.health", deployment.get("health"), required=True)
        version = self.recipe("deployment.version", deployment.get("version"), required=expected_version is not None)
        digest = self.recipe("deployment.digest", deployment.get("digest"), required=expected_digest is not None)
        results = [before, diff, precondition, apply, after, health, version, digest]
        mismatches: list[dict[str, str]] = []
        if expected_version is not None and version["stdout"].strip() != expected_version:
            mismatches.append({"field": "version", "expected": expected_version, "actual": version["stdout"].strip()})
        if expected_digest is not None and digest["stdout"].strip() != expected_digest:
            mismatches.append({"field": "digest", "expected": expected_digest, "actual": digest["stdout"].strip()})
        failed = [result["name"] for result in results if result["status"] in {"fail", "missing"}]
        success = not failed and not mismatches
        receipt = {
            "taskId": task_id,
            "operation": "deploy",
            "target": target,
            "timestamp": utc_now(),
            "expected": {"version": expected_version, "digest": expected_digest},
            "before": before,
            "after": after,
            "result": {"status": "pass" if success else "fail", "apply": apply, "mismatches": mismatches},
            "verification": {"health": health, "version": version, "digest": digest},
        }
        receipt_path = self.store.run_dir(self.run_id) / "mutations" / f"deploy-{uuid.uuid4().hex}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(redact(receipt), indent=2) + "\n", encoding="utf-8")
        receipt_id = f"deployment-receipt-{uuid.uuid4().hex}"
        evidence: str | None = None
        receipt_error: str | None = None
        if apply["status"] == "pass":
            try:
                self.store._record_mutation_receipt(
                    self.run_id,
                    artifact_id=receipt_id,
                    path=receipt_path.relative_to(self.repository).as_posix(),
                    evidence_refs=[f"task:{task_id}"],
                )
            except RuntimeFailure as exc:
                receipt_error = exc.message
                success = False
            else:
                evidence = f"artifact:{receipt_id}"
                self.store.reconcile_side_effect(
                    self.run_id,
                    task_id,
                    result="applied",
                    evidence_ref=evidence,
                )
        gate_id = f"deployment-{uuid.uuid4().hex[:10]}"
        if apply["status"] == "pass":
            self.store.record_gate(
                self.run_id,
                gate_id=gate_id,
                task_id=task_id,
                gate_type="reality",
                status="PASS" if success else "FAIL",
                evidence_refs=[evidence] if evidence else [],
                surface="deployment",
            )
        return {
            "status": "pass" if success else "fail",
            "failed": failed,
            "mismatches": mismatches,
            "receiptError": receipt_error,
            "receipt": receipt_path.relative_to(self.repository).as_posix(),
            "gateId": gate_id if apply["status"] == "pass" else None,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect bounded product/runtime evidence")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--run-id", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("surface", choices=["web", "electron", "ios"])
    verify.add_argument("--task-id")
    subparsers.add_parser("deployment-current")
    deploy = subparsers.add_parser("deployment-apply")
    deploy.add_argument("--confirmed", action="store_true")
    deploy.add_argument("--expected-version")
    deploy.add_argument("--expected-digest")
    deploy.add_argument("--task-id")
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runner = LegibilityRunner(args.repo, args.run_id)
        if args.command == "verify":
            result = runner.verify_surface(args.surface, task_id=args.task_id)
        elif args.command == "deployment-current":
            result = runner.observe_deployment()
        else:
            result = runner.apply_deployment(
                confirmed=args.confirmed,
                expected_version=args.expected_version,
                expected_digest=args.expected_digest,
                task_id=args.task_id,
            )
        print(json.dumps({"status": "ok" if result["status"] == "pass" else "failed", "result": redact(result)}, indent=2))
        return 0 if result["status"] == "pass" else 1
    except RuntimeFailure as exc:
        print(
            json.dumps(
                {"status": "failed", "error": {"code": exc.code, "message": exc.message, "details": redact(exc.details)}},
                indent=2,
            ),
            file=sys.stderr,
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(cli())