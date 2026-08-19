"""
Phase-1 CRSP raw pull driver for the CSI thesis: S&P 500 membership,
returns, delistings, and identifiers, 2000-01-01 through today.

Raw pull only — does NOT build the canonical interval-format membership
panel (that is src/universe/build_constituent_panel.py, a later step).
Writes immutable dated files to data_raw/crsp/ following the project's
<source>_<content>_<YYYYMMDD>.<ext> convention, and logs row counts / date
coverage / any unresolved permnos to outputs/logs/.

Run with the tesi-wrds conda env:
    C:\\Users\\rebec\\anaconda3\\envs\\tesi-wrds\\python.exe src/crsp/pull_sp500_raw.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.crsp.connect import get_connection  # noqa: E402
from src.crsp.queries import (  # noqa: E402
    get_sp500_delistings,
    get_sp500_membership,
    get_sp500_names,
    get_sp500_returns,
)
from src.utils.paths import CRSP_RAW, LOGS  # noqa: E402

START_DATE = "2000-01-01"
END_DATE = "2026-08-19"
PULL_DATE_TAG = "20260819"

MEMBERSHIP_OUT = CRSP_RAW / f"crsp_sp500_membership_{PULL_DATE_TAG}.csv"
RETURNS_OUT = CRSP_RAW / f"crsp_sp500_returns_daily_{PULL_DATE_TAG}.csv"
DELIST_OUT = CRSP_RAW / f"crsp_sp500_delistings_{PULL_DATE_TAG}.csv"
NAMES_OUT = CRSP_RAW / f"crsp_sp500_names_{PULL_DATE_TAG}.csv"

LOG_OUT = LOGS / f"crsp_sp500_raw_pull_{PULL_DATE_TAG}.txt"


def _fail_if_exists(path: Path):
    if path.exists():
        raise FileExistsError(
            f"{path} already exists — data_raw/ is immutable, re-pull into a "
            "new dated file instead of overwriting."
        )


def main():
    for p in [MEMBERSHIP_OUT, RETURNS_OUT, DELIST_OUT, NAMES_OUT]:
        _fail_if_exists(p)

    log_lines = [
        f"CRSP S&P 500 raw pull — generated {datetime.now(timezone.utc).isoformat()}",
        f"Window requested: {START_DATE} to {END_DATE}",
        "Table family: CIZ (_v2) — see crsp_legacy_vs_v2_resolution_20260819.txt",
        "Physical schemas used: crsp_m_indexes (membership), crsp_m_stock (returns/delisting/names)",
        "=" * 70,
    ]

    db = get_connection()
    try:
        # 1. Membership
        print("Pulling membership...")
        membership = get_sp500_membership(db, START_DATE, END_DATE)
        permnos = sorted(membership["permno"].unique().tolist())
        log_lines.append("\n## Membership (dsp500list_v2, indno=1000500)")
        log_lines.append(f"Rows: {len(membership)}")
        log_lines.append(f"Distinct PERMNOs (full historical membership, not just current): {len(permnos)}")
        log_lines.append(
            f"mbrstartdt range: {membership['mbrstartdt'].min()} to {membership['mbrstartdt'].max()}"
        )
        log_lines.append(
            f"mbrenddt range: {membership['mbrenddt'].min()} to {membership['mbrenddt'].max()}"
        )
        membership.to_csv(MEMBERSHIP_OUT, index=False)
        log_lines.append(f"Saved: {MEMBERSHIP_OUT}")

        # 2. Returns
        print(f"Pulling daily returns for {len(permnos)} permnos...")
        returns = get_sp500_returns(db, permnos, START_DATE, END_DATE)
        log_lines.append("\n## Returns (dsf_v2)")
        log_lines.append(f"Rows: {len(returns)}")
        log_lines.append(f"Distinct PERMNOs returned: {returns['permno'].nunique()}")
        missing_permnos = sorted(set(permnos) - set(returns["permno"].unique()))
        log_lines.append(f"PERMNOs in membership with ZERO return rows returned: {len(missing_permnos)}")
        if missing_permnos:
            log_lines.append(f"  {missing_permnos}")
        log_lines.append(
            f"dlycaldt range: {returns['dlycaldt'].min()} to {returns['dlycaldt'].max()}"
        )
        returns.to_csv(RETURNS_OUT, index=False)
        log_lines.append(f"Saved: {RETURNS_OUT}")

        # 3. Delistings
        print("Pulling delistings...")
        delistings = get_sp500_delistings(db, permnos)
        log_lines.append("\n## Delistings (stkdelists, CIZ)")
        log_lines.append(f"Rows: {len(delistings)}")
        log_lines.append(f"Distinct PERMNOs with a delisting event: {delistings['permno'].nunique()}")
        if len(delistings):
            log_lines.append(
                f"delistingdt range: {delistings['delistingdt'].min()} to {delistings['delistingdt'].max()}"
            )
        delistings.to_csv(DELIST_OUT, index=False)
        log_lines.append(f"Saved: {DELIST_OUT}")

        # 4. Names / identifiers
        print("Pulling names/identifiers...")
        names = get_sp500_names(db, permnos)
        log_lines.append("\n## Names/identifiers (stocknames_v2, CIZ)")
        log_lines.append(f"Rows: {len(names)}")
        log_lines.append(f"Distinct PERMNOs: {names['permno'].nunique()}")
        names.to_csv(NAMES_OUT, index=False)
        log_lines.append(f"Saved: {NAMES_OUT}")

        # Sample distinct-PERMNO-per-month checks (start/middle/end of range)
        log_lines.append("\n## Distinct PERMNO count per month, sample dates (membership table)")
        import pandas as pd

        membership["mbrstartdt"] = pd.to_datetime(membership["mbrstartdt"])
        membership["mbrenddt"] = pd.to_datetime(membership["mbrenddt"])
        for sample_date in ["2000-06-30", "2013-06-28", "2020-06-30", "2026-06-30"]:
            sd = pd.Timestamp(sample_date)
            active = membership[(membership["mbrstartdt"] <= sd) & (membership["mbrenddt"] >= sd)]
            log_lines.append(f"{sample_date}: {active['permno'].nunique()} distinct PERMNOs active")

    finally:
        db.close()

    LOG_OUT.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\nLog written to {LOG_OUT}")
    print("\n".join(log_lines))


if __name__ == "__main__":
    main()
