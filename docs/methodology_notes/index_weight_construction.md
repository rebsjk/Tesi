# Index weight construction

Status: **decided** (2026-08-19).

## The gap this resolves

The official point-in-time S&P 500 constituent weight (as published by
S&P and mirrored in CRSP's `idx_const_close_v2`/`idx_const_open_v2`
tables, which carry an `index_weight` field) lives under the
`crsp_q_mi_hist` physical schema, which this project's WRDS subscription
tier does not grant `USAGE` on. `dsp500list_v2`/`msp500list_v2` (the
membership tables this project uses — see `membership_interval_convention.md`
and `docs/data_notes/crsp_sp500_raw_pull_20260819.md`) carry membership
intervals only (`permno, indno, mbrstartdt, mbrenddt, mbrflg, indfam`),
no weight column. See `docs/data_notes/crsp_sp500_raw_pull_20260819.md`
for the full access-path finding.

## Decision

Constituent weight is **self-computed from CRSP daily market
capitalization**, not sourced from a published S&P/CRSP index-weight
field:

```
weight_i,t = dlycap_i,t / sum_{j in M_t} dlycap_j,t
```

where `dlycap_i,t` is CRSP's own daily market cap for permno `i` on date
`t` (`crsp_m_stock.dsf_v2.dlycap`, already pulled — see
`docs/data_notes/crsp_sp500_raw_pull_20260819.md`), and `M_t` is the set
of permnos with an open membership interval at `t` per `dsp500list_v2`
(i.e. `mbrstartdt <= t < mbrenddt`, matching the half-open convention in
`membership_interval_convention.md`). This is computed in
`src/universe/` at the point the CRSP membership and returns files are
merged into the canonical constituent panel — it is not part of the raw
pull.

## Why this is the right choice for this thesis, not just a workaround

- **Standard in the concentration-measurement literature.** Cap-weighted
  concentration measures (HHI, CR-k, effective-N — see
  `csi_construction.md`) are conventionally computed from constituent
  market capitalization relative to total index market cap, not from a
  vendor's published index weight, which additionally embeds
  index-methodology adjustments (float adjustment, foreign-ownership
  caps, cross-holding exclusions, IWF changes between rebalances) that
  are about *replicating the tradable index level*, not about measuring
  *relative concentration structure*. Those adjustments are immaterial to
  — and in some cases would actively distort — a state variable meant to
  track how concentrated market value is among constituents.
- **Point-in-time by construction.** `dlycap_i,t = dlyprc_i,t *
  shrout_i,t` as of date `t` alone; nothing about it depends on a value
  known only after `t`. This satisfies the CSI's anti-look-ahead
  requirement (`csi_construction.md`, "Anti-look-ahead rules") without
  any extra handling.
- **No new access dependency.** Requesting `crsp_q_mi_hist` access from
  WRDS is a separate administrative step with no guaranteed outcome or
  timeline (see `docs/data_notes/crsp_sp500_raw_pull_20260819.md`); the
  self-computed weight uses data already pulled and available now.
- **Immaterial for this thesis's object of interest.** The CSI compares
  *relative* concentration over time and across regimes (is concentration
  rising, is it associated with elevated risk), not the exact published
  index level. A permno's self-computed weight and its officially
  published weight will differ only at the margin (float-adjustment
  effects), and that margin is far smaller than the concentration swings
  the CSI is designed to detect.

## What this means downstream

- Every capital-concentration measure in `csi_construction.md` (HHI,
  CR-k, effective-N, entropy) that consumes `weight` is computed from
  this self-computed series, not a published S&P weight.
- If a future robustness check specifically requires reconciliation
  against the *published* S&P 500 weight (e.g. to validate against a
  Bloomberg- or vendor-reported concentration series), that requires
  either obtaining `crsp_q_mi_hist` access or sourcing weights from
  Bloomberg directly — treat as a phase-6 robustness item, not a
  Phase 1 blocker.
- Logged here per `csi_construction.md`'s and CLAUDE.md's requirement
  that every derived variable's exact formula and source columns be
  documented — see also `docs/variable_definitions/weight.md`.
