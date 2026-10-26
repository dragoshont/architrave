#!/usr/bin/env python3
"""Score judge output against benchmarks/semantic-cases.json by responsibility id (REQ-39).

Usage: python scripts/score-semantic-cases.py <judge-output.json> [--blind]
--blind prints the cases without expected outcomes, for the judge prompt.
Judge output: [{"case": "C1", "verdict": "REVISE", "responsibilities": {"R1": "preserved", ...}}, ...]
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

CASES = Path(__file__).resolve().parents[1] / "benchmarks/semantic-cases.json"


def main() -> int:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    if "--hard" in sys.argv:
        return hard(data["hard_cases"])
    cases = data["cases"]
    if "--blind" in sys.argv:
        print(json.dumps([{k: v for k, v in case.items() if k != "expected"} for case in cases], indent=1))
        return 0
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    answers = {item["case"]: item for item in json.loads(text[text.index("["):text.rindex("]") + 1])}
    verdicts = lost_hit = lost_total = false_lost = preserved_total = unverified_hit = unverified_total = 0
    for case in cases:
        expected, got = case["expected"], answers.get(case["id"], {})
        statuses = got.get("responsibilities", {})
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
        print(f"{case['id']}: verdict {got.get('verdict', 'missing')} ({'ok' if ok else 'want ' + expected['verdict']})"
              + (f"; {', '.join(misses)}" if misses else ""))
    print(f"verdict accuracy {verdicts}/{len(cases)}; lost detected {lost_hit}/{lost_total}; "
          f"false 'lost' on preserved {false_lost}/{preserved_total}; insufficient evidence flagged {unverified_hit}/{unverified_total}")
    return 0 if verdicts == len(cases) and lost_hit == lost_total and not false_lost else 1


def hard(cases: list[dict]) -> int:
    """--hard [--blind] or --hard <output>: judge returns {"case","verdict","lost":[S..],"unverified":[S..]}."""
    if "--blind" in sys.argv:
        print(json.dumps([{k: v for k, v in case.items() if k != "expected"} for case in cases], indent=1))
        return 0
    path = next(arg for arg in sys.argv[1:] if not arg.startswith("--"))
    text = Path(path).read_text(encoding="utf-8")
    answers = {item["case"]: item for item in json.loads(text[text.index("["):text.rindex("]") + 1])}
    verdicts = hit = total = false = flagged = flag_total = 0
    for case in cases:
        expected, got = case["expected"], answers.get(case["id"], {})
        want, have = set(expected["lost"]), set(got.get("lost", []))
        unsure, have_unsure = set(expected["unverified"]), set(got.get("unverified", [])) | have
        ok = str(got.get("verdict", "")).upper() == expected["verdict"]
        verdicts += ok
        hit, total = hit + len(want & have), total + len(want)
        false += len(have - want - unsure)
        flagged, flag_total = flagged + len(unsure & have_unsure), flag_total + len(unsure)
        print(f"{case['id']}: verdict {got.get('verdict', 'missing')} ({'ok' if ok else 'want ' + expected['verdict']}); "
              f"missed {sorted(want - have) or '-'}; false lost {sorted(have - want - unsure) or '-'}")
    print(f"hard: verdict accuracy {verdicts}/{len(cases)}; lost found {hit}/{total}; false lost {false}; "
          f"insufficient evidence flagged {flagged}/{flag_total}")
    return 0 if verdicts == len(cases) and hit == total and not false else 1


if __name__ == "__main__":
    sys.exit(main())
