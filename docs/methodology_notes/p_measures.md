# Physical-risk (P-measure) methodology — Phase 4

Status: **first minimal model implemented and reported (2026-08-20)**.
This note documents the first P-measure specification only — a
deliberately minimal, defensible baseline to extend from, not a survey
of every planned physical-risk model. Extensions (regime dummies,
alternative dependent variables, longer horizons, panel specifications)
are listed at the end as explicit next steps, not implemented here.

## Dependent variable: self-weighted index realized volatility

`src/physical_risk/build_index_returns.py` builds the P-measure's first
dependent variable directly from the Phase-1 constituent panel
(`data_final/universe/`), not from a vendor index-return file (e.g.
CRSP's `vwretd`):

```
r_idx,d = sum_i weight_i,d * ret_i,d          (daily, same-day weight and return)
RV_t = sqrt(sum_{d in month t} r_idx,d^2)     (monthly realized volatility, un-annualized)
```

**Why self-weighted, not a vendor index file:** the CSI's capital-
concentration measures (`hhi`, `cr_10`) are computed from this project's
own self-computed weight (`weight = dlycap_i,t / sum(dlycap over active
members)` — see `docs/methodology_notes/index_weight_construction.md`,
decided because the official point-in-time S&P weight table isn't
reachable under this project's WRDS subscription). Using a different,
vendor-computed index return series (with its own float-adjustment and
methodology idiosyncrasies) as the P-measure's outcome would introduce a
subtle mismatch between "the index whose concentration is measured" and
"the index whose risk is predicted." Building the index return from the
exact same weights keeps the two internally consistent.

**Sanity-checked** against known market history: the single worst daily
return in the series is **2020-03-16 (-11.6%)** and the best is
**2008-10-13 (+12.0%)** — both match the actual most extreme trading
days in this period (the COVID crash and a major GFC relief rally
respectively), confirming the self-built series behaves correctly.

Output: `data_final/physical_risk/index_returns_daily_<date>.csv`,
`data_final/physical_risk/realized_vol_monthly_<date>.csv`.

## Model

```
RV_{t+1} = alpha + beta * CSI_t + gamma * RV_t + eps_{t+1}
```

**Hypothesis (H1):** `beta > 0` — elevated concentration (state at
month-end `t`) predicts higher realized volatility in the following
month, consistent with this thesis's core framing of concentration as a
structural driver of systemic risk.

**Why CSI enters continuous, not as regime dummies, in this first
model:** the continuous composite z-score preserves all the information
in the series and gives the simplest possible first read of "does the
concentration state predict risk" — regime dummies (or a continuous ×
regime interaction) are a natural extension once this linear baseline
exists, not the first cut. See "Next steps" below.

**Why `RV_t` (the AR(1) term) is included from the start, not added
after the fact:** both `CSI` and realized volatility are strongly
persistent series (`CSI` has a pronounced secular trend —
`csi_construction.md`; realized volatility exhibits well-documented
clustering). A regression of `RV_{t+1}` on `CSI_t` alone risks
attributing shared persistence between two autocorrelated series to
genuine predictive content, the same class of confound already
encountered in the Phase-3 collinearity check (trending series inflate
correlation in levels). Controlling for `RV_t` from the first
specification, not as a robustness afterthought, is the more defensible
default.

**Timing:** `CSI_t` is the composite as of month-end `t`; `RV_{t+1}` is
realized volatility computed from daily returns strictly within calendar
month `t+1` — a genuine predictive (non-contemporaneous) regression, not
a contemporaneous correlation.

**Estimator:** OLS with HAC (Newey-West) standard errors, 12 lags (one
year of monthly data) — standard for monthly financial predictive
regressions with potential residual autocorrelation/heteroskedasticity.
Panel/Fama-MacBeth (natural for a future constituent-level extension) and
a VAR (for bidirectional/Granger-causality dynamics) are both considered
and deferred — see "Next steps."

**Implementation:** `src/physical_risk/regression_csi_predicts_vol.py`.

## Results (2026-08-20 build)

Sample: 295 months, 2001-12 to 2026-06 (bounded by CSI's own burn-in at
the start and by the need for a subsequent month's realized data at the
end).

| | coef | HAC se | z | p |
|---|---|---|---|---|
| const | 0.0163 | 0.004 | 4.01 | <0.001 |
| **csi_t** | **0.0003** | 0.001 | 0.42 | **0.678** |
| rv_t | 0.6427 | 0.097 | 6.60 | <0.001 |

R² = 0.416, N = 295.

**Reading — a clean null result for beta, reported as-is, not
reframed.** The AR(1) term (`rv_t`) is highly significant and does most
of the explanatory work (vol clustering, as expected). **`csi_t`'s
coefficient is statistically indistinguishable from zero** (p = 0.68) —
this linear, continuous, 1-month-ahead specification finds no detectable
incremental predictive power for concentration once last month's
volatility is accounted for.

**This is not an artifact of the AR(1) control "stealing" CSI's effect**
— a univariate check (`RV_{t+1}` on `csi_t` alone, no `rv_t` control)
is *also* insignificant (coef=0.0018, p=0.27, R²=0.9%), and the raw
contemporaneous correlation between `csi_t` and `rv_t` is weak (0.12).
There was little linear CSI → next-month-volatility relationship to
begin with at this specification, with or without the persistence
control.

**Interpretation, held provisional:** a null result at this specific
horizon/functional form does not resolve the thesis's core question — it
narrows down what *doesn't* work as the first cut. Plausible next
directions (see below): the relationship may be nonlinear/regime-
specific rather than linear-continuous; realized index-level volatility
may not be the P-measure target most sensitive to concentration
(cross-sectional dispersion or downside/tail severity are conceptually
closer to "concentration risk" specifically); the 1-month horizon may be
too short for a slow-moving structural state variable to show up against
volatility's own strong short-run persistence.

## Model 2: regime dummies instead of the continuous composite

```
RV_{t+1} = alpha + beta_med * 1{regime_t=medium} + beta_high * 1{regime_t=high}
           + gamma * RV_t + eps_{t+1}
```

**Regime → dummy translation:** `low` is the omitted/reference category
(per the standard dummy-coding convention — including a dummy for all
three categories plus a constant would be collinear). `regime_medium`
and `regime_high` are read as the RV difference relative to the
low-concentration regime, holding `RV_t` fixed. Regime labels come from
`data_final/csi/csi_regime_monthly_<date>.csv` (Phase-3 rolling 60-month
tercile classification); months with no defined regime (that
classification's own burn-in, on top of the composite's own burn-in) are
dropped from this regression's sample, same treatment as any other
missing regressor — not backfilled.

**Hypotheses:**
- **H1 (primary):** `beta_high > 0` — being in the high-concentration
  regime predicts higher next-month realized volatility than the
  low-concentration regime, the same directional prediction as the
  continuous model's `beta`, just in threshold form.
- **H2 (secondary, weaker prior):** `beta_med` between 0 and `beta_high`
  — a monotonic staircase (low < medium < high) would be the cleanest
  confirmation of a genuine dose-response relationship. Held as a weaker
  prior than H1 since the continuous model's null result already
  suggests any relationship, if present, may not be a smooth linear one
  across the medium range specifically.

**Implementation:** `src/physical_risk/regression_csi_regime_predicts_vol.py`.
Same dependent variable, `RV_t` AR(1) control, and HAC (12 lags) as
Model 1 — the only change is how CSI enters the regression, isolating
the effect of functional form.

### Results (2026-08-20 build)

Sample: 236 months, 2006-11 to 2026-06 — **shorter than Model 1's 295**,
because the regime classification's own 60-month rolling-window burn-in
(ending 2006-10, see `csi_construction.md`) sits on top of the
composite's 24-month burn-in. Regime distribution in-sample: high=149,
medium=49, low=38 (the imbalance already documented and explained in
`csi_construction.md` — not new here).

| | coef | HAC se | z | p |
|---|---|---|---|---|
| const | 0.0137 | 0.004 | 3.51 | <0.001 |
| **regime_medium** | 0.0054 | 0.004 | 1.37 | 0.171 |
| **regime_high** | 0.0049 | 0.003 | 1.87 | **0.062** |
| rv_t | 0.6186 | 0.107 | 5.76 | <0.001 |

R² = 0.399, N = 236.

**Reading — closer to significance than the continuous model, but not
there yet, and the comparison is apples-to-apples, not a sample-period
artifact.** `beta_high` is positive, as H1 predicts, and at p=0.062 is
much closer to conventional significance than the continuous model's
p=0.68 — but does not clear the 5% threshold on its own. To rule out
"this difference is just because the regime model runs on a shorter,
later-starting sample" (2006-2026 vs. 2001-2026), re-ran Model 1
restricted to the *exact same* 236-month sample as Model 2: on that
identical sample, the continuous CSI coefficient becomes **even more
null** (coef≈0.00007, p=0.929, vs. p=0.68 on the full sample) while
`beta_high` stays at p=0.062. This is a genuine, same-sample
threshold-vs-linear comparison, not a confound of which months are
included — **the nonlinear/regime specification is telling a materially
different, more suggestive story than the linear one on identical
data**, even though neither clears conventional significance yet.

**Non-monotonicity, flagged honestly, not smoothed over:**
`beta_medium` (0.0054) is numerically slightly *larger* than
`beta_high` (0.0049), the opposite of the clean low<medium<high
staircase H2 anticipated — though `beta_medium` itself is not
significant (p=0.17), so this shouldn't be over-read as "medium
concentration is riskier than high." Worth carrying forward as an open
question rather than resolving here: it could reflect genuine
non-monotonicity, or simply noise in the smaller medium-regime cell
(49 months).

**Where this leaves the thesis's core question:** still short of a
significant finding at conventional levels, but the threshold
specification is directionally more supportive of H1 than the linear one
on the same data — motivates continuing to the dependent-variable and
horizon extensions below rather than concluding the null from Model 1
is final.

## Next steps

### Immediate next block: cross-sectional dispersion as the dependent variable

Quick construction plan, to implement next:

1. From `data_final/universe/` (the Phase-1 panel — already has
   `permno, date, ret, weight`), compute daily **cross-sectional
   dispersion** of constituent returns: `disp_d = std(ret_i,d across
   active i)` (equal-weight cross-sectional std dev — deliberately not
   weight-weighted, since the point is to measure how much individual
   names diverge from each other, not to re-derive a capital-weighted
   quantity the CSI already captures).
2. Aggregate to monthly, analogous to `RV_t`: either the average daily
   dispersion within the month, or `sqrt(mean(disp_d^2))` — decide by
   analogy with the realized-vol construction already in place, document
   whichever is chosen.
3. Re-run both Model 1 (continuous CSI) and Model 2 (regime dummies)
   with `disp_{t+1}` in place of `RV_{t+1}`, same AR(1)-control and HAC
   structure, same sample-restriction discipline (apples-to-apples
   comparison) demonstrated above.

### Other candidates, not yet scheduled

- **Downside/tail severity:** the severity-vs-frequency decomposition
  template already flagged in `csi_construction.md` from Tasitsiomi and
  Noguer i Alonso.
- **Horizon sensitivity:** 3- or 6-month-ahead realized vol/dispersion —
  a structural state variable may operate on a slower cycle than 1
  month.
- **Panel / Fama-MacBeth:** constituent-level realized risk conditioned
  on CSI, with cross-sectional as well as time-series variation.
- **VAR / Granger causality:** joint CSI-volatility dynamics, testing
  lead-lag direction rather than assuming CSI is purely a leading
  indicator.
- **Formal test of `beta_medium = beta_high`:** a Wald test on the
  regime-dummy model, to directly test the non-monotonicity flagged
  above rather than eyeballing the point estimates.
