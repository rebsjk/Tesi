"""
Quick internal sanity-check plot for the risk-concentration monthly panel —
small multiples of risk_share_top5/7/10, n_eff_risk, risk_entropy,
shrinkage_intensity, and subset coverage, 2000-today, with the SAME shaded
event spans (GFC, COVID, Mag7/AI) already used in
`plot_concentration_sanity_check.py` (imported directly, not redefined) so
the two sanity-check figures are visually comparable. Not a polished/
deliverable figure — a diagnostic.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.concentration.plot_concentration_sanity_check import EVENT_SPANS  # noqa: E402
from src.utils.paths import CONCENTRATION_FINAL, FIGURES, latest_raw_file  # noqa: E402

PANELS = [
    ("risk_share_top5", "Risk share, top-5 (by weight)"),
    ("risk_share_top7", "Risk share, top-7"),
    ("risk_share_top10", "Risk share, top-10"),
    ("n_eff_risk", "Effective N (risk-space, inverted direction)"),
    ("risk_entropy", "Risk entropy (1 - normalized Shannon entropy of p_i,t)"),
    ("shrinkage_intensity", "Ledoit-Wolf shrinkage intensity"),
    ("n_subset_included", "Names included in Sigma_t (of nominal top-100)"),
]


def main() -> None:
    panel_path = latest_raw_file(CONCENTRATION_FINAL, "risk_concentration_measures_monthly")
    df = pd.read_csv(panel_path, parse_dates=["date"])

    fig, axes = plt.subplots(len(PANELS), 1, figsize=(11, 16), sharex=True)

    for ax, (col, label) in zip(axes, PANELS):
        ax.plot(df["date"], df[col], color="#1f4e79", linewidth=1.2)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(alpha=0.25)
        for start, end, event_label in EVENT_SPANS:
            end_ts = pd.Timestamp(end) if end else df["date"].max()
            ax.axvspan(pd.Timestamp(start), end_ts, color="#d9534f", alpha=0.08)

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
        "Risk-concentration measures — monthly, month-end, top-100 subset, "
        "252-trading-day Ledoit-Wolf Sigma_t (sanity check, not a final figure)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    FIGURES.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES / f"risk_concentration_sanity_check_{datetime.now(timezone.utc):%Y%m%d}.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
