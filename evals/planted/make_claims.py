"""Generate the planted-error benchmark: 40 claims, 20 true and 20 with one planted error.

Run once, commit the output, then run evals/run_planted.py. Claims are never edited after a run starts."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from claimcert.expr import lean_number
from claimcert.units import parse_quantity

HERE = Path(__file__).resolve().parent
OUT = HERE / "claims"


def lit(text: str) -> str:
    return lean_number(parse_quantity(text).si_value)


NMAX, SMAX = lit("1e29 m^-3"), lit("5 b")

GEOM_PROOF = ("  rw [ClaimCert.cylinderFitsInSphere_iff (by norm_num) (by norm_num)]\n"
              "  norm_num\n")

RANGE_PROOF = ("  unfold A_bm_fit_linear at h_bm_fit_linear\n"
               "  have hx : x ∈ Set.Icc (1 : ℝ) (6 : ℝ) := ⟨by linarith [dom_x.1], by linarith [dom_x.2]⟩\n"
               "  have hy := h_bm_fit_linear hx\n"
               "  linarith [dom_x.2]\n")

POWER_PROOF = ("  unfold A_bm_power_balance at h_bm_power_balance\n"
               "  unfold A_bm_source_min at h_bm_source_min\n"
               "  unfold A_bm_loss_b at h_bm_loss_b\n"
               "  unfold A_bm_loss_c at h_bm_loss_c\n"
               "  linarith\n")


def floor_proof(k: int, f_text: str) -> str:
    f = lit(f_text)
    return ("  unfold A_bm_max_density at h_bm_max_density\n"
            "  unfold A_bm_max_sigma at h_bm_max_sigma\n"
            "  have hpos : 0 < n * s := mul_pos dom_n dom_s\n"
            f"  have hle : n * s ≤ {NMAX} * {SMAX} :=\n"
            "    mul_le_mul h_bm_max_density h_bm_max_sigma dom_s.le (by norm_num)\n"
            f"  have key : {f} * ({NMAX} * {SMAX}) ≤ ({k} : ℝ) * Real.log (10 : ℝ) := by\n"
            "    leancert\n"
            "  rw [ge_iff_le, le_div_iff₀ hpos]\n"
            f"  calc {f} * (n * s) ≤ {f} * ({NMAX} * {SMAX}) :=\n"
            "        mul_le_mul_of_nonneg_left hle (by norm_num)\n"
            f"    _ ≤ ({k} : ℝ) * Real.log (10 : ℝ) := key\n")


def floor_claim(name: str, k: int, f_text: str, intent: str) -> dict:
    return {"name": name, "type": "floor", "intent": intent,
            "variables": {"n": {"unit": "m^-3", "domain": "positive"}, "s": {"unit": "m^2", "domain": "positive"}},
            "assumptions": {"bm_max_density": ["n"], "bm_max_sigma": ["s"]},
            "constants": {"F": f_text}, "goals": [f"{k} * log(10) / (n * s) >= F"]}


def build() -> list[tuple[dict, str, str]]:
    """(claim yaml, proof text, expected status)."""
    out = []
    geom_true = [("3 cm", "4 cm", "5.1 cm"), ("6 cm", "2 cm", "6.5 cm"), ("1 cm", "1 cm", "1.5 cm"), ("7 cm", "5 cm", "8.7 cm")]
    geom_planted = [("5 cm", "4 cm", "6 cm"), ("6 cm", "3 cm", "6.5 cm"), ("2 cm", "2 cm", "2.5 cm"), ("4 cm", "1 cm", "4.1 cm")]
    for i, (r, h, R) in enumerate(geom_true, 1):
        out.append(({"name": f"geom_true_{i}", "type": "fits_in_sphere", "intent": f"cylinder r {r}, h {h} fits in R {R}",
                     "cylinder": {"r": r, "h": h, "R": R}}, GEOM_PROOF, "PASS"))
    for i, (r, h, R) in enumerate(geom_planted, 1):
        out.append(({"name": f"geom_planted_{i}", "type": "fits_in_sphere",
                     "intent": f"planted: r {r} < R {R} radially, but the corner with h {h} is outside",
                     "cylinder": {"r": r, "h": h, "R": R}}, GEOM_PROOF, "FAIL"))

    arith_true = ["4.55 cm", "9.11 cm", "13.67 cm", "18.23 cm"]
    arith_planted = ["4.84 cm", "9.68 cm", "14.51 cm", "19.35 cm"]
    for k, f in enumerate(arith_true, 1):
        out.append((floor_claim(f"arith_true_{k}", k, f, f"{k} decades need at least {f}"), floor_proof(k, f), "PASS"))
    for k, f in enumerate(arith_planted, 1):
        out.append((floor_claim(f"arith_planted_{k}", k, f, f"planted: floor 5 % above the true {k}-decade value"),
                    floor_proof(k, f), "FAIL"))

    unit_true = ["45.5 mm", "9.11 cm", "0.1367 m", "182.3 mm"]
    unit_planted = ["4.55 m", "91.1 cm", "0.1367 s", "18.23 cm^2"]
    for k, f in enumerate(unit_true, 1):
        out.append((floor_claim(f"unit_true_{k}", k, f, f"{k} decades need at least {f}"), floor_proof(k, f), "PASS"))
    for k, f in enumerate(unit_planted, 1):
        proof = floor_proof(k, f) if parse_quantity(f).dim == parse_quantity("1 m").dim else "  sorry\n"
        out.append((floor_claim(f"unit_planted_{k}", k, f, f"planted unit error: {f}"), proof, "FAIL"))

    range_true = [("2", "3"), ("1", "6"), ("1.5", "4"), ("5", "6")]
    range_planted = [("5", "8"), ("0", "2"), ("6", "7"), ("0.5", "1.5")]
    for i, (lo, hi) in enumerate(range_true + range_planted):
        planted = i >= 4
        u = 3 * float(hi) + 2
        name = f"range_{'planted' if planted else 'true'}_{i % 4 + 1}"
        out.append(({"name": name, "type": "bound",
                     "intent": f"{'planted: fit used outside [1, 6]; ' if planted else ''}y <= {u:g} for x in [{lo}, {hi}]",
                     "variables": {"x": {"unit": "1", "domain": [lo, hi]}, "y": {"unit": "1", "domain": "real"}},
                     "assumptions": {"bm_fit_linear": ["x", "y"]}, "constants": {"U": f"{u:g}"},
                     "goals": ["y <= U"]}, RANGE_PROOF, "FAIL" if planted else "PASS"))

    power_true = ["500 kW", "400 kW", "490 kW", "100 kW"]
    power_planted = ["800 kW", "700 kW", "1 MW", "750 kW"]
    for i, bound in enumerate(power_true + power_planted):
        planted = i >= 4
        name = f"power_{'planted' if planted else 'true'}_{i % 4 + 1}"
        out.append(({"name": name, "type": "bound",
                     "intent": f"{'planted: a loss term dropped; ' if planted else ''}net power at least {bound}",
                     "variables": {v: {"unit": "W", "domain": "real"} for v in ("Pnet", "Ps", "Pb", "Pc")},
                     "assumptions": {"bm_power_balance": ["Pnet", "Ps", "Pb", "Pc"], "bm_source_min": ["Ps"],
                                     "bm_loss_b": ["Pb"], "bm_loss_c": ["Pc"]},
                     "constants": {"L": bound}, "goals": ["Pnet >= L"]}, POWER_PROOF, "FAIL" if planted else "PASS"))
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    expected = {}
    for claim, proof, status in build():
        (OUT / f"{claim['name']}.yaml").write_text(yaml.safe_dump(claim, allow_unicode=True, sort_keys=False),
                                                   encoding="utf-8", newline="\n")
        (OUT / f"{claim['name']}.proof.lean").write_text(proof, encoding="utf-8", newline="\n")
        expected[claim["name"]] = status
    assert len(expected) == 40 and sum(s == "PASS" for s in expected.values()) == 20
    (HERE / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(expected)} claims")


if __name__ == "__main__":
    main()
