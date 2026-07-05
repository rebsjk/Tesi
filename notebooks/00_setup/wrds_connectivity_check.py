"""
Phase-0 WRDS connectivity check for the CSI thesis.

Connects to WRDS, lists every library the account has access to, then lists
tables for crsp, comp, and ff specifically (the three libraries Chapter 3's
data inventory depends on). Does not pull any row-level data — inventory
only. Requires a working .pgpass (see notebooks/00_setup/README or the
one-time `wrds.Connection()` interactive login) before it can run
non-interactively.
"""

import sys
from datetime import datetime, timezone

import wrds

REPORT_PATH = sys.argv[1] if len(sys.argv) > 1 else "wrds_access_report.txt"
TARGET_LIBRARIES = ["crsp", "comp", "ff"]


def main():
    lines = []
    lines.append(f"WRDS access report — generated {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 70)

    db = wrds.Connection()
    try:
        lines.append("\n## All libraries visible to this account\n")
        libraries = db.list_libraries()
        for lib in sorted(libraries):
            lines.append(lib)

        lines.append(f"\nTotal libraries: {len(libraries)}")

        for target in TARGET_LIBRARIES:
            lines.append("\n" + "=" * 70)
            if target in libraries:
                lines.append(f"## Tables in '{target}'\n")
                try:
                    tables = db.list_tables(library=target)
                    for t in sorted(tables):
                        lines.append(t)
                    lines.append(f"\nTotal tables in {target}: {len(tables)}")
                except Exception as e:
                    lines.append(f"ERROR listing tables for {target}: {e}")
            else:
                lines.append(f"## '{target}' NOT in accessible library list — subscription gap")

        # Explicitly note optionm presence/absence, relevant to the
        # Bloomberg-vs-OptionMetrics open decision in data_inventory.md
        lines.append("\n" + "=" * 70)
        lines.append("## OptionMetrics check")
        optionm_libs = [lib for lib in libraries if "optionm" in lib.lower()]
        if optionm_libs:
            lines.append(f"Found optionm-related libraries: {optionm_libs}")
        else:
            lines.append("No optionm-related library found — confirms no OptionMetrics access.")

    finally:
        db.close()

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
