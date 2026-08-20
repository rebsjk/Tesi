"""
Quick internal sanity-check plot for the Phase-2 monthly concentration
panel — small multiples of hhi, cr_5, cr_7, cr_10, effective_n, and
entropy_concentration, 2000-today, with shaded spans for GFC, COVID, and
the informal 2023+ "Mag7/AI boom" period, so a qualitative eyeball check
against known concentration episodes is possible before any further
analysis. Not a polished/deliverable figure — a diagnostic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CONCENTRATION_FINAL, FIGURES, latest_raw_file  # noqa: E402

# NBER-dated recessions; the third span is an informal qualitative window,
# not an official event — labeled as such in the plot.
EVENT_SPANS = [
    ("2007-12-01", "2009-06-30", "GFC (NBER)"),
    ("2020-02-01", "2020-04-30", "COVID (NBER)"),
    ("2023-01-01", None, "Mag7 / AI boom (informal)"),
]

PANELS = [
    ("hhi", "HHI"),
    ("cr_5", "CR-5"),
    ("cr_7", "CR-7 (Mag7)"),
    ("cr_10", "CR-10"),
    ("effective_n", "Effective N (inverted direction)"),
    ("entropy_concentration", "Entropy concentration"),
]


def main() -> None:
    panel_path = latest_raw_file(CONCENTRATION_FINAL, "concentration_measures_monthly")
    df = pd.read_csv(panel_path, parse_dates=["date"])

    fig, axes = plt.subplots(len(PANELS), 1, figsize=(11, 14), sharex=True)

    for ax, (col, label) in zip(axes, PANELS):
        ax.plot(df["date"], df[col], color="#1f4e79", linewidth=1.2)
        ax.set_ylabel(label, fontsize=9)
        ax.grid(alpha=0.25)
        for start, end, event_label in EVENT_SPANS:
            end_ts = pd.Timestamp(end) if end else df["date"].max()
            ax.axvspan(pd.Timestamp(start), end_ts, color="#d9534f", alpha=0.08)

    # Event legend once, on the top panel only.
    for start, end, event_label in EVENT_SPANS:
        end_ts = pd.Timestamp(end) if end else df["date"].max()
        mid = pd.Timestamp(start) + (end_ts - pd.Timestamp(start)) / 2
        axes[0].annotate(
            event_label,
            xy=(mid, axes[0].get_ylim()[1]),
            xytext=(0, 2),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7,
            color="#d9534f",
        )

    axes[-1].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(
        "Phase-2 concentration measures — monthly, month-end, 2000–today "
        "(sanity check, not a final figure)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    FIGURES.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    out_path = FIGURES / f"concentration_measures_sanity_check_{datetime.now(timezone.utc):%Y%m%d}.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
