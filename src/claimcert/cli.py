"""claimcert command line. Exit codes: 0 pass or done, 1 fail, 2 toolchain absent."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _claim_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("claim")
    parser.add_argument("--registry", help="default: the nearest registry.yaml at or above the claim")


def _lake_root(a: argparse.Namespace) -> Path:
    from .replay import repo_root
    if a.lake_root:
        return Path(a.lake_root)
    root = repo_root(Path(a.claim).parent if getattr(a, "claim", None) else None) or repo_root()
    if root is None:
        raise FileNotFoundError("no lean/lakefile.toml at or above here; pass --lake-root")
    return root / "lean"


def _root() -> Path:
    from .replay import repo_root
    root = repo_root()
    if root is None:
        raise FileNotFoundError("run this inside a claimcert checkout (no lean/lakefile.toml found here)")
    return root


def _registry(a: argparse.Namespace):
    from .replay import registry_for
    return a.registry or registry_for(a.claim)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="claimcert", description="Check AI-written numeric claims with Lean's kernel; "
                                "every pass lists the assumptions its proof used.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="show a planted false claim next to a true one; no Lean, a few seconds")
    sub.add_parser("doctor", help="say what is missing for each mode")
    s = sub.add_parser("setup", help="download the Mathlib cache and build the Lean library")
    s.add_argument("--lake", default="lake")

    r = sub.add_parser("replay", help="match recorded verdicts to the files; re-run the stages that need no Lean")
    r.add_argument("path", nargs="?", default="examples")
    r.add_argument("--lake-root")

    g = sub.add_parser("gen-assumptions", help="write the Lean definitions for a registry")
    g.add_argument("--registry", required=True)
    g.add_argument("--out", required=True)

    n = sub.add_parser("new", help="write the Lean file for a claim (statement generated)")
    _claim_args(n)
    n.add_argument("--proof", help="file holding the proof body (indented tactic lines)")
    n.add_argument("--force", action="store_true", help="overwrite; keeps the old proof unless --proof")

    c = sub.add_parser("check", help="kernel-check a claim and write its verdict")
    _claim_args(c)
    c.add_argument("--lake-root")
    c.add_argument("--timeout", type=float, default=1800.0)
    c.add_argument("--lake", default="lake")

    pv = sub.add_parser("prove", help="ask an agent for the proof, then kernel-check what it wrote")
    _claim_args(pv)
    pv.add_argument("--agent", required=True, help="command that reads a prompt on stdin and writes a reply to stdout")
    pv.add_argument("--attempts", type=int, default=3)
    pv.add_argument("--lake-root")
    pv.add_argument("--timeout", type=float, default=1800.0)
    pv.add_argument("--lake", default="lake")

    ap = sub.add_parser("audit-pack", help="write the back-translation prompt for a claim")
    _claim_args(ap)

    ar = sub.add_parser("audit-record", help="record the faithfulness comparison")
    _claim_args(ar)
    ar.add_argument("--match", required=True, choices=["yes", "no"])
    ar.add_argument("--by", required=True, choices=["operator", "agent"])
    ar.add_argument("--notes", required=True)

    aa = sub.add_parser("audit-agent", help="blind back-translation by one agent run, compared by a second")
    _claim_args(aa)
    aa.add_argument("--agent", required=True, help="command that reads a prompt on stdin and writes a reply to stdout")

    a = p.parse_args(argv)
    import yaml
    from .agent import AgentError
    from .claims import ClaimError
    from .expr import ExprError
    from .registry import RegistryError
    from .units import DimensionError, UnitError
    try:
        return _run(a)
    except (ClaimError, RegistryError, DimensionError, UnitError, ExprError, FileExistsError, FileNotFoundError,
            AgentError, yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _run(a: argparse.Namespace) -> int:
    if a.cmd == "demo":
        from .replay import demo
        text, ok = demo(_root())
        print(text, end="")
        return 0 if ok else 1
    if a.cmd == "doctor":
        from .doctor import diagnose, report
        text, code = report(diagnose(_root()))
        print(text, end="")
        return code
    if a.cmd == "setup":
        from .doctor import setup
        return setup(_root(), a.lake)
    if a.cmd == "replay":
        from .replay import replay_tree
        text, ok = replay_tree(Path(a.path), Path(a.lake_root) if a.lake_root else _root() / "lean")
        print(text, end="")
        return 0 if ok else 1
    if a.cmd == "gen-assumptions":
        from .registry import lean_assumptions, load_registry
        Path(a.out).write_text(lean_assumptions(load_registry(a.registry)), encoding="utf-8", newline="\n")
        print(f"wrote {a.out}")
        return 0
    if a.cmd == "new":
        from .claims import write_new
        print(f"wrote {write_new(a.claim, _registry(a), a.proof, a.force)}")
        return 0
    if a.cmd == "check":
        from .check import check_claim
        from .verdict import summary_text
        v = check_claim(a.claim, _registry(a), _lake_root(a), a.timeout, a.lake)
        print(summary_text(v))
        if v["status"] == "PASS":
            return 0
        return 2 if v["stage"] == "toolchain" else 1
    if a.cmd == "prove":
        from .prove import prove
        from .verdict import summary_text
        v, log = prove(a.claim, _registry(a), _lake_root(a), a.agent, a.attempts, a.timeout, a.lake)
        for t in log:
            print(f"attempt {t.number}: {t.status} at stage {t.stage}")
            if t.status in ("GAVE-UP", "AGENT-ERROR"):
                print(f"  {t.reply[:500]}")
        if v is not None:
            print(summary_text(v))
        return 0 if v is not None and v["status"] == "PASS" else 1
    from .audit import audit_agent, audit_pack, audit_record
    from .claims import load_claim
    from .registry import load_registry
    reg = load_registry(_registry(a))
    claim = load_claim(a.claim, reg)
    if a.cmd == "audit-pack":
        print(f"wrote {audit_pack(claim, reg)}")
    elif a.cmd == "audit-agent":
        match, reason = audit_agent(claim, reg, a.agent)
        print(f"audit: {'MATCH' if match else 'MISMATCH'}\n  {reason}")
    else:
        print(f"wrote {audit_record(claim, reg, a.match == 'yes', a.by, a.notes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
