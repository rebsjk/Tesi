"""
Quick internal sanity-check plot for the CSI regime classification —
composite CSI line with background shaded by regime (low/medium/high),
plus the GFC/COVID/Mag7 event markers used in earlier sanity checks, so
the classification can be eyeballed against known episodes before moving
on. Not a polished/deliverable figure — a diagnostic.
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

REGIME_COLORS = {"low": "#c6dbef", "medium": "#fdd0a2", "high": "#fcae91"}
EVENT_SPANS = [
    ("2007-12-01", "2009-06-30", "GFC (NBER)"),
    ("2020-02-01", "2020-04-30", "COVID (NBER)"),
    ("2023-01-01", None, "Mag7 / AI boom (informal)"),
]


def main() -> None:
    panel_path = latest_raw_file(CSI_FINAL, "csi_regime_monthly")
    df = pd.read_csv(panel_path, parse_dates=["date"])

    fig, ax = plt.subplots(figsize=(13, 6))

    # Shade contiguous regime blocks.
    labeled = df.dropna(subset=["regime"]).reset_index(drop=True)
    block_start = labeled.loc[0, "date"]
    block_regime = labeled.loc[0, "regime"]
    for i in range(1, len(labeled)):
        if labeled.loc[i, "regime"] != block_regime:
            ax.axvspan(block_start, labeled.loc[i, "date"], color=REGIME_COLORS[block_regime], alpha=0.6, linewidth=0)
            block_start = labeled.loc[i, "date"]
            block_regime = labeled.loc[i, "regime"]
    ax.axvspan(block_start, labeled["date"].max(), color=REGIME_COLORS[block_regime], alpha=0.6, linewidth=0)

    ax.plot(df["date"], df["csi"], color="black", linewidth=1.6, label="CSI")
    ax.plot(df["date"], df["rolling_p33"], color="#555555", linewidth=0.8, linestyle="--", alpha=0.6, label="rolling 33rd/67th pct")
    ax.plot(df["date"], df["rolling_p67"], color="#555555", linewidth=0.8, linestyle="--", alpha=0.6)

    for start, end, event_label in EVENT_SPANS:
        end_ts = pd.Timestamp(end) if end else df["date"].max()
        ax.axvline(pd.Timestamp(start), color="#d9534f", linewidth=0.8, alpha=0.5)
        ax.annotate(
            event_label,
            xy=(pd.Timestamp(start), ax.get_ylim()[1] if False else 5.4),
            fontsize=8,
            color="#d9534f",
            rotation=90,
            va="top",
        )

    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("CSI (expanding z-score composite)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.2)
    fig.suptitle(
        "CSI regime classification — rolling 60-month terciles, no hysteresis "
        "(sanity check, not a final figure)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    FIGURES.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES / f"csi_regime_sanity_check_{datetime.now(timezone.utc):%Y%m%d}.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
