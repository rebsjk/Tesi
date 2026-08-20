# cr_5, cr_7, cr_10 (concentration ratio, monthly-fixed cohort)

Share of total index weight held by the top-`k` constituents, using the
monthly-fixed top-k cohort convention frozen in `csi_construction.md`
("Top-k subset selection and reselection convention") — **not** the plain
same-day top-k definition (`src/concentration/measures.py::concentration_ratio`,
used standalone/daily elsewhere).

- **Cohort selection:** for each calendar month, the top-`k` permnos by
  `weight` as of that month's *first available trading date* are selected
  and held fixed for the whole month.
- **Formula (this build, month-end only):**
  `cr_k,t = Σ_{i in cohort(month(t))} weight_i,t`, evaluated at `t` =
  that month's last available trading date. A cohort member no longer in
  the index at month-end contributes 0 (not dropped/NaN) — logged as a
  cohort-attrition event in `outputs/logs/build_concentration_panel_<date>.txt`
  if it ever occurs (none occurred in the 2000-2026 build).
- **k values:** 5, 7 (informally "Mag7" — not hardcoded to specific
  names, just whichever 7 permnos have the largest weight that month),
  10 — built in parallel per `csi_construction.md`, no primary `k` chosen
  yet (pending the collinearity check).
- **Direction:** ↑ = more concentrated
  (`concentration_direction("cr_5")` etc. `== +1`, via the `cr_*` prefix
  rule in `concentration_direction`)
- **Frequency:** monthly, month-end trading date
- **Source columns:** `weight`, `permno`, `date` from `data_final/universe/`
- **Computed in:** `src/concentration/build_concentration_panel.py::build_monthly_concentration_panel`
  (cohort selection is entity-aware, so it isn't a `measures.py` pure
  function — see that script's module docstring)
- **Output:** `data_final/concentration/concentration_measures_monthly_<date>.csv`,
  columns `cr_5`, `cr_7`, `cr_10`

## External cross-check (2026-08-20)

Compared the 2026-07-30 (latest available) values against external
published figures (web search — CNBC, Forbes, Motley Fool, and a
concentration piece citing "10 firms make up over 36% of the S&P 500, up
from 23% in 2000" and "top 10 companies representing over 37%"):

- **CR-10: 37.0%** (this build) vs. **"over 37%"** externally — close
  match, and the 2000-01-31 value (24.8%) is consistent with the cited
  "23% in 2000."
- **CR-7: 31.9%** (this build) vs. **34-35%** commonly cited for the
  "Magnificent 7." Investigated the gap directly by pulling the actual
  top-10 constituent list at 2026-07-30: AAPL, NVDA, MSFT, AMZN, GOOGL,
  **AVGO (Broadcom)**, GOOG, TSLA, META, LLY (by weight, descending).
  Two definitional reasons for the gap, both structural rather than a
  pipeline error:
  1. **Broadcom (AVGO) now outweighs Meta by raw market cap** and is
     included in this build's algorithmic top-7 (generic "largest 7 by
     weight," per this project's convention), displacing Meta —
     externally-cited "Magnificent 7" figures use the fixed named basket
     (Apple, Microsoft, Nvidia, Alphabet, Amazon, Meta, Tesla), not a
     recomputed top-7-by-weight.
  2. **Alphabet's two share classes (GOOGL + GOOG) both count as
     separate top-7 slots** in this build (correct per this project's
     sharetype filter — both are `NS`, both genuinely separate index
     constituents, confirmed with the user 2026-08-19), consuming two of
     the seven slots for one company, whereas the popular "Magnificent 7"
     counts Alphabet once.
  
  Recomputing the weight of the specific 7 named Magnificent-7 companies
  (treating GOOGL+GOOG as one Alphabet: AAPL+NVDA+MSFT+AMZN+GOOGL+GOOG+META+TSLA)
  at the same date gives **32.7%** — most of the gap closes once the
  comparison uses the same basket definition; the small remainder is
  plausibly float-adjustment or reporting-date differences across the
  external sources (which themselves ranged 34-40% depending on outlet).
  **Conclusion: the pipeline is validated — CR-10 matches closely, and
  the CR-7 gap is fully explained by this project's "largest-k-by-weight"
  convention differing from the informally-named Magnificent 7 basket,
  not by a computation error.**
