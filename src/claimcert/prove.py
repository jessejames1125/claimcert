"""Ask an agent for the proof. The agent is untrusted: only the kernel run decides."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .agent import AgentError, run_agent
from .audit import CYLINDER_DEF
from .check import check_claim
from .claims import lean_path, load_claim, render, statement_block
from .registry import lean_assumption_def, load_registry

PROMPT = """Write a Lean 4 tactic proof, with Mathlib and the LeanCert `leancert` tactic available.
The numbers below are exact real numbers in SI units.

Definitions:
{defs}

Statement to prove:
{statement}

Rules: reply with only the tactic lines in one ```lean code block, each line indented two spaces.
Do not repeat the statement. Never use sorry, admit, axiom, native_decide, set_option, open, strings,
attributes or commands that start with #. If the statement is false or cannot follow from its
hypotheses, reply with the single word UNPROVABLE and one sentence saying why.
{feedback}"""

_BLOCK = re.compile(r"```(?:lean4?)?[ \t]*\n(.*?)```", re.DOTALL)


@dataclass
class Attempt:
    number: int
    reply: str
    status: str
    stage: str


def extract_proof(reply: str) -> str | None:
    """The tactic lines from a reply, or None when the agent gave up or sent no code block."""
    if reply.strip().upper().startswith("UNPROVABLE"):
        return None
    found = _BLOCK.findall(reply)
    return found[-1].rstrip() + "\n" if found else None


def build_prompt(claim, reg, feedback: str = "") -> str:
    defs = [lean_assumption_def(reg.assumptions[a]) for a in claim.assumptions]
    if claim.cylinder is not None:
        defs.append(CYLINDER_DEF)
    statement = "\n".join(l for l in statement_block(claim, reg).splitlines() if not l.startswith("example :"))
    note = f"\nYour last attempt failed. Lean said:\n{feedback[-1500:]}\n" if feedback else ""
    return PROMPT.format(defs="\n".join(defs).strip() or "(none)", statement=statement, feedback=note)


def prove(claim_path, registry_path, lake_root, agent: str, attempts: int = 3, timeout_s: float = 1800.0,
          lake: str = "lake") -> tuple[dict | None, list[Attempt]]:
    """Up to `attempts` rounds of proof then check. Returns the last verdict and what each round did."""
    claim_path = Path(claim_path)
    reg = load_registry(registry_path)
    claim = load_claim(claim_path, reg)
    log, feedback, verdict = [], "", None
    for number in range(1, attempts + 1):
        try:
            reply = run_agent(agent, build_prompt(claim, reg, feedback))
        except AgentError as e:
            log.append(Attempt(number, str(e), "AGENT-ERROR", "agent"))
            break
        proof = extract_proof(reply)
        if proof is None:
            log.append(Attempt(number, reply.strip(), "GAVE-UP", "agent"))
            break
        lean_path(claim_path).write_text(render(claim, reg, proof), encoding="utf-8", newline="\n")
        verdict = check_claim(claim_path, registry_path, lake_root, timeout_s, lake)
        log.append(Attempt(number, reply.strip(), verdict["status"], verdict["stage"]))
        if verdict["status"] == "PASS":
            break
        feedback = verdict["reason"]
    return verdict, log
