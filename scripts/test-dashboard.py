#!/usr/bin/env python3
"""Real YAML/CLI/renderer dashboard paths; synthetic host events are evaluation only."""
from __future__ import annotations

import copy
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from board_data import (INSIGHTS, collect_observations, dashboard_model, insight_packet,
                        repository_id, save_insights)
import board_data
from lifecycle import StateError, StateStore, encode, snapshot, utc_now

COORD = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
THIRD = "33333333-3333-3333-3333-333333333333"
NOW = "2026-11-11T19:00:00Z"


def cooperative_collector(root, home, captured, release=None, lock_requested=None):
    original_collect = board_data.collect_session

    class ReportingLock(board_data.FileLock):
        def __enter__(self):
            if lock_requested is not None:
                lock_requested.set()
            return super().__enter__()

    def capture(*args):
        row = original_collect(*args)
        captured.set()
        if release is not None and not release.wait(20):
            raise RuntimeError("Timed out waiting for the synthetic collector release")
        return row

    with mock.patch.object(board_data, "FileLock", ReportingLock), \
            mock.patch.object(board_data, "collect_session", capture), \
            mock.patch.object(board_data, "utc_now", return_value=NOW):
        collect_observations(StateStore(root), COORD, home=Path(home))


class Dashboard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "tasks.md").write_text("| Task | Status |\n| --- | --- |\n| First <task> | Code ready |\n| Second task | |\n")
        self.store = StateStore(self.root)
        state = self.store.initialize("dashboard", import_tasks=True)
        self.ids = list(state["tasks"])
        self.home = self.root / "copilot-home"
        self.n = 0

    def command(self, op, payload):
        self.n += 1
        return self.store.apply(dict(project_id="dashboard", command_id=f"command-{self.n}",
                                     expected_revision=self.store.read()["revision"], operation=op, payload=payload))

    def model(self, ids=None):
        state = self.store.read()
        return dashboard_model(self.store, state, snapshot(state, now=NOW, task_ids=ids), COORD)

    def events(self, rows, sid=COORD):
        path = self.home / "session-state" / sid / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        return path

    def event(self, kind, data=None, eid=None, stamp=NOW):
        return dict(id=eid, type=kind, timestamp=stamp, data=data or {})

    def analysis(self, ids=None):
        ids = ids or self.ids
        view = snapshot(self.store.read(), now=NOW, task_ids=ids)
        return dict(schema=INSIGHTS, project_id="dashboard", repository_id=repository_id(self.root),
                    revision=1, captured_at=NOW, state_revision=view["revision"], scope=ids,
                    input_fingerprint=insight_packet(view)["input_fingerprint"], model="reported-host-model",
                    summary="Implementation readiness is not acceptance.",
                    items=[dict(kind="suggestion", text="Inspect declared acceptance before integration.",
                                task_ids=[ids[0]], evidence_ids=[])])

    def test_scoped_counts_do_not_equate_written_current_or_acceptance(self):
        self.assertEqual(self.model()["counts"]["written"], 1)
        self.assertEqual(self.model()["counts"]["current"], 0)
        self.command("record_progress", dict(task_id=self.ids[0], progress="Code ready"))
        small = self.model([self.ids[0]])
        self.assertEqual(small["counts"]["total"], 1)
        self.assertEqual(small["counts"]["current"], 1)
        self.assertEqual(small["evidence_kinds"]["runtime"],
                         {"declared": 0, "recorded_pass": 0, "unresolved_fail": 0, "conflicts": 0})

    def test_collector_persists_yaml_and_display_never_reads_host_logs_directly(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10, "outputTokens": 0}})])
        before = self.store.path.read_bytes()
        collect_observations(self.store, COORD, home=self.home)
        sidecar = self.root / ".architrave/board-observations.yaml"
        self.assertTrue(sidecar.exists())
        self.assertEqual(self.model()["sessions"][0]["metrics"]["input_tokens"], 10)
        path.write_text("")
        self.assertEqual(self.model()["sessions"][0]["metrics"]["input_tokens"], 10)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_missing_and_zero_are_distinct_and_no_prompt_as_context(self):
        self.events([self.event("session.usage_record", {"usage": {"inputTokens": 20, "outputTokens": 0, "maxPromptTokens": 100}})])
        collect_observations(self.store, COORD, home=self.home)
        row = self.model()["sessions"][0]
        self.assertEqual(row["metrics"]["output_tokens"], 0)
        self.assertIsNone(row["metrics"]["cache_read_tokens"])
        self.assertIsNone(row["context"]["used"])

    def test_duplicate_delivery_and_repeated_capture_do_not_inflate_counts(self):
        event = self.event("session.usage_record", {"usage": {"inputTokens": 10}}, eid="same")
        self.events([event, event])
        first = collect_observations(self.store, COORD, home=self.home)
        second = collect_observations(self.store, COORD, home=self.home)
        self.assertEqual(first["sessions"][0]["metrics"]["input_tokens"], 10)
        self.assertEqual(second["sessions"][0]["metrics"]["input_tokens"], 10)

    def test_real_context_and_model_clear_have_explicit_provenance(self):
        self.events([self.event("session.usage_info", {"currentTokens": 40, "tokenLimit": 100}),
                     self.event("assistant.turn_start", eid="start"),
                     self.event("assistant.turn_end", eid="end", stamp="2026-11-11T19:00:10Z")])
        doc = collect_observations(self.store, COORD, home=self.home)
        row = doc["sessions"][0]
        self.assertEqual(row["context"]["used"], 40)
        self.assertEqual(row["metrics"]["assistant_turn_seconds"], 10)
        self.assertEqual(row["activity"], "idle")
        self.events([self.event("session.usage_info", {"currentTokens": 40, "tokenLimit": 100}),
                     self.event("session.context_cleared")])
        self.assertIsNone(collect_observations(self.store, COORD, home=self.home)["sessions"][0]["context"]["used"])

    def test_missing_session_is_unknown_not_zero_or_completed(self):
        doc = collect_observations(self.store, COORD, home=self.home)
        row = doc["sessions"][0]
        self.assertEqual(row["coverage"], "unavailable")
        self.assertEqual(row["activity"], "unknown")
        self.assertTrue(all(v is None for v in row["metrics"].values()))
        self.assertTrue(row["diagnostics"])

    def test_multiple_selected_collectors_do_not_erase_each_others_sources(self):
        self.events([self.event("session.start")])
        self.events([self.event("session.start")], OTHER)
        collect_observations(self.store, COORD, home=self.home)
        doc = collect_observations(self.store, OTHER, home=self.home)
        self.assertEqual({s["id"] for s in doc["sessions"]}, {COORD, OTHER})
        self.assertEqual([s["id"] for s in self.model()["sessions"]], [COORD])

    def test_same_source_collectors_serialize_capture_before_merging(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10}})])
        context = multiprocessing.get_context("spawn")
        first_captured, second_captured = context.Event(), context.Event()
        release, lock_requested = context.Event(), context.Event()
        first = context.Process(target=cooperative_collector,
                                args=(str(self.root), str(self.home), first_captured, release))
        second = context.Process(target=cooperative_collector,
                                 args=(str(self.root), str(self.home), second_captured, None, lock_requested))
        started = []
        sampled_while_first_pending = None
        try:
            first.start()
            started.append(first)
            self.assertTrue(first_captured.wait(10), "First collector never captured its source")
            with path.open("a") as handle:
                handle.write(json.dumps(self.event("session.usage_record", {"usage": {"inputTokens": 10}})) + "\n")
            second.start()
            started.append(second)
            self.assertTrue(lock_requested.wait(10), "Second collector never requested the sidecar lock")
            sampled_while_first_pending = second_captured.is_set()
            if sampled_while_first_pending:
                second.join(10)
                self.assertEqual(second.exitcode, 0)
        finally:
            release.set()
            for process in started:
                process.join(10)
                if process.is_alive():
                    process.terminate()
                    process.join(10)
        for process in started:
            self.assertEqual(process.exitcode, 0)
        row = self.model()["sessions"][0]
        self.assertEqual(row["metrics"]["input_tokens"], 20)
        self.assertEqual(row["source_bytes"], path.stat().st_size)
        self.assertEqual(row["captured_at"], NOW)
        self.assertEqual(self.model()["observations_revision"], 2)
        self.assertFalse(sampled_while_first_pending, "A waiting collector sampled before acquiring the lock")

    def test_capture_excludes_appends_beyond_its_recorded_extent(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10}})])
        original = collect_observations(self.store, COORD, home=self.home)["sessions"][0]
        original_stat = os.fstat
        appended = []

        def append_after_stat(fd):
            info = original_stat(fd)
            if info.st_ino == path.stat().st_ino and not appended:
                appended.append(True)
                with path.open("a") as handle:
                    handle.write(json.dumps(self.event("session.usage_record", {"usage": {"inputTokens": 10}},
                                                       stamp="2026-11-11T19:00:10Z")) + "\n")
            return info

        with mock.patch.object(board_data.os, "fstat", side_effect=append_after_stat):
            captured = collect_observations(self.store, COORD, home=self.home)["sessions"][0]
        self.assertTrue(appended)
        self.assertGreater(path.stat().st_size, captured["source_bytes"])
        self.assertEqual(captured["source_bytes"], original["source_bytes"])
        self.assertEqual(captured["source_identity"], original["source_identity"])
        self.assertEqual(captured["metrics"]["input_tokens"], 10)
        self.assertEqual(captured["start"], captured["end"])
        self.assertEqual(captured["coverage"], "complete")
        self.assertEqual(collect_observations(self.store, COORD, home=self.home)["sessions"][0]
                         ["metrics"]["input_tokens"], 20)

    def test_serialized_capture_survives_wall_clock_rollback(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10}})])
        with mock.patch.object(board_data, "utc_now", return_value=NOW):
            collect_observations(self.store, COORD, home=self.home)
        with path.open("a") as handle:
            handle.write(json.dumps(self.event("session.usage_record", {"usage": {"inputTokens": 10}})) + "\n")
        earlier = "2026-11-11T18:59:59Z"
        with mock.patch.object(board_data, "utc_now", return_value=earlier):
            doc = collect_observations(self.store, COORD, home=self.home)
        self.assertEqual(doc["revision"], 2)
        self.assertEqual(doc["sessions"][0]["captured_at"], earlier)
        self.assertEqual(doc["sessions"][0]["source_bytes"], path.stat().st_size)
        self.assertEqual(doc["sessions"][0]["metrics"]["input_tokens"], 20)

    def test_bounded_window_stops_at_the_captured_extent(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 1}}),
                            self.event("session.usage_record", {"usage": {"inputTokens": 10}},
                                       stamp="2026-11-11T19:00:10Z")])
        raw = path.read_bytes()
        limit = len(raw.splitlines(keepends=True)[-1]) + 1
        original_stat = os.fstat
        appended = []

        def append_after_stat(fd):
            info = original_stat(fd)
            if info.st_ino == path.stat().st_ino and not appended:
                appended.append(True)
                with path.open("a") as handle:
                    handle.write(json.dumps(self.event("session.usage_record", {"usage": {"inputTokens": 999}},
                                                       stamp="2026-11-11T19:00:20Z")) + "\n")
            return info

        with mock.patch.object(board_data, "MAX_LOG_BYTES", limit), \
                mock.patch.object(board_data.os, "fstat", side_effect=append_after_stat):
            row = collect_observations(self.store, COORD, home=self.home)["sessions"][0]
        self.assertTrue(appended)
        self.assertEqual(row["coverage"], "window")
        self.assertEqual(row["source_bytes"], len(raw))
        self.assertEqual(row["metrics"]["input_tokens"], 10)
        self.assertEqual(row["start"], row["end"])
        self.assertEqual(row["end"], "2026-11-11T19:00:10.000000Z")
        self.assertTrue(any("Bounded source window" in item for item in row["diagnostics"]))

    def test_subsecond_intervals_and_same_second_endpoints_keep_precision(self):
        from board_view import compact
        self.assertEqual(compact(0.2), "<1")
        self.assertEqual(compact(0), "0")
        self.assertEqual(compact(None), "Unknown")
        for start, end, seconds in (
                ("2026-11-11T19:00:00.900Z", "2026-11-11T19:00:01.100Z", 0.2),
                ("2026-11-11T19:00:00.100Z", "2026-11-11T19:00:00.900Z", 0.8),
                (NOW, "2026-11-11T19:00:00.250Z", 0.25)):
            with self.subTest(start=start, end=end):
                self.events([self.event("assistant.turn_start", stamp=start),
                             self.event("assistant.turn_end", stamp=end)])
                row = collect_observations(self.store, COORD, home=self.home)["sessions"][0]
                self.assertAlmostEqual(row["metrics"]["assistant_turn_seconds"], seconds)
                self.assertEqual(row["intervals"], [[row["start"], row["end"]]])
                self.assertLess(row["start"], row["end"])

    def test_reversed_subsecond_interval_is_not_a_zero_duration_turn(self):
        self.events([self.event("assistant.turn_start", stamp="2026-11-11T19:00:00.900Z"),
                     self.event("assistant.turn_end", stamp="2026-11-11T19:00:00.100Z")])
        row = collect_observations(self.store, COORD, home=self.home)["sessions"][0]
        self.assertIsNone(row["metrics"]["assistant_turn_seconds"])
        self.assertFalse(row["intervals"])
        self.assertLess(row["start"], row["end"])
        self.assertTrue(any("invalid" in item for item in row["diagnostics"]))

    def test_cached_render_preserves_newly_selected_uncollected_sources(self):
        import board_view
        self.command("claim_task", dict(id="first", task_id=self.ids[0], worker=COORD, host="test:host",
                                       read_only=True))
        self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10}})])
        collect_observations(self.store, COORD, task_ids=[self.ids[0]], home=self.home)
        self.command("claim_task", dict(id="second", task_id=self.ids[1], worker=OTHER, host="test:host",
                                       read_only=True))
        self.events([self.event("session.usage_record", {"usage": {"inputTokens": 999}})], OTHER)
        sidecar = self.root / ".architrave/board-observations.yaml"
        before = sidecar.read_bytes(), self.store.path.read_bytes()
        original_open = Path.open

        def cache_only(path, *args, **kwargs):
            self.assertNotEqual(path.name, "events.jsonl", "Cached display must not read host logs")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", cache_only):
            model = self.model()
            page = board_view.render(dict(dashboard=model, title="Selected source coverage"))
        self.assertEqual({row["id"] for row in model["sessions"]}, {COORD, OTHER})
        missing = next(row for row in model["sessions"] if row["id"] == OTHER)
        self.assertEqual(missing["task_ids"], [self.ids[1]])
        self.assertFalse(missing["coordinator"])
        self.assertEqual(missing["coverage"], "unavailable")
        self.assertEqual(missing["activity"], "unknown")
        for field in ("source_identity", "source_bytes", "captured_at", "observed_at",
                      "start", "end", "model", "selected_model"):
            self.assertIsNone(missing[field], field)
        self.assertTrue(all(value is None for value in missing["metrics"].values()))
        self.assertTrue(all(value is None for value in missing["context"].values()))
        self.assertFalse(missing["intervals"])
        self.assertTrue(missing["diagnostics"])
        self.assertIn("<strong>1/2</strong>", page)
        output = self.root / "cached-board.html"
        result = subprocess.run([sys.executable, str(ROOT / "harness/program_board.py"), "--ledger", str(self.root),
                                 "--session", COORD, "--output", str(output)], cwd=self.root,
                                env=dict(os.environ, COPILOT_HOME=str(self.home)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<strong>1/2</strong>", output.read_text())
        self.assertEqual(before, (sidecar.read_bytes(), self.store.path.read_bytes()))

    def test_uncollected_sources_and_shared_worker_task_links_are_scoped(self):
        self.command("claim_task", dict(id="first", task_id=self.ids[0], worker=OTHER, host="test:host",
                                       read_only=True))
        self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10}})], OTHER)
        collect_observations(self.store, OTHER, task_ids=[self.ids[0]], home=self.home)
        self.command("claim_task", dict(id="second", task_id=self.ids[1], worker=THIRD, host="test:host",
                                       read_only=True))
        model = self.model([self.ids[1]])
        self.assertEqual({row["id"] for row in model["sessions"]}, {COORD, THIRD})
        self.assertTrue(all(row["coverage"] == "unavailable" for row in model["sessions"]))
        self.command("observe_attempt", dict(attempt_id="second", activity="completed", stop_acknowledged=False,
                                            reference="test:terminal", observed_at=NOW))
        self.command("claim_task", dict(id="shared", task_id=self.ids[1], worker=OTHER, host="test:host",
                                       read_only=True))
        observed = next(row for row in self.model([self.ids[1]])["sessions"] if row["id"] == OTHER)
        self.assertEqual(observed["task_ids"], [self.ids[1]])
        self.assertEqual(observed["metrics"]["input_tokens"], 10)
        self.assertEqual([row["id"] for row in self.model([])["sessions"]], [COORD])

    def test_invalid_optional_sidecar_does_not_hide_valid_tasks(self):
        path = self.root / ".architrave/board-observations.yaml"
        path.write_text("invalid YAML")
        view = self.model()
        self.assertEqual(view["counts"]["total"], 2)
        self.assertEqual([row["id"] for row in view["sessions"]], [COORD])
        self.assertIsNone(view["sessions"][0]["captured_at"])
        self.assertEqual(view["sessions"][0]["coverage"], "unavailable")
        self.assertIn("Observations unavailable", view["diagnostics"][0])

    def test_cross_project_sidecar_rejected_without_factual_merge(self):
        self.events([self.event("session.start")])
        doc = collect_observations(self.store, COORD, home=self.home)
        doc["project_id"] = "other-project"
        (self.root / ".architrave/board-observations.yaml").write_bytes(encode(doc))
        self.assertEqual([row["id"] for row in self.model()["sessions"]], [COORD])
        self.assertIsNone(self.model()["sessions"][0]["captured_at"])
        self.assertTrue(all(value is None for value in self.model()["sessions"][0]["metrics"].values()))
        self.assertTrue(self.model()["diagnostics"])

    def test_linked_sidecar_is_rejected_without_reading_or_overwriting_target(self):
        outside = self.root / "outside.yaml"
        outside.write_text("PRIVATE")
        (self.root / ".architrave/board-observations.yaml").symlink_to(outside)
        self.assertTrue(self.model()["diagnostics"])
        with self.assertRaises(StateError):
            collect_observations(self.store, COORD, home=self.home)
        self.assertEqual(outside.read_text(), "PRIVATE")

    def test_insights_are_optional_and_rendering_never_invokes_a_model(self):
        before = self.store.path.read_bytes()
        self.assertIsNone(self.model()["insights"])
        doc = self.analysis()
        save_insights(self.store, doc)
        self.assertEqual(self.model()["insights"]["applicability"], "current")
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_analysis_stales_only_when_scoped_facts_change_not_clock_or_phase(self):
        doc = self.analysis([self.ids[0]])
        save_insights(self.store, doc)
        self.command("set_phase", {"phase": "review"})
        self.assertEqual(self.model([self.ids[0]])["insights"]["applicability"], "current")
        self.command("record_progress", {"task_id": self.ids[0], "progress": "In progress"})
        self.assertEqual(self.model([self.ids[0]])["insights"]["applicability"], "stale")
        self.assertEqual(self.model([self.ids[0]])["insights"]["summary"], doc["summary"])

    def test_subset_and_disjoint_scope_omit_entire_analysis_from_html(self):
        import board_view
        for revision, (scope, selected) in enumerate(((self.ids, [self.ids[0]]),
                                                     ([self.ids[0]], [self.ids[1]])), 1):
            with self.subTest(scope=scope, selected=selected):
                doc = self.analysis(scope)
                doc["revision"] = revision
                doc["summary"] = "PRIVATE_OTHER_SCOPE_SUMMARY"
                doc["items"][0]["text"] = "PRIVATE_OTHER_SCOPE_ITEM"
                save_insights(self.store, doc)
                self.assertEqual(self.model(scope)["insights"]["applicability"], "current")
                model = self.model(selected)
                self.assertIsNone(model["insights"])
                page = board_view.render(dict(dashboard=model, title="Scoped analysis"))
                for marker in (doc["summary"], doc["items"][0]["text"], *set(scope).difference(selected)):
                    self.assertNotIn(marker, page)

    def test_analysis_reference_and_shape_and_revision_conflicts(self):
        original = self.analysis()
        for field, value in (("dispatch", "deploy"), ("items", [dict(kind="suggestion", text="do it",
                                   task_ids=["missing"], evidence_ids=[])])):
            doc = copy.deepcopy(original)
            doc[field] = value
            with self.assertRaises(StateError):
                save_insights(self.store, doc)
        save_insights(self.store, original)
        with self.assertRaises(StateError):
            save_insights(self.store, original)
        future = self.analysis()
        future["revision"] = 2
        future["state_revision"] = self.store.read()["revision"] + 1
        with self.assertRaises(StateError):
            save_insights(self.store, future)

    def test_collection_does_not_copy_raw_tool_or_message_content(self):
        private = "PRIVATE_RAW_TOOL_BODY_NOT_FOR_DISPLAY"
        self.events([self.event("tool.execution_start", {"toolName": "bash", "arguments": private}),
                     self.event("assistant.message", {"content": private}),
                     self.event("session.usage_info", {"currentTokens": 1, "tokenLimit": 10})])
        doc = collect_observations(self.store, COORD, home=self.home)
        self.assertNotIn(private, encode(doc).decode())
        self.assertEqual(doc["sessions"][0]["context"]["used"], 1)

    def test_valid_final_event_without_newline_and_partial_event_diagnostics(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 0}})])
        path.write_text(path.read_text().rstrip())
        doc = collect_observations(self.store, COORD, home=self.home)
        self.assertEqual(doc["sessions"][0]["metrics"]["input_tokens"], 0)
        path.write_text(path.read_text() + '\n{"type":')
        doc = collect_observations(self.store, COORD, home=self.home)
        self.assertTrue(any("incomplete" in d for d in doc["sessions"][0]["diagnostics"]))

    def test_source_replacement_recomputes_instead_of_adding_counters(self):
        path = self.events([self.event("session.usage_record", {"usage": {"inputTokens": 10}})])
        collect_observations(self.store, COORD, home=self.home)
        path.write_text(json.dumps(self.event("session.usage_record", {"usage": {"inputTokens": 2}})) + "\n")
        doc = collect_observations(self.store, COORD, home=self.home)
        self.assertEqual(doc["sessions"][0]["metrics"]["input_tokens"], 2)

    def test_subagent_and_compaction_usage_cannot_become_root_context(self):
        child = self.event("session.usage_info", {"currentTokens": 999, "tokenLimit": 1000})
        child["agentId"] = "child"
        self.events([child, self.event("session.usage_info", {"currentTokens": 2, "tokenLimit": 10, "initiator": "compaction"})])
        doc = collect_observations(self.store, COORD, home=self.home)
        self.assertIsNone(doc["sessions"][0]["context"]["used"])

    def test_rich_renderer_is_deterministic_escaped_and_not_a_model_call(self):
        import board_view
        data = {"dashboard": self.model(), "title": "<script>not trusted</script>", "refresh": 30}
        before = copy.deepcopy(data)
        page = board_view.render(data)
        self.assertEqual(page, board_view.render(data))
        self.assertEqual(before, data)
        self.assertIn("&lt;script&gt;not trusted&lt;/script&gt;", page)
        self.assertNotIn("<script>not trusted", page)
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("connect-src &#x27;none&#x27;", page)
        self.assertNotIn("http-equiv='refresh'", page)
        self.assertIn("Pause updates", page)
        self.assertIn("Not declared in this scope", page)
        self.assertIn("<strong>0/1</strong>", page)
        self.assertIn("No session observations yet", page)

    def test_real_cli_packet_and_insight_submission(self):
        command = [sys.executable, str(ROOT / "harness/architrave_cli.py"), "board", "--repo", str(self.root)]
        result = subprocess.run(command + ["packet", "--tasks", self.ids[0]], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        binding = json.loads(result.stdout)["output_binding"]
        doc = dict(binding, captured_at=NOW, model="reported-evaluation-host", summary="One selected item.",
                   items=[dict(kind="question", text="Inspect acceptance before integration.",
                               task_ids=[self.ids[0]], evidence_ids=[])])
        result = subprocess.run(command + ["insights", "--input", "-"], input=encode(doc).decode(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.model([self.ids[0]])["insights"]["applicability"], "current")

    def test_actual_installer_ships_assets_and_adopted_cli_board(self):
        target = self.root / "consumer"
        target.mkdir()
        result = subprocess.run([sys.executable, str(ROOT / "tools/install_update.py"), "install",
                                 "--profile", "knowledge", str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("board_data.py", "board_view.py", "board.css", "board.js"):
            self.assertEqual((target / "harness" / name).read_bytes(), (ROOT / "harness" / name).read_bytes())
        self.assertTrue((target / "docs/dashboard.md").is_file())
        (target / "tasks.md").write_text("| Task | Status |\n| --- | --- |\n| Adopted board | Code ready |\n")
        command = [sys.executable, str(target / "harness/architrave_cli.py"), "state", "--repo", str(target)]
        result = subprocess.run(command + ["init", "--project", "consumer", "--import-tasks"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = target / "board.html"
        result = subprocess.run([sys.executable, str(target / "harness/program_board.py"), "--ledger", str(target),
                                 "--session", COORD, "--output", str(output)],
                                cwd=target, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = output.read_text()
        self.assertIn("Adopted board", page)
        self.assertIn("data-readiness='unavailable'", page)
        self.assertIn("data-next-action='reevaluate'", page)
        self.assertIn("<strong>0/1</strong>", page)
        self.assertIn("No session observations yet", page)
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("board-*.yaml", (target / ".gitignore").read_text())


if __name__ == "__main__":
    unittest.main()
