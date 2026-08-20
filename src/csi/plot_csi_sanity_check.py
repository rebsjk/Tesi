"""
Quick internal sanity-check plot for the composite CSI — the composite
(bold) against its three underlying z-scored components (thin), with the
same GFC/COVID/Mag7 event shading used in the Phase-2 sanity check, so a
qualitative eyeball check is possible before moving on to state/regime
classification. Not a polished/deliverable figure — a diagnostic.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CSI_FINAL, FIGURES, latest_raw_file  # noqa: E402

EVENT_SPANS = [
    ("2007-12-01", "2009-06-30", "GFC (NBER)"),
    ("2020-02-01", "2020-04-30", "COVID (NBER)"),
    ("2023-01-01", None, "Mag7 / AI boom (informal)"),
]


def main() -> None:
    panel_path = latest_raw_file(CSI_FINAL, "csi_composite_monthly")
    df = pd.read_csv(panel_path, parse_dates=["date"])

    fig, ax = plt.subplots(figsize=(12, 6))

    for col, label, alpha, lw in [
        ("z_hhi", "z(hhi)", 0.35, 1.0),
        ("z_cr_10", "z(cr_10)", 0.35, 1.0),
        ("z_entropy_concentration", "z(entropy)", 0.35, 1.0),
        ("csi", "CSI (composite)", 1.0, 2.2),
    ]:
        ax.plot(df["date"], df[col], label=label, alpha=alpha, linewidth=lw)

    ax.axhline(0, color="black", linewidth=0.6, alpha=0.4)
    for start, end, event_label in EVENT_SPANS:
        end_ts = pd.Timestamp(end) if end else df["date"].max()
        ax.axvspan(pd.Timestamp(start), end_ts, color="#d9534f", alpha=0.08)
        mid = pd.Timestamp(start) + (end_ts - pd.Timestamp(start)) / 2
        ax.annotate(
            event_label,
            xy=(mid, ax.get_ylim()[1]),
            xytext=(0, 2),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#d9534f",
        )

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("Expanding z-score")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    fig.suptitle(
        "Composite CSI vs. its 3 components — monthly, 2001-today "
        "(sanity check, not a final figure)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    FIGURES.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES / f"csi_sanity_check_{datetime.now(timezone.utc):%Y%m%d}.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
