# CSI construction methodology

Status: **draft — aggregation method not yet finalized.** This note
documents the candidate components and the decision that still needs to be
made, plus the anti-look-ahead rules that apply regardless of which
aggregation method is chosen. Update this file the moment the aggregation
method is decided, and again if it changes — every downstream P-measure and
Q-measure result will cite a CSI version, and that version is defined by
this document.

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

## Candidate components

All computed in `src/concentration/measures.py` on the constituent weights
panel from `src/universe/build_constituent_panel.py`:

| Measure | Function | Direction | Captures |
|---|---|---|---|
| HHI | `herfindahl_index` | ↑ = more concentrated | Overall dispersion of index weight; standard concentration benchmark |
| CR-1, CR-5, CR-10, CR-20 | `concentration_ratio` | ↑ = more concentrated | Weight held by the largest 1/5/10/20 names specifically — more sensitive to mega-cap dominance than HHI |
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

## Aggregation choices under consideration

**Option A — single primary measure, others as robustness.**
Use one measure (e.g. HHI) as *the* CSI, and treat CR-k/effective-N/entropy
purely as phase-6 robustness checks (does the P-vs-Q result survive if HHI
is swapped for CR-10?). Simplest to defend, easiest to interpret, but
discards information the other measures capture (e.g. entropy's tail
sensitivity).

**Option B — z-score average.**
Standardize each measure (using a trailing/expanding window, never the full
sample — see below) and average the standardized scores into one composite.
Straightforward and transparent, but the averaging weights are implicitly
equal across measures unless deliberately chosen otherwise, and equal
weighting is itself an assumption that should be stated, not defaulted
into silently.

**Option C — first principal component.**
Fit PCA on the standardized measures and take the first component as the
CSI. Captures common variation efficiently, but with only ~5 candidate
measures the "first PC" can be unstable/hard to interpret economically, and
re-fitting PCA loadings on an expanding window (required for point-in-time
validity — see below) adds real complexity for a possibly small
interpretability gain over Option A/B. Worth reporting as a robustness
cross-check even if not chosen as the primary construction method.

**Recommendation for the first implementation pass:** build Option A (HHI
as the primary CSI) first, since it is the simplest to get point-in-time
correct and gives phase 4/5 something concrete to condition on immediately.
Implement Option B as the first robustness variant once phase 6 exists.
Revisit Option C only if A and B disagree in a way that matters for the
thesis's conclusion.

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
