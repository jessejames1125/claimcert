"""Measure the gap the planted benchmark cannot see: a formal statement that does not say what the
English says.

    python evals/run_translation.py --agent "claude -p --model sonnet"

Every claim in evals/translation is true as formal mathematics, so Lean should pass all 12. Six of
them were written to disagree with their English intent. The question is whether the blind audit
(one agent run reads only the Lean, a second compares that reading with the intent) notices.
Writes evals/results/translation.json. Pass --no-kernel to reuse the recorded verdicts."""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from claimcert.agent import AgentError
from claimcert.audit import audit_agent
from claimcert.check import check_claim
from claimcert.claims import load_claim
from claimcert.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "evals" / "translation"
REG = SET / "registry.yaml"
OUT = ROOT / "evals" / "results" / "translation.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--no-kernel", action="store_true")
    a = ap.parse_args()
    expected = json.loads((SET / "expected.json").read_text(encoding="utf-8"))
    reg = load_registry(REG)
    rows = {}
    for name in sorted(expected):
        path = SET / f"{name}.yaml"
        if a.no_kernel:
            verdict = json.loads(path.with_suffix(".verdict.json").read_text(encoding="utf-8"))
        else:
            record = SET / "audit" / name / "record.json"
            record.unlink(missing_ok=True)  # an old mismatch would stop Lean from running at all
            verdict = check_claim(path, REG, ROOT / "lean")
        try:
            match, reason = audit_agent(load_claim(path, reg), reg, a.agent)
        except AgentError as e:
            match, reason = None, str(e)
        rows[name] = {"group": expected[name]["group"], "planted_error": expected[name].get("error"),
                      "kernel": verdict["status"], "stage": verdict["stage"], "audit_match": match, "reason": reason}
        print(f"{name}: kernel {verdict['status']}, audit {match}: {reason}", flush=True)
    if not a.no_kernel:
        # Check again so each verdict carries its audit: a MISMATCH now fails at stage audit.
        for name in sorted(expected):
            check_claim(SET / f"{name}.yaml", REG, ROOT / "lean")
    wrong = [r for r in rows.values() if r["group"] == "mistranslated"]
    right = [r for r in rows.values() if r["group"] == "faithful"]
    result = {"date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(), "agent": a.agent, "runs": 1,
              "mistranslated": len(wrong), "faithful": len(right),
              "mistranslated_passed_by_kernel": sum(r["kernel"] == "PASS" for r in wrong),
              "mistranslated_caught_by_audit": sum(r["audit_match"] is False for r in wrong),
              "faithful_passed_by_kernel": sum(r["kernel"] == "PASS" for r in right),
              "faithful_flagged_by_audit": sum(r["audit_match"] is False for r in right),
              "rows": rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
