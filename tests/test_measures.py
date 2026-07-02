import pandas as pd
import pytest

from src.concentration.measures import (
    DEFAULT_CR_K,
    compute_concentration_panel,
    concentration_direction,
    concentration_ratio,
    effective_number_of_constituents,
    entropy_concentration,
    herfindahl_index,
)


def test_hhi_equals_one_over_n_for_equal_weights():
    assert herfindahl_index([0.25, 0.25, 0.25, 0.25]) == pytest.approx(0.25)


def test_hhi_equals_one_for_single_name_concentration():
    assert herfindahl_index([1.0, 0.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_hhi_renormalizes_weights_that_do_not_sum_to_one():
    assert herfindahl_index([0.3, 0.3, 0.3]) == pytest.approx(1 / 3)


def test_hhi_rejects_negative_weights():
    with pytest.raises(ValueError):
        herfindahl_index([0.5, -0.1, 0.6])


def test_hhi_rejects_all_zero_weights():
    with pytest.raises(ValueError):
        herfindahl_index([0.0, 0.0, 0.0])


def test_concentration_ratio_is_monotonic_and_clamps_k_to_n():
    w = [0.5, 0.3, 0.1, 0.1]
    assert concentration_ratio(w, 1) == pytest.approx(0.5)
    assert concentration_ratio(w, 2) == pytest.approx(0.8)
    assert concentration_ratio(w, 4) == pytest.approx(1.0)
    # k > n must clamp to n, not error or double-count
    assert concentration_ratio(w, 20) == pytest.approx(1.0)


def test_effective_n_moves_opposite_to_hhi():
    equal = [0.25, 0.25, 0.25, 0.25]
    skewed = [1.0, 0.0, 0.0, 0.0]
    assert herfindahl_index(skewed) > herfindahl_index(equal)
    assert effective_number_of_constituents(skewed) < effective_number_of_constituents(equal)
    assert effective_number_of_constituents(equal) == pytest.approx(4.0)
    assert effective_number_of_constituents(skewed) == pytest.approx(1.0)


def test_entropy_concentration_bounds_and_direction():
    equal = [0.25, 0.25, 0.25, 0.25]
    skewed = [0.97, 0.01, 0.01, 0.01]
    single = [1.0, 0.0, 0.0, 0.0]

    assert entropy_concentration(equal) == pytest.approx(0.0, abs=1e-9)
    assert entropy_concentration(single) == pytest.approx(1.0, abs=1e-9)
    assert 0.0 <= entropy_concentration(skewed) <= 1.0
    # same direction as hhi: more skewed => more concentrated
    assert entropy_concentration(skewed) > entropy_concentration(equal)


def test_concentration_direction_flags_effective_n_as_inverted():
    assert concentration_direction("hhi") == 1
    assert concentration_direction("entropy_concentration") == 1
    assert concentration_direction("effective_n") == -1
    assert concentration_direction("cr_10") == 1
    with pytest.raises(KeyError):
        concentration_direction("not_a_measure")


def test_compute_concentration_panel_matches_direct_calls_and_columns():
    weights_panel = pd.DataFrame(
        {
            "date": ["2020-01-01"] * 4 + ["2020-02-01"] * 4,
            "entity_id": ["A", "B", "C", "D"] * 2,
            "weight": [0.4, 0.3, 0.2, 0.1, 0.25, 0.25, 0.25, 0.25],
        }
    )
    out = compute_concentration_panel(weights_panel)

    assert list(out["date"]) == ["2020-01-01", "2020-02-01"]
    assert set(f"cr_{k}" for k in DEFAULT_CR_K).issubset(out.columns)

    row_jan = out.loc[out["date"] == "2020-01-01"].iloc[0]
    assert row_jan["hhi"] == pytest.approx(herfindahl_index([0.4, 0.3, 0.2, 0.1]))

    row_feb = out.loc[out["date"] == "2020-02-01"].iloc[0]
    assert row_feb["hhi"] == pytest.approx(0.25)
    assert row_feb["hhi"] < row_jan["hhi"]
