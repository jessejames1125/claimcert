"""Baseline for the planted benchmark: the same 40 claims, one model, no Lean.

    python evals/run_baseline.py --agent "claude -p --model sonnet" --runs 3

Each run sends every claim in one prompt, in a shuffled order, with the intent text removed because
it names the planted error. The model answers true or false per claim. Writes
evals/results/baseline.json, or baseline-no-definitions.json with --no-definitions."""
from __future__ import annotations

import argparse
import datetime
import json
import random
import re
import sys
from pathlib import Path

import yaml

from claimcert.agent import AgentError, run_agent

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "evals" / "planted"
OUT = ROOT / "evals" / "results" / "baseline.json"

DEFINITIONS = """
Definitions: fits_in_sphere means a solid cylinder of radius r and half-length h (total length 2h),
centred on the centre of a sphere of radius R, lies entirely inside the sphere. valid_when means the
assumption holds only for arguments in that range and says nothing outside it.
"""

PROMPT = """Below are {n} engineering claims and the assumptions they may use. Numbers carry units. Decide
for each claim whether its goal follows from its assumptions. A goal that compares different kinds
of quantity is false. Do the arithmetic. Do not use any tools.

{definitions}
Assumptions by name:
{assumptions}

Claims:
{claims}

Reply with one JSON object and nothing else, mapping each claim id to true or false.
"""


def blind(claim: dict) -> dict:
    return {k: v for k, v in claim.items() if k not in ("name", "intent")}


def prompt_for(names: list[str], ids: dict[str, str], definitions: str = DEFINITIONS) -> str:
    registry = yaml.safe_load((BENCH / "registry.yaml").read_text(encoding="utf-8"))
    assumptions = yaml.safe_dump({a["name"]: {k: a[k] for k in ("statement", "constants", "valid_when") if k in a}
                                  for a in registry["assumptions"]}, sort_keys=False)
    claims = {ids[n]: blind(yaml.safe_load((BENCH / "claims" / f"{n}.yaml").read_text(encoding="utf-8")))
              for n in sorted(names, key=lambda x: ids[x])}
    return PROMPT.format(n=len(names), definitions=definitions, assumptions=assumptions, claims=yaml.safe_dump(claims, sort_keys=True))


def parse_reply(reply: str) -> dict[str, bool]:
    found = re.findall(r"\{.*\}", reply, re.DOTALL)
    if not found:
        raise ValueError("no JSON object in the reply")
    return {k: bool(v) for k, v in json.loads(found[-1]).items()}


def score_run(answers: dict[str, bool], ids: dict[str, str], expected: dict[str, str]) -> dict:
    wrong_pass, wrong_fail, missing = [], [], []
    for name, want in expected.items():
        got = answers.get(ids[name])
        if got is None:
            missing.append(name)
        elif got and want == "FAIL":
            wrong_pass.append(name)
        elif not got and want == "PASS":
            wrong_fail.append(name)
    return {"planted_called_true": wrong_pass, "true_called_false": wrong_fail, "unanswered": missing}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20261102)
    ap.add_argument("--no-definitions", action="store_true",
                    help="leave out what fits_in_sphere and valid_when mean, as an under-specified prompt would")
    a = ap.parse_args()
    expected = json.loads((BENCH / "expected.json").read_text(encoding="utf-8"))
    runs = []
    for i in range(a.runs):
        names = sorted(expected)
        random.Random(a.seed + i).shuffle(names)
        ids = {n: f"C{j:02d}" for j, n in enumerate(names)}
        try:
            prompt = prompt_for(names, ids, "" if a.no_definitions else DEFINITIONS)
            reply = run_agent(a.agent, prompt, timeout_s=600.0)
            scored = score_run(parse_reply(reply), ids, expected)
        except (AgentError, ValueError) as e:
            scored = {"error": str(e)}
        runs.append(scored)
        print(f"run {i + 1}: {scored}", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    out = OUT.with_name("baseline-no-definitions.json") if a.no_definitions else OUT
    out.write_text(json.dumps({"date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                               "agent": a.agent, "seed": a.seed, "claims": len(expected), "runs": runs}, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
