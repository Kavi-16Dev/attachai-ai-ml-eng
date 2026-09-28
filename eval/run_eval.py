"""Runs the REAL extraction client (real OpenAI API calls, no test double)
against eval/golden_set.json and scores it.

    python -m eval.run_eval

Per record, three checks are made against ONE extracted attribute - the one
that satisfies the most checks - so a record only passes if a single
attribute is right on all three at once (not kind from one attribute and
keywords from another):
  kind_match        attribute.kind == expected_kind
  restricted_match  attribute.restricted == expected_restricted (exact)
  keyword_match     attribute.text contains >=1 expected keyword (case-insens.)

Prints a line per record and an overall score; exits 1 if the score is
below THRESHOLD.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.llm_providers.openai_client import OpenAILLMClient

# 0.75 = at least 3 of the 4 golden records must fully pass. With only four
# hand-labelled records, one borderline call (e.g. kind context vs interest)
# is tolerable noise, but two misses is a real regression. See DESIGN_NOTES.
THRESHOLD = 0.75


def score_record(record: dict, extracted: list[dict]) -> dict:
    best = {"kind_match": False, "restricted_match": False, "keyword_match": False}
    best_score = -1
    best_attr = None
    for attr in extracted:
        checks = {
            "kind_match": attr["kind"] == record["expected_kind"],
            "restricted_match": bool(attr["restricted"]) == bool(record["expected_restricted"]),
            "keyword_match": any(
                kw.lower() in attr["text"].lower() for kw in record["expected_keywords"]
            ),
        }
        if sum(checks.values()) > best_score:
            best, best_score, best_attr = checks, sum(checks.values()), attr
    return {**best, "passed": all(best.values()), "best_attribute": best_attr}


def main() -> int:
    golden = json.loads((Path(__file__).parent / "golden_set.json").read_text())
    client = OpenAILLMClient()

    passed = 0
    for i, record in enumerate(golden, 1):
        try:
            extracted = client.extract_attributes(record["message"])
        except Exception as exc:  # noqa: BLE001 - report and keep scoring
            print(f"[{i}] FAIL  error: {exc}\n      message: {record['message']!r}")
            continue
        r = score_record(record, extracted)
        passed += r["passed"]
        print(
            f"[{i}] {'PASS' if r['passed'] else 'FAIL'}  "
            f"kind={r['kind_match']} restricted={r['restricted_match']} keywords={r['keyword_match']}\n"
            f"      message:  {record['message']!r}\n"
            f"      expected: kind={record['expected_kind']} restricted={record['expected_restricted']} "
            f"keywords={record['expected_keywords']}\n"
            f"      got:      {extracted}"
        )

    score = passed / len(golden)
    print(f"\nOverall: {passed}/{len(golden)} = {score:.2f}  (threshold {THRESHOLD})")
    if score < THRESHOLD:
        print("BELOW THRESHOLD")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
