You are given a Lean 4 theorem statement and the definitions it uses. Write in plain English
exactly what the statement asserts: every variable, every hypothesis, and the conclusion. All
numbers are in SI units. Do not guess at the author's purpose and do not judge whether it is true.

## Definitions

```lean
/-- NUMBER. Range: n/a. Source: illustrative value for this evaluation -/
def A_rate_cap (r : ℝ) : Prop :=
  r ≤ (200 : ℝ)
```

## Statement

```lean
theorem claim (r : ℝ) (h_rate_cap : A_rate_cap r) :
    r ≤ (300 : ℝ) := by ...
```
