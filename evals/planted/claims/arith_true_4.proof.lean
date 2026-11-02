  unfold A_bm_max_density at h_bm_max_density
  unfold A_bm_max_sigma at h_bm_max_sigma
  have hpos : 0 < n * s := mul_pos dom_n dom_s
  have hle : n * s ≤ (100000000000000000000000000000 : ℝ) * (1 / 2000000000000000000000000000 : ℝ) :=
    mul_le_mul h_bm_max_density h_bm_max_sigma dom_s.le (by norm_num)
  have key : (1823 / 10000 : ℝ) * ((100000000000000000000000000000 : ℝ) * (1 / 2000000000000000000000000000 : ℝ)) ≤ (4 : ℝ) * Real.log (10 : ℝ) := by
    leancert
  rw [ge_iff_le, le_div_iff₀ hpos]
  calc (1823 / 10000 : ℝ) * (n * s) ≤ (1823 / 10000 : ℝ) * ((100000000000000000000000000000 : ℝ) * (1 / 2000000000000000000000000000 : ℝ)) :=
        mul_le_mul_of_nonneg_left hle (by norm_num)
    _ ≤ (4 : ℝ) * Real.log (10 : ℝ) := key
