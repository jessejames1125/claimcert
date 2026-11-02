"""Verdicts: assembled from the Lean report, never from the proof text."""
from __future__ import annotations

import json
from pathlib import Path

from .claims import premises

KINDS = ("LAW", "FIT", "TECH", "NUMBER")
STD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


def fail(name: str, stage: str, reason: str, claim=None, seconds: float = 0.0) -> dict:
    return {"claim": name, "type": getattr(claim, "type", None), "intent": getattr(claim, "intent", None),
            "status": "FAIL", "stage": stage, "reason": reason,
            "assumptions": {k: [] for k in KINDS}, "details": {}, "unused_assumptions": [], "premises": [],
            "axioms": [], "audit": "UNAUDITED", "lean_seconds": round(seconds, 2)}


def _shape_error(report) -> str | None:
    if not isinstance(report, dict):
        return "report is not an object"
    if not isinstance(report.get("theorem"), str):
        return "report has no theorem name"
    ax = report.get("axioms")
    if not isinstance(ax, list) or not all(isinstance(a, str) for a in ax):
        return "report axioms are malformed"
    bs = report.get("binders")
    if not isinstance(bs, list):
        return "report binders are malformed"
    for b in bs:
        if not (isinstance(b, dict) and isinstance(b.get("name"), str) and isinstance(b.get("head"), str)
                and isinstance(b.get("prop"), bool) and isinstance(b.get("used"), bool)):
            return "report binder entry is malformed"
    return None


def assemble(claim, reg, report: dict, seconds: float) -> dict:
    bad = _shape_error(report)
    if bad:
        return fail(claim.name, "report", bad, claim, seconds)
    if report["theorem"] != claim.name:
        return fail(claim.name, "report", f"report is for {report['theorem']!r}", claim, seconds)
    extra = sorted(set(report["axioms"]) - STD_AXIOMS)
    if extra:
        return fail(claim.name, "axioms", f"depends on non-standard axioms: {extra}", claim, seconds)
    used, details, unused = {k: [] for k in KINDS}, {}, []
    for b in report["binders"]:
        if not b["prop"] or b["name"].startswith("dom_"):
            continue
        aname = b["name"][2:] if b["name"].startswith("h_") else None
        head_ok = aname is not None and (b["head"] == f"A_{aname}" or b["head"].endswith(f".A_{aname}"))
        if aname not in claim.assumptions or not head_ok:
            return fail(claim.name, "assumptions",
                        f"hypothesis {b['name']} is not a registered assumption of type A_<name>", claim, seconds)
        if not b["used"]:
            unused.append(aname)
            continue
        a = reg.assumptions[aname]
        used[a.kind.value].append(aname)
        details[aname] = {"kind": a.kind.value, "source": a.source, "range": a.range, "date": a.date,
                          "produced_by": a.produced_by}
    # Domains and conditions are hypotheses too: every hypothesis the statement carries is listed.
    # They come from the claim, are not typed by the registry, and are never dropped as unused.
    binder_used = {b["name"]: b["used"] for b in report["binders"]}
    prem = [{**p, "used": binder_used.get(p["name"])} for p in premises(claim)]
    return {"claim": claim.name, "type": claim.type, "intent": claim.intent, "status": "PASS",
            "stage": "kernel", "reason": "kernel-checked", "assumptions": used, "details": details,
            "unused_assumptions": unused, "premises": prem, "axioms": sorted(report["axioms"]),
            "audit": "UNAUDITED", "lean_seconds": round(seconds, 2)}


def summary_text(v: dict) -> str:
    kind = f" ({v['type']})" if v["type"] else ""
    lines = [f"{v['claim']}: {v['status']}{kind} at stage {v['stage']}"]
    if v.get("intent"):
        lines.append(f"  intent: {v['intent'].strip()}")
    if v["status"] == "FAIL":
        reason = [l for l in v["reason"][-1500:].splitlines() if l.strip() and "CCREPORT" not in l]
        lines.append("  reason: " + "\n          ".join(reason))
    else:
        lines.append("  assumptions used:")
        any_used = False
        for kind in KINDS:
            for name in v["assumptions"][kind]:
                d = v["details"][name]
                extra = f"; range: {d['range']}" if d.get("range") else ""
                if d.get("produced_by"):
                    extra += f"; produced by: {d['produced_by']}"
                lines.append(f"    {kind:<6} {name}  (source: {d['source']}{extra})")
                any_used = True
        if not any_used:
            lines.append("    none")
        lines.append(f"  unused, dropped: {', '.join(v['unused_assumptions']) or 'none'}")
        prem = v.get("premises") or []
        if prem:
            lines.append("  premises from the claim (domains and conditions, not in the registry):")
            for p in prem:
                note = "  (unused)" if p.get("used") is False else ""
                lines.append(f"    {p['kind']:<9} {p['name']}: {p['statement']}{note}")
        else:
            lines.append("  premises from the claim: none")
        lines.append(f"  axioms: {', '.join(v['axioms']) or 'none'}")
    lines.append(f"  audit: {v['audit']}   lean: {v['lean_seconds']} s")
    return "\n".join(lines)


def write_verdict(claim_path, v: dict) -> dict:
    claim_path = Path(claim_path)
    claim_path.with_suffix(".verdict.json").write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n",
                                                       encoding="utf-8", newline="\n")
    claim_path.with_suffix(".verdict.txt").write_text(summary_text(v) + "\n", encoding="utf-8", newline="\n")
    return v
