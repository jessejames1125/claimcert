"""Replay recorded verdicts without Lean.

A recorded verdict is a statement about a past run, and anyone can edit the file. Replay does not
re-check a proof. It re-runs every stage that needs no Lean, and it confirms the claim, proof,
assumptions and pinned toolchain are the ones the recorded run saw. `claimcert check` is the proof."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .audit import audit_status
from .check import _module_error, prepare
from .provenance import differences, fingerprint
from .verdict import summary_text


@dataclass
class Replayed:
    name: str
    state: str  # recorded | live | stale | missing
    verdict: dict | None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state in ("recorded", "live")


def replay_claim(claim_path, registry_path, lake_root) -> Replayed:
    claim_path = Path(claim_path)
    name = claim_path.stem
    verdict_file = claim_path.with_suffix(".verdict.json")
    p = prepare(claim_path, registry_path)
    if p.failure:
        # Refused before Lean would run: this result is computed now, not read from a file.
        return Replayed(name, "live", p.failure)
    if not verdict_file.is_file():
        return Replayed(name, "missing", None, "no recorded verdict; run claimcert check")
    recorded = json.loads(verdict_file.read_text(encoding="utf-8"))
    bad = _module_error(Path(lake_root), p.reg)
    if bad:
        return Replayed(name, "stale", recorded, bad)
    changed = differences(recorded.get("recorded"), fingerprint(claim_path, p.reg, lake_root))
    if changed:
        return Replayed(name, "stale", recorded, "changed since the recorded run: " + ", ".join(changed))
    if recorded.get("status") == "PASS":
        # check fails a claim whose audit says MISMATCH, so a recorded PASS must still agree with the audit
        audit = audit_status(p.claim, p.reg)
        if audit == "MISMATCH" or recorded.get("audit") != audit:
            return Replayed(name, "stale", recorded, f"audit recorded as {recorded.get('audit')}, now {audit}")
    return Replayed(name, "recorded", recorded)


def registry_for(claim_path) -> Path:
    """The nearest registry.yaml at or above the claim."""
    start = Path(claim_path).resolve().parent
    for folder in (start, *start.parents):
        candidate = folder / "registry.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no registry.yaml at or above {Path(claim_path).name}; pass --registry")


def repo_root(start=None) -> Path | None:
    """The nearest folder at or above start that holds lean/lakefile.toml."""
    start = Path(start or ".").resolve()
    for folder in (start, *start.parents):
        if (folder / "lean" / "lakefile.toml").is_file():
            return folder
    return None


def render(result: Replayed) -> str:
    if result.verdict is None:
        return f"{result.name}: {result.detail}"
    label = {"recorded": "recorded result, not re-checked here; same files as that run",
             "live": "computed just now, no Lean needed",
             "stale": f"STALE, do not trust: {result.detail}"}[result.state]
    date = (result.verdict.get("recorded") or {}).get("date")
    toolchain = (result.verdict.get("recorded") or {}).get("toolchain")
    if result.state == "recorded" and date:
        label += f" ({date}, {toolchain})"
    return f"[{label}]\n{summary_text(result.verdict)}"


DEMO = ("examples/software/gpu_memory_planted.yaml", "examples/software/gpu_memory_true.yaml",
        "examples/software/rate_vs_size_planted.yaml", "examples/software/inflight_requests_true.yaml")


def demo(root: Path) -> tuple[str, bool]:
    lines = ["Lean does not run in this mode. Results marked recorded come from a real kernel run",
             "of the files in this checkout; to re-run the kernel, see claimcert doctor.", ""]
    ok = True
    for rel in DEMO:
        claim = root / rel
        result = replay_claim(claim, registry_for(claim), root / "lean")
        ok = ok and result.ok
        lines += [render(result), ""]
    return "\n".join(lines).rstrip() + "\n", ok


def replay_tree(root: Path, lake_root: Path) -> tuple[str, bool]:
    """Replay every claim under root. The summary line counts what was and was not reproducible."""
    claims = sorted(y for y in root.rglob("*.yaml") if y.name != "registry.yaml" and "audit" not in y.parts)
    lines, counts = [], {}
    ok = True
    for claim in claims:
        result = replay_claim(claim, registry_for(claim), lake_root)
        ok = ok and result.ok
        counts[result.state] = counts.get(result.state, 0) + 1
        status = result.verdict["status"] if result.verdict else "-"
        lines.append(f"{result.state:<9}{status:<5}{result.name}" + (f"  {result.detail}" if result.detail else ""))
    summary = ", ".join(f"{n} {state}" for state, n in sorted(counts.items())) or "no claims found"
    return "\n".join([*lines, summary]) + "\n", ok and bool(claims)
