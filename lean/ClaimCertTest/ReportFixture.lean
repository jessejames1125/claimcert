import ClaimCert

theorem fx_uses (a : ℝ) (dom_a : 0 < a) (h_unused : a ≤ 5) (h_used : a ≤ 3) : a < 4 :=
  lt_of_le_of_lt h_used (by norm_num)

#cc_report fx_uses
