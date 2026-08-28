# External review — 2026-08-24

Status: **reasoning recorded, no action taken yet.** This note documents
an external supervisory review received 2026-08-24, after Phase 3 closed
(CSI as a capital-concentration-only composite) and the first two Phase 4
models ran (continuous CSI null on 1-month realized vol; regime model
marginal, `beta_high` p≈0.06). It exists so the reasoning behind two
open decisions is traceable later, not lost in chat history. Nothing in
`src/` or Chapter One has been changed as a result of this review yet —
see "What this note does not do" at the end.

## 1. Gap identified: Chapter One vs. the actual CSI pipeline

Chapter One presents the CSI as a **four-dimensional** object — capital,
risk, return-space, and dependence concentration (paragraphs 9-15, and
paragraph 31: "The CSI explicitly separates capital concentration, risk
concentration, return-space concentration, and dependence concentration").

The construction actually decided and implemented so far
(`csi_construction.md`, "Decision (2026-08-20)") is:

```
csi_t = mean(z_hhi,t, z_cr_10,t, z_entropy_concentration,t)
```

— three components, all three **capital concentration** measures (weight-
based; no covariance or comovement information enters). Risk concentration
and dependence concentration are already specified conceptually in
`csi_construction.md` (including the hard parts: the T-vs-N caveat, the
top-100 point-in-time subset, Ledoit-Wolf shrinkage) but **not
implemented** in `src/concentration/measures.py`. Return-space
concentration is defined but likewise not implemented.

So the CSI as it stands today is, in substance, exactly the kind of
weights-only object Chapter One's own motivation (paragraphs 4 and 9)
argues is insufficient for systemic-risk analysis ("weight-based
statistics are useful as a starting point... but they are not sufficient
to characterize the economic implications of concentration"). This is not
a claim that the three-component composite is poorly built — the
collinearity check behind it (levels vs. differences, the `effective_n`
identity handling) is careful, documented work — only that it is one
dimension, not four, while the introductory chapter currently reads as if
all four already exist.

## 2. Decision: complete the CSI, don't just reword the chapter now

**Decision (2026-08-24):** do not treat this gap as a credibility problem
to patch in the text immediately. No reviewer/committee member will read
the work before final submission, so there is no near-term audience for
whom the mismatch is currently live. Instead:

- The goal is to **actually complete the CSI to four dimensions** before
  the thesis is finalized — build risk concentration and, time
  permitting, dependence concentration and return-space concentration,
  reusing the design already worked out in `csi_construction.md` rather
  than re-deriving it.
- Chapter One's text will be **synchronized with the real pipeline only
  at the end**, once it is known which dimensions were actually built and
  successfully aggregated into the composite. Rewriting the chapter now,
  before knowing the final component set, risks a second rewrite later or
  text that undersells what eventually gets built.
- This means the four-dimensional framing in Chapter One is currently an
  aspirational description of the target, not a description of the
  current artifact, and is being carried as such deliberately — not an
  oversight.

**Trade-off, stated explicitly:** this defers a real inconsistency rather
than resolving it immediately. If time runs out before risk/return-space/
dependence concentration are built, Chapter One will need the "align text
with pipeline" edit anyway (Recommendation 1 from the 2026-08-23 review),
just later and under more time pressure. The decision to defer is a bet
that implementation time is better spent now than editing time, given no
external reader sees the gap in the meantime.

## 3. Open identification risk: detrending vs. genuine non-linearity in Phase 4

Model 1 (continuous CSI, expanding-window z-score) and Model 2 (regime
dummies, rolling 60-month tercile classification) currently differ along
**two** dimensions at once: continuous → discrete, *and* expanding window
→ rolling window. `p_measures.md` currently reads Model 2 outperforming
Model 1 (p≈0.06 vs. p=0.68 on `beta_high`/`csi_t` respectively) as
evidence of non-linearity ("the nonlinear/regime specification is telling
a materially different... story"). That is not yet established — the
regime series is relative to its own trailing 5-year window by
construction (i.e., already detrended), while the continuous CSI's
expanding z-score is not (it is standardized against the full sample
history, and the CSI series itself has a documented "pronounced secular
trend" — `csi_construction.md`). The performance gap between the two
models could equally be a **detrending** effect rather than a
**non-linearity** effect, and the current setup cannot distinguish the
two because it changes both things simultaneously.

**Test proposed, not yet run:** construct a detrended continuous CSI —
either `csi_t - rolling_mean_60m(csi_t)` or a rank-percentile computed
over the same rolling 60-month window used by `classify_regime.py` — and
re-estimate Model 1 with that series in place of the raw expanding
z-score, holding everything else (dependent variable, `RV_t` control, HAC
lags) fixed. If the coefficient becomes meaningfully significant once
detrended, the story is "CSI predicts vol once the shared trend is
removed," which motivates rebuilding the composite itself on a rolling
basis (already listed as a Phase-6 robustness variant in `csi.md`) ahead
of other extensions. If it stays null even detrended, the "genuine
non-linearity / regime specification" reading in `p_measures.md` is
better supported, and the priority shifts toward the dependent-variable
extensions instead.

## 4. Priority ordering for what comes next

Agreed ordering, reasoning included so it doesn't need to be
re-derived later:

1. **Resolve the detrending/non-linearity ambiguity on the existing
   P-measure result first** (Section 3 above) — cheap (reuses existing
   data and regression scaffolding), and its outcome changes which of the
   next two items is actually the right next step rather than a guess.
2. **Then evaluate cross-sectional dispersion / downside-tail severity as
   the primary test of RQ2**, ahead of further iteration on mean realized
   volatility. Chapter One's own theory (paragraphs 6, 28) predicts the
   effect should show up in tail/dispersion objects, not the mean — RV was
   always a weaker-prior test of the thesis's actual claim, so it should
   not anchor the interpretation before the tail-focused specifications
   have been run.
3. **In parallel or after that, build risk concentration as the CSI's
   fourth dimension**, reusing the top-100 subset + Ledoit-Wolf design
   already specified in `csi_construction.md` rather than redesigning it.
   Chosen over dependence concentration as the next build target because
   it shares the same estimated `Σ_t` needed anyway and is the cheaper of
   the two remaining dimensions to add first.

## What this note does not do

- Does not change Chapter One's text — the four-dimension framing there
  is left as-is, deliberately, per the decision in Section 2.
- Does not implement risk concentration, return-space concentration, or
  the detrended-CSI test — all three are next steps, not actioned here.
- Does not change `src/csi/build_csi.py`, `classify_regime.py`, or either
  Phase 4 regression script.

Cross-references: `docs/methodology_notes/csi_construction.md` (component
selection, the risk/dependence concentration design not yet built),
`docs/methodology_notes/p_measures.md` (Phase 4 Model 1/Model 2 results
this review reacts to), `docs/variable_definitions/csi.md` (expanding vs.
rolling standardization trade-off referenced in Section 3).
