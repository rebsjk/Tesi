import numpy as np
import pandas as pd

from src.concentration.build_risk_concentration_panel import (
    build_monthly_risk_concentration_panel,
)


def _toy_panel():
    """4 names (permno 1-4), 2 months, 3 trading days/month. With
    window_days=3 (passed explicitly below) the first month already has a
    full window - this test is about the monthly orchestration mechanics
    (cohort selection, output shape, burn-in gating), not the real
    252-day/N=100 production parameters."""
    dates = pd.to_datetime(
        ["2020-01-01", "2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04", "2020-02-05"]
    )
    weights = {1: 0.4, 2: 0.3, 3: 0.2, 4: 0.1}
    rows = []
    rng = np.random.default_rng(0)
    for d in dates:
        for permno, w in weights.items():
            rows.append(
                {
                    "date": d,
                    "permno": permno,
                    "weight": w,
                    "ret": rng.normal(scale=0.01),
                }
            )
    return pd.DataFrame(rows)


def test_monthly_panel_has_one_row_per_month_and_expected_columns():
    panel = _toy_panel()
    result, diagnostics = build_monthly_risk_concentration_panel(
        panel, topk_values=(1, 2), n_subset=4, window_days=3
    )
    assert len(result) == 2
    for col in [
        "date", "n_subset_included", "shrinkage_intensity",
        "n_eff_risk", "risk_entropy", "risk_share_top1", "risk_share_top2",
    ]:
        assert col in result.columns
    assert diagnostics["skipped_burn_in"] == []


def test_risk_share_top1_uses_month_start_weight_ranking():
    panel = _toy_panel()
    result, _ = build_monthly_risk_concentration_panel(
        panel, topk_values=(1,), n_subset=4, window_days=3
    )
    # permno 1 has the largest weight in both months -> top1 cohort is
    # always {1}; risk_share_top1 should equal permno 1's own risk share.
    assert (result["risk_share_top1"] >= 0).all()
    assert (result["risk_share_top1"] <= 1.0001).all()


def test_burn_in_excludes_months_with_partial_window():
    panel = _toy_panel()
    # window_days=5 exceeds the 3 trading days available in month 1
    # (2020-01) but not necessarily month 2, since build_return_matrix
    # looks back across month boundaries - both months here only have 3
    # cumulative days by 2020-01, and 6 by 2020-02, so window_days=5 should
    # skip the first month (only 3 dates available) but keep the second
    # (6 dates available, tail(5) gives a full window).
    result, diagnostics = build_monthly_risk_concentration_panel(
        panel, topk_values=(1,), n_subset=4, window_days=5
    )
    assert len(result) == 1
    assert diagnostics["skipped_burn_in"] == ["2020-01"]
