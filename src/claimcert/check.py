"""claimcert check: a claim from YAML to a written verdict."""
from __future__ import annotations

import secrets
from pathlib import Path

import yaml

from .audit import audit_status
from .claims import ClaimError, header, lean_path, load_claim
from .expr import ExprError
from .leanrun import hygiene, run_lean
from .registry import RegistryError, lean_assumptions, load_registry
from .report import parse_report
from .units import DimensionError, UnitError
from .verdict import assemble, fail, write_verdict


def _module_error(lake_root: Path, reg) -> str | None:
    """The assumption module Lean imports must be exactly what gen-assumptions writes from the
    registry: the verdict and the audit describe the registry, so the kernel must see the same."""
    path = lake_root.joinpath(*reg.lean_module.split(".")).with_suffix(".lean")
    if not path.is_file():
        return f"{path} not found; run claimcert gen-assumptions"
    on_disk = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    if on_disk != lean_assumptions(reg):
        return f"{path} differs from what the registry generates; run claimcert gen-assumptions"
    return None


def check_claim(claim_path, registry_path, lake_root, timeout_s: float = 1800.0, lake: str = "lake") -> dict:
    claim_path = Path(claim_path)
    name = claim_path.stem
    try:
        reg = load_registry(registry_path)
    except (RegistryError, DimensionError, UnitError, ExprError, yaml.YAMLError) as e:
        return write_verdict(claim_path, fail(name, "registry", str(e)))
    try:
        claim = load_claim(claim_path, reg)
    except DimensionError as e:
        return write_verdict(claim_path, fail(name, "dimension", str(e)))
    except (ClaimError, UnitError, ExprError, KeyError, TypeError, yaml.YAMLError) as e:
        return write_verdict(claim_path, fail(name, "schema", str(e)))
    lean_file = lean_path(claim_path)
    if not lean_file.exists():
        return write_verdict(claim_path, fail(name, "file", f"{lean_file.name} not found; run claimcert new", claim))
    text = lean_file.read_text(encoding="utf-8")
    head = header(claim, reg)
    if not text.startswith(head):
        return write_verdict(claim_path, fail(
            name, "statement", "the generated statement was edited; run claimcert new --force (keeps the proof)", claim))
    trailer = f"#cc_report {claim.name}"
    body = text[len(head):].rstrip()
    if not body.endswith("\n" + trailer) or body.count("#cc_report") != 1:
        return write_verdict(claim_path, fail(name, "trailer", f"the file must end with exactly one line '{trailer}'", claim))
    bad = hygiene(body[: -len(trailer)])
    if bad:
        return write_verdict(claim_path, fail(name, "hygiene", bad, claim))
    lake_root = Path(lake_root)
    if not lake_root.is_dir():
        return write_verdict(claim_path, fail(name, "toolchain", f"lake root {lake_root} not found", claim))
    bad = _module_error(lake_root, reg)
    if bad:
        return write_verdict(claim_path, fail(name, "assumptions", bad, claim))
    audit = audit_status(claim, reg)
    if audit == "MISMATCH":
        # a mismatch fails the claim, whatever the kernel says
        v = fail(name, "audit", "the faithfulness audit found the statement does not say what the intent says",
                 claim)
        v["audit"] = audit
        return write_verdict(claim_path, v)
    nonce = secrets.token_hex(16)
    run = run_lean(lake_root, lean_file, reg.lean_module, timeout_s, lake, nonce=nonce)
    if run.status != "ok":
        stage = {"missing": "toolchain", "timeout": "timeout", "build": "build", "error": "elaboration"}[run.status]
        if run.status == "error" and "error: (kernel)" in run.output:
            stage = "kernel"
        return write_verdict(claim_path, fail(name, stage, run.output[-4000:], claim, run.seconds))
    report = parse_report(run.output, nonce)
    if report is None:
        return write_verdict(claim_path, fail(name, "report", "expected exactly one CCREPORT line", claim, run.seconds))
    v = assemble(claim, reg, report, run.seconds)
    if v["status"] == "PASS":
        # STALE (statement or definitions changed since the audit) is shown on the verdict and the
        # status is kept; consumers that need an audit must treat STALE as unaudited.
        v["audit"] = audit
    return write_verdict(claim_path, v)
