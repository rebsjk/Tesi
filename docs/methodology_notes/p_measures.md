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

## Next steps (not implemented in this pass)

- **Regime-dummy / interaction specification:** replace or augment
  `csi_t` with the Phase-3 regime labels
  (`data_final/csi/csi_regime_monthly_<date>.csv`) — tests whether the
  relationship is threshold/nonlinear rather than linear-continuous.
- **Alternative dependent variables:** cross-sectional return dispersion,
  downside/tail severity (the severity-vs-frequency decomposition
  template already flagged in `csi_construction.md` from Tasitsiomi and
  Noguer i Alonso).
- **Horizon sensitivity:** re-run at longer horizons (e.g. 3- or
  6-month-ahead realized vol) — a structural state variable may operate
  on a slower cycle than 1 month.
- **Panel / Fama-MacBeth:** constituent-level realized risk (not just
  index-level) conditioned on CSI, with cross-sectional as well as
  time-series variation.
- **VAR / Granger causality:** joint CSI-volatility dynamics, testing
  lead-lag direction rather than assuming CSI is purely a leading
  indicator.

None of these are decided or scheduled yet — listed here so the next
model iteration starts from a documented menu, not from scratch.
