#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

from architrave_runtime import RunStore, RuntimeFailure

_fixture_add_task = RunStore.add_task
RunStore.add_task = lambda self, run_id, task, actor="coordinator": _fixture_add_task(
    self, run_id, {"pushback": "KEEP:test fixture", **task}, actor)
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
        return self.python_command("; ".join(statements))

    def python_command(self, source: str) -> str:
        payload = base64.b64encode(source.encode("utf-8")).decode("ascii")
        loader = f"import base64;exec(base64.b64decode('{payload}'))"
        if os.name == "nt":
            executable = str(Path(sys.executable)).replace("'", "''")
            return f"& '{executable}' -c \"{loader}\""
        return shlex.join([sys.executable, "-c", loader])

    def pass_command(self, output: str = "") -> str:
        return self.python_command(f"print({output!r}, end='')" if output else "pass")

    def fail_command(self) -> str:
        return self.python_command("raise SystemExit(1)")

    def touch_command(self, path: str) -> str:
        return self.python_command(f"from pathlib import Path; Path({path!r}).touch()")

    def append_command(self, path: str, value: str) -> str:
        return self.python_command(
            f"from pathlib import Path; p=Path({path!r}); p.open('a', encoding='utf-8').write({value!r})"
        )

    def script_command(self, path: str) -> str:
        return self.python_command(f"exec(compile(open({path!r}, encoding='utf-8').read(), {path!r}, 'exec'))")

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
        runner, run_id = self.create_runner({"health": self.pass_command(), "web": {"url": "http://fixture.invalid"}})
        result = runner.verify_surface("web")
        self.assertEqual("fail", result["status"])
        self.assertIn("web.e2e", result["failed"])
        state = self.store.load(run_id)
        gate = next(item for item in state["gateResults"] if item["id"] == result["gateId"])
        self.assertEqual("FAIL", gate["status"])
        self.assertTrue(gate["evidenceRefs"])
        self.assertEqual("gate.failed", self.store.events(run_id)[-1]["type"])
        self.store.set_criterion(run_id, "REALITY-001", "FAIL", [f"gate:{gate['id']}"])
        verified, completed = self.store.verify(run_id)
        self.assertFalse(completed)
        self.assertEqual("FAILED", verified["status"])
        self.assertEqual("FAIL", verified["acceptanceCriteria"][0]["status"])
        with self.assertRaisesRegex(RuntimeFailure, "passing observed product"):
            self.store.record_gate(run_id, gate_id="cannot-relabel", task_id=None, gate_type="reality",
                                  status="PASS", criteria=["REALITY-001"], surface="web",
                                  evidence_refs=gate["evidenceRefs"])
        (self.repo / "changed-source.md").write_text("Changed after the failed observation\n", encoding="utf-8")
        self.git("add", "changed-source.md")
        self.git("commit", "-qm", "source changed after failure")
        with self.assertRaises(RuntimeFailure) as stale:
            self.store.assert_gate_sources_current(verified, [f"gate:{gate['id']}"])
        self.assertEqual("EVIDENCE_SOURCE_STALE", stale.exception.code)

    def test_repeated_and_independent_observations_keep_prior_authenticated_bytes(self) -> None:
        runner, run_id = self.create_runner({"health": self.pass_command(), "web": {"url": "http://fixture.invalid"}})
        first = runner._finalize_gate("web", [
            runner.recipe("runtime.health", self.pass_command("first")),
            runner.recipe("web.e2e", self.pass_command("workflow-one")),
        ], task_id=None)
        retained = {path: (self.repo / path).read_bytes()
                    for result in first["results"] for path in result["artifacts"]}
        independent = LegibilityRunner(self.repo, run_id)
        second = independent._finalize_gate("web", [
            independent.recipe("runtime.health", self.pass_command("second")),
            independent.recipe("web.e2e", self.pass_command("workflow-two")),
        ], task_id=None)
        third = runner._finalize_gate("web", [
            runner.recipe("runtime.health", self.fail_command()),
            runner.recipe("web.e2e", self.pass_command("workflow-three")),
        ], task_id=None)
        self.assertEqual(retained, {path: (self.repo / path).read_bytes() for path in retained})
        state = self.store.load(run_id)
        self.assertEqual(["PASS", "PASS", "FAIL"], [gate["status"] for gate in state["gateResults"]])
        self.assertEqual({first["gateId"], second["gateId"], third["gateId"]},
                         {gate["id"] for gate in state["gateResults"]})
        paths = [path for result in [*first["results"], *second["results"], *third["results"]]
                 for path in result["artifacts"]]
        self.assertEqual(len(paths), len(set(paths)))

    def test_visual_retention_preserves_exact_validated_bytes_during_source_rewrite(self) -> None:
        import legibility
        with (self.repo / ".gitignore").open("a", encoding="utf-8") as stream:
            stream.write("shot.png\ndom.json\na11y.json\n")
        for structured in (True, False):
            with self.subTest(structured=structured):
                (self.repo / "dom.json").write_text("{}\n", encoding="utf-8")
                (self.repo / "a11y.json").write_text("{}\n", encoding="utf-8")
                screenshot = self.repo / "shot.png"
                self.write_png(screenshot, [(0, 0, 0), (255, 255, 255)])
                observed = screenshot.read_bytes()
                payload = {"url": "http://fixture.invalid/release", "domSnapshot": "dom.json",
                           "accessibilityTree": "a11y.json", "screenshot": "shot.png",
                           "workflowPassed": True, "consoleErrors": [], "networkFailures": []}
                runner, _ = self.create_runner({"health": self.pass_command(), "web": {
                    "url": payload["url"], "e2e": self.json_command(payload, ["dom.json", "a11y.json", "shot.png"])}})
                original = legibility.png_luminance_range

                def validate_then_rewrite(path):
                    result = original(path)
                    self.write_png(screenshot, [(32, 32, 32), (32, 32, 32)])
                    return result

                with mock.patch("legibility.png_luminance_range", side_effect=validate_then_rewrite):
                    result = runner.verify_surface("web") if structured else runner.analyze_ios_screenshot("shot.png")
                self.assertEqual("pass", result["status"])
                artifacts = ([path for entry in result["results"] for path in entry["artifacts"]]
                             if structured else result["artifacts"])
                retained = next(self.repo / path for path in artifacts if path.endswith("-shot.png"))
                self.assertEqual(observed, retained.read_bytes())
                self.assertNotEqual(observed, screenshot.read_bytes())

    def test_failed_gate_admission_rechecks_source_after_preliminary_observation_check(self) -> None:
        runner, run_id = self.create_runner({"health": self.pass_command(), "web": {"url": "http://fixture.invalid"}})
        original = runner.store.record_gate

        def change_before_admission(*args, **kwargs):
            (self.repo / "late-source-edit.md").write_text("Changed after observation checks\n", encoding="utf-8")
            return original(*args, **kwargs)

        with mock.patch.object(runner.store, "record_gate", side_effect=change_before_admission):
            with self.assertRaises(RuntimeFailure) as rejected:
                runner.verify_surface("web")
        self.assertEqual("EVIDENCE_SOURCE_STALE", rejected.exception.code)
        state = self.store.load(run_id)
        self.assertEqual([], state["gateResults"])
        self.assertNotEqual("FAILED", state["status"])

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
            {"health": self.pass_command("healthy"), "web": {"url": "http://fixture.invalid/release", "e2e": evidence}}
        )
        result = runner.verify_surface("web")
        self.assertEqual("pass", result["status"])
        gate = self.store.load(run_id)["gateResults"][-1]
        self.assertEqual("reality", gate["type"])
        self.assertEqual("PASS", gate["status"])

    def test_refreshed_visual_artifacts_do_not_overwrite_prior_receipt_evidence(self) -> None:
        runner, run_id = self.create_runner({"health": self.pass_command(), "web": {"url": "http://fixture.invalid"}})
        input_dir = self.store.run_dir(run_id) / "observed-inputs"
        input_dir.mkdir()
        dom, a11y, image = input_dir / "dom.json", input_dir / "a11y.json", input_dir / "screen.png"
        dom.write_text('{"observed":"first"}')
        a11y.write_text("{}")
        self.write_png(image, [(0, 0, 0), (255, 255, 255)])
        paths = [path.relative_to(runner.repository).as_posix() for path in (dom, a11y, image)]
        payload = {"url": "http://fixture.invalid", "domSnapshot": paths[0],
                   "accessibilityTree": paths[1], "screenshot": paths[2],
                   "workflowPassed": True, "consoleErrors": [], "networkFailures": []}
        def observe():
            structured = runner.structured_recipe("web.e2e", self.json_command(payload, paths),
                lambda value: runner.validate_web_evidence(value, "http://fixture.invalid"))
            return runner._finalize_gate("web", [
                runner.recipe("runtime.health", self.pass_command()), structured], task_id=None)
        first = observe()
        prior = {path: (runner.repository / path).read_bytes()
                 for result in first["results"] for path in result["artifacts"]}
        dom.write_text('{"observed":"second"}')
        self.write_png(image, [(255, 255, 255), (0, 0, 0)])
        second = observe()
        self.assertEqual("pass", second["status"])
        self.assertEqual(prior, {path: (runner.repository / path).read_bytes() for path in prior})
        self.assertEqual(2, len(self.store.load(run_id)["gateResults"]))

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
                    {"health": self.pass_command(), "web": {"url": "http://fixture.invalid/release", "e2e": evidence}}
                )
                result = runner.verify_surface("web")
                self.assertEqual("fail", result["status"])
                web_e2e = next(item for item in result["results"] if item["name"] == "web.e2e")
                self.assertIn("url must match config.runtime.web.url origin and route", web_e2e["stdout"])

    def test_web_trivial_exit_zero_cannot_pass_reality_gate(self) -> None:
        runner, _ = self.create_runner(
            {"health": self.pass_command(), "web": {"url": "http://fixture.invalid", "e2e": self.pass_command()}}
        )
        result = runner.verify_surface("web")
        self.assertEqual("fail", result["status"])
        self.assertIn("web.e2e", result["failed"])

    def test_electron_is_verified_distinctly_from_web(self) -> None:
        runner, _ = self.create_runner(
            {
                "health": self.pass_command(),
                "web": {"url": "http://fixture.invalid", "e2e": self.pass_command()},
                "electron": {"launch": self.fail_command(), "health": self.pass_command(), "screenshot": self.pass_command()},
            }
        )
        before = self.store.load(runner.run_id)
        with self.assertRaisesRegex(RuntimeFailure, "explicit criterion surface ownership"):
            runner.verify_surface("electron")
        after = self.store.load(runner.run_id)
        self.assertEqual(before["gateResults"], after["gateResults"])
        self.assertNotEqual("FAILED", after["status"])

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
            {"electron": {"launch": evidence, "health": self.pass_command(), "screenshot": self.pass_command()}}, surface="electron"
        )
        self.assertEqual("pass", runner.verify_surface("electron")["status"])

    def test_ios_compile_only_cannot_pass_reality_gate(self) -> None:
        runner, _ = self.create_runner(
            {
                "ios": {
                    "bundleId": "example.fixture",
                    "build": self.pass_command(),
                    "install": self.pass_command(),
                    "launch": self.pass_command(),
                    "screenshot": self.pass_command()
                }
            }, surface="ios"
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
                    "build": self.pass_command("build"),
                    "install": self.pass_command("install"),
                    "launch": self.ios_evidence("ios-custom.png"),
                    "logs": self.pass_command("logs"),
                    "screenshot": self.pass_command("screenshot"),
                    "screenshotPath": "ios-custom.png"
                }
            },
            surface="ios",
        )
        self.assertEqual("pass", runner.verify_surface("ios")["status"])

    def test_ios_lifecycle_runs_in_build_to_blank_screen_order(self) -> None:
        lifecycle = self.repo / "ios-lifecycle"
        with (self.repo / ".gitignore").open("a", encoding="utf-8") as handle:
            handle.write("\nios-lifecycle\n")
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
                    "build": self.append_command("ios-lifecycle", "build\n"),
                    "install": self.append_command("ios-lifecycle", "install\n"),
                    "launch": self.python_command(launch_source),
                    "screenshot": self.append_command("ios-lifecycle", "screenshot\n"),
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
                    "build": self.pass_command(),
                    "install": self.pass_command(),
                    "launch": self.ios_evidence("ios-flat.png"),
                    "screenshot": self.pass_command(),
                    "screenshotPath": "ios-flat.png"
                }
            }, surface="ios"
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
                    "build": self.pass_command(),
                    "install": self.pass_command(),
                    "launch": self.ios_evidence("ios-content.png"),
                    "screenshot": self.pass_command(),
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
                    "build": self.pass_command(),
                    "install": self.pass_command(),
                    "launch": stale_command,
                    "screenshot": self.pass_command(),
                    "screenshotPath": "ios-stale.png"
                }
            }, surface="ios"
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
                    "current": self.pass_command("before"),
                    "apply": self.touch_command(sentinel.name),
                    "health": self.pass_command()
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
                    "current": self.pass_command("current"),
                    "diff": self.pass_command("diff"),
                    "apply": self.pass_command("apply"),
                    "health": self.pass_command("healthy"),
                    "version": self.pass_command("1.2.3"),
                    "digest": self.pass_command("sha256:abc")
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
                    "current": self.pass_command("current"),
                    "apply": self.pass_command(),
                    "health": self.pass_command(),
                    "version": self.pass_command("stale"),
                    "digest": self.pass_command("sha256:actual")
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
        apply_command = self.python_command(
            f"from pathlib import Path; p=Path({counter.name!r}); "
            "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1'); raise SystemExit(1)"
        )
        runner, run_id = self.create_runner(
            {
                "deployment": {
                    "target": "sandbox:fixture",
                    "current": self.pass_command("current"),
                    "apply": apply_command,
                    "health": self.pass_command(),
                    "version": self.pass_command("1.0.0"),
                    "digest": self.pass_command("sha256:test")
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
                    "current": self.script_command("current_state.py"),
                    "apply": self.touch_command(sentinel.name),
                    "health": self.pass_command(),
                    "version": self.pass_command("1.0.0"),
                    "digest": self.pass_command("sha256:test")
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
                    "current": self.pass_command("current"),
                    "diff": self.fail_command(),
                    "apply": self.touch_command(sentinel.name),
                    "health": self.pass_command(),
                    "version": self.pass_command("1.0.0"),
                    "digest": self.pass_command("sha256:test"),
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
                    "current": self.script_command("current_state.py"),
                    "diff": self.pass_command(),
                    "apply": self.touch_command(sentinel.name),
                    "health": self.pass_command(),
                    "version": self.pass_command("1.0.0"),
                    "digest": self.pass_command("sha256:test"),
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