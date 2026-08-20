# effective_n

Effective number of constituents — `1/hhi`, interpretable as "the number
of equal-weight names that would produce the same HHI."

- **Formula:** `effective_n_t = 1 / hhi_t`
- **Direction:** ↓ = more concentrated — the **only** inverted measure
  among the Phase-2 candidates (`concentration_direction("effective_n") == -1`).
  Must be sign-flipped before any z-score/PCA aggregation with the other
  measures (`csi_construction.md`, "Measure directionality").
- **Frequency (this build):** monthly, month-end trading date
- **Source columns:** `weight` from `data_final/universe/` (via `hhi`)
- **Computed in:** `src/concentration/measures.py::effective_number_of_constituents`,
  applied at month-end by `src/concentration/build_concentration_panel.py`
- **Output:** `data_final/concentration/concentration_measures_monthly_<date>.csv`,
  column `effective_n`
