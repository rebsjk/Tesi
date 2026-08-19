# weight

Constituent capital weight within the S&P 500 universe panel — the input
every capital-concentration measure in `csi_construction.md` (HHI, CR-k,
effective-N, entropy) is computed from.

- **Formula:** `weight_i,t = dlycap_i,t / sum_{j in M_t} dlycap_j,t`
- **`dlycap_i,t`:** CRSP daily market capitalization for permno `i` on
  date `t` (`crsp_m_stock.dsf_v2.dlycap`, `dlyprc_i,t * shrout_i,t`)
- **`M_t`:** permnos with an open S&P 500 membership interval at `t`
  (`crsp_m_indexes.dsp500list_v2`, `mbrstartdt <= t < mbrenddt`, per the
  half-open convention in `membership_interval_convention.md`)
- **Units:** unitless share of index total market cap, sums to 1 across
  `M_t` at each `t`
- **Frequency:** daily
- **Source columns:** `crsp_m_stock.dsf_v2` (`permno, dlycaldt, dlycap`),
  `crsp_m_indexes.dsp500list_v2` (`permno, mbrstartdt, mbrenddt`)
- **Computed in:** `src/universe/` (constituent panel build step), not in
  the raw pull
- **Rationale and what this deliberately is not (official S&P published
  weight):** see `docs/methodology_notes/index_weight_construction.md`
