"""claimcert check: a claim from YAML to a written verdict."""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import yaml

from .audit import audit_status
from .claims import ClaimError, header, lean_path, load_claim
from .expr import ExprError
from .leanrun import hygiene, run_lean
from .provenance import fingerprint
from .registry import RegistryError, lean_assumptions, load_registry
from .report import parse_report
from .units import DimensionError, UnitError
from .verdict import assemble, fail, write_verdict


def _module_error(lake_root: Path, reg) -> str | None:
    """The assumption module Lean imports must be exactly what gen-assumptions writes from the
    registry: the verdict and the audit describe the registry, so the kernel must see the same."""
    path = lake_root.joinpath(*reg.lean_module.split(".")).with_suffix(".lean")
    if not path.is_file():
        return f"{path.name} not found under the lake root; run claimcert gen-assumptions"
    on_disk = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    if on_disk != lean_assumptions(reg):
        return f"{path.name} differs from what the registry generates; run claimcert gen-assumptions"
    return None


def _scrub(output: str, lean_file: Path, lake_root: Path, nonce: str) -> str:
    """Verdicts get committed, so they carry no absolute paths and no per-run nonce."""
    text = output.replace(nonce, "<nonce>") if nonce else output
    for path, short in ((lean_file.resolve(), lean_file.name), (lake_root.resolve(), "<lake-root>"),
                        (Path.home(), "~")):
        pattern = r"[\\/]".join(re.escape(part) for part in str(path).replace("\\", "/").split("/"))
        text = re.sub(pattern, lambda _: short, text, flags=re.IGNORECASE)
    return text


def _as_written(claim_path: Path) -> SimpleNamespace | None:
    """Type and intent from a claim that did not load, so its verdict can still say what it claimed."""
    try:
        raw = yaml.safe_load(claim_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    kind, intent = raw.get("type"), raw.get("intent")
    return SimpleNamespace(type=kind if isinstance(kind, str) else None, intent=intent if isinstance(intent, str) else None)


@dataclass
class Prepared:
    """What the stages before Lean produced. failure is set when one of them refused the claim."""
    reg: object = None
    claim: object = None
    lean_file: Path | None = None
    failure: dict | None = None
    source: str | None = None  # the Lean text that passed the screen; Lean compiles this copy


def prepare(claim_path, registry_path) -> Prepared:
    """Every stage that needs no Lean: schema, dimensions, frozen statement, trailer, proof screen."""
    claim_path = Path(claim_path)
    name = claim_path.stem
    try:
        reg = load_registry(registry_path)
    except (RegistryError, DimensionError, UnitError, ExprError, yaml.YAMLError) as e:
        return Prepared(failure=fail(name, "registry", str(e)))
    try:
        claim = load_claim(claim_path, reg)
    except DimensionError as e:
        return Prepared(reg, failure=fail(name, "dimension", str(e), _as_written(claim_path)))
    except (ClaimError, UnitError, ExprError, KeyError, TypeError, yaml.YAMLError) as e:
        return Prepared(reg, failure=fail(name, "schema", str(e), _as_written(claim_path)))
    lean_file = lean_path(claim_path)
    if not lean_file.exists():
        return Prepared(reg, claim, failure=fail(name, "file", f"{lean_file.name} not found; run claimcert new", claim))
    text = lean_file.read_text(encoding="utf-8")
    head = header(claim, reg)
    if not text.startswith(head):
        return Prepared(reg, claim, lean_file, fail(
            name, "statement", "the generated statement was edited; run claimcert new --force (keeps the proof)", claim))
    trailer = f"#cc_report {claim.name}"
    body = text[len(head):].rstrip()
    if not body.endswith("\n" + trailer) or body.count("#cc_report") != 1:
        return Prepared(reg, claim, lean_file,
                        fail(name, "trailer", f"the file must end with exactly one line '{trailer}'", claim))
    bad = hygiene(body[: -len(trailer)])
    if bad:
        return Prepared(reg, claim, lean_file, fail(name, "hygiene", bad, claim))
    return Prepared(reg, claim, lean_file, source=text)


def check_claim(claim_path, registry_path, lake_root, timeout_s: float = 1800.0, lake: str = "lake") -> dict:
    claim_path = Path(claim_path)
    lake_root = Path(lake_root)
    name = claim_path.stem
    p = prepare(claim_path, registry_path)
    reg, claim, lean_file = p.reg, p.claim, p.lean_file

    def done(v: dict) -> dict:
        v["recorded"] = fingerprint(claim_path, reg, lake_root)
        return write_verdict(claim_path, v)

    if p.failure:
        return done(p.failure)
    if not lake_root.is_dir():
        return done(fail(name, "toolchain", f"lake root {lake_root.name} not found", claim))
    bad = _module_error(lake_root, reg)
    if bad:
        return done(fail(name, "assumptions", bad, claim))
    audit = audit_status(claim, reg)
    if audit == "MISMATCH":
        # a mismatch fails the claim, whatever the kernel says
        v = fail(name, "audit", "the faithfulness audit found the statement does not say what the intent says",
                 claim)
        v["audit"] = audit
        return done(v)
    nonce = secrets.token_hex(16)
    run = run_lean(lake_root, lean_file, reg.lean_module, timeout_s, lake, nonce=nonce, theorem=claim.name,
                   source=p.source)
    if run.status != "ok":
        stage = {"missing": "toolchain", "timeout": "timeout", "build": "build", "error": "elaboration",
                 "kernel": "kernel"}[run.status]
        if run.status == "error" and "error: (kernel)" in run.output:
            stage = "kernel"
        return done(fail(name, stage, _scrub(run.output[-4000:], lean_file, lake_root, nonce), claim, run.seconds))
    report = parse_report(run.output, nonce)
    if report is None:
        return done(fail(name, "report", "expected exactly one CCREPORT line", claim, run.seconds))
    v = assemble(claim, reg, report, run.seconds)
    if v["status"] == "PASS":
        # STALE (statement or definitions changed since the audit) is shown on the verdict and the
        # status is kept; consumers that need an audit must treat STALE as unaudited.
        v["audit"] = audit
    return done(v)
