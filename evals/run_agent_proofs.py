"""Let an agent write proofs it has never seen, then let the kernel decide.

    python evals/run_agent_proofs.py --agent "claude -p --model sonnet"

Three claims with no proof on disk: two true, one false. Writes evals/results/agent-proofs.json."""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from claimcert.prove import prove

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "evals" / "agent"
REG = SET / "registry.yaml"
OUT = ROOT / "evals" / "results" / "agent-proofs.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--attempts", type=int, default=2)
    a = ap.parse_args()
    expected = json.loads((SET / "expected.json").read_text(encoding="utf-8"))
    rows = {}
    for name in sorted(expected):
        verdict, log = prove(SET / f"{name}.yaml", REG, ROOT / "lean", a.agent, attempts=a.attempts)
        rows[name] = {"truth": expected[name], "attempts": [{"status": t.status, "stage": t.stage} for t in log],
                      "final": verdict["status"] if verdict else "NO-PROOF",
                      "agent_said": log[-1].reply[:300] if log and log[-1].status == "GAVE-UP" else None}
        print(name, rows[name], flush=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                               "agent": a.agent, "runs": 1, "max_attempts": a.attempts, "rows": rows}, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
