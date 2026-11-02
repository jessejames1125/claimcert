You are given a Lean 4 theorem statement and the definitions it uses. Write in plain English
exactly what the statement asserts: every variable, every hypothesis, and the conclusion. All
numbers are in SI units. Do not guess at the author's purpose and do not judge whether it is true.

## Definitions

```lean
/-- NUMBER. Range: n/a. Source: illustrative value for this evaluation -/
def A_wait_cap (w : ℝ) : Prop :=
  w ≤ (1 / 5 : ℝ)
```

## Statement

```lean
theorem claim (w : ℝ) (h_wait_cap : A_wait_cap w) :
    ((5 : ℝ) * w) ≤ (1 : ℝ) := by ...
```
