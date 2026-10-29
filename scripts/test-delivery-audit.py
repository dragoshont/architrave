#!/usr/bin/env python3
"""Exercise the audit on real temporary Git repositories; no provider substitutes."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("delivery_audit", ROOT / "gates" / "delivery_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DeliveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.git("init", "--quiet")
        self.write("SPEC.md", "# Requirements\nREQ-01: use the real provider.\n")
        self.write("README.md", "Run the actual integration.\n")
        self.git("add", ".")
        self.git("-c", "user.name=Scanner Test", "-c", "user.email=scanner@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Audit baseline")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], stderr=subprocess.STDOUT)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def report(self, **kwargs):
        return audit.scan(self.root, **kwargs)

    def test_real_call_does_not_claim_live_acceptance(self):
        self.write("src/client.py", "result = client.execute(request)\n")
        report = self.report()
        self.assertEqual(report["status"], "NO_CANDIDATES")
        self.assertTrue(any("not real-integration" in s for s in report["limitations"]))

    def test_untracked_runtime_substitute(self):
        self.write("src/provider.cs", 'var provider = new FakeProvider();\n')
        row = self.report()["findings"][0]
        self.assertEqual((row["path"], row["line"], row["category"]),
                         ("src/provider.cs", 1, "substitute"))

    def test_literal_and_variable_nock_interception(self):
        self.write("src/intercept.js",
                   'nock("https://example.invalid").get("/data").reply(200, {});\n'
                   "nock('https://example.invalid');\n"
                   "nock  ( serviceUrl );\n")
        self.assertEqual({r["line"] for r in self.report()["findings"]
                          if r["category"] == "interception"}, {1, 2, 3})

    def test_source_and_base_identity_bind_unchanged_dependencies(self):
        self.write("src/provider.py", "result = client.execute(request)\n")
        first = self.report()
        self.assertEqual(first["base_sha"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertTrue(any(f["path"] == "src/provider.py" for f in first["source_files"]))
        self.write("src/provider.py", "result = client.execute(another_request)\n")
        self.assertNotEqual(first["source_sha256"], self.report()["source_sha256"])

    def test_nondefault_requirements_supported_by_current_schema(self):
        schema = json.loads((ROOT / "kit" / "architrave.config.schema.json").read_text())
        self.assertEqual(schema["properties"]["requirements"]["type"], "string")
        self.write("docs/intent.md", "Owner requirement: real integration.\n")
        self.write("architrave.config.json", json.dumps({
            "kind": "knowledge", "build": "git diff --check", "test": "python checks.py",
            "requirements": "docs/intent.md"}))
        self.assertEqual(self.report()["documents"][0]["path"], "docs/intent.md")

    def test_default_false_eligibility_detected(self):
        self.write("src/options.cs", "public record Options(bool ProviderEligible = false);\n")
        self.assertTrue(any(r["category"] == "flag-or-selector" for r in self.report()["findings"]))

    def test_launcher_environment_selector_detected_without_exposing_values(self):
        self.write("launch.ps1", '$env:EXAMPLE_PROVIDER_ELIGIBLE = "private-value-not-for-output"\n')
        serialized = json.dumps(self.report())
        self.assertIn("environment-selector", serialized)
        self.assertNotIn("private-value-not-for-output", serialized)

    def test_keyword_in_sensitive_value_never_printed(self):
        private_value = "fakePrivateKey123"
        self.write("settings.json", json.dumps({"ApiKey": private_value}))
        self.assertNotIn(private_value, json.dumps(self.report()))
        for mode in ([], ["--json"]):
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / "gates" / "delivery_audit.py"),
                 "--repo", str(self.root), *mode],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(private_value, result.stdout + result.stderr)

    def test_effective_config_files_in_default_and_all_scopes(self):
        self.write(".env", "USE_REAL_PROVIDER=False\n")
        self.write("settings.ini", "[providers]\nintegrationEnabled=false\n")
        self.git("add", ".")
        self.git("-c", "user.name=Scanner Test", "-c", "user.email=scanner@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Effective settings")
        self.write(".env", "USE_REAL_PROVIDER=False\nCURRENT_MODE=local\n")
        self.write("settings.ini", "[providers]\nintegrationEnabled=false\nmode=local\n")
        self.write(".env.development", "USE_REAL_PROVIDER=False\n")
        for kwargs in ({}, {"all_files": True}):
            report = self.report(**kwargs)
            for name in (".env", ".env.development", "settings.ini"):
                self.assertIn(name, report["inspected_files"])
                self.assertTrue(any(r["path"] == name for r in report["findings"]))

    def test_uppercase_and_snake_case_switches(self):
        self.write("src/options.py", 'USE_REAL_PROVIDER = False\nuse_mock = False\n')
        self.assertEqual(
            {r["line"] for r in self.report()["findings"] if r["category"] == "flag-or-selector"},
            {1, 2})

    def test_lower_camel_switches_not_ordinary_user_words(self):
        self.write("settings.json", '{"useRealProvider": false, "enableLiveApi": false}\n')
        self.assertTrue(any(r["category"] == "flag-or-selector" for r in self.report()["findings"]))
        self.write("settings.json", '{"username": "ordinary", "useful": true}\n')
        self.assertFalse(any(r["category"] == "flag-or-selector" for r in self.report()["findings"]))

    def test_existing_default_in_modified_file(self):
        self.write("src/options.py", 'enabled = False\n')
        self.git("add", ".")
        self.git("-c", "user.name=Scanner Test", "-c", "user.email=scanner@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Existing option")
        self.write("src/options.py", 'enabled = False\nresult = real_provider()\n')
        self.assertTrue(any(r["line"] == 1 for r in self.report()["findings"]))

    def test_test_directory_is_not_silently_exempt(self):
        self.write("tests/provider.py", 'return_value = "deterministic-test"\n')
        rows = self.report()["findings"]
        self.assertTrue(rows)
        self.assertTrue(all(r["scope"] == "test-location-unverified" for r in rows))

    def test_document_mention_is_not_permission(self):
        self.write("docs/demo.md", "REQ-01: FakeProvider is mentioned, not authorized.\n")
        self.write("src/provider.ts", "const provider = new FakeProvider();\n")
        report = self.report(documents=["docs/demo.md"])
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["findings"][0]["contract_mentions"],
                         [{"path": "docs/demo.md", "line": 1}])
        self.assertEqual(len(report["documents"]), 2)

    def test_explicit_all_includes_unchanged_sources(self):
        self.write("src/provider.py", 'mode = "deterministic-test"\n')
        self.git("add", ".")
        self.git("-c", "user.name=Scanner Test", "-c", "user.email=scanner@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Baseline provider")
        self.assertEqual(self.report()["status"], "NO_CANDIDATES")
        self.assertEqual(self.report(all_files=True)["status"], "REVIEW_REQUIRED")

    def test_missing_documents_and_invalid_base_block(self):
        with self.assertRaises(ValueError):
            self.report(documents=["docs/missing.md"])
        with self.assertRaises(ValueError):
            self.report(base="missing-branch")
        (self.root / "SPEC.md").unlink()
        with self.assertRaises(ValueError):
            self.report()

    def test_invalid_source_encoding_blocks(self):
        (self.root / "src.py").write_bytes(b"\xff\xfe")
        with self.assertRaises(ValueError):
            self.report()

    def test_external_contract_path_rejected(self):
        with self.assertRaises(ValueError):
            self.report(documents=["../README.md"])
        self.write("docs/empty.md", "")
        with self.assertRaises(ValueError):
            self.report(documents=["docs/empty.md"])
        with self.assertRaises(ValueError):
            self.report(base="--output=unrequested")
        self.assertFalse((self.root / "unrequested").exists())

    def test_command_exit_codes_and_plugin_only_gate(self):
        self.write("src/options.json", '{"integrationEnabled": false}')
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "gates" / "gate_runner.py"),
             "delivery-audit", "--repo", str(self.root), "--json"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "REVIEW_REQUIRED")
        self.assertFalse((self.root / "architrave.config.json").exists())

    def test_ignored_outputs_not_read_and_no_target_writes(self):
        self.write(".gitignore", "private/\n")
        self.write("private/secret.json", '{"FakeProvider": "do-not-read"}')
        before = self.git("status", "--porcelain")
        report = self.report(all_files=True)
        self.assertNotIn("private/secret.json", report["inspected_files"])
        self.assertEqual(before, self.git("status", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
