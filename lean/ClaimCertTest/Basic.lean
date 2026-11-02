import ClaimCert

open ClaimCert

example : Dim.mul (Dim.mk 1 0 0 0 0 0 0 0) (Dim.mk (-3) 0 0 0 0 0 0 0) = Dim.mk (-2) 0 0 0 0 0 0 0 := by
  decide

example : CylinderFitsInSphere (3 / 100 : ℝ) (4 / 100 : ℝ) (51 / 1000 : ℝ) := by
  rw [cylinderFitsInSphere_iff (by norm_num) (by norm_num)]
  norm_num

example : ¬ CylinderFitsInSphere (5 / 100 : ℝ) (4 / 100 : ℝ) (6 / 100 : ℝ) := by
  rw [cylinderFitsInSphere_iff (by norm_num) (by norm_num)]
  norm_num
