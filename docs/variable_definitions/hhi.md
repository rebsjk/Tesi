# hhi

Herfindahl-Hirschman Index of constituent capital weight — the baseline
capital-concentration measure in `csi_construction.md`.

- **Formula:** `hhi_t = Σ_i weight_i,t^2`, over all active constituents at
  `t` (no top-k restriction)
- **Range:** `1/N_t` (perfectly diffuse) to `1` (single name)
- **Direction:** ↑ = more concentrated (`concentration_direction("hhi") == +1`)
- **Frequency (this build):** monthly, month-end trading date
- **Source columns:** `weight` from `data_final/universe/` (see
  `docs/variable_definitions/weight.md`)
- **Computed in:** `src/concentration/measures.py::herfindahl_index`,
  applied at month-end by `src/concentration/build_concentration_panel.py`
- **Output:** `data_final/concentration/concentration_measures_monthly_<date>.csv`,
  column `hhi`
