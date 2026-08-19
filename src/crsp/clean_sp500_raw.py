"""
Phase-1 CRSP source-cleaning step: turns the raw `data_raw/crsp/` S&P 500
pull (`crsp-extractor`, 2026-08-19) into the canonical shapes
`src/universe/build_constituent_panel.py` consumes.

Two things happen here, and nowhere else:

1. **Share type / exchange filter.** Restrict daily observations to
   ordinary common shares on a major exchange (`sharetype == "NS"`,
   `primaryexch in {"N", "Q", "A"}`) — decided 2026-08-19, see
   `docs/workflow_notes/data_inventory.md` for the pre/post row counts
   this run produces. `data_raw/` itself is left untouched (raw data is
   immutable); this filter is applied only when producing the
   `data_interim/crsp/` output below.
2. **Delisting-return adjustment.** CRSP's documented convention: if a
   permno's delisting date coincides with its last regular daily
   observation, compound the delisting return into that observation
   (`(1 + ret) * (1 + delret) - 1`); if the delisting date falls after
   the last regular observation, append a new observation on the
   delisting date with `ret = delret`. Permnos with a missing `delret`
   (`delretmisstype` flags this) are left unadjusted and logged — no
   value is invented for a missing delisting return (e.g. the Shumway
   1997 -30%/-55% imputation), since that is a separate research-design
   decision this script does not make on its own.

**Not done here — deliberately left to `build_constituent_panel.py`:**
weight. `dlycap` (CRSP daily market cap) is carried through unfiltered by
membership-interval containment, because `weight_i,t = dlycap_i,t /
sum_{j in M_t} dlycap_j,t` requires knowing the *point-in-time* active
membership set `M_t`, which is exactly what the interval join in
`build_constituent_panel.py` already computes — recomputing it here would
duplicate that logic. See `docs/methodology_notes/index_weight_construction.md`.

Output (data_interim/crsp/):
- `crsp_sp500_membership_clean_<date>.csv`: entity_id, start_date, end_date
  (entity_id == permno; no weight column — see above)
- `crsp_sp500_returns_clean_<date>.csv`: permno, date, ret, dlycap
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CRSP_INTERIM, CRSP_RAW, LOGS, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

KEEP_SHARETYPE = "NS"
KEEP_PRIMARYEXCH = {"N", "Q", "A"}

RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    membership_path = latest_raw_file(CRSP_RAW, "crsp_sp500_membership")
    returns_path = latest_raw_file(CRSP_RAW, "crsp_sp500_returns_daily")
    delist_path = latest_raw_file(CRSP_RAW, "crsp_sp500_delistings")

    membership = pd.read_csv(membership_path, parse_dates=["mbrstartdt", "mbrenddt"])
    returns = pd.read_csv(returns_path, parse_dates=["dlycaldt"])
    delistings = pd.read_csv(delist_path, parse_dates=["delistingdt"])

    logger.info("Loaded raw membership: %s (%d rows)", membership_path, len(membership))
    logger.info("Loaded raw returns:    %s (%d rows)", returns_path, len(returns))
    logger.info("Loaded raw delistings: %s (%d rows)", delist_path, len(delistings))

    return membership, returns, delistings


def filter_share_exchange(returns: pd.DataFrame) -> pd.DataFrame:
    """Restrict to ordinary common shares (sharetype='NS') on a major
    exchange (primaryexch in {N, Q, A}). Decided 2026-08-19 — see
    docs/workflow_notes/data_inventory.md for this run's before/after counts.
    """
    pre_rows = len(returns)
    pre_permnos = returns["permno"].nunique()

    keep = (returns["sharetype"] == KEEP_SHARETYPE) & (
        returns["primaryexch"].isin(KEEP_PRIMARYEXCH)
    )
    filtered = returns.loc[keep].copy()

    post_rows = len(filtered)
    post_permnos = filtered["permno"].nunique()
    dropped_sharetype = returns.loc[~keep, "sharetype"].value_counts().to_dict()
    dropped_exch = returns.loc[~keep, "primaryexch"].value_counts().to_dict()

    logger.info(
        "Share/exchange filter (sharetype=%s, primaryexch in %s): "
        "%d -> %d rows (%d -> %d distinct permnos)",
        KEEP_SHARETYPE,
        sorted(KEEP_PRIMARYEXCH),
        pre_rows,
        post_rows,
        pre_permnos,
        post_permnos,
    )
    logger.info("Dropped rows by sharetype: %s", dropped_sharetype)
    logger.info("Dropped rows by primaryexch: %s", dropped_exch)

    return filtered, {
        "pre_rows": pre_rows,
        "post_rows": post_rows,
        "pre_permnos": pre_permnos,
        "post_permnos": post_permnos,
        "dropped_by_sharetype": dropped_sharetype,
        "dropped_by_primaryexch": dropped_exch,
    }


def apply_delisting_adjustment(
    returns: pd.DataFrame, delistings: pd.DataFrame
) -> tuple[pd.DataFrame, list[int]]:
    """Compound or append the delisting return per CRSP's documented
    convention. Returns the adjusted frame and the list of permnos whose
    delret was missing (left unadjusted).
    """
    returns = returns.sort_values(["permno", "dlycaldt"]).reset_index(drop=True)
    last_obs_idx = returns.groupby("permno")["dlycaldt"].idxmax()
    last_obs = returns.loc[last_obs_idx, ["permno", "dlycaldt"]].rename(
        columns={"dlycaldt": "last_date"}
    )

    delist = delistings[["permno", "delistingdt", "delret", "delretmisstype"]].merge(
        last_obs, on="permno", how="left"
    )

    missing_delret = delist.loc[delist["delret"].isna(), "permno"].tolist()
    delist = delist.dropna(subset=["delret"])

    compound_mask = delist["delistingdt"] == delist["last_date"]
    append_mask = delist["delistingdt"] > delist["last_date"]
    stale_mask = delist["delistingdt"] < delist["last_date"]

    n_compound = int(compound_mask.sum())
    n_append = int(append_mask.sum())
    n_stale = int(stale_mask.sum())

    if n_stale:
        logger.warning(
            "%d delisting events have a delistingdt BEFORE the permno's last "
            "regular return observation — left unadjusted, flagged for review: %s",
            n_stale,
            delist.loc[stale_mask, "permno"].tolist(),
        )

    # Compound: same-date delisting return folds into the existing row.
    compound_rows = delist.loc[compound_mask, ["permno", "delistingdt", "delret"]]
    for _, row in compound_rows.iterrows():
        idx = returns.index[
            (returns["permno"] == row["permno"]) & (returns["dlycaldt"] == row["delistingdt"])
        ]
        returns.loc[idx, "dlyret"] = (1 + returns.loc[idx, "dlyret"]) * (1 + row["delret"]) - 1

    # Append: delisting return becomes a new final observation. dlycap is
    # left NaN (no market cap observation exists on a date with no regular
    # trading) — downstream weight computation naturally excludes it.
    append_rows = delist.loc[append_mask, ["permno", "delistingdt", "delret"]]
    if len(append_rows):
        new_rows = pd.DataFrame(
            {
                "permno": append_rows["permno"].to_numpy(),
                "dlycaldt": append_rows["delistingdt"].to_numpy(),
                "dlyret": append_rows["delret"].to_numpy(),
                "dlycap": float("nan"),
            }
        )
        returns = pd.concat([returns, new_rows], ignore_index=True)

    logger.info(
        "Delisting adjustment: %d compounded into last observation, %d appended as "
        "a new final observation, %d missing delret left unadjusted (permnos: %s)",
        n_compound,
        n_append,
        len(missing_delret),
        missing_delret,
    )

    return returns.sort_values(["permno", "dlycaldt"]).reset_index(drop=True), missing_delret


def build_clean_membership(membership_raw: pd.DataFrame) -> pd.DataFrame:
    """entity_id == permno (native — no Bloomberg crosswalk needed for a
    CRSP-sourced index; see docs/workflow_notes/data_inventory.md).
    """
    out = membership_raw.rename(
        columns={"permno": "entity_id", "mbrstartdt": "start_date", "mbrenddt": "end_date"}
    )[["entity_id", "start_date", "end_date"]].copy()
    out["permno"] = membership_raw["permno"]
    return out


def build_clean_returns(returns_filtered: pd.DataFrame) -> pd.DataFrame:
    return returns_filtered.rename(columns={"dlycaldt": "date", "dlyret": "ret"})[
        ["permno", "date", "ret", "dlycap"]
    ].copy()


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"clean_sp500_raw_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    membership_raw, returns_raw, delistings_raw = load_raw()

    returns_filtered, filter_stats = filter_share_exchange(returns_raw)
    returns_adjusted, missing_delret = apply_delisting_adjustment(returns_filtered, delistings_raw)

    membership_clean = build_clean_membership(membership_raw)
    returns_clean = build_clean_returns(returns_adjusted)

    CRSP_INTERIM.mkdir(parents=True, exist_ok=True)
    membership_out = CRSP_INTERIM / f"crsp_sp500_membership_clean_{RUN_TAG}.csv"
    returns_out = CRSP_INTERIM / f"crsp_sp500_returns_clean_{RUN_TAG}.csv"

    membership_clean.to_csv(membership_out, index=False)
    returns_clean.to_csv(returns_out, index=False)

    logger.info("Wrote %d membership rows to %s", len(membership_clean), membership_out)
    logger.info("Wrote %d return rows to %s", len(returns_clean), returns_out)
    logger.info("Filter stats: %s", filter_stats)
    logger.info("Permnos with missing delret (unadjusted): %s", missing_delret)


if __name__ == "__main__":
    main()
