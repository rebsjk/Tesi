import numpy as np
import pandas as pd
import pytest

from src.concentration.covariance_estimation import (
    build_return_matrix,
    estimate_sigma_t,
    ledoit_wolf_constant_correlation,
    select_topN_subset,
)


def _toy_panel():
    """3 names, 3 dates. C has a missing return on the middle date (e.g. a
    recent entrant with incomplete trailing history)."""
    dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    rows = []
    for d, ret_a, ret_b, ret_c, w_a, w_b, w_c in [
        (dates[0], 0.01, -0.02, np.nan, 0.5, 0.3, 0.2),
        (dates[1], 0.02, 0.01, np.nan, 0.5, 0.3, 0.2),
        (dates[2], -0.01, 0.03, 0.02, 0.5, 0.3, 0.2),
    ]:
        rows += [
            {"date": d, "permno": 1, "ret": ret_a, "weight": w_a},
            {"date": d, "permno": 2, "ret": ret_b, "weight": w_b},
            {"date": d, "permno": 3, "ret": ret_c, "weight": w_c},
        ]
    return pd.DataFrame(rows)


def test_select_topN_subset_ranks_by_weight_descending():
    panel = _toy_panel()
    subset = select_topN_subset(panel, pd.Timestamp("2020-01-01"), n=2)
    assert subset == [1, 2]


def test_select_topN_subset_raises_on_missing_date():
    panel = _toy_panel()
    with pytest.raises(ValueError):
        select_topN_subset(panel, pd.Timestamp("2019-01-01"), n=2)


def test_build_return_matrix_excludes_incomplete_history_name():
    panel = _toy_panel()
    result = build_return_matrix(
        panel, subset_permnos=[1, 2, 3], window_end_date=pd.Timestamp("2020-01-03"), window_days=3
    )
    assert result.included == [1, 2]
    assert result.excluded_insufficient_history == [3]
    assert result.returns.shape == (3, 2)


def test_build_return_matrix_never_uses_dates_after_window_end():
    panel = _toy_panel()
    result = build_return_matrix(
        panel, subset_permnos=[1, 2], window_end_date=pd.Timestamp("2020-01-02"), window_days=3
    )
    assert result.returns.index.max() == pd.Timestamp("2020-01-02")
    assert len(result.returns) == 2


def _random_returns(t, n, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(scale=0.01, size=(t, n))


def test_ledoit_wolf_shrinkage_in_unit_interval():
    x = _random_returns(300, 20, seed=1)
    _, shrinkage = ledoit_wolf_constant_correlation(x)
    assert 0.0 <= shrinkage <= 1.0


def test_ledoit_wolf_output_symmetric():
    x = _random_returns(300, 15, seed=2)
    sigma, _ = ledoit_wolf_constant_correlation(x)
    assert np.allclose(sigma, sigma.T)


def test_ledoit_wolf_diagonal_equals_sample_variance():
    x = _random_returns(300, 15, seed=3)
    sample_var = np.var(x, axis=0, ddof=0)
    sigma, _ = ledoit_wolf_constant_correlation(x)
    assert np.allclose(np.diag(sigma), sample_var)


def test_ledoit_wolf_invertible_and_psd_when_T_less_than_N():
    # T=30 < N=100 - the raw sample covariance matrix here is singular by
    # construction; the shrinkage estimator must still be invertible.
    x = _random_returns(30, 100, seed=4)
    sigma, shrinkage = ledoit_wolf_constant_correlation(x)
    eigvals = np.linalg.eigvalsh(sigma)
    assert eigvals.min() > -1e-8  # PSD (allow tiny float noise)
    assert np.linalg.matrix_rank(sigma) == 100  # fully invertible
    assert shrinkage > 0  # some shrinkage must occur when T < N


def test_ledoit_wolf_high_T_relative_to_N_gives_small_shrinkage():
    x = _random_returns(2000, 10, seed=5)
    _, shrinkage_high_t = ledoit_wolf_constant_correlation(x)
    x_low_t = x[:20]
    _, shrinkage_low_t = ledoit_wolf_constant_correlation(x_low_t)
    assert shrinkage_high_t < shrinkage_low_t


def test_estimate_sigma_t_end_to_end_on_toy_panel():
    panel = _toy_panel()
    result = estimate_sigma_t(
        panel,
        subset_anchor_date=pd.Timestamp("2020-01-01"),
        window_end_date=pd.Timestamp("2020-01-03"),
        n=3,
        window_days=3,
    )
    # name 3 lacked history in [01-01, 01-03] -> excluded from Sigma_t
    assert result.excluded_insufficient_history == [3]
    assert result.included == [1, 2]
    assert list(result.weights.index) == [1, 2]
    assert result.sigma.shape == (2, 2)
