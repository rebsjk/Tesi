# CRSP S&P 500 raw pull — 2026-08-19

Phase-1 raw pull (`crsp-extractor`). Raw only — does not build the
canonical interval-format constituent panel; that is a later step in
`src/universe/build_constituent_panel.py`.

## Source tables and table-family decision

Legacy ("SIZ") vs. `_v2` ("CIZ") resolved empirically before pulling —
see `outputs/logs/crsp_legacy_vs_v2_resolution_20260819.txt` for full
evidence. Summary: every legacy table (`dsf`, `msf`, `dsp500list`,
`msp500list`, `dsedelist`, `msedelist`) is frozen at **2024-12-31**; every
`_v2` (CIZ) table (`dsf_v2`, `msf_v2`, `dsp500list_v2`, `msp500list_v2`,
`stkdelists`) is current through **2026-07-30/31**. **Decision: `_v2`
(CIZ) family used throughout, for membership, returns, delisting, and
names — no mixing with legacy.**

**Access-path finding (logged, not a research decision):** the unified
`crsp.<table>` logical schema (used in most published WRDS examples, and
in `db.list_tables()`'s listing) is not reachable under this account's
subscription tier — it resolves to physical schemas (`crsp_a_stock`,
`crsp_a_indexes`, `crsp_a_ccm`, `crsp_q_stock*`, `crsp_q_indexes*`,
`crsp_q_mi_hist`) with no `USAGE` grant, even though `db.list_tables()`
and `has_table_privilege()` on the logical view both suggest access.
The account's actual entitlement is the physical schemas
`crsp_m_stock`, `crsp_m_indexes`, `crsp_m_ccm`, `crsp_q_mutualfunds`,
which contain identically-named tables (both legacy and `_v2`). All
queries in `src/crsp/queries.py` target these physical schemas directly
(`crsp_m_stock.dsf_v2`, `crsp_m_indexes.dsp500list_v2`, etc.), not the
`crsp.*` synonyms.

**Weight gap:** point-in-time official index weight
(`idx_const_close_v2`/`idx_const_open_v2`, which carry `index_weight`)
lives only under `crsp_q_mi_hist`, which this account cannot reach.
`dsp500list_v2`/`msp500list_v2` (membership) carry no weight column
(`permno, indno, mbrstartdt, mbrenddt, mbrflg, indfam` only). Pulled
`dlycap` (CRSP daily market cap) and `dlyprevcap` from `dsf_v2` instead,
so `src/universe/` can derive weight = `dlycap_i` / sum(`dlycap`) over
current members per date. If official point-in-time index weights are
required for Bloomberg reconciliation, `crsp_q_mi_hist` access needs to
be requested from WRDS separately (not resolved this session).

## Index identity

`dsp500list_v2`/`msp500list_v2` both resolve to a single
`(indno=1000500, indfam=1100500)`, confirmed via
`crsp_m_indexes.indseriesinfohdr_ind` as `"CRSP Value-Weighted Index of
the S&P 500 Universe"` — single index series, not a bundle of S&P 400/
600/1500 series.

## Variables pulled

**Membership** (`crsp_sp500_membership_20260819.csv`, from
`crsp_m_indexes.dsp500list_v2`): `permno, indno, indfam, mbrstartdt,
mbrenddt, mbrflg`. Full historical membership intervals overlapping
2000-01-01 to 2026-08-19 — driven by full historical S&P 500 index
membership, not today's constituents (survivorship-bias check satisfied
by construction: distinct-PERMNO count is checked below at multiple
sample dates, and turnover across the ~1,000+ distinct historical
PERMNOs vs. ~500 active at any one time confirms the pull is not scoped
to current membership only).

**Returns** (`crsp_sp500_returns_daily_20260819.csv`, from
`crsp_m_stock.dsf_v2`): `permno, hdrcusip, cusip, permco, ticker,
dlycaldt, sharetype, securitytype, securitysubtype, primaryexch,
conditionaltype, tradingstatusflg, usincflg, issuertype, dlyprc,
dlyprcflg, dlyret, dlyretx, dlyreti, dlyretmissflg, dlyretdurflg, dlyvol,
dlyclose, dlyopen, dlyhigh, dlylow, dlybid, dlyask, shrout, dlycap,
dlycapflg, dlyprevcap, dlycumfacpr, dlycumfacshr`. Daily frequency
(matches the task's explicit instruction and is what
`physical-risk-analyst`'s realized-vol/tail-comovement models need;
monthly can be aggregated downstream from daily if ever needed —
re-pulling monthly separately was judged unnecessary).

**Delistings** (`crsp_sp500_delistings_20260819.csv`, from
`crsp_m_stock.stkdelists`, the CIZ delisting-event table paired with
`dsf_v2`/CIZ per the legacy-vs-v2 decision above): `permno, delistingdt,
deldtprc, deldtprcflg, delactiontype, delstatustype, delreasontype,
delpaymenttype, delpermno, delpermco, delret, delretmisstype, delnextdt,
delnextprc, delnextprcflg`. Pulled for every PERMNO that ever appears in
the membership pull (not just currently-active names) — delisting
events at index-exit are exactly the events this thesis needs, per
CLAUDE.md's systemic-risk framing.

**Delisting-adjustment method — NOT YET APPLIED in this raw pull.**
This file is delivered as-is (one row per delisting event, `delret` =
CRSP's own delisting return). Per CRSP's documented convention, `delret`
is meant to replace (if the delisting date has no regular daily
observation) or be compounded with (if it does) the last regular `dlyret`
observation for that PERMNO. **This compounding/replacement is
downstream `src/universe/` logic, not applied here** — flagging
explicitly so it isn't silently skipped later. Do not treat the raw
`dsf_v2` `dlyret` series alone as adjusted for delisting.

**Names/identifiers** (`crsp_sp500_names_20260819.csv`, from
`crsp_m_stock.stocknames_v2`): `permno, permco, namedt, nameenddt,
securitybegdt, securityenddt, hdrcusip, hdrcusip9, cusip, cusip9,
ticker, issuernm, primaryexch, conditionaltype, tradingstatusflg,
shareclass, sharetype, securitytype, securitysubtype, usincflg,
issuertype, siccd`. Full identifier history (not just current
CUSIP/ticker) for `src/merges/` crosswalk matching against Bloomberg IDs
across renames/re-CUSIPing events.

## Identifier used

**PERMNO** — primary/stable key throughout, per CLAUDE.md/crsp-extractor
scope. CUSIP (both `hdrcusip`/issuer-level and `cusip`/security-level, CIZ
separates the two) and ticker history carried in the names pull for
crosswalk matching.

## Share code / exchange filter — OPEN, NOT APPLIED

Per task instructions, this decision needs explicit user confirmation,
not a silent default. **No share-code/exchange filter has been applied
in this raw pull** — `sharetype`, `securitytype`, `securitysubtype`,
`primaryexch`, `tradingstatusflg`, `conditionaltype`, and `usincflg` are
all carried as columns on both the returns and names pulls so the filter
can be applied (and the decision documented) at the `src/universe/`
build step, once the user confirms which values should be kept (e.g.
`sharetype = 'NS'`/ordinary shares only; `primaryexch` restricted to
NYSE/NASDAQ/NYSE MKT). Raw data intentionally left unfiltered per
CLAUDE.md's "raw data is immutable" principle — filtering is a build
decision, not a pull decision.

## Date range requested vs. returned

Requested: 2000-01-01 to 2026-08-19. Full detail in
`outputs/logs/crsp_sp500_raw_pull_20260819.txt`. Summary:

| File | Rows | Distinct PERMNOs | Date range returned |
|---|---|---|---|
| `crsp_sp500_membership_20260819.csv` | 1,146 | 1,117 | mbrstartdt 1925-12-31–2026-06-29; mbrenddt 2000-01-05–2026-07-31 |
| `crsp_sp500_returns_daily_20260819.csv` | 5,019,232 | 1,117 (0 membership PERMNOs returned zero rows) | 2000-01-03 to 2026-07-31 |
| `crsp_sp500_delistings_20260819.csv` | 467 | 467 | 2000-01-05 to 2026-05-06 |
| `crsp_sp500_names_20260819.csv` | 4,727 | 1,117 | (identifier history, no single date range) |

Sample distinct-PERMNO-per-month counts from the membership table (the
survivorship-bias check): 2000-06-30: 500; 2013-06-28: 500; 2020-06-30:
505; 2026-06-30: 503 — consistent with S&P 500 sizing at every sample
point, confirming the pull is not scoped to today's constituents only
and is not double-counting share classes.

`sharetype` distribution in the returns pull (not filtered, see the open
decision above): `NS` (ordinary common) 4,970,570; `SB` 34,920; `UG`
11,795; `AD` 1,480. `securitytype` is `EQTY` for all but 467 rows (NaN).
`primaryexch` distribution: `N` (NYSE) 3,717,007; `Q` (NASDAQ) 1,280,155;
`X` 11,866; `A` 7,975; `B` 1,978; `I` 251 — the small non-N/Q counts are
the ones a share/exchange filter decision would actually affect.
`delactiontype` in the delistings pull: `MER` (merger) 403, `GDR`
(going-private/reorg) 59, `GEX` (exchange) 5 — dominated by M&A exits, as
expected for a concentration/systemic-risk thesis universe.

## Open observation for a separate decision (not resolved here)

`src/universe/build_constituent_panel.py` and
`docs/workflow_notes/data_inventory.md` were written expecting
Bloomberg-sourced membership (`entity_id, weight, start_date, end_date`)
plus a `data_raw/manual/` PERMNO↔entity_id crosswalk file. Since CRSP's
own `dsp500list_v2` is already PERMNO-native and point-in-time (start/end
per membership interval), that crosswalk step may not be needed for
Phase 1 if CRSP is used as the membership source of record (consistent
with the 2026-07-05 session decision in
`docs/workflow_notes/session_03_CSI_data_pull_claude_summary.md`:
"membership + pesi S&P 500 vengono da CRSP via WRDS ... non da un pull
Bloomberg"). No file has been invented to fill that gap. This needs a
separate decision by the user/build-phase owner, not made here.
