"""claimcert command line. Exit codes: 0 pass or done, 1 fail, 2 toolchain absent."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="claimcert")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen-assumptions", help="write the Lean definitions for a registry")
    g.add_argument("--registry", required=True)
    g.add_argument("--out", required=True)

    n = sub.add_parser("new", help="write the Lean file for a claim (statement generated)")
    n.add_argument("claim")
    n.add_argument("--registry", required=True)
    n.add_argument("--proof", help="file holding the proof body (indented tactic lines)")
    n.add_argument("--force", action="store_true", help="overwrite; keeps the old proof unless --proof")

    c = sub.add_parser("check", help="kernel-check a claim and write its verdict")
    c.add_argument("claim")
    c.add_argument("--registry", required=True)
    c.add_argument("--lake-root", required=True)
    c.add_argument("--timeout", type=float, default=1800.0)
    c.add_argument("--lake", default="lake")

    ap = sub.add_parser("audit-pack", help="write the back-translation prompt for a claim")
    ap.add_argument("claim")
    ap.add_argument("--registry", required=True)

    ar = sub.add_parser("audit-record", help="record the faithfulness comparison")
    ar.add_argument("claim")
    ar.add_argument("--registry", required=True)
    ar.add_argument("--match", required=True, choices=["yes", "no"])
    ar.add_argument("--by", required=True, choices=["operator", "agent"])
    ar.add_argument("--notes", required=True)

    a = p.parse_args(argv)
    import yaml
    from .claims import ClaimError
    from .expr import ExprError
    from .registry import RegistryError
    from .units import DimensionError, UnitError
    try:
        return _run(a)
    except (ClaimError, RegistryError, DimensionError, UnitError, ExprError, FileExistsError,
            yaml.YAMLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _run(a: argparse.Namespace) -> int:
    if a.cmd == "gen-assumptions":
        from .registry import lean_assumptions, load_registry
        Path(a.out).write_text(lean_assumptions(load_registry(a.registry)), encoding="utf-8", newline="\n")
        print(f"wrote {a.out}")
        return 0
    if a.cmd == "new":
        from .claims import write_new
        print(f"wrote {write_new(a.claim, a.registry, a.proof, a.force)}")
        return 0
    if a.cmd == "check":
        from .check import check_claim
        from .verdict import summary_text
        v = check_claim(a.claim, a.registry, a.lake_root, a.timeout, a.lake)
        print(summary_text(v))
        if v["status"] == "PASS":
            return 0
        return 2 if v["stage"] == "toolchain" else 1
    from .audit import audit_pack, audit_record
    from .claims import load_claim
    from .registry import load_registry
    reg = load_registry(a.registry)
    claim = load_claim(a.claim, reg)
    if a.cmd == "audit-pack":
        print(f"wrote {audit_pack(claim, reg)}")
    else:
        print(f"wrote {audit_record(claim, reg, a.match == 'yes', a.by, a.notes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
