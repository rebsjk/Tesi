import pandas as pd
import pytest

from src.universe.build_constituent_panel import build_constituent_panel


def _sample_membership() -> pd.DataFrame:
    """Two entities, half-open contiguous intervals: E1 reconstitutes once
    and stays in the index (open-ended); E2 reconstitutes once and then
    leaves the index, leaving a gap after 2020-07-01."""
    return pd.DataFrame(
        {
            "entity_id": ["E1", "E1", "E2", "E2"],
            "weight": [0.60, 0.55, 0.40, 0.45],
            "start_date": pd.to_datetime(
                ["2020-01-01", "2020-04-01", "2020-01-01", "2020-04-01"]
            ),
            "end_date": pd.to_datetime(
                ["2020-04-01", None, "2020-04-01", "2020-07-01"]
            ),
        }
    )


def _sample_crosswalk() -> pd.DataFrame:
    return pd.DataFrame({"entity_id": ["E1", "E2"], "permno": [10, 20]})


def _sample_returns() -> pd.DataFrame:
    dates_10 = pd.to_datetime(
        ["2019-12-31", "2020-01-01", "2020-03-31", "2020-04-01", "2020-06-01"]
    )
    permno_10 = pd.DataFrame({"permno": 10, "date": dates_10, "ret": 0.01})

    dates_20 = pd.to_datetime(
        ["2020-01-01", "2020-04-01", "2020-06-30", "2020-07-01", "2020-08-01"]
    )
    permno_20 = pd.DataFrame({"permno": 20, "date": dates_20, "ret": 0.02})

    return pd.concat([permno_10, permno_20], ignore_index=True)


def test_reconstitution_boundary_date_uses_new_weight_not_old():
    panel = build_constituent_panel(
        _sample_membership(), _sample_crosswalk(), _sample_returns()
    )

    boundary = panel[(panel["permno"] == 10) & (panel["date"] == "2020-04-01")]
    assert len(boundary) == 1
    assert boundary["weight"].iloc[0] == pytest.approx(0.55)

    day_before = panel[(panel["permno"] == 10) & (panel["date"] == "2020-03-31")]
    assert day_before["weight"].iloc[0] == pytest.approx(0.60)


def test_return_before_first_membership_interval_is_excluded():
    panel = build_constituent_panel(
        _sample_membership(), _sample_crosswalk(), _sample_returns()
    )
    assert panel[(panel["permno"] == 10) & (panel["date"] == "2019-12-31")].empty


def test_gap_after_membership_ends_is_excluded_not_forward_filled():
    panel = build_constituent_panel(
        _sample_membership(), _sample_crosswalk(), _sample_returns()
    )
    # end_date is exclusive: 2020-07-01 itself is already outside membership.
    assert panel[(panel["permno"] == 20) & (panel["date"] == "2020-07-01")].empty
    assert panel[(panel["permno"] == 20) & (panel["date"] == "2020-08-01")].empty
    assert not panel[(panel["permno"] == 20) & (panel["date"] == "2020-06-30")].empty


def test_open_ended_interval_matches_dates_after_last_reconstitution():
    panel = build_constituent_panel(
        _sample_membership(), _sample_crosswalk(), _sample_returns()
    )
    row = panel[(panel["permno"] == 10) & (panel["date"] == "2020-06-01")]
    assert row["weight"].iloc[0] == pytest.approx(0.55)


def test_overlapping_membership_intervals_raise():
    membership = _sample_membership()
    membership.loc[membership["entity_id"] == "E1", "start_date"] = pd.to_datetime(
        ["2020-01-01", "2020-03-01"]  # now overlaps the first interval's end (2020-04-01)
    )
    with pytest.raises(AssertionError):
        build_constituent_panel(membership, _sample_crosswalk(), _sample_returns())


def test_duplicate_return_rows_raise_unique_grain_error():
    returns = _sample_returns()
    duplicate_row = returns.iloc[[1]]  # permno 10, 2020-01-01
    returns_with_dupe = pd.concat([returns, duplicate_row], ignore_index=True)

    with pytest.raises(AssertionError):
        build_constituent_panel(_sample_membership(), _sample_crosswalk(), returns_with_dupe)
