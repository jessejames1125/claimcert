"""Re-run the 40-claim planted-error benchmark through Lean and score it.

    python evals/run_planted.py

Runs one claim at a time. Writes evals/results/planted.json and each claim's verdict files."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

from claimcert.check import check_claim
from claimcert.claims import write_new

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "evals" / "planted"
REG = BENCH / "registry.yaml"
OUT = ROOT / "evals" / "results" / "planted.json"


def git_state() -> dict:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "lean", "evals/planted/expected.json",
                            "evals/planted/registry.yaml"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": commit or None, "core_files_modified": bool(dirty)}


def score(rows: dict) -> dict:
    planted = [r for r in rows.values() if r["expected"] == "FAIL"]
    true = [r for r in rows.values() if r["expected"] == "PASS"]
    return {"claims": len(rows), "planted": len(planted), "true": len(true),
            "planted_that_passed": sum(r["status"] == "PASS" for r in planted),
            "true_that_failed": sum(r["status"] == "FAIL" for r in true)}


def main() -> int:
    expected = json.loads((BENCH / "expected.json").read_text(encoding="utf-8"))
    rows = {}
    started = time.perf_counter()
    for name in sorted(expected):
        claim = BENCH / "claims" / f"{name}.yaml"
        try:
            write_new(claim, REG, BENCH / "claims" / f"{name}.proof.lean", force=True)
        except Exception as e:  # generation failure is recorded by check as its stage
            print(f"{name}: generation failed: {e}")
        v = check_claim(claim, REG, ROOT / "lean")
        rows[name] = {"expected": expected[name], "status": v["status"], "stage": v["stage"],
                      "seconds": v["lean_seconds"]}
        print(f"{name}: {v['status']} ({v['stage']}) expected {expected[name]} {v['lean_seconds']} s", flush=True)
    stages = {}
    for r in rows.values():
        if r["status"] == "FAIL":
            stages[r["stage"]] = stages.get(r["stage"], 0) + 1
    summary = score(rows)
    result = {"date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
              "toolchain": (ROOT / "lean" / "lean-toolchain").read_text(encoding="utf-8").strip(), **git_state(),
              "runs": 1, "wall_seconds": round(time.perf_counter() - started), **summary,
              "planted_failed_at_stage": stages,
              "note": "planted errors were designed by the tool's author and sit in goal values, so a planted claim "
                      "that fails mostly shows Lean is sound and the plumbing works. See evals/README.md.",
              "rows": rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return 0 if summary["planted_that_passed"] == 0 and summary["true_that_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
