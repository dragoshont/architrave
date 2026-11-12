#!/usr/bin/env python3
"""Score semantic calibration outputs (REQ-39, REQ-49).

Usage: python scripts/score-semantic-cases.py [--hard|--analysis|--domain] <output.json>
--blind prints the cases without expected outcomes, for the judge prompt.
Judge output: [{"case": "C1", "verdict": "REVISE", "responsibilities": {"R1": "preserved", ...}}, ...]
Analysis output: [{"case": "A1", "result": {...}, "rationale": "..."}]
Analysis exit 0 means mechanical match only; rationale needs semantic review.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import re
import argparse

CASES = Path(__file__).resolve().parents[1] / "benchmarks/semantic-cases.json"


def check_host_findings(text: str, target: Path) -> dict:
    """Validate references and record shape, never infer a semantic verdict."""
    errors = []
    records = []
    try:
        stripped = text.strip()
        if stripped.startswith("```json") and stripped.endswith("```"):
            stripped = stripped[7:-3].strip()
        answer = json.loads(stripped)
        if not isinstance(answer, dict) or not isinstance(answer.get("findings"), list):
            raise ValueError("answer must contain a findings array")
        allowed = {"confirmed violation", "supported concern", "unknown/needs domain input",
                   "valid alternative/no violation", "not applicable"}
        ids = set()
        for index, finding in enumerate(answer["findings"]):
            if not isinstance(finding, dict):
                errors.append(f"finding {index}: must be an object")
                continue
            records.append(finding)
            label = str(finding.get("id", index))
            for key in ("id", "scenario", "alternative_or_unknown", "remedy", "falsifier", "confidence"):
                if not isinstance(finding.get(key), str) or not finding[key].strip():
                    errors.append(f"{label}: missing {key}")
            if label in ids:
                errors.append(f"{label}: duplicate id")
            ids.add(label)
            if finding.get("classification") not in allowed:
                errors.append(f"{label}: invalid classification")
            for key in ("code", "source"):
                reference = finding.get(key)
                if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
                    errors.append(f"{label}: missing {key} reference")
                    continue
                relative = Path(reference["path"])
                resolved = (target / relative).resolve()
                if relative.is_absolute() or not resolved.is_relative_to(target.resolve()) or not resolved.is_file():
                    errors.append(f"{label}: {key} must name an existing target file")
                    continue
                try:
                    content = resolved.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    errors.append(f"{label}: unreadable {key}: {exc}")
                    continue
                start, end = reference.get("start_line"), reference.get("end_line")
                if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(content.splitlines()):
                    errors.append(f"{label}: {key} line range outside file")
                if key == "source":
                    for field in ("status", "authority"):
                        if not isinstance(reference.get(field), str) or not reference[field].strip():
                            errors.append(f"{label}: source missing {field}")
                    declared = re.search(r"(?im)^Status:\s*(.+)$", content)
                    status = reference.get("status")
                    if declared and isinstance(status, str):
                        # Qualifiers are reviewed semantically; compare the declared status itself.
                        document_status = re.split(r"[;,(]|\s+by\s+", declared[1], maxsplit=1, flags=re.I)[0].strip().casefold()
                        reported_status = re.split(r"[;,(]|\s+by\s+", status, maxsplit=1, flags=re.I)[0].strip().casefold()
                        if document_status != reported_status:
                            errors.append(f"{label}: source status contradicts document label")
    except (ValueError, TypeError) as exc:
        errors.append(str(exc))
    return {"mechanical_valid": not errors, "errors": errors, "records": records,
            "semantic_adjudication": None, "identified_defects": None, "false_positives": None,
            "correct_unknowns": None, "basis": "shape, existing paths/lines and declared status only; entailment unassessed"}


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
    if "--host-findings" in sys.argv:
        parser = argparse.ArgumentParser(description="Mechanical evidence validation only; no semantic PASS.")
        parser.add_argument("--host-findings", type=Path, required=True)
        parser.add_argument("--target", type=Path, required=True)
        args = parser.parse_args()
        report = check_host_findings(args.host_findings.read_text(encoding="utf-8"), args.target)
        print(json.dumps(report, indent=2))
        return 0 if report["mechanical_valid"] else 1
    data = json.loads(CASES.read_text(encoding="utf-8"))
    if sum(flag in sys.argv for flag in ("--hard", "--analysis", "--domain")) > 1:
        raise ValueError("choose one of --hard, --analysis or --domain")
    if "--domain" in sys.argv:
        return analysis(data["domain_cases"])
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
