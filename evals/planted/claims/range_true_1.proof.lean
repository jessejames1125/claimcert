  unfold A_bm_fit_linear at h_bm_fit_linear
  have hx : x ∈ Set.Icc (1 : ℝ) (6 : ℝ) := ⟨by linarith [dom_x.1], by linarith [dom_x.2]⟩
  have hy := h_bm_fit_linear hx
  linarith [dom_x.2]
