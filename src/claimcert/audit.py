"""Faithfulness gate: does the Lean statement say what the claim's intent says?"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from .claims import statement_block
from .registry import lean_assumption_def, lean_assumptions

CYLINDER_DEF = """def CylinderFitsInSphere (r h R : ℝ) : Prop :=
  ∀ ρ ∈ Set.Icc (0 : ℝ) r, ∀ z ∈ Set.Icc (-h) h, ρ ^ 2 + z ^ 2 ≤ R ^ 2"""

PROMPT = """You are given a Lean 4 theorem statement and the definitions it uses. Write in plain English
exactly what the statement asserts: every variable, every hypothesis, and the conclusion. All
numbers are in SI units. Do not guess at the author's purpose and do not judge whether it is true.
"""


def statement_hash(claim, reg) -> str:
    """What an audit approved: the statement plus every definition it can reach. The generated
    assumption module is hashed whole (check holds the module on disk to it), so any registry
    change makes an old record STALE, as does a change to the core's cylinder definition."""
    parts = [statement_block(claim, reg), lean_assumptions(reg)]
    if claim.cylinder is not None:
        parts.append(CYLINDER_DEF)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def audit_dir(claim) -> Path:
    return claim.path.parent / "audit" / claim.name


def audit_pack(claim, reg) -> Path:
    defs = [lean_assumption_def(reg.assumptions[a]) for a in claim.assumptions]
    if claim.cylinder is not None:
        defs.append(CYLINDER_DEF)
    statement = "\n".join(l for l in statement_block(claim, reg).splitlines() if not l.startswith("example :"))
    text = (PROMPT + "\n## Definitions\n\n```lean\n" + "\n".join(defs).strip() + "\n```\n\n"
            "## Statement\n\n```lean\n" + statement + " ...\n```\n")
    d = audit_dir(claim)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "backtranslate-prompt.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    return out


def audit_record(claim, reg, match: bool, by: str, notes: str) -> Path:
    d = audit_dir(claim)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "record.json"
    out.write_text(json.dumps({"audit_sha256": statement_hash(claim, reg), "match": match, "by": by,
                               "notes": notes, "date": datetime.date.today().isoformat()}, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    return out


def audit_status(claim, reg) -> str:
    rec = audit_dir(claim) / "record.json"
    if not rec.exists():
        return "UNAUDITED"
    try:
        data = json.loads(rec.read_text(encoding="utf-8"))
        recorded, match = data["audit_sha256"], data["match"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        # unreadable, partial, or written before the hash covered the definitions
        return "STALE"
    if recorded != statement_hash(claim, reg) or not isinstance(match, bool):
        return "STALE"
    return "MATCH" if match else "MISMATCH"
