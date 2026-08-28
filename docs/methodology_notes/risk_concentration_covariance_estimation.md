# Risk-concentration covariance estimation (Sigma_t) — design and decisions

Status: **implemented (2026-08-24)**. This is the dedicated design note for
`src/concentration/covariance_estimation.py`, referenced from
`docs/methodology_notes/csi_construction.md`'s "Risk concentration"
section rather than folded into it — the estimator design has enough
content of its own (window, subset, shrinkage target, point-in-time
handling of recent index entrants) to warrant its own file, the same way
`index_weight_construction.md` and `membership_interval_convention.md` are
split out from `csi_construction.md` rather than inlined.

`Sigma_t` estimated here is meant to be **reused as-is** by a future
dependence-concentration build (the eigenvalue-share dimension) — see
`csi_construction.md`'s explicit instruction not to use two independently-
chosen estimation windows for the two measures. Nothing below is specific
to risk concentration; `src/concentration/risk_measures.py` is the only
risk-concentration-specific code that consumes this module's output.

## 1. Estimation window: 252 trading days (rolling), not the 60-90 day placeholder

`csi_construction.md` mentions "60-90 trading days already proposed
elsewhere in this document" only as a loose cross-reference to
return-space concentration's own (never formally decided) window — it is
not a decision that was ever made for Sigma_t specifically, and it does
not carry over here.

**Why not 60-90 days:** with the top-100 subset (below), T=60-90 gives
T/N ≈ 0.6-0.9 — **T < N**. The sample covariance matrix is singular by
construction before any shrinkage is applied; even with Ledoit-Wolf
shrinkage guaranteeing invertibility via the target, the optimal shrinkage
intensity would sit very close to 1 nearly always, meaning the estimate
would mostly reflect the shrinkage target (a constant-correlation
structure) rather than genuine sample information — the opposite of what a
state variable meant to track *changes* in risk structure needs.

**Why this differs from return-space concentration's placeholder:** that
measure's R² regression degrades gracefully with a short window (more
noise, not outright singularity) — it never needs to invert an N×N
matrix. The T-vs-N invertibility failure mode this module exists to avoid
simply does not apply there, so the two measures are allowed to use
different windows despite both starting from the same document.

**Decision: 252 trading days (~12 months), rolling, refreshed monthly.**
Gives T/N ≈ 2.5 with N=100 — a defensible ratio for Ledoit-Wolf shrinkage
(the literature's typical comfort zone), without stretching the window so
long that the measure goes stale relative to the CSI's own monthly
cadence. Alternatives considered:
- **126 days (~6 months):** T/N ≈ 1.26 — still tight, would rely on
  shrinkage more heavily than 252 days does (see the empirical shrinkage
  range below).
- **Expanding window:** rejected for the same reason already argued for
  regime classification in `csi_construction.md` — it would make "high
  risk concentration" increasingly synonymous with the full-sample
  average as the sample grows, near-collinear with calendar time, and a
  poor conditioning variable for Phase 4/6 regressions.
- **Half-life/EWMA:** the Ledoit-Wolf shrinkage-intensity formula (below)
  assumes T i.i.d. observations; combining it with exponential weighting
  requires a different derivation. Deferred to Phase 6, consistent with
  how DCC is already deferred there for the same reason (this document's
  own "Covariance/correlation estimation caveat" section).

**Burn-in and GFC coverage (verified 2026-08-24).** The trailing window
needs 252 trading days of history before the first Sigma_t is defined;
the panel starts 2000-01-03, so the first defined monthly observation is
**2000-12-29** (11 of the 319 capital-concentration months are excluded by
this burn-in). Checked against the GFC window (2007-12 to 2009-06, the
same NBER dates used throughout this project's sanity checks): **all 19
GFC months have a defined observation** — burn-in ends nearly 7 years
before the GFC starts, no coverage risk there.

## 2. Subset: top-100 by weight, point-in-time anchored, monthly-fixed

Confirms `csi_construction.md`'s original recommendation, using the
already-frozen global top-k/top-N convention (anchor at each calendar
month's first available trading date, held fixed for the whole month) —
the same convention `build_concentration_panel.py` already applies to
`cr_5`/`cr_7`/`cr_10`.

- **Top-500 (full universe):** rejected outright — no window length keeps
  T/N in a workable range without making the window multi-year, which
  contradicts the "current state" framing of a state variable, and the
  long tail of small names contributes negligible risk/eigenvalue
  structure anyway.
- **Top-200:** T/N ≈ 1.26 at the chosen 252-day window — too tight.
- **Top-100 (chosen):** T/N ≈ 2.5.
- **Top-50:** T/N ≈ 5, statistically the most comfortable, but rejected —
  a subset this small would make `risk_share_topk`/`N_eff_risk`
  mechanically close to capital concentration (little daylight between
  "who's in the subset" and "who's in the top-k cohort"), undermining the
  entire point of building a distinct risk-space measure. The cross-
  dimension collinearity check below confirms top-100 already keeps
  enough distance from capital concentration on short-run (differenced)
  comovement; a top-50 subset would likely erode that margin further.

### Point-in-time handling of recent index entrants (found empirically, not anticipated in `csi_construction.md`)

`src/universe/build_constituent_panel.py` only retains a return
observation while a permno is an **actual index constituent** — a name
that joins the S&P 500 mid-sample has no earlier row here, regardless of
its real pre-entry trading history. Combined with a 252-day window, this
means a newly-added mega-cap name can be a nominal top-100 (even top-5)
member by weight immediately, while lacking the return history needed to
enter Sigma_t for up to ~12 months after joining.

**Confirmed concretely in this build:** permno 93436 (Tesla, S&P 500
entry effective 2020-12-21) is excluded from Sigma_t for insufficient
history in every month from 2021-01 through 2021-11 (11 consecutive
months) despite being a top-5/top-7/top-10 weight cohort member throughout
— resolving exactly once ~252 trading days have accumulated since its
2020-12 entry. The same pattern recurs for other permnos at smaller scale
around later reconstitution dates (2023-11 to 2024-08, 2024-12 to
2026-07) — see `outputs/logs/build_risk_concentration_panel_20260824.txt`
for the full attrition log.

**Decision: complete-case exclusion, not pairwise imputation.** A name
without a full, no-NaN return series across the entire 252-day window is
dropped from that month's Sigma_t entirely (logged as "topk-cohort
attrition" whenever the dropped name also sits in the `cr_5`/`cr_7`/
`cr_10`-comparable top-k cohort). Rejected alternative: pairwise-complete
covariance (using whatever overlapping history exists per pair) — not
used, because a pairwise-complete covariance matrix is not guaranteed
positive semi-definite, which would break the Ledoit-Wolf shrinkage
target's assumptions and could silently produce an uninvertible or
nonsensical "shrunk" matrix.

**Empirical impact:** `n_subset_included` ranges 95-100 (median 99) across
the 308 defined months — the exclusion is a minor, well-understood
correction, not a structural data problem. Weight-side attrition (a name
present in Sigma_t losing its weight observation exactly at month-end,
e.g. a delisting) occurred zero times in this build.

### Multi-share-class entities (GOOGL/GOOG) — reviewed decision (implemented 2026-08-24, confirmed after empirical review 2026-08-25)

**Decision: permnos kept separate, no aggregation in production code.**
Reached in two passes — an initial (2026-08-24) recommendation on
analogy grounds alone, and a follow-up empirical review (2026-08-25)
requested before approval, which changed what evidence backs the
decision (see "What changed between the two passes" below) without
changing the decision itself.

**What the original capital-concentration precedent actually says.**
`docs/variable_definitions/cr_k.md` addresses this same GOOGL/GOOG pair,
quoted verbatim (its "External cross-check (2026-08-20)" section):

> "2. **Alphabet's two share classes (GOOGL + GOOG) both count as
> separate top-7 slots** in this build (correct per this project's
> sharetype filter — both are `NS`, both genuinely separate index
> constituents, confirmed with the user 2026-08-19), consuming two of
> the seven slots for one company, whereas the popular "Magnificent 7"
> counts Alphabet once."

**Confirmed: that note contains no discussion of covariance, correlation,
matrix conditioning, or shrinkage** (checked by direct search of the
file's full text — zero matches for any of those terms). It resolves an
external-benchmark discrepancy (this build's CR-7 vs. the commonly-cited
"Magnificent 7" weight) by appeal to the index's own membership
definition ("both genuinely separate index constituents"), not by
weighing alternative treatments against a covariance-estimation cost —
because none existed yet: risk concentration did not exist when that note
was written. Reusing it here as a coherence argument is therefore a
**design-consistency** argument only, not a transferred empirical result.

**Which pairs are actually at stake (checked directly against the panel,
not assumed):** of six multi-share-class companies present in the raw
CRSP names file (permco groupings) with both classes appearing in
`data_final/universe/` — Alphabet, Discovery, Under Armour, News Corp,
Fox Corp, Comcast — **only Alphabet (GOOG/GOOGL) ever has both classes
inside the top-100 subset simultaneously, in any month of the 2000-2026
sample** (147 of 147 months where both are in the panel; the other five
pairs: 0 of 92/74/130/88/3 months respectively). This is a single-name
issue, not a pervasive one.

**The channel risk concentration adds that CR-k never had:** two
near-duplicate return columns (GOOG/GOOGL correlate at 0.992-0.998 over
the trailing 252-day window, essentially throughout the sample) affect
the sample average pairwise correlation used as the Ledoit-Wolf
constant-correlation target, and therefore potentially the shrinkage
intensity applied to the *entire* 100-name matrix, not just to Alphabet's
own risk share. This channel cannot exist in a weights-only measure like
CR-k, since no covariance matrix is ever estimated there.

**Full-sample empirical test (2026-08-25 — supersedes an earlier
17-month check).** The 2026-08-24 answer to this question used a
17-month sample deliberately built from two mixed criteria — 12 months
spread arbitrarily across different years, plus the 5 months of highest
GOOG/GOOGL correlation in the entire dataset — and reported "mean absolute
delta 0.32 percentage points" without qualifying that this was a
convenience/extreme-correlation sample, not the full population. Reviewed
and corrected: the check below now covers **all 147 months** where both
GOOG and GOOGL sit in the top-100 subset (the complete relevant
population, not a selected subsample), comparing production
(`shrinkage_intensity` already in
`data_final/concentration/risk_concentration_measures_monthly_20260824.csv`)
against an ad-hoc Alphabet-merged re-run (same unmodified
`covariance_estimation`/`risk_measures` functions, no production code
changed):

| | mean (pp) | median (pp) | std (pp) | min (pp) | max (pp) | sign split (+/−) |
|---|---|---|---|---|---|---|
| Merge Alphabet, keep N=100 (realistic comparison) | −0.062 | +0.050 | 0.79 | **−6.83** | +1.15 | 89 / 58 |
| Merge Alphabet, hold the OTHER 99 names fixed (isolates just the merge) | +0.046 | −0.010 | 0.22 | −0.36 | +0.76 | 63 / 83 |

The full-sample check surfaces a **-6.83 percentage-point outlier
(2020-06)** that the 17-month convenience sample missed entirely (its own
max magnitude was 1.49pp) — the 2026-08-24 answer's "trascurabile" framing
was too confident given what it had actually checked. This is exactly
what qualifying "mean over which sample" as requested prevents from
happening silently.

**Why the sign (and the outlier's size) varies — mechanism, not noise
alone.** Merging GOOG+GOOGL into one row frees one top-100 slot, which is
then filled by whichever name is now ranked 100th by weight — a different
name than in the separate-permno case. The "realistic" row above bundles
**two effects**: (i) the Alphabet redundancy itself, and (ii) an
unrelated substitution of one marginal (100th-ranked) name for another.
The second row isolates effect (i) alone, by holding the exact same
99-name non-Alphabet set fixed in both scenarios (adding the merged
Alphabet row as name #100 in both, so no marginal-name substitution
occurs). Isolating it this way **shrinks the effect by roughly 3-4x** (std
0.79pp -> 0.22pp, max magnitude 6.83pp -> 0.76pp) and explains the
outlier directly: at 2020-06-30, the realistic comparison shows -6.83pp,
but the isolated comparison for the same month is only -0.16pp — almost
the entire outlier is the marginal 100th-ranked name swap (plausibly a
high-volatility 2020 reopening-trade name entering the subset), not
Alphabet's redundancy.

**Statistical test of the isolated sign split (2026-08-25, requested
before closing this decision — not run in the original 2026-08-24 pass,
which reported the sign split without a formal test):**

| Test | Result | Significant? |
|---|---|---|
| Binomial sign test, all 147 months (63 pos / 83 neg) | p = 0.116 | No |
| One-sample t-test on the mean (all 147 months) | mean +0.046pp, t = 2.52, p = 0.013 | Yes |
| Wilcoxon signed-rank (robust to skew/outliers), all 147 months | p = 0.410 | No |

**Statistical significance is not the same question as economic
relevance, and both are answered separately here.** The p = 0.0072 result
below (sign test excluding 2018) is a real, statistically detectable
directional tendency — not a coin flip. But every annual mean shrinkage
delta, in every year including 2018 (the most extreme), stays **under
0.6 percentage points** on an intensity scale that itself ranges roughly
0.08-1.00. That is an order of magnitude smaller than the previously-
measured final effect on the measures that matter for this decision
(`n_eff_risk` -2.3% to -6.9%, `risk_share_top10` +0.6% to +3.9%, both
whole percentage points, not fractions of one). A statistically real
effect of economically trivial size does not change the trascurabilità
conclusion — the two questions ("is this distinguishable from zero" and
"is this large enough to matter") have different answers here, and both
are reported rather than letting the first stand in for the second.

These three disagree because **2018 is a distinct sub-period, not
noise**: all 12 months of 2018 have a positive delta (annual mean
+0.59pp, std only 0.11 — far tighter than the full-sample std of
0.22pp), driving the t-test's significance almost entirely. **Excluding
2018:** mean drops to -0.0024pp (t-test p = 0.857 — no longer
significant), but the sign test on the remaining 135 months becomes
**significant** (51 positive / 83 negative, p = 0.0072) — a genuine,
small-magnitude, statistically real tendency toward *less* shrinkage when
the redundant pair is merged, once 2018's anomalous cluster is set aside.

**Investigated the 2018 pattern directly rather than leaving it as an
unexamined fact (requested before closing this decision):**
- **No Alphabet-specific corporate event found.** Checked GOOG/GOOGL rank,
  weight, and 252-day correlation across 2016-2021: correlation in 2018
  (0.991-0.994) is in the normal-to-high range for the sample, not
  anomalous, and Alphabet's share-class structure (the 2015 holding-
  company reorganization) had no 2018 event associated with it.
- **No panel/reconstitution artifact found.** Top-100 turnover and
  `n_subset_included` in 2018 look ordinary relative to neighboring years
  in the production build log.
- **A partial mechanistic explanation was found and verified directly
  against this project's own data.** Decomposing the Ledoit-Wolf formula
  (`shrinkage = kappa/T`, `kappa = (phi - rho) / gamma`, module docstring
  above) and computing `gamma` — the squared Frobenius distance between
  the sample covariance and the constant-correlation target — for all 147
  months: **2018's mean `gamma` (8.4e-6) is far below the full-sample mean
  (3.3e-5)**, and `gamma` sits in this same low range for the broader
  2014-2019 period, rising sharply from 2020 onward (annual means: 2014
  3e-6, 2015 6e-6, 2016 11e-6, 2017 6e-6, 2018 8e-6, 2019 16e-6, then
  2020-2026 ranging 20e-6 to 96e-6). Correlation between `gamma` and
  `|delta_N99_fixed|` across all 147 months: **-0.27** (moderate, in the
  expected direction — a smaller denominator in `kappa/gamma` mechanically
  amplifies the same-sized perturbation from merging GOOG/GOOGL into a
  larger shrinkage-intensity swing, in whichever direction that
  perturbation happens to point that month).
- **What this does and does not explain, stated honestly:** it accounts
  for why 2014-2019 as a *group* show larger and more variable
  `delta_N99_fixed` magnitudes than 2020-2026 (a moderate, verified
  correlation, not a perfect one), but does **not** fully explain why 2018
  specifically — rather than 2016, another low-`gamma` year with a
  comparably tight annual std (0.073) but the *opposite* sign (mean
  -0.170) — shows this particular direction with this much consistency.
  That residual is **not resolved** and is documented as such, per the
  instruction not to leave an unexamined claim but also not to overstate
  a partial finding as a complete explanation.

**Corrected characterization:** the direction is **not stable across the
full sample** (2018 alone reverses the sign relative to the rest of the
period, and does so consistently, not noisily) — a stronger and more
precise statement than "no systematic pattern," which the 2026-08-24 pass
asserted without running these tests. Once 2018 is excluded, a real but
small directional tendency remains (p = 0.0072, mean magnitude still
under 0.6pp even in 2018, the most extreme annual sub-period). This does
not change the trascurabilità conclusion in magnitude terms — every
annual mean stays under 0.6pp, an order of magnitude below anything that
would move `risk_share_top10`/`n_eff_risk` materially — but the earlier
"no systematic bias" framing is corrected to "small in magnitude
throughout, with a real but economically minor directional component once
a specific 2018 episode is set aside," per the same discipline that
already corrected the 17-month sample's understated range. Per-year
breakdown (`std`, mean) is in the ad-hoc diagnostic underlying this table,
reproducible from `covariance_estimation.estimate_sigma_t` grouped by
calendar year — not persisted to `data_final/`.

**Connecting this back to the previously-measured final effect on the
measures themselves** (n_eff_risk -2.3% to -6.9%, risk_share_top10 +0.6%
to +3.9% relative, separate vs. aggregated — first computed in the
2026-08-25 share-class review, not previously written into any doc file
before this note): the shrinkage channel this section isolates (std
0.22pp on an intensity that ranges roughly 0.08-1.00 across the sample) is
far too small to explain most of that final effect, whether or not the
2018-driven directional component above is counted. The two mechanisms
were checked independently and answer different questions — the final
risk_share_top10/n_eff_risk effect is explained almost entirely by (a) the
mechanical sum-of-squares-splitting identity for n_eff_risk (Euler
contribution math, not covariance estimation) and (b) the
marginal-name-swap-driven cohort recomposition for risk_share_top10 (which
11th name enters/leaves top-10) — not by any shrinkage-intensity
distortion from the redundant pair, which this section now shows is small
on its own terms even where it is statistically detectable.

**Verified consistent across documentation (2026-08-25):** the
n_eff_risk/risk_share_top10 figures above appear in exactly this one
location across `risk_concentration.md`,
`risk_concentration_covariance_estimation.md`, and `csi_construction.md`
(checked by direct search of all three files) — no other version of these
numbers exists elsewhere in the documentation to reconcile.

**Decision, with the two arguments kept separate as required:**
- **Design-consistency argument (a choice, not a measurement):** treating
  risk concentration differently from capital concentration on this point
  would mean the CSI's dimensions no longer share the same top-100/top-10
  entity definition — a comparability cost for the framework, independent
  of any number.
- **Empirical-negligibility argument (a measurement, now checked on the
  full relevant population, not a subsample, WITH formal significance
  tests, not an eyeballed sign split):** the isolated effect of the
  redundant pair on shrinkage intensity is small in magnitude throughout
  (std 0.22pp, max 0.76pp across all 147 months where the question
  arises) — small enough on its own to not matter for this decision
  regardless of direction. Its DIRECTION is not stable across the full
  sample (2018 alone, consistently, reverses the sign found in the rest
  of the period; a real but small residual directional tendency toward
  less shrinkage remains once 2018 is excluded, p = 0.0072) — see the
  statistical test table above. The realistic comparison's much larger,
  erratic range (up to -6.83pp) is separately explained by an unrelated
  marginal-name-substitution confound, not by the redundancy itself.

Both arguments point the same way: **permnos stay separate, no
aggregation in production code.** Documented here as a reviewed decision,
not a default — a materially different check (the full 147-month
population plus the isolation test) than what supported the original
2026-08-24 recommendation, though it reaches the same conclusion.

## 3. Shrinkage: Ledoit-Wolf, constant-correlation target — implemented manually

`csi_construction.md` cites "Ledoit and Wolf, 2004, 'Honey, I Shrunk the
Sample Covariance Matrix'" (Journal of Portfolio Management). Verified
directly: **that specific paper's shrinkage target is the
constant-correlation matrix** (every pairwise correlation shrunk toward
the sample's average pairwise correlation, each name's own variance
preserved on the diagonal) — a *different* paper from the one
`sklearn.covariance.LedoitWolf` implements (Ledoit & Wolf 2004, "A
Well-Conditioned Estimator for Large-Dimensional Covariance Matrices",
Journal of Multivariate Analysis — target = scaled identity matrix).

**Why the target matters here, not just the citation:** shrinking toward
scaled identity compresses each name's own variance toward a common scale
in addition to structuring correlations — for a risk-concentration
measure, where `p_i,t` depends on each name's own variance level as well
as its comovement with the rest of the subset, that would blunt exactly
the individual-risk-level information the measure needs to keep. The
constant-correlation target leaves the diagonal (individual variances)
untouched and shrinks only the correlation structure — the economically
appropriate choice for this use.

**Decision: implemented the constant-correlation-target estimator
directly** (`covariance_estimation.ledoit_wolf_constant_correlation`, a
direct port of the reference `covCor.m` algorithm), rather than adding
`scikit-learn` as a project dependency. Two reasons: (a) `scikit-learn` is
not used anywhere else in this project and was not already a dependency of
the `tesi-wrds` conda environment; (b) even if added, its `LedoitWolf`
class implements the wrong target for this use, so installing it would
not actually resolve the citation match — a manual implementation was
required either way once the target mismatch was identified.

**Alternatives considered/rejected:**
- **Raw sample covariance (no shrinkage):** rejected — singular/unstable
  at this T/N ratio.
- **Identity-target shrinkage (`sklearn.covariance.LedoitWolf`/`OAS`):**
  wrong target for the reasons above; noted as a lower-fidelity fallback
  if manual maintenance of the constant-correlation estimator ever becomes
  a burden, not used here.
- **Single-index/CAPM-target shrinkage (Ledoit & Wolf 2003):** would
  require estimating a market-model beta first, adding an assumption and
  an estimation step. Deferred to Phase 6 as a robustness alternative,
  consistent with how DCC is already deferred there.

**Empirical behavior (verified 2026-08-24, tests in
`tests/test_covariance_estimation.py`):** shrinkage intensity is bounded
in [0, 1] and the resulting Sigma_t is symmetric, positive semi-definite,
and full rank (invertible) even when a given month's window has T < N
after complete-case exclusion. Across the 308 defined months, shrinkage
intensity ranges **0.078 to 1.000 (median 0.243)**. The extremes are
economically interpretable, not artifacts:
- **2020-03 (COVID crash month): shrinkage = 1.000** — the sample
  covariance's estimation noise (extreme daily moves cluster in a single
  month) swamps the target-distance term in the optimal-shrinkage formula,
  saturating at the boundary. A known property of Ledoit-Wolf shrinkage
  under acute volatility, not a bug.
- **2008-10 (Lehman/GFC): shrinkage = 0.588**; **2011-08 (US downgrade /
  European sovereign stress): shrinkage = 0.563** — both recognizable
  stress-episode spikes, well above the sample median.
- Shrinkage falls to its lowest, most stable levels (~0.10-0.15) during
  the 2022-2026 Mag7/AI period — see `outputs/figures/
  risk_concentration_sanity_check_20260824.png`, bottom-but-one panel.

## 4. Point-in-time integrity

Sigma_t at date `t` uses only return observations with `date <= t` (the
trailing window's own construction) and only membership/weight
information already point-in-time-correct from
`src/universe/build_constituent_panel.py` — no rule here differs from the
anti-look-ahead rules already listed in `csi_construction.md`. The subset
anchor date (month-start) and the Sigma_t/weight evaluation date
(month-end) are both always `<=` the date a given monthly observation is
reported for.

## 5. What's implemented vs. deferred

**Implemented (2026-08-24):**
- `select_topN_subset`, `build_return_matrix`, `ledoit_wolf_constant_correlation`,
  `estimate_sigma_t` in `src/concentration/covariance_estimation.py`.
- 252-trading-day rolling window, top-100 subset, monthly refresh,
  complete-case exclusion, constant-correlation Ledoit-Wolf shrinkage.

**Robustness checks planned, not yet run (Phase 6 candidates, consistent
with how PCA/DCC/hysteresis are already deferred elsewhere in this
project):**
- Window length sensitivity (126 days vs. 252 days vs. expanding).
- Subset size sensitivity (top-50 vs. top-100 vs. top-200).
- Shrinkage target sensitivity (identity-target vs. constant-correlation-
  target vs. single-index-target).
- A full cross-product grid of the above was deliberately NOT run for this
  first pass (27 combinations) — only univariate perturbations are
  planned, mirroring this project's "get a point-in-time-correct first
  pass working, treat the full grid as Phase-6 robustness" pattern already
  used for Option A→B→C and expanding-vs-rolling elsewhere in
  `csi_construction.md`.

**Decisions explicitly deferred pending the collinearity-check evidence
(see `docs/variable_definitions/risk_concentration.md`):** whether any
risk-concentration measure enters the composite CSI, and if so, which one
— not decided in this note.
