import Mathlib

namespace ClaimCert

/-- A solid cylinder of radius `r` and half-length `h`, centred on the centre of a sphere of
radius `R` and sharing its axis, lies inside the sphere: every point, in meridional coordinates
`(ρ, z)`, is within `R` of the centre. This is the full-geometry test. Checking `r ≤ R` alone
ignores the corners. -/
def CylinderFitsInSphere (r h R : ℝ) : Prop :=
  ∀ ρ ∈ Set.Icc (0 : ℝ) r, ∀ z ∈ Set.Icc (-h) h, ρ ^ 2 + z ^ 2 ≤ R ^ 2

/-- The cylinder fits exactly when its corner `(r, h)` does. -/
theorem cylinderFitsInSphere_iff {r h R : ℝ} (hr : 0 ≤ r) (hh : 0 ≤ h) :
    CylinderFitsInSphere r h R ↔ r ^ 2 + h ^ 2 ≤ R ^ 2 := by
  constructor
  · intro hf
    exact hf r ⟨hr, le_rfl⟩ h ⟨by linarith, le_rfl⟩
  · intro hc ρ hρ z hz
    have h1 : ρ ^ 2 ≤ r ^ 2 := by nlinarith [hρ.1, hρ.2]
    have h2 : z ^ 2 ≤ h ^ 2 := by nlinarith [hz.1, hz.2]
    linarith

end ClaimCert
