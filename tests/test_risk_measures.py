import numpy as np
import pytest

from src.concentration.risk_measures import (
    effective_n_risk,
    risk_concentration_direction,
    risk_contributions,
    risk_entropy,
    risk_share_topk,
)


def test_risk_contributions_sum_to_one_regardless_of_weight_scale():
    sigma = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.0], [0.0, 0.0, 0.16]])
    w_normalized = np.array([0.5, 0.3, 0.2])
    w_raw_scale = np.array([0.05, 0.03, 0.02])  # same proportions, sums to 0.10

    p_norm = risk_contributions(w_normalized, sigma)
    p_raw = risk_contributions(w_raw_scale, sigma)

    assert p_norm.sum() == pytest.approx(1.0)
    assert p_raw.sum() == pytest.approx(1.0)
    # Euler decomposition is scale-invariant in the RATIO, so both should
    # agree exactly despite the different overall weight scale.
    assert np.allclose(p_norm, p_raw)


def test_risk_contributions_uncorrelated_equal_vol_proportional_to_weight_squared():
    # Under diagonal Sigma (no correlation, equal variance across names),
    # (Sigma w)_i = var * w_i, so p_i = w_i^2 / sum(w_j^2) - NOT w_i itself.
    # This means risk concentration is mechanically MORE concentrated than
    # capital concentration whenever weights are unequal (squares skew a
    # dispersed weight vector further), a useful invariant to pin down here
    # since it is exactly the kind of thing a future collinearity check
    # needs to distinguish from genuine comovement-driven concentration.
    sigma = np.eye(3) * 0.04
    w = np.array([0.5, 0.3, 0.2])
    p = risk_contributions(w, sigma)
    expected = w**2 / np.sum(w**2)
    assert np.allclose(p, expected)
    assert p[0] > w[0]  # the largest name's risk share exceeds its capital share


def test_risk_contributions_equal_weights_equal_vol_matches_capital_share():
    # The one case where risk share and capital share DO coincide exactly:
    # equal weights (so w_i^2/sum(w_j^2) = w_i/sum(w_j) = w_i trivially).
    sigma = np.eye(3) * 0.04
    w = np.array([1 / 3, 1 / 3, 1 / 3])
    p = risk_contributions(w, sigma)
    assert np.allclose(p, w)


def test_risk_contributions_can_be_negative_for_hedging_name():
    # Name 3 is negatively correlated with the other two and small-weighted
    # -> its Euler contribution should be negative.
    sigma = np.array(
        [
            [0.04, 0.02, -0.01],
            [0.02, 0.04, -0.01],
            [-0.01, -0.01, 0.02],
        ]
    )
    w = np.array([0.45, 0.45, 0.10])
    p = risk_contributions(w, sigma)
    assert p[2] < 0
    assert p.sum() == pytest.approx(1.0)


def test_risk_contributions_rejects_nonpositive_portfolio_variance():
    sigma = np.zeros((2, 2))
    w = np.array([0.5, 0.5])
    with pytest.raises(ValueError):
        risk_contributions(w, sigma)


def test_risk_share_topk_uses_weight_based_mask_not_risk_ranking():
    sigma = np.eye(3) * 0.04
    w = np.array([0.5, 0.3, 0.2])
    top2_by_weight = np.array([True, True, False])
    share = risk_share_topk(w, sigma, top2_by_weight)
    # p = w^2 / sum(w^2) under diagonal Sigma (see risk_contributions test
    # above); top-2-by-weight (indices 0,1) risk share = (0.25+0.09)/0.38.
    assert share == pytest.approx((0.5**2 + 0.3**2) / (0.5**2 + 0.3**2 + 0.2**2))
    assert share > 0.8  # exceeds the capital weight share (0.8) of the same cohort


def test_effective_n_risk_matches_effective_n_when_risk_equals_weight():
    sigma = np.eye(4) * 0.04
    w_equal = np.array([0.25, 0.25, 0.25, 0.25])
    assert effective_n_risk(w_equal, sigma) == pytest.approx(4.0)

    w_skewed = np.array([1.0, 0.0, 0.0, 0.0])
    # degenerate (single name) - guard division, use a near-degenerate case
    w_near_skewed = np.array([0.97, 0.01, 0.01, 0.01])
    assert effective_n_risk(w_near_skewed, sigma) < effective_n_risk(w_equal, sigma)


def test_risk_entropy_bounds_and_direction():
    sigma = np.eye(4) * 0.04
    equal = np.array([0.25, 0.25, 0.25, 0.25])
    skewed = np.array([0.97, 0.01, 0.01, 0.01])

    assert risk_entropy(equal, sigma) == pytest.approx(0.0, abs=1e-9)
    assert 0.0 <= risk_entropy(skewed, sigma) <= 1.0
    assert risk_entropy(skewed, sigma) > risk_entropy(equal, sigma)


def test_risk_entropy_clips_negative_contributions_without_error():
    sigma = np.array(
        [
            [0.04, 0.02, -0.01],
            [0.02, 0.04, -0.01],
            [-0.01, -0.01, 0.02],
        ]
    )
    w = np.array([0.45, 0.45, 0.10])
    # must not raise despite a negative risk contribution present
    value = risk_entropy(w, sigma)
    assert 0.0 <= value <= 1.0


def test_risk_concentration_direction_flags_n_eff_risk_as_inverted():
    assert risk_concentration_direction("risk_share_top10") == 1
    assert risk_concentration_direction("risk_entropy") == 1
    assert risk_concentration_direction("n_eff_risk") == -1
    with pytest.raises(KeyError):
        risk_concentration_direction("not_a_measure")
