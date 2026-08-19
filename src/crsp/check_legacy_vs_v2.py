"""
Phase-1 CRSP pull, Step 1 (continued): confirm dsp500list_v2/msp500list_v2
indno/indfam values actually correspond to the S&P 500 (single index id
expected, not multiple series bundled in), and check whether an index
metadata table (indseriesinfohdr_ind) is reachable to cross-check the name.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.crsp.connect import get_connection  # noqa: E402
from src.utils.paths import LOGS  # noqa: E402

LOG_PATH = LOGS / "crsp_legacy_vs_v2_resolution_20260819.txt"


def main():
    lines = [
        f"CRSP dsp500list_v2 index-id confirmation — generated "
        f"{datetime.now(timezone.utc).isoformat()}",
        "=" * 70,
    ]

    db = get_connection()
    try:
        lines.append("\n## distinct (indno, indfam) in crsp_m_indexes.dsp500list_v2")
        df = db.raw_sql("select distinct indno, indfam from crsp_m_indexes.dsp500list_v2")
        lines.append(df.to_string(index=False))

        lines.append("\n## distinct (indno, indfam) in crsp_m_indexes.msp500list_v2")
        df2 = db.raw_sql("select distinct indno, indfam from crsp_m_indexes.msp500list_v2")
        lines.append(df2.to_string(index=False))

        lines.append("\n## indseriesinfohdr_ind columns + row for indno=1000500")
        try:
            cols = db.raw_sql(
                "select column_name from information_schema.columns "
                "where table_schema='crsp_m_indexes' and table_name='indseriesinfohdr_ind' order by ordinal_position"
            )
            lines.append(f"columns: {list(cols['column_name'])}")
            df3 = db.raw_sql("select * from crsp_m_indexes.indseriesinfohdr_ind where indno = 1000500")
            lines.append(df3.to_string(index=False))
        except Exception as e:
            lines.append(f"ERROR: {str(e).splitlines()[0]}")

        lines.append("\n## legacy dsp500list min/max start date (for reference, even though frozen)")
        df4 = db.raw_sql("select min(start) as min_dt, max(ending) as max_dt, count(*) as n from crsp_m_indexes.dsp500list")
        lines.append(df4.to_string(index=False))

        lines.append("\n## v2 dsp500list_v2 min(mbrstartdt), count distinct permno")
        df5 = db.raw_sql("select min(mbrstartdt) as min_dt, max(mbrenddt) as max_dt, count(*) as n, count(distinct permno) as n_permno from crsp_m_indexes.dsp500list_v2")
        lines.append(df5.to_string(index=False))
    finally:
        db.close()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Log written to {LOG_PATH}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
