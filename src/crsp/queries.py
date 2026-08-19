"""
CRSP/WRDS query builders for the Phase-1 S&P 500 raw pull (CIZ / _v2
family only — see outputs/logs/crsp_legacy_vs_v2_resolution_20260819.txt
for the legacy-vs-v2 resolution).

IMPORTANT — physical schema, not the 'crsp' logical schema:
This WRDS account has USAGE on the physical schemas crsp_m_stock,
crsp_m_indexes, crsp_m_ccm, crsp_q_mutualfunds, but NOT on crsp_a_stock /
crsp_a_indexes / crsp_a_ccm / crsp_q_stock* / crsp_q_indexes* /
crsp_q_mi_hist. The unified 'crsp.<table>' logical synonyms (e.g.
crsp.dsf_v2) resolve to the denied crsp_a_stock/crsp_a_indexes physical
schemas and fail with "permission denied for schema crsp_a_stock" even
though has_table_privilege() on the logical view returns True. The same
tables exist directly under the granted physical schemas
(crsp_m_stock.dsf_v2, crsp_m_indexes.dsp500list_v2, etc.) and ARE
queryable there. All functions below query the physical schema directly.

Index identity: dsp500list_v2 / msp500list_v2 both resolve to
(indno=1000500, indfam=1100500) = "CRSP Value-Weighted Index of the S&P
500 Universe" (confirmed via crsp_m_indexes.indseriesinfohdr_ind).

Known gap: point-in-time official index weight (idx_const_close_v2 /
idx_const_open_v2) lives only under the crsp_q_mi_hist schema, which this
account cannot reach. dsf_v2's dlycap (CRSP-computed daily market cap) is
pulled instead so weight can be derived downstream as
dlycap_i / sum(dlycap over current members) — see the resolution log.
"""

from __future__ import annotations

import pandas as pd
import wrds

SP500_INDNO = 1000500
SP500_INDFAM = 1100500

MEMBERSHIP_SCHEMA = "crsp_m_indexes"
MEMBERSHIP_TABLE = "dsp500list_v2"

STOCK_SCHEMA = "crsp_m_stock"
RETURNS_TABLE = "dsf_v2"
DELIST_TABLE = "stkdelists"
NAMES_TABLE = "stocknames_v2"


def get_sp500_membership(db: wrds.Connection, start: str, end: str) -> pd.DataFrame:
    """Full historical S&P 500 membership intervals overlapping [start, end].

    Uses dsp500list_v2 (CIZ), NOT scoped to currently-listed constituents —
    returns every permno with a membership interval overlapping the window,
    so downstream survivorship bias is avoided by construction.
    """
    sql = f"""
        select permno, indno, indfam, mbrstartdt, mbrenddt, mbrflg
        from {MEMBERSHIP_SCHEMA}.{MEMBERSHIP_TABLE}
        where indno = {SP500_INDNO}
          and mbrenddt >= '{start}'
          and mbrstartdt <= '{end}'
        order by permno, mbrstartdt
    """
    return db.raw_sql(sql, date_cols=["mbrstartdt", "mbrenddt"])


def get_sp500_returns(
    db: wrds.Connection, permnos: list[int], start: str, end: str, chunk_size: int = 500
) -> pd.DataFrame:
    """Daily returns/prices/shares/market-cap (dsf_v2, CIZ) for the given
    permno list over [start, end]. Chunked to keep individual queries a
    manageable size given a full S&P 500 historical constituent list.
    """
    frames = []
    for i in range(0, len(permnos), chunk_size):
        chunk = permnos[i : i + chunk_size]
        permno_list = ",".join(str(p) for p in chunk)
        sql = f"""
            select permno, hdrcusip, cusip, permco, ticker, dlycaldt,
                   sharetype, securitytype, securitysubtype, primaryexch,
                   conditionaltype, tradingstatusflg, usincflg, issuertype,
                   dlyprc, dlyprcflg, dlyret, dlyretx, dlyreti,
                   dlyretmissflg, dlyretdurflg, dlyvol, dlyclose, dlyopen,
                   dlyhigh, dlylow, dlybid, dlyask, shrout,
                   dlycap, dlycapflg, dlyprevcap,
                   dlycumfacpr, dlycumfacshr
            from {STOCK_SCHEMA}.{RETURNS_TABLE}
            where permno in ({permno_list})
              and dlycaldt >= '{start}'
              and dlycaldt <= '{end}'
        """
        frames.append(db.raw_sql(sql, date_cols=["dlycaldt"]))
    return pd.concat(frames, ignore_index=True)


def get_sp500_delistings(db: wrds.Connection, permnos: list[int], chunk_size: int = 1000) -> pd.DataFrame:
    """Delisting events (stkdelists, CIZ) for the given permno list.

    No date filter applied (delisting table is small; keeping full history
    for any permno that ever appears in the membership pull avoids
    accidentally dropping a delisting event right at the window edge).
    """
    frames = []
    for i in range(0, len(permnos), chunk_size):
        chunk = permnos[i : i + chunk_size]
        permno_list = ",".join(str(p) for p in chunk)
        sql = f"""
            select permno, delistingdt, deldtprc, deldtprcflg,
                   delactiontype, delstatustype, delreasontype,
                   delpaymenttype, delpermno, delpermco, delret,
                   delretmisstype, delnextdt, delnextprc, delnextprcflg
            from {STOCK_SCHEMA}.{DELIST_TABLE}
            where permno in ({permno_list})
        """
        frames.append(db.raw_sql(sql, date_cols=["delistingdt", "delnextdt"]))
    return pd.concat(frames, ignore_index=True)


def get_sp500_names(db: wrds.Connection, permnos: list[int], chunk_size: int = 1000) -> pd.DataFrame:
    """Identifier/name history (stocknames_v2, CIZ) for the given permno
    list — CUSIP/ticker history for src/merges/ crosswalk matching against
    Bloomberg identifiers, plus share/exchange-code fields for confirming
    the common-share/exchange filter (not applied in this raw pull).
    """
    frames = []
    for i in range(0, len(permnos), chunk_size):
        chunk = permnos[i : i + chunk_size]
        permno_list = ",".join(str(p) for p in chunk)
        sql = f"""
            select permno, permco, namedt, nameenddt, securitybegdt,
                   securityenddt, hdrcusip, hdrcusip9, cusip, cusip9,
                   ticker, issuernm, primaryexch, conditionaltype,
                   tradingstatusflg, shareclass, sharetype, securitytype,
                   securitysubtype, usincflg, issuertype, siccd
            from {STOCK_SCHEMA}.{NAMES_TABLE}
            where permno in ({permno_list})
        """
        frames.append(
            db.raw_sql(sql, date_cols=["namedt", "nameenddt", "securitybegdt", "securityenddt"])
        )
    return pd.concat(frames, ignore_index=True)
