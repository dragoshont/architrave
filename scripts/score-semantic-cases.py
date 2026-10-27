#!/usr/bin/env python3
"""Score semantic calibration outputs (REQ-39, REQ-49).

Usage: python scripts/score-semantic-cases.py [--hard|--analysis] <output.json>
--blind prints the cases without expected outcomes, for the judge prompt.
Judge output: [{"case": "C1", "verdict": "REVISE", "responsibilities": {"R1": "preserved", ...}}, ...]
Analysis output: [{"case": "A1", "result": {...}, "rationale": "..."}]
Analysis exit 0 means mechanical match only; rationale needs semantic review.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

CASES = Path(__file__).resolve().parents[1] / "benchmarks/semantic-cases.json"


def read_answers(cases: list[dict]) -> dict[str, dict]:
    path = next((arg for arg in sys.argv[1:] if not arg.startswith("--")), None)
    if path is None:
        raise ValueError("provide an output JSON file, or use --blind")
    text = Path(path).read_text(encoding="utf-8")
    items = json.loads(text[text.index("["):text.rindex("]") + 1])
    allowed = {case["id"] for case in cases}
    answers = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("case"), str):
            raise ValueError("each answer must be an object with a string case id")
        cid = item["case"]
        if cid not in allowed:
            raise ValueError(f"unknown case: {cid}")
        if cid in answers:
            raise ValueError(f"duplicate case: {cid}")
        answers[cid] = item
    return answers


def analysis(cases: list[dict]) -> int:
    if "--blind" in sys.argv:
        print(json.dumps([{k: v for k, v in case.items() if k != "expected"} for case in cases], indent=1))
        return 0
    answers = read_answers(cases)
    matched = 0
    for case in cases:
        got = answers.get(case["id"], {})
        rationale = got.get("rationale")
        has_reasoning = isinstance(rationale, str) and bool(rationale.strip())
        # JSON encoding keeps booleans distinct from integers, including nested fields.
        same = json.dumps(got.get("result"), sort_keys=True) == json.dumps(case["expected"], sort_keys=True)
        ok = same and has_reasoning
        matched += ok
        print(f"{case['id']}: {'match' if ok else 'MISMATCH or missing rationale'}")
    print(f"analysis artifacts {matched}/{len(cases)}; mechanical only, reasoning NOT assessed")
    return 0 if matched == len(cases) else 1


def main() -> int:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    if "--hard" in sys.argv and "--analysis" in sys.argv:
        raise ValueError("choose --hard or --analysis, not both")
    if "--analysis" in sys.argv:
        return analysis(data["analysis_cases"])
    if "--hard" in sys.argv:
        return hard(data["hard_cases"])
    cases = data["cases"]
    if "--blind" in sys.argv:
        print(json.dumps([{k: v for k, v in case.items() if k != "expected"} for case in cases], indent=1))
        return 0
    answers = read_answers(cases)
    verdicts = lost_hit = lost_total = false_lost = preserved_total = unverified_hit = unverified_total = 0
    responsibilities_ok = True
    for case in cases:
        expected, got = case["expected"], answers.get(case["id"], {})
        statuses = got.get("responsibilities", {})
        if not isinstance(statuses, dict):
            raise ValueError(f"{case['id']}: responsibilities must be an object")
        ok = str(got.get("verdict", "")).upper() == expected["verdict"]
        verdicts += ok
        misses = []
        for rid in case["responsibilities"]:
            want, have = expected[rid], str(statuses.get(rid, "missing")).lower()
            if want == "lost":
                lost_total += 1
                lost_hit += have == "lost"
            elif want == "preserved":
                preserved_total += 1
                false_lost += have == "lost"
            else:
                unverified_total += 1
                unverified_hit += have in {"unverified", "lost"}
            if have != want:
                misses.append(f"{rid} {have}!={want}")
                responsibilities_ok = False
        print(f"{case['id']}: verdict {got.get('verdict', 'missing')} ({'ok' if ok else 'want ' + expected['verdict']})"
              + (f"; {', '.join(misses)}" if misses else ""))
    print(f"verdict accuracy {verdicts}/{len(cases)}; lost detected {lost_hit}/{lost_total}; "
          f"false 'lost' on preserved {false_lost}/{preserved_total}; insufficient evidence flagged {unverified_hit}/{unverified_total}")
    return 0 if verdicts == len(cases) and responsibilities_ok else 1


def hard(cases: list[dict]) -> int:
    """--hard [--blind] or --hard <output>: judge returns {"case","verdict","lost":[S..],"unverified":[S..]}."""
    if "--blind" in sys.argv:
        print(json.dumps([{k: v for k, v in case.items() if k != "expected"} for case in cases], indent=1))
        return 0
    answers = read_answers(cases)
    verdicts = hit = total = false = flagged = flag_total = 0
    responsibilities_ok = True
    for case in cases:
        expected, got = case["expected"], answers.get(case["id"], {})
        for field in ("lost", "unverified"):
            values = got.get(field, [])
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ValueError(f"{case['id']}: {field} must be a list of sentence ids")
        want, have = set(expected["lost"]), set(got.get("lost", []))
        unsure, have_unsure = set(expected["unverified"]), set(got.get("unverified", []))
        responsibilities_ok &= want == have and unsure == have_unsure
        ok = str(got.get("verdict", "")).upper() == expected["verdict"]
        verdicts += ok
        hit, total = hit + len(want & have), total + len(want)
        false += len(have - want - unsure)
        flagged, flag_total = flagged + len(unsure & have_unsure), flag_total + len(unsure)
        print(f"{case['id']}: verdict {got.get('verdict', 'missing')} ({'ok' if ok else 'want ' + expected['verdict']}); "
              f"missed {sorted(want - have) or '-'}; false lost {sorted(have - want - unsure) or '-'}")
    print(f"hard: verdict accuracy {verdicts}/{len(cases)}; lost found {hit}/{total}; false lost {false}; "
          f"insufficient evidence flagged {flagged}/{flag_total}")
    return 0 if verdicts == len(cases) and responsibilities_ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
