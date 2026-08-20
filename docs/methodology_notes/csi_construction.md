# CSI construction methodology

Status: **aggregation and regime classification both decided (2026-08-20).**
Composite CSI = equal-weight z-score average of `hhi`, `cr_10`,
`entropy_concentration` — see "Collinearity check results and component
selection" and the "Decision" block under "Aggregation choices under
consideration" below. Regime classification = rolling 60-month tercile
thresholds, no hysteresis — see the "Decision" block under "State /
regime classification" below. This document still governs every
downstream P-measure and Q-measure result's CSI version — update it again
if the construction ever changes.

## What the CSI is

The Concentration State Index (CSI) is a **structural state variable**, not
a descriptive statistic. It is built once, in `src/csi/` (phase 3), from
the individual concentration measures computed in `src/concentration/`
(phase 2), and is then held fixed as an input to both the physical-risk
work (phase 4, `src/physical_risk/`) and the risk-neutral tail work
(phase 5, `src/options_tails/`). Because it conditions regressions run over
the same historical window it was estimated on, any leakage of future
information into a past CSI value would invalidate every result built on
top of it. Point-in-time validity (below) is therefore treated as a
hard constraint, not a nice-to-have.

## Top-k subset selection and reselection convention (global design choice)

This applies to **every** top-k/top-N-based measure defined anywhere in this
document: CR-k (capital concentration, below), the top-k basket used in
return-space concentration, the top-k cohort used in risk-share
concentration, and the top-N subset used for the covariance/correlation
estimation that risk concentration and dependence concentration both depend
on. It is stated once here, before any individual measure is defined,
because it is a single global design choice, not a detail local to one
measure — every section below that uses a top-k or top-N cohort follows this
convention rather than redefining its own.

**Anchor.** The composition of any top-k/top-N cohort as of date `t` is
always selected using weights **as of `t` itself** — the date the measure's
value is being computed for — never using weights from `t-T` (the start of
whatever rolling window that measure's own return/covariance estimation
otherwise uses). This keeps every cohort-based measure using the freshest
information available at `t`, consistent with the point-in-time convention
already governing the constituent panel. Using `t`-dated weights to decide
who is "in" the cohort at `t` is not a look-ahead violation — nothing later
than `t` is used, only the anchor point within the measure's own window
differs from window-start.

**Reselection frequency.** The specific list of names occupying the
top-k/top-N is refreshed **monthly**, not daily. Within a calendar month, the
same named cohort is held fixed for the entire month. For return-space
concentration and risk-share concentration this is not optional: the
trailing return series / covariance matrix computed inside that month's
rolling window requires a stable, unchanging set of names throughout the
window to be well-defined at all (see the covariance/correlation estimation
caveat below). For CR-k it is not mathematically required — CR-k is a
same-day statistic with no window of its own — but it is adopted anyway so
that CR-k, return-space concentration, and risk-share concentration can be
compared against each other in the mandatory collinearity check using the
*identical* named cohort at every date, rather than three independently
daily-refreshed cohorts that only mostly overlap. At the start of each new
calendar month, the cohort is refreshed using weights as of that month's
first available trading date.

**Standalone CR-k exception.** If CR-k is reported on its own as a
capital-concentration diagnostic (its role in the candidate-components table
below), rather than as one side of a collinearity comparison, it may
additionally be computed using the plain daily-recomputed definition (top-k
by weight exactly as of each date, no monthly freeze) as a secondary series.
The two will usually differ only marginally, since mega-cap membership near
the existing cutoffs is rarely volatile within a single month, but whichever
definition is used in a given table or figure must be stated explicitly —
silently mixing the monthly-fixed and daily-recomputed versions would be a
labeling error, not a computation error, and would be easy to miss.

## Candidate components

All computed in `src/concentration/measures.py` on the constituent weights
panel from `src/universe/build_constituent_panel.py`:

| Measure | Function | Direction | Captures |
|---|---|---|---|
| HHI | `herfindahl_index` | ↑ = more concentrated | Overall dispersion of index weight; standard concentration benchmark |
| CR-1, CR-5, CR-10, CR-20 | `concentration_ratio` | ↑ = more concentrated | Weight held by the largest 1/5/10/20 names specifically — more sensitive to mega-cap dominance than HHI. When used in the collinearity check against return-space/risk-share concentration, computed on the monthly-fixed cohort per the top-k subset selection and reselection convention above; may also be reported standalone using the plain daily-recomputed definition — see that convention's standalone exception |
| Effective N | `effective_number_of_constituents` | ↓ = more concentrated (**inverted**) | 1/HHI; interpretable as "equivalent equal-weighted constituent count" |
| Entropy concentration | `entropy_concentration` | ↑ = more concentrated | Cross-check against HHI; entropy and HHI can diverge when a few very large names coexist with a long, non-trivial tail (HHI is dominated by the largest terms; entropy is more sensitive to the whole distribution) |

Open question to confirm with the advisor before phase 3 starts: does the
CSI use a single primary measure (most likely HHI or CR-10, for
interpretability and comparability to existing literature) with the others
retained only as robustness checks, or a genuine multi-measure composite?
The rest of this document lays out both paths so the decision doesn't block
`src/csi/` from being scaffolded.

## Measure directionality (resolve before any aggregation)

`effective_n` is `1/HHI`, so it runs in the **opposite direction** from
every other candidate measure: a *higher* HHI/CR-k/entropy-concentration
means *more* concentration, but a *higher* effective_n means *less*
concentration. `src/concentration/measures.py` exposes this explicitly via
`CONCENTRATION_DIRECTION` / `concentration_direction(name)` (`+1` = already
aggregation-ready, `-1` = must be sign-flipped first).

This is not a cosmetic detail — it directly determines whether `src/csi/`
produces a meaningful index or a self-canceling one:

- **Option A (single primary measure):** direction is moot only if
  `effective_n` is never the chosen primary measure, or is used purely as a
  descriptive/robustness companion that is never averaged with the others.
  If `effective_n` is ever plotted or compared against HHI/CR-k in the same
  exhibit, its axis or sign must be flagged as inverted, not just left as-is.
- **Option B (z-score average):** every standardized component **must** be
  multiplied by `concentration_direction(name)` before averaging. Averaging
  raw z-scores without this flip means `effective_n` partially cancels
  HHI/CR-k/entropy instead of reinforcing them, which would understate the
  composite's sensitivity to concentration without being obviously wrong in
  the output — this is the failure mode most likely to slip through review.
- **Option C (PCA):** sign-flip before fitting, not after. PCA loadings on
  a mixed-direction input are not just wrong in sign — the component
  itself may load onto whichever subset of measures numerically dominates,
  producing a "first principal component" that doesn't cleanly represent
  concentration in either direction.

## Risk concentration and dependence concentration (candidate additional dimensions)

Neither is yet implemented in `src/concentration/measures.py`. Both share a
single, non-obvious estimation problem (below) that must be decided before
either is coded — this is the same kind of "decide before implementing"
issue as the return-space tautology above, not a detail to leave to whoever
writes the function.

### Covariance/correlation estimation caveat (applies to both)

Both measures below require an estimated return covariance or correlation
matrix `Σ_t` over a rolling window `W_t` ending at date `t`, computed across
the constituent universe (or a subset of it — see recommendation). This runs
into the classic **T-vs-N problem**: if the window length `T` (e.g. the
60-90 trading days already proposed elsewhere in this document for other
rolling measures) is smaller than the number of names `N` (~500 for the
full S&P 500 universe), the sample covariance matrix is not even invertible
and has structurally zero eigenvalues; even once `T` modestly exceeds `N`,
the largest eigenvalues remain heavily noise-inflated relative to their true
values. This is a well-documented random matrix theory result (Laloux,
Cizeau, Bouchaud and Potters, 1999; Plerou, Gopikrishnan, Rosenow, Amaral and
Stanley, 1999 — both in `Papers/`, both cited by Tasitsiomi and Noguer i
Alonso's literature review as the reason "return-space diagnostics" were
proposed as an alternative in the first place). Skipping this caveat would
mean the dependence-concentration eigenvalue share, in particular, is mostly
measuring estimation noise rather than genuine co-movement.

**Recommendation:** do not estimate `Σ_t` on the full ~500-name universe with
a short rolling window. Instead:
1. Restrict covariance/correlation estimation to a fixed, point-in-time
   subset (e.g. the top 100 names by weight, selected per the top-k subset
   selection and reselection convention above — anchored at `t`, refreshed
   monthly, not re-selected at the window's start) — the long tail of small
   names contributes negligible risk or eigenvalue structure and including
   it only worsens the `T`-vs-`N` ratio.
2. Apply Ledoit-Wolf shrinkage (Ledoit and Wolf, 2004, "Honey, I Shrunk the
   Sample Covariance Matrix" — also cited by the same paper's literature
   review) on top of that subset, blending the sample covariance with a
   structured shrinkage target, rather than using the raw sample covariance
   matrix directly.
3. Treat a full DCC (Dynamic Conditional Correlation) model — the "eventuale"
   extension the thesis guida mentions — as a phase-6 robustness variant,
   not the first-pass implementation, consistent with how PCA and
   Markov-switching are already deferred elsewhere in this document. DCC is
   normally fit on a small number of series, so a large-N version would
   itself need the same top-100-subset treatment as above.

This same subset and window choice should be reused for both measures below,
so that risk concentration and dependence concentration are computed from
the *same* estimated `Σ_t`, not two independently-chosen estimation windows —
otherwise any difference between the two series could be an artifact of
different covariance estimates rather than a genuine conceptual difference.

### Risk concentration (variance-share)

Definition follows Tasitsiomi and Noguer i Alonso's formalization directly
(their Section 3.2, "risk concentration"), since it is already precise and
there is no reason to re-derive it. Let `Σ_t` be the covariance matrix
estimated as above, and `w_t` the point-in-time weight vector restricted to
the same subset. Define ex-ante risk shares

```
p_i,t = w_i,t * (Σ_t w_t)_i / (w_t' Σ_t w_t),      sum_i p_i,t = 1
```

i.e. each name's Euler contribution to total portfolio variance, normalized
to sum to 1. From this, define two companion statistics — deliberately
paired with the existing capital-concentration measures so the collinearity
check below has a clean like-for-like comparison:

- **risk_share_topk,t** = `sum_{i in topk-by-weight} p_i,t` — the fraction of
  total variance generated by the *same* top-k cohort (k=5,7,10, matching
  the return-space and CR-k cutoffs) used elsewhere, answering "this cohort
  holds X% of the weight — does it also generate X% of the risk, more, or
  less?" directly.
- **N_eff_risk,t** = `1 / sum_i p_i,t^2` — a risk-space analogue of
  `effective_n`, over the full estimation subset, not just the top-k.

Both are logged the same way as the other candidate components.

### Dependence concentration (eigenvalue share)

Over the same window and subset, compute the **correlation** matrix (not
covariance) of constituent returns — correlation is used deliberately here,
not covariance, so the measure captures comovement structure specifically
and is not contaminated by pure volatility-level changes, which risk
concentration and the physical-risk phase already capture separately.
Extract its eigenvalues `λ_1,t ≥ λ_2,t ≥ ... ≥ λ_N,t` and define

```
dependence_concentration_t = λ_1,t / sum_i λ_i,t
```

the share of total cross-sectional variation explained by the first
principal component — the standard "market mode strength" diagnostic. As a
simpler cross-check (not a replacement), also report the average pairwise
correlation from the same matrix: for a matrix close to equicorrelation,
`λ_1/N` approximates the average correlation, so the two should move
together; a divergence between them is itself worth flagging rather than
silently resolving, since it usually means the correlation structure is not
well described by a single common factor.

**Why this is not redundant with risk concentration despite sharing `Σ_t`:**
dependence concentration is a **symmetric, name-agnostic** property of the
correlation structure — it takes the same value regardless of which specific
names carry the most weight, since it never uses `w_t`. Risk concentration
is explicitly weight-dependent (`p_i,t` scales with `w_i,t`). Concretely: a
uniform rise in all pairwise correlations raises dependence concentration
but leaves risk concentration's `p_i,t` largely unchanged (both numerator and
denominator of `p_i,t` scale together), so the two measures can and should
diverge under that scenario — this is the argument for building both, not
just the more familiar eigenvalue-share measure alone. This is a theoretical
argument for expected distinctness, not a substitute for actually running the
collinearity check below on the two resulting series.

### Collinearity check extension

The mandatory collinearity check (below) must include, in addition to
return-space vs. capital concentration:
- **risk_share_topk vs. CR-k** (same k) — the pair the paper's own Section 4
  argument (weight concentration can be "variance-neutral") predicts may
  still be highly correlated in practice despite being conceptually distinct.
- **dependence_concentration vs. risk_share_topk** — expected to be more
  distinct per the argument above, but only an empirical test confirms it.

## Return-space concentration (candidate additional dimension)

Not yet implemented in `src/concentration/measures.py` — this section defines
it ahead of implementation because its construction has a subtle failure mode
that must be decided before any code is written, not discovered afterward.

**Definition used here:** over a rolling window `W_t` ending at date `t`, let
`R_rest(u)` be the return of the index **recomputed excluding the top-k
constituents**, with the remaining constituents' weights renormalized to sum
to 1, and let `R_topk_eq(u)` be the **equal-weight** return of the top-k
basket. The top-k basket's membership follows the top-k subset selection and
reselection convention above (anchored at `t`, refreshed monthly) — it is
not reselected day-by-day inside `W_t`, for the same reason the covariance
estimation subset below cannot be: a coherent basket return series requires
a fixed, unchanging set of names across the window. Define

```
R_rest(u) = alpha_t + beta_t * R_topk_eq(u) + eta_t(u),   u in W_t
return_space_concentration_t = R2_t(R_rest ~ R_topk_eq)
```

i.e. the R² of regressing the *rest-of-index* return on the top-k basket
return, not the R² of regressing the full index return on the top-k basket.

**Why not regress the full index return (`R_idx`) on the top-k basket, as is
more common in practice:** if `R_idx` is used as the dependent variable, the
top-k constituents' returns are **algebraically embedded** in `R_idx` itself
(`R_idx = sum_i w_i * r_i`, and the top-k names are part of that sum with
their own cap weights). A rolling R² of `R_idx ~ R_topk` is then partly a
mechanical restatement of capital concentration (a higher top-k weight share
`θ` mechanically raises how much of `R_idx`'s variance is literally composed
of top-k returns) rather than independent evidence of return-space dominance.
Regressing on `R_rest` instead removes the top-k names from the dependent
variable entirely, so a high R² can only reflect genuine comovement/spillover
from the top-k cohort onto the remainder of the index, not the trivial fact
that the top-k names are counted on both sides of the regression.

**Precedent checked and found insufficient:** Tasitsiomi and Noguer i Alonso,
*"How Concentrated is the SP500, really?"* (2026, in `Papers/`), define their
return-space concentration index `C_t` as the rolling R² of the *full* index
return (SPY) on an *equal-weight* top-k basket — i.e. `R_idx ~ R_topk_eq`, not
`R_rest ~ R_topk_eq`. Using an equal-weight (rather than cap-weight) basket on
the right-hand side removes sensitivity to which single name inside the
cohort currently carries the most cap weight, but it does **not** remove the
more basic issue that the top-k names are still embedded in their dependent
variable. Their paper defends `C_t`'s independence from weight concentration
only theoretically (Section 4: rising weight concentration can be
"variance-neutral" for the index, so the map from capital concentration to
`C_t` is not one-to-one) and via a placebo test against randomly-drawn
7-stock baskets (Section 6.2.3) — useful as a robustness idea (see collinearity
check below) but not a substitute for excluding the top-k names from the
dependent variable, and not a direct empirical test against a capital
concentration series. No correlation between their `C_t` and HHI/top-k weight
share is reported anywhere in the paper. This project's `R_rest`-based
definition closes that specific gap by construction rather than by argument.

**Worth adapting from that paper regardless of the LHS choice above:**
- The **random-basket placebo test** (regress `R_rest` on many randomly drawn
  equal-weight k-stock baskets from the contemporaneous universe, and report
  where the actual top-k basket's R² ranks against that null distribution) is
  a good additional robustness check — it tests whether the chosen top-k
  cohort is unusual, not just whether *some* cohort explains variance.
- Their **severity-vs-frequency downside decomposition** (regressing
  `min(r_t, 0)` on the concentration measure, then decomposing into a
  frequency channel `1{r_t<0}` and a severity channel `r_t | r_t<0`) is a
  ready-made specification template for testing this project's own H1/H2
  (Chapter 4: does concentration raise the severity of downside outcomes
  rather than their frequency) — cite as precedent when specifying the
  physical-risk regressions in phase 4.

### Choice of k (top-k cutoff)

Build k=5, k=7 (Mag7), and k=10 **in parallel**, all with the identical
definition above (equal-weight basket, regression on `R_rest`, same rolling
window length, same top-k subset selection and reselection convention —
anchored at `t`, refreshed monthly). Do not pick a single primary `k` before
seeing the numbers —
the point of building all three at once is that the choice of `k` is itself
an empirical question, not a modeling preference decided up front:

- A `k` that is too small (e.g. 5) risks being noisy and overly sensitive to
  a single name's idiosyncratic return dominating the equal-weight basket.
- A `k` that is too large (e.g. 10) starts to blur "mega-cap cohort" into
  "generic large-cap subset," diluting the economic interpretation the
  measure is meant to capture.
- The right `k` for this thesis is whichever one is most stable and most
  clearly distinct from capital concentration once the collinearity check
  below is run — so run that check separately for k=5, k=7, and k=10 (each
  against the capital concentration measure computed at the *same* k, e.g.
  return-space-k10 vs CR-10, not against CR-1) before deciding which becomes
  the primary series and which two are retained as robustness variants.

## Collinearity check before aggregation (mandatory step)

Before any aggregation method (Option A/B/C below) is applied, compute the
pairwise correlation (or a simple regression R²) between every candidate
component's time series — most importantly between **return-space
concentration and capital concentration (HHI or top-k weight share)**, since
that is the pair most likely to be near-redundant by construction (see
above). This check is a required, documented step of phase 3, not an
optional robustness idea:

1. Compute each candidate component as its own point-in-time series (same
   rolling/expanding window conventions as the anti-look-ahead rules below,
   and — for any top-k-based component — the same top-k subset selection and
   reselection convention above, so the pairwise comparisons are computed
   against the identical named cohort, not independently-refreshed ones).
2. Report the full pairwise correlation matrix across candidates in
   `outputs/tables/` alongside whichever CSI version is built from them.
3. If any pair exceeds a pre-registered threshold (e.g. |corr| > 0.85 — pick
   and record the actual threshold used, don't leave it implicit), do not
   average both into the composite unchanged. Either (a) orthogonalize the
   more redundant series against the other before standardizing it, or (b)
   demote it to a phase-6 robustness check rather than a primary component —
   and record which option was chosen and why, the same way the aggregation
   method itself is logged.
4. This check must be re-run any time a component's definition changes (e.g.
   if the return-space window length or top-k cutoff changes), since
   collinearity is an empirical property of the specific implementation, not
   a one-time theoretical judgment.

## Collinearity check results and component selection (decided 2026-08-20)

Ran the mandatory check above on the six Phase-2 candidates (`hhi`, `cr_5`,
`cr_7`, `cr_10`, `effective_n`, `entropy_concentration`), monthly,
2000-01 to 2026-07 (`data_final/concentration/concentration_measures_monthly_20260820.csv`,
`src/concentration/collinearity_check.py`). `effective_n` is sign-flipped
(negated) throughout so all six series agree on direction (↑ = more
concentrated) before comparison. Threshold: **|r| > 0.90** (Pearson OR
Spearman) — stricter than the 0.85 placeholder above. Rationale: two of
the six candidates (`hhi`, `effective_n`) are related by mathematical
identity, not empirical correlation (see below), so any reasonable
threshold flags that pair regardless; for the other pairs, 0.90 sets the
bar at "this is functionally the same information," not just "these
usually move together" — a pair at, say, r=0.87 still leaves ~24% of
variance unexplained by the other, which can matter for a variable later
used to condition Phase 4/5 regressions.

**Two bases, not one, computed on purpose.** A levels-only check risked
overstating collinearity: 2000-2026 has a single dominant secular trend
(concentration declining to ~2014, then rising sharply through the Mag7
era). Correlating two long-trending series in levels inflates their
correlation mechanically — they share a common nonstationary component —
independent of whether they actually move together at a shorter,
operationally relevant horizon. First-differencing (month-over-month
change) removes the shared trend and tests genuine short-run comovement.
Both bases are reported below, not one replacing the other, because they
turned out to disagree in an economically informative way (see the
three-cluster reading below) — full tables and the heatmap are in
`outputs/tables/csi_component_correlation_{pearson,spearman}_{levels,diff}_20260820.csv`
and `outputs/figures/csi_component_correlation_levels_vs_diff_20260820.png`.

**Levels** (Pearson above diagonal, Spearman below):

| | hhi | cr_5 | cr_7 | cr_10 | effective_n | entropy |
|---|---|---|---|---|---|---|
| **hhi** | — | 0.99 | 0.99 | 0.98 | 0.96 | 0.95 |
| **cr_5** | 0.98 | — | 0.99 | 0.98 | 0.97 | 0.94 |
| **cr_7** | 0.99 | 0.99 | — | 0.99 | 0.97 | 0.96 |
| **cr_10** | 0.99 | 0.98 | 0.99 | — | 0.96 | 0.97 |
| **effective_n** | 1.00 | 0.98 | 0.99 | 0.99 | — | 0.96 |
| **entropy** | 0.98 | 0.95 | 0.96 | 0.97 | 0.98 | — |

**First differences (MoM change)** (Pearson above diagonal, Spearman below):

| | hhi | cr_5 | cr_7 | cr_10 | effective_n | entropy |
|---|---|---|---|---|---|---|
| **hhi** | — | 0.92 | 0.91 | 0.90 | 0.82 | 0.92 |
| **cr_5** | 0.91 | — | 0.92 | 0.89 | 0.84 | 0.85 |
| **cr_7** | 0.91 | 0.91 | — | 0.95 | 0.83 | 0.88 |
| **cr_10** | 0.90 | 0.87 | 0.92 | — | 0.84 | 0.89 |
| **effective_n** | 0.96 | 0.90 | 0.90 | 0.89 | — | 0.88 |
| **entropy** | 0.94 | 0.83 | 0.85 | 0.86 | 0.92 | — |

**Reading — three clusters, not one undifferentiated block.** All 14 of
the non-deterministic pairs clear 0.90 on levels, which taken alone would
suggest near-total redundancy and argue for Option A. Differencing
changes this picture substantially — several pairs drop below threshold —
and reveals structure:

1. **`hhi` is the hub.** It stays correlated with essentially everything,
   including on differences (0.90-0.94 with every `cr_k` and with
   `entropy`). It doesn't cleanly separate from either the `cr_k` family
   or `entropy` even once the shared trend is removed.
2. **The `cr_k` family is internally redundant, especially at adjacent
   `k`.** `cr_5`/`cr_7` and `cr_7`/`cr_10` stay high on differences
   (0.91-0.95) — adjacent cutoffs share too many constituents to diverge
   short-run. `cr_5`/`cr_10` (the two endpoints) is the one `cr_k` pair
   that drops meaningfully on differences (0.87-0.89) — some real
   short-run distinctness at the extremes, but not enough on its own to
   justify keeping more than one `cr_k` in a parsimonious composite.
3. **`entropy_concentration` carries short-run information the `cr_k`
   family does not.** Its correlation with every `cr_k` falls below 0.90
   on differences (0.83-0.89), a clean drop from 0.94-0.97 in levels —
   the clearest confirmation in this check that entropy captures
   something the top-k cutoffs miss, consistent with the theoretical
   argument for including it in the first place (see "Candidate
   components" above). It stays linked to `hhi` on differences (0.92/0.94)
   — it behaves more like a whole-distribution measure (HHI's family)
   than a top-k-threshold measure.

**`effective_n` is a special case, not a fourth cluster.** In levels its
near-1.0 correlation with `hhi` is not an empirical finding — `effective_n
= 1/hhi` is a deterministic, monotonic transform, so knowing `hhi_t`
determines `effective_n_t` exactly, for every `t`, by construction. The
apparent "divergence" on differences (Pearson drops to 0.82, versus
0.90+ for every other `hhi` pair) is **not genuine new information** —
it is a mechanical artifact of the transform's changing local slope:
since `d(1/x) = -dx/x²`, the same-sized change in `hhi` produces a
change in `effective_n` whose magnitude depends on `hhi`'s *level* at
that moment (large swings in `effective_n` per unit of `Δhhi` when `hhi`
is small, small swings when `hhi` is large). This heteroskedastic,
level-dependent local slope degrades a *linear* correlation measure
(Pearson) on differences without reflecting any real additional
economic content. The diagnostic that confirms this reading:
**Spearman on differences stays at 0.96** — a monotonic transform
preserves rank ordering almost exactly regardless of curvature, which is
exactly what a mechanical-artifact explanation predicts and a
genuine-new-information explanation would not (genuine new information
would degrade the *rank* correlation too, not just the linear one).
**Decision: `effective_n` is excluded from the composite** — including
it alongside `hhi` would double-count the same information with a
weight that implicitly shifts across the sample depending on `hhi`'s
level, without adding real distinctness. It remains a reported
diagnostic (`data_final/concentration/`), valued for its intuitive
"equivalent equal-weight name count" framing, just not a composite input.

## Aggregation choices under consideration

**Option A — single primary measure, others as robustness.**
Use one measure (e.g. HHI) as *the* CSI, and treat CR-k/effective-N/entropy
purely as phase-6 robustness checks (does the P-vs-Q result survive if HHI
is swapped for CR-10?). Simplest to defend, easiest to interpret, but
discards information the other measures capture (e.g. entropy's tail
sensitivity) — and the collinearity check above shows that sensitivity is
real (entropy's differences correlate with `cr_k` at only 0.83-0.89, well
below the redundancy threshold), so Option A alone would throw away a
component demonstrated to carry distinct short-run information, not just
a theoretically-motivated one. **Considered and set aside** for the
primary construction for this reason — kept as the natural robustness
comparison in Phase 6 (does the P-vs-Q result survive collapsing the CSI
to HHI alone?).

**Option B — z-score average.**
Standardize each measure (using a trailing/expanding window, never the full
sample — see below) and average the standardized scores into one composite.
Straightforward and transparent, but the averaging weights are implicitly
equal across measures unless deliberately chosen otherwise, and equal
weighting is itself an assumption that should be stated, not defaulted
into silently. **Chosen — see decision below.** Equal-weighting is only
safe here because the *input set* was curated first (one component per
cluster identified above) — equal-weighting the full six-candidate set
(or even all three `cr_k`) would let the redundant `cr_k` block
implicitly dominate the composite (three near-duplicate votes vs. one
each for `hhi`/`entropy`), which is exactly the failure mode a naive
"more data is more information" approach to Option B would produce.

**Option C — first principal component.**
Fit PCA on the standardized measures and take the first component as the
CSI. Captures common variation efficiently, but with only ~5 candidate
measures the "first PC" can be unstable/hard to interpret economically, and
re-fitting PCA loadings on an expanding window (required for point-in-time
validity — see below) adds real complexity for a possibly small
interpretability gain over Option A/B. **Considered and deferred to Phase
6.** PCA does not solve the redundancy problem by itself — the first PC
maximizes variance explained, so it would still be pulled toward whatever
block contributes the most shared variance (the `cr_k` family, per the
check above) unless the input set is curated first, exactly as for Option
B. Once curated (the same three components chosen for Option B), PCA is a
natural robustness cross-check on the equal-weight choice, not an
alternative that needs deciding now — reported in Phase 6.

### Decision (2026-08-20)

**Component set:** `hhi`, `cr_10`, `entropy_concentration` — one
representative per cluster identified in the collinearity check above.

- **Why `cr_10` and not `cr_5`/`cr_7` as the `cr_k` representative:**
  `cr_7` is itself the internal hub of the `cr_k` trio (correlated
  0.91-0.95 with *both* `cr_5` and `cr_10` on differences) — the same
  "correlated with everything, therefore least uniquely informative"
  logic that applies to `hhi` among all six. Between the two more
  mutually-distinct endpoints, `cr_10` is preferred over `cr_5` on two
  further grounds: (a) it already has a clean external validation
  (Phase 2, `docs/variable_definitions/cr_k.md` — 37.0% computed vs.
  "over 37%" published, vs. `cr_7`'s messier reconciliation against the
  informally-named "Magnificent 7" basket), and (b) spanning more names
  makes it less sensitive to a single constituent's idiosyncratic
  month-to-month move, more appropriate for a broad systemic-risk state
  variable. `cr_5` and `cr_7` remain in the output as standalone
  diagnostics, not composite inputs.
- **Why `effective_n` is excluded:** see the dedicated discussion above
  — deterministic identity with `hhi` in levels, and its apparent
  differenced-series divergence is a curvature artifact of the `1/x`
  transform (confirmed by differenced Spearman staying at 0.96),
  not genuine new information.
- **Weighting:** equal-weight z-score average (Option B), using a
  trailing/expanding standardization window per the anti-look-ahead rules
  below — safe here specifically because the input set is already
  curated to one component per empirically-distinct cluster.
- **PCA (Option C)** on the same three-component set: deferred to Phase 6
  as a robustness cross-check on the equal-weight choice, not decided now.
- **Alternatives considered:** a two-component composite (`hhi` +
  `entropy_concentration`, dropping any `cr_k`) was the most
  redundancy-minimal option but sacrifices the externally-validated,
  literature-standard top-k number; dropping `hhi` entirely (`cr_10` +
  `entropy_concentration`, on the grounds that `hhi` is the most
  cross-correlated component of all six, even more than any single
  `cr_k`) was judged statistically defensible but a poor choice for
  thesis exposition, since HHI is the most standard, most expected
  concentration measure for a reader/committee. Both are noted here so
  the choice of `hhi + cr_10 + entropy_concentration` is traceable
  against its alternatives, not just asserted.

## State / regime classification

The CSI is a *state* variable, so its continuous value must also map to a
discrete classification (e.g. low / medium / high concentration). Candidates:

- **Fixed absolute thresholds** — simplest, but arbitrary unless anchored to
  an economically meaningful benchmark (e.g. a specific historical episode).
- **Trailing-quantile thresholds** — e.g. top/bottom tercile of the CSI's
  own trailing distribution as of each date. Point-in-time safe by
  construction if the trailing window is respected. Preferred default.
- **Regime-switching (Markov-switching) model** — lets the data determine
  regime boundaries and transition dynamics jointly, at the cost of a much
  more complex estimation step and its own point-in-time subtleties
  (the model must be re-fit or filtered on an expanding basis, not
  smoothed with the full sample, or its regime labels leak future
  information — see below).

**Recommendation:** trailing-quantile thresholds for the first pass, for
the same reason as Option A above — get something point-in-time-correct
and usable quickly, treat the Markov-switching alternative as phase-6
robustness.

### Decision (2026-08-20)

**Thresholds:** terciles (33rd/67th percentile) — 3 regimes (low/medium/
high), not a 2-way median split or asymmetric/tail-only cutoffs (e.g.
20th/80th). A median split maximizes per-regime sample size but can't
distinguish "moderately elevated" from "extreme," which matters for a
thesis specifically about systemic-risk episodes. Asymmetric tail
thresholds implicitly assume only the high tail is economically
interesting, an assumption not yet tested against the Phase 4/5
regressions — premature to bake into the classification itself. Terciles
are the standard choice in the regime/systemic-risk literature and keep
both options open. Median split and asymmetric thresholds are documented
here as considered alternatives, deferred to Phase 6 robustness.

**Window: rolling 60 months, not expanding — a different choice from the
composite's own z-score, deliberately.** The composite's expanding
window was chosen because its job was scale-normalization, indifferent
to trailing-vs-expanding. Regime classification asks a different
question — "is this month unusual relative to *recent* conditions," not
"relative to the whole sample since 2000" — and an expanding
classification on a series with CSI's persistent secular trend (declining
to ~2014, then rising sharply through the Mag7 era) would make "high
regime" nearly synonymous with "post-2019," which is a poor conditioning
variable for Phase 4/6 regressions: if the regime dummy is almost
collinear with calendar time, it becomes hard to attribute any P-vs-Q
result to concentration specifically rather than to whatever else changed
after 2019. A 60-month rolling window produces genuine transitions in and
out of "high" over time (visible in the sanity-check plot below), giving
the regime label real time-series variation to identify against. 60
months also reuses the length already flagged as a Phase-6 rolling-window
candidate for the composite itself (see above), rather than introducing a
third arbitrary window length into this document.

**Burn-in and GFC coverage (verified 2026-08-20).** The rolling window
needs 60 CSI observations before the first tercile cutoff is defined; the
CSI series itself starts 2001-12 (its own 24-month burn-in), so the first
defined regime is **2006-11-30** — 2001-12 through 2006-10 (59 months)
have no regime label, excluded rather than backfilled, per the
anti-look-ahead rules below. Checked explicitly against the GFC window
(2007-12 to 2009-06, the same NBER dates used throughout this project's
sanity checks): **every GFC month has a defined regime**, with roughly 13
months of margin between the end of burn-in and the start of the GFC —
the burn-in choice does not compromise coverage of this project's primary
reference stress episode. `src/csi/classify_regime.py` logs this check on
every run and fails loudly (not silently) if a future re-pull or
parameter change ever pushes burn-in past 2007-12.

**Distribution is not a balanced 33/33/33 split, and that's expected, not
a bug.** Across the 237 defined months: **high=149 (63%), medium=50
(21%), low=38 (16%)** — see
`data_final/csi/csi_regime_monthly_20260820.csv`,
`outputs/figures/csi_regime_sanity_check_20260820.png`. This is a known
property of trailing-quantile classification on a persistently trending
series, not a computation error: because the rolling window at date `t`
includes `t` itself, and CSI has spent most of the post-2006 sample on a
multi-year upward trajectory (with only a sustained multi-year dip around
2013-2015), a given month is disproportionately likely to sit in the
upper tercile *of its own trailing window* whenever the series has been
rising over the preceding ~5 years — in the limiting case of a purely
monotonically rising series, every point is the maximum of its own
window, so "high" would approach 100% by construction, not 33%. The
tercile balance is only guaranteed to hold *within* any fixed 60-month
window at a single point in time, not across the full classified series
once the series has genuine multi-year momentum. This does not
invalidate the classification — "high" here correctly means "elevated
relative to the trailing 5 years," which is exactly the question this
window choice was designed to ask (see above) — but the resulting label
proportions should not be read as a balanced 3-way split, and this
imbalance is itself indirect confirmation of how persistent the
2019-2026 concentration trend has been.

**Hysteresis: none in this first pass.** Raw threshold crossing, no
buffer band or minimum-duration smoothing. `classify_regime.py` logs a
flickering diagnostic (quick round-trip transitions, regime returns to
its prior value within 2 months) on every run rather than assuming
hysteresis is or isn't needed: the 2026-08-20 build found **7 flicker
events out of 237 defined months (~3%)**, clustered mainly around 2007,
2010-2011 (European sovereign debt stress), 2016, and 2025-2026 — low
enough that a hysteresis band is not obviously required, but the
diagnostic is logged every run specifically so this is an empirical
call, not a guess, and so a Phase-6 hysteresis-band or Markov-switching
revisit (both already noted as candidates above) has real data to react
to rather than a hypothetical concern.

## Anti-look-ahead rules

These apply no matter which aggregation and state-classification options
above are chosen. `concentration-builder` and `data-validator` should both
check every new CSI version against this list.

1. **Any normalization statistic (mean/std for z-scoring, PCA loadings,
   quantile cutoffs) used at date *t* must be computed using only data
   available as of date *t*** — a trailing or expanding window ending at
   *t*, never the full sample applied backward. This is the single most
   common way a constructed index accidentally leaks the future into the
   past.
2. **A minimum trailing history (burn-in) is required before the CSI is
   defined.** Dates before enough trailing history exists to compute a
   stable window statistic are excluded from the CSI series entirely, not
   backfilled with a full-sample statistic. The burn-in length is itself a
   parameter to record here once chosen (function of window length used
   for normalization/thresholds).
3. **Membership/weight revisions must not leak backward.** The constituent
   panel from `src/universe/build_constituent_panel.py` is already
   point-in-time by construction (membership intervals, not current
   snapshot); the CSI must consume that panel as-is and must not use any
   later restatement of a weight or membership interval when computing an
   earlier date's CSI value.
4. **If PCA or a regime-switching model is used, parameters must be
   re-estimated on an expanding (or rolling) window and applied
   out-of-sample to date *t*.** Fitting once on the full sample and
   applying the result to every historical date is exactly the kind of
   look-ahead this thesis's P-vs-Q comparison cannot tolerate — a CSI that
   "knows" the full-sample distribution of concentration would make any
   predictive claim about phase-4/phase-5 risk circular.
5. **Every CSI version is logged with its construction parameters**
   (aggregation method, window lengths, threshold method) in
   `outputs/logs/` when built, and any result that cites the CSI states
   which version it used. Treat CSI versions as immutable once used in a
   downstream result, the same way `data_raw/` files are immutable —
   don't overwrite a CSI file that a phase-4/5/6 result already depends on.
