# entropy_concentration

Status: **decided** (2026-08-20 — confirmed by user after reviewing the
N_t-sensitivity, collinearity-check, and literature-precedent reasoning
below).
`csi_construction.md`'s candidate-components table names this measure and
fixes its direction (↑ = more concentrated) but does not pin down the
exact formula — this document makes that choice explicit and citable, as
required by CLAUDE.md's "every derived variable gets an entry" rule.
Already implemented this way in `src/concentration/measures.py` (pre-dates
this note); this file exists to record *why*.

## Formula

**Normalized Shannon entropy, complemented so higher = more concentrated:**

```
H_t = -Σ_i weight_i,t * ln(weight_i,t)      (Shannon entropy, nats)
entropy_concentration_t = 1 - H_t / ln(N_t)
```

where `N_t` is the number of active constituents at `t`. Equivalently,
`entropy_concentration_t` is one minus **Pielou's evenness index**
(ecology) applied to constituent weights, and is the *normalized* form of
the **Theil entropy index** for market concentration
(`T_t = ln(N_t) - H_t = Σ_i weight_i,t * ln(N_t * weight_i,t)`, standard
in industrial-organization literature) — `entropy_concentration_t =
T_t / ln(N_t)`.

- **Range:** `[0, 1]` — 0 at perfectly equal weights, 1 at single-name
  concentration.
- **Direction:** ↑ = more concentrated (`concentration_direction("entropy_concentration") == +1`,
  no sign flip needed for aggregation).

## Why normalized rather than raw Theil (`ln(N_t) - H_t`)

Decided against the unnormalized Theil index specifically because `N_t`
(active constituent count) is not perfectly constant in this project's
CRSP-sourced panel (~489-502 across the 2000-2026 build, see
`data_final/concentration/concentration_measures_monthly_<date>.csv`) —
almost certainly a filtering/pull artifact (the share-type/exchange filter
in `src/crsp/clean_sp500_raw.py`, monthly snapshot granularity), not
genuine index-composition churn. Raw Theil's `ln(N_t)` term shifts
mechanically whenever a near-zero-weight tail name enters or leaves the
panel, independent of any real change in how weight is distributed
(`H_t` barely moves when a ~0-weight name is added/dropped, but `ln(N_t)`
does). Since this measure's whole purpose is to be one of four inputs to
a collinearity check against `hhi`/`cr_k` (none of which are perturbed by
tail-name count at all) and a future composite aggregation, contaminating
it with `N_t`-churn noise the other three don't share would make any
observed distinctness from HHI hard to interpret — is it genuine
tail-shape signal, or just composition-count noise? Normalizing by
`ln(N_t)` largely cancels this artifact (the two `N_t`-dependent terms
move together), at the cost of losing the literal "nats" units — judged
an acceptable trade for a [0,1] concentration score that's also easier to
present. See the discussion in the phase-2 planning session
(2026-08-20) for the full reasoning (N_t-sensitivity magnitude, literature
precedent in Jacquemin & Berry 1979 and Pielou's evenness index).

## Downstream use

- Input to the mandatory collinearity check
  (`csi_construction.md`, "Collinearity check before aggregation") against
  `hhi`, `cr_5`/`cr_7`/`cr_10`, and `effective_n`.
- Candidate component for CSI aggregation (Option B/C in
  `csi_construction.md`) if selected as non-redundant.

- **Frequency (this build):** monthly, month-end trading date
- **Source columns:** `weight` from `data_final/universe/`
- **Computed in:** `src/concentration/measures.py::entropy_concentration`,
  applied at month-end by `src/concentration/build_concentration_panel.py`
- **Output:** `data_final/concentration/concentration_measures_monthly_<date>.csv`,
  column `entropy_concentration`
