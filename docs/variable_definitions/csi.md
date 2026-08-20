# csi (Concentration State Index, composite)

Status: **decided** (2026-08-20). Full selection evidence and reasoning
in `docs/methodology_notes/csi_construction.md`, "Collinearity check
results and component selection" and "Decision (2026-08-20)". This file
documents the composite formula and its two governing construction
parameters (standardization window, burn-in), each with the trade-off
made explicit — required before either is changed.

## Formula

```
z_c,t = (c_t - mean(c_1..t)) / std(c_1..t)      for c in {hhi, cr_10, entropy_concentration}
csi_t = mean(z_hhi,t, z_cr_10,t, z_entropy_concentration,t)
```

Equal-weight z-score average (Option B in `csi_construction.md`) of the
three components chosen in the collinearity check — one representative
per empirically-distinct cluster (`hhi` as the whole-distribution hub,
`cr_10` as the top-k representative, `entropy_concentration` for the
short-run information the `cr_k` family doesn't carry). No sign-flip
needed: all three already have direction +1 (higher = more concentrated).
`effective_n` is excluded (deterministic identity with `hhi`, not a
fourth independent signal — see the csi_construction.md discussion);
`cr_5`/`cr_7` remain standalone diagnostics in
`data_final/concentration/`, not composite inputs.

## Standardization window: expanding, not rolling

`mean(c_1..t)`/`std(c_1..t)` are computed over an **expanding window**
— every observation from the start of the series through `t` itself,
inclusive — not a fixed-length rolling window. Chosen over rolling
because it introduces no arbitrary window-length parameter to justify,
matches the "simplest first" approach already used elsewhere in
`csi_construction.md` (Option A→B before C, PCA deferred), and because
the z-score's job here is purely to bring three differently-scaled series
onto a comparable scale for equal-weight averaging — *not* to characterize
the current concentration regime, which is a separate, later step
(state/regime classification, still open in `csi_construction.md`).

**Trade-off, stated explicitly: the historical CSI is not frozen against
future extensions of the sample.** Because the window is expanding, the
mean/std used to standardize, say, January 2015 is computed from
2000-01 through 2015-01 *as available at the time the standardization is
run* — if the panel is extended with new months in the future and
`build_csi.py` is re-run, January 2015's mean/std base changes (a few
more years of data now sit in "the sample used to define what's
normal"), so its z-score, and therefore `csi` for that date, will shift
slightly. This is **point-in-time valid** — no future information is
used relative to the date being standardized — but it is **not
immutable** the way a rolling-window or fixed-parameter statistic would
be. Acceptable for this thesis's one-time historical construction (the
full 2000-2026 panel is built once, not incrementally extended month by
month during the analysis), but worth being explicit about: a "CSI value
for January 2015" computed today and a "CSI value for January 2015"
recomputed after a future re-pull are both legitimate and point-in-time
correct, but are not guaranteed to be numerically identical. Per the
anti-look-ahead rules' logging requirement (`csi_construction.md`, rule
5), every CSI file cites the pull/build date it was computed from
(`data_final/csi/csi_composite_monthly_<date>.csv`) precisely so a
downstream result can identify which vintage it used.

**Phase-6 robustness variant:** rolling window (candidate lengths: 36,
60, 120 months), same treatment as PCA — reported as a robustness
cross-check on whether the P-vs-Q conclusions are sensitive to expanding
vs. rolling standardization, not decided now.

## Burn-in: 24 months

The first 24 monthly observations of each component are excluded from
the CSI series entirely — not backfilled with a full-sample statistic —
because `std(c_1..t)` computed on very few points is unstable: with only,
say, 6-12 observations, a single outlying month can dominate the
estimated standard deviation and produce an erratic early z-score that
says more about small-sample noise than about the concentration state.
24 months (2 years) is a round, defensible minimum for a moderately
stable monthly standard-deviation estimate — not derived from a formal
power calculation, and **exactly as much of an arbitrary parameter
choice as a rolling window length would have been**; picking a burn-in
threshold instead of a rolling window avoids the window-length choice
for the *ongoing* standardization basis, but does not avoid an arbitrary
parameter choice altogether.

**Phase-6 robustness variant:** re-run with burn-in = 12 and 36 months,
alongside the rolling-vs-expanding check above, and confirm the Phase-4/5
conclusions are not sensitive to this choice.

## Validation: the 2022 dip is price-driven, not composition-driven (2026-08-20)

The sanity-check plot (`outputs/figures/csi_sanity_check_20260820.png`)
shows a clear CSI decline through 2022. Checked directly against the
underlying panel (`data_final/universe/`) whether this reflects mega-cap
weights actually falling, or a change in which names occupy the top-10 /
universe composition:

- **Cohort overlap:** the top-10-by-weight cohort at 2021-12 start
  (AAPL, MSFT, AMZN, TSLA, GOOG, GOOGL, NVDA, META, JPM, UNH) and at
  2022-12 start (AAPL, MSFT, AMZN, GOOG, TSLA, GOOGL, UNH, JNJ, XOM, NVDA)
  share **8 of 10 names**. Only META and JPM dropped out, replaced by
  JNJ and XOM — itself an economically coherent rotation (mega-cap growth
  → defensive healthcare / energy, matching 2022's well-documented
  growth-to-value and energy-sector rotation), not arbitrary churn.
- **Fixed-cohort price tracking:** holding the exact December-2021 top-10
  names fixed (not re-selecting), their combined CRSP market cap
  (`dlycap`) fell **-38.5%** from 2021-12-31 to 2022-12-30, while the
  rest of the index fell only **-12.8%** over the same window (total
  index -20.4%). The top-10 lost value at roughly **3x** the rate of the
  rest of the market in dollar terms.

**Conclusion:** the 2022 CSI decline is explained almost entirely by
mega-cap names losing market value disproportionately (the 2022
growth/tech de-rating), not by new names entering the universe or a
reshuffling of the top-10 unrelated to price. This is exactly the
behavior expected of a market-cap-weighted concentration measure and
argues against the CSI being an artifact of constituent churn or
membership-panel noise — a useful additional validation point alongside
the Phase-2 external cross-check (`docs/variable_definitions/cr_k.md`)
before closing Phase 3.

## Output

- **Frequency:** monthly, month-end (inherited from
  `data_final/concentration/`)
- **Source:** `data_final/concentration/concentration_measures_monthly_<date>.csv`
  (`hhi`, `cr_10`, `entropy_concentration` columns)
- **Computed in:** `src/csi/build_csi.py`
- **Output:** `data_final/csi/csi_composite_monthly_<date>.csv` — columns
  `date, csi, z_hhi, z_cr_10, z_entropy_concentration, hhi, cr_10, entropy_concentration`
  (raw component values carried through for audit/traceability)
- **Construction parameters logged to:** `outputs/logs/build_csi_<date>.txt`
  per the anti-look-ahead rules' logging requirement
