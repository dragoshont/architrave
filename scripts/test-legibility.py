#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore, RuntimeFailure
from legibility import LegibilityRunner


class LegibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "architrave@example.invalid")
        self.git("config", "user.name", "Architrave Test")
        (self.repo / ".gitignore").write_text(".architrave/runs/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "fixture")
        self.store = RunStore(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write_png(self, path: Path, pixels: list[tuple[int, int, int]]) -> None:
        width = len(pixels)
        raw = b"\x00" + b"".join(bytes(pixel) for pixel in pixels)

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"")
        )

    def json_command(self, payload: dict[str, object], refresh_paths: list[str] | None = None) -> str:
        refresh = "; ".join(f"Path({path!r}).touch()" for path in (refresh_paths or []))
        statements = ["from pathlib import Path", "import json"]
        if refresh:
            statements.append(refresh)
        statements.append(f"print(json.dumps({payload!r}))")
        source = "; ".join(statements)
        return f"python3 -c {shlex.quote(source)}"

    def ios_evidence(self, screenshot: str) -> str:
        return self.json_command(
            {
                "bundleId": "example.fixture",
                "installed": True,
                "launched": True,
                "terminated": True,
                "relaunched": True,
                "navigationPassed": True,
                "crashed": False,
                "screenshot": screenshot,
            },
            [screenshot],
        )

    def create_runner(
        self, runtime: dict[str, object], *, allow_deploy: bool = False, surface: str = "web"
    ) -> tuple[LegibilityRunner, str]:
        (self.repo / "architrave.config.json").write_text(json.dumps({"runtime": runtime}), encoding="utf-8")
        state = self.store.create(
            goal="Verify the actual fixture product.",
            outcome="The configured application surface is usable.",
            criteria=[
                {
                    "id": "REALITY-001",
                    "description": "The actual product surface is usable.",
                    "scope": "product",
                    "risk": "R3",
                    "verificationType": "reality",
                    "surface": surface,
                    "status": "UNTESTED",
                    "evidenceRefs": [],
                    "blocking": True,
                }
            ],
            autonomy_scope="approved-program",
            policy_allow=[{"scope": "sandbox:fixture", "operations": ["deploy"]}] if allow_deploy else [],
        )
        if runtime.get("deployment"):
            self.store.add_task(
                state["runId"],
                {
                    "id": "deployment",
                    "title": "Deployment",
                    "objective": "Apply and verify the sandbox deployment.",
                    "workerProfile": "shell",
                    "mutablePaths": [],
                    "tools": [],
                    "risk": "R3",
                    "acceptanceCriteria": ["REALITY-001"],
                    "requiredArtifacts": [],
                    "gate": "deployment reality gate",
                    "sideEffect": {"operation": "deploy", "target": "sandbox:fixture"},
                },
            )
            if allow_deploy:
                self.store.start_task(state["runId"], "deployment", worker_id="deployment-worker")
        return LegibilityRunner(self.repo, state["runId"]), state["runId"]

    def test_web_requires_health_and_product_evidence(self) -> None:
        runner, _ = self.create_runner({"health": "true", "web": {"url": "http://fixture.invalid"}})
        result = runner.verify_surface("web")
        self.assertEqual("fail", result["status"])
        self.assertIn("web.e2e", result["failed"])

    def test_web_e2e_is_recorded_as_reality_gate(self) -> None:
        (self.repo / "dom.json").write_text("{}\n", encoding="utf-8")
        (self.repo / "a11y.json").write_text("{}\n", encoding="utf-8")
        self.write_png(self.repo / "web.png", [(0, 0, 0), (255, 255, 255)])
        evidence = self.json_command(
            {
                "url": "http://fixture.invalid/release",
                "domSnapshot": "dom.json",
                "accessibilityTree": "a11y.json",
                "screenshot": "web.png",
                "workflowPassed": True,
                "consoleErrors": [],
                "networkFailures": [],
            },
            ["dom.json", "a11y.json", "web.png"],
        )
        runner, run_id = self.create_runner(
            {"health": "printf healthy", "web": {"url": "http://fixture.invalid/release", "e2e": evidence}}
        )
        result = runner.verify_surface("web")
        self.assertEqual("pass", result["status"])
        gate = self.store.load(run_id)["gateResults"][-1]
        self.assertEqual("reality", gate["type"])
        self.assertEqual("PASS", gate["status"])

    def test_web_e2e_url_must_match_configured_origin_and_route(self) -> None:
        for url in ("http://other.invalid/release", "http://fixture.invalid/other"):
            with self.subTest(url=url):
                (self.repo / "dom.json").write_text("{}\n", encoding="utf-8")
                (self.repo / "a11y.json").write_text("{}\n", encoding="utf-8")
                self.write_png(self.repo / "web.png", [(0, 0, 0), (255, 255, 255)])
                evidence = self.json_command(
                    {
                        "url": url,
                        "domSnapshot": "dom.json",
                        "accessibilityTree": "a11y.json",
                        "screenshot": "web.png",
                        "workflowPassed": True,
                        "consoleErrors": [],
                        "networkFailures": [],
                    },
                    ["dom.json", "a11y.json", "web.png"],
                )
                runner, _ = self.create_runner(
                    {"health": "true", "web": {"url": "http://fixture.invalid/release", "e2e": evidence}}
                )
                result = runner.verify_surface("web")
                self.assertEqual("fail", result["status"])
                web_e2e = next(item for item in result["results"] if item["name"] == "web.e2e")
                self.assertIn("url must match config.runtime.web.url origin and route", web_e2e["stdout"])

    def test_web_trivial_exit_zero_cannot_pass_reality_gate(self) -> None:
        runner, _ = self.create_runner(
            {"health": "true", "web": {"url": "http://fixture.invalid", "e2e": "true"}}
        )
        result = runner.verify_surface("web")
        self.assertEqual("fail", result["status"])
        self.assertIn("web.e2e", result["failed"])

    def test_electron_is_verified_distinctly_from_web(self) -> None:
        runner, _ = self.create_runner(
            {
                "health": "true",
                "web": {"url": "http://fixture.invalid", "e2e": "true"},
                "electron": {"launch": "false", "health": "true", "screenshot": "true"},
            }
        )
        result = runner.verify_surface("electron")
        self.assertEqual("fail", result["status"])
        self.assertIn("electron.launch", result["failed"])

    def test_electron_structured_window_evidence_passes(self) -> None:
        self.write_png(self.repo / "electron.png", [(0, 0, 0), (255, 255, 255)])
        evidence = self.json_command(
            {
                "windowCount": 1,
                "route": "/release",
                "screenshot": "electron.png",
                "workflowPassed": True,
                "crashed": False,
                "consoleErrors": [],
                "ipcErrors": [],
            },
            ["electron.png"],
        )
        runner, _ = self.create_runner(
            {"electron": {"launch": evidence, "health": "true", "screenshot": "true"}}, surface="electron"
        )
        self.assertEqual("pass", runner.verify_surface("electron")["status"])

    def test_ios_compile_only_cannot_pass_reality_gate(self) -> None:
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": "true",
                    "install": "true",
                    "launch": "true",
                    "screenshot": "true"
                }
            }
        )
        result = runner.verify_surface("ios")
        self.assertEqual("fail", result["status"])
        self.assertIn("ios.blank-screen", result["failed"])

    def test_ios_launch_screenshot_and_blank_check_pass(self) -> None:
        self.write_png(self.repo / "ios-custom.png", [(0, 0, 0), (255, 255, 255)])
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": "printf build",
                    "install": "printf install",
                    "launch": self.ios_evidence("ios-custom.png"),
                    "logs": "printf logs",
                    "screenshot": "printf screenshot",
                    "screenshotPath": "ios-custom.png"
                }
            },
            surface="ios",
        )
        self.assertEqual("pass", runner.verify_surface("ios")["status"])

    def test_ios_lifecycle_runs_in_build_to_blank_screen_order(self) -> None:
        lifecycle = self.repo / "ios-lifecycle"
        screenshot = self.repo / "ios-lifecycle.png"
        self.write_png(screenshot, [(0, 0, 0), (255, 255, 255)])
        payload = {
            "bundleId": "example.fixture",
            "installed": True,
            "launched": True,
            "terminated": True,
            "relaunched": True,
            "navigationPassed": True,
            "crashed": False,
            "screenshot": screenshot.name,
        }
        launch_source = (
            "from pathlib import Path; import json; "
            "Path('ios-lifecycle').open('a').write('launch\\n'); "
            "Path('ios-lifecycle.png').touch(); "
            f"print(json.dumps({payload!r}))"
        )
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": "printf 'build\\n' >> ios-lifecycle",
                    "install": "printf 'install\\n' >> ios-lifecycle",
                    "launch": f"python3 -c {shlex.quote(launch_source)}",
                    "screenshot": "printf 'screenshot\\n' >> ios-lifecycle",
                    "screenshotPath": screenshot.name,
                }
            },
            surface="ios",
        )
        analyze = runner.analyze_ios_screenshot

        def check_blank_screen(path: str | None) -> dict[str, object]:
            self.assertEqual("build\ninstall\nlaunch\nscreenshot\n", lifecycle.read_text(encoding="utf-8"))
            return analyze(path)

        runner.analyze_ios_screenshot = check_blank_screen  # type: ignore[method-assign]
        self.assertEqual("pass", runner.verify_surface("ios")["status"])

    def test_ios_builtin_pixel_check_rejects_flat_screenshot(self) -> None:
        screenshot = self.repo / "ios-flat.png"
        self.write_png(screenshot, [(255, 255, 255), (255, 255, 255)])
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": "true",
                    "install": "true",
                    "launch": self.ios_evidence("ios-flat.png"),
                    "screenshot": "true",
                    "screenshotPath": "ios-flat.png"
                }
            }
        )
        result = runner.verify_surface("ios")
        self.assertEqual("fail", result["status"])
        blank = next(item for item in result["results"] if item["name"] == "ios.blank-screen")
        self.assertIn('"luminanceRange": 0', blank["stdout"])

    def test_ios_builtin_pixel_check_accepts_nonblank_screenshot(self) -> None:
        screenshot = self.repo / "ios-content.png"
        self.write_png(screenshot, [(0, 0, 0), (255, 255, 255)])
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": "true",
                    "install": "true",
                    "launch": self.ios_evidence("ios-content.png"),
                    "screenshot": "true",
                    "screenshotPath": "ios-content.png"
                }
            },
            surface="ios",
        )
        self.assertEqual("pass", runner.verify_surface("ios")["status"])

    def test_ios_stale_preexisting_evidence_is_rejected(self) -> None:
        screenshot = self.repo / "ios-stale.png"
        self.write_png(screenshot, [(0, 0, 0), (255, 255, 255)])
        stale_command = self.json_command(
            {
                "bundleId": "example.fixture",
                "installed": True,
                "launched": True,
                "terminated": True,
                "relaunched": True,
                "navigationPassed": True,
                "crashed": False,
                "screenshot": "ios-stale.png",
            }
        )
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": "true",
                    "install": "true",
                    "launch": stale_command,
                    "screenshot": "true",
                    "screenshotPath": "ios-stale.png"
                }
            }
        )
        result = runner.verify_surface("ios")
        self.assertEqual("fail", result["status"])
        self.assertIn("ios.launch", result["failed"])

    def test_deployment_apply_is_denied_without_scoped_authorization(self) -> None:
        sentinel = self.repo / "deployed"
        runner, _ = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "printf before",
                    "apply": f"touch {sentinel.name}",
                    "health": "true"
                }
            }
        )
        with self.assertRaisesRegex(RuntimeFailure, "denied"):
            runner.apply_deployment(confirmed=True, task_id="deployment")
        self.assertFalse(sentinel.exists())

    def test_authorized_deployment_emits_verified_receipt(self) -> None:
        runner, run_id = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "printf current",
                    "diff": "printf diff",
                    "apply": "printf apply",
                    "health": "printf healthy",
                    "version": "printf 1.2.3",
                    "digest": "printf sha256:abc"
                }
            },
            allow_deploy=True,
            surface="deployment",
        )
        result = runner.apply_deployment(
            confirmed=True,
            expected_version="1.2.3",
            expected_digest="sha256:abc",
            task_id="deployment",
        )
        self.assertEqual("pass", result["status"])
        receipt = self.repo / result["receipt"]
        self.assertTrue(receipt.is_file())
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual("sandbox:fixture", payload["target"])
        self.assertEqual("pass", payload["result"]["status"])
        self.assertEqual("PASS", self.store.load(run_id)["gateResults"][-1]["status"])

    def test_deployment_version_mismatch_fails_reality_gate(self) -> None:
        runner, run_id = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "printf current",
                    "apply": "true",
                    "health": "true",
                    "version": "printf stale",
                    "digest": "printf sha256:actual"
                }
            },
            allow_deploy=True,
        )
        result = runner.apply_deployment(
            confirmed=True,
            expected_version="new",
            expected_digest="sha256:actual",
            task_id="deployment",
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual("version", result["mismatches"][0]["field"])
        self.assertEqual("FAIL", self.store.load(run_id)["gateResults"][-1]["status"])

    def test_failed_deployment_cannot_replay_before_reconciliation(self) -> None:
        counter = self.repo / "apply-count"
        apply_command = (
            f"python3 -c \"from pathlib import Path; p=Path('{counter.name}'); "
            "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1'); raise SystemExit(1)\""
        )
        runner, run_id = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "printf current",
                    "apply": apply_command,
                    "health": "true",
                    "version": "printf 1.0.0",
                    "digest": "printf sha256:test"
                }
            },
            allow_deploy=True,
        )
        first = runner.apply_deployment(
            confirmed=True,
            expected_version="1.0.0",
            expected_digest="sha256:test",
            task_id="deployment",
        )
        self.assertEqual("fail", first["status"])
        task = next(item for item in self.store.load(run_id)["tasks"] if item["id"] == "deployment")
        self.assertEqual("UNCERTAIN", task["sideEffect"]["state"])
        with self.assertRaisesRegex(RuntimeFailure, "already uncertain"):
            runner.apply_deployment(
                confirmed=True,
                expected_version="1.0.0",
                expected_digest="sha256:test",
                task_id="deployment",
            )
        self.assertEqual("1", counter.read_text(encoding="utf-8"))

    def test_deployment_precondition_compares_full_output(self) -> None:
        script = self.repo / "current_state.py"
        script.write_text(
            "from pathlib import Path\n"
            "counter = Path('current-count')\n"
            "value = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            "counter.write_text(str(value))\n"
            "print('x' * 2500 + str(value))\n",
            encoding="utf-8",
        )
        sentinel = self.repo / "applied"
        runner, _ = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "python3 current_state.py",
                    "apply": f"touch {sentinel.name}",
                    "health": "true",
                    "version": "printf 1.0.0",
                    "digest": "printf sha256:test"
                }
            },
            allow_deploy=True,
        )
        with self.assertRaisesRegex(RuntimeFailure, "changed before apply"):
            runner.apply_deployment(
                confirmed=True,
                expected_version="1.0.0",
                expected_digest="sha256:test",
                task_id="deployment",
            )
        self.assertFalse(sentinel.exists())

    def test_failed_deployment_diff_does_not_prepare_or_apply(self) -> None:
        sentinel = self.repo / "applied"
        runner, run_id = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "printf current",
                    "diff": "false",
                    "apply": f"touch {sentinel.name}",
                    "health": "true",
                    "version": "printf 1.0.0",
                    "digest": "printf sha256:test",
                }
            },
            allow_deploy=True,
        )
        with self.assertRaisesRegex(RuntimeFailure, "deployment diff failed before apply"):
            runner.apply_deployment(
                confirmed=True,
                expected_version="1.0.0",
                expected_digest="sha256:test",
                task_id="deployment",
            )
        self.assertFalse(sentinel.exists())
        task = next(item for item in self.store.load(run_id)["tasks"] if item["id"] == "deployment")
        self.assertEqual("PENDING", task["sideEffect"]["state"])

    def test_failed_deployment_preflight_does_not_prepare_or_apply(self) -> None:
        current = self.repo / "current_state.py"
        current.write_text(
            "from pathlib import Path\n"
            "counter = Path('current-count')\n"
            "value = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            "counter.write_text(str(value))\n"
            "if value == 2:\n"
            "    raise SystemExit(1)\n"
            "print('current')\n",
            encoding="utf-8",
        )
        sentinel = self.repo / "applied"
        runner, run_id = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": "python3 current_state.py",
                    "diff": "true",
                    "apply": f"touch {sentinel.name}",
                    "health": "true",
                    "version": "printf 1.0.0",
                    "digest": "printf sha256:test",
                }
            },
            allow_deploy=True,
        )
        with self.assertRaisesRegex(RuntimeFailure, "deployment preflight failed before apply"):
            runner.apply_deployment(
                confirmed=True,
                expected_version="1.0.0",
                expected_digest="sha256:test",
                task_id="deployment",
            )
        self.assertEqual("2", (self.repo / "current-count").read_text(encoding="utf-8"))
        self.assertFalse(sentinel.exists())
        task = next(item for item in self.store.load(run_id)["tasks"] if item["id"] == "deployment")
        self.assertEqual("PENDING", task["sideEffect"]["state"])


if __name__ == "__main__":
    unittest.main(verbosity=2)