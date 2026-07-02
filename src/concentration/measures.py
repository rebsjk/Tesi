"""Phase-2 concentration measures.

Each measure is implemented independently and is individually auditable —
none of them are combined here. CSI aggregation (choosing how these measures
combine into the composite state index) is phase 3, implemented in
src/csi/ once the methodology in docs/methodology_notes/csi_construction.md
is settled.

All functions take a single date's weights (a 1-D array of constituent
weights, any order) and return a scalar. `compute_concentration_panel`
applies them across a full date-entity weights panel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_CR_K = (1, 5, 10, 20)
_WEIGHT_SUM_TOLERANCE = 1e-3


def _normalized_weights(weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    if np.any(weights < 0):
        raise ValueError("weights must be non-negative")
    total = weights.sum()
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        # Small deviations from 1.0 are expected (index-methodology rounding,
        # cash drag). Renormalize rather than let it distort every measure,
        # but this is exactly the kind of drift data-validator should also
        # be flagging at the panel level.
        weights = weights / total
    return weights


def herfindahl_index(weights: np.ndarray) -> float:
    """HHI = sum(w_i^2). Ranges from 1/N (perfectly diffuse) to 1 (single name)."""
    w = _normalized_weights(weights)
    return float(np.sum(w**2))


def concentration_ratio(weights: np.ndarray, k: int) -> float:
    """CR-k = sum of the k largest weights."""
    w = _normalized_weights(weights)
    if k <= 0:
        raise ValueError("k must be a positive integer")
    k = min(k, w.size)
    top_k = np.sort(w)[::-1][:k]
    return float(top_k.sum())


def effective_number_of_constituents(weights: np.ndarray) -> float:
    """1/HHI — the number of equal-weight names that would produce the same HHI.

    Directionality warning: unlike every other measure in this module, a
    HIGHER effective_n means LESS concentration. See CONCENTRATION_DIRECTION
    — averaging this in with hhi/cr_k/entropy_concentration without sign-
    flipping it first will partially cancel the others instead of
    reinforcing them.
    """
    hhi = herfindahl_index(weights)
    return float(1.0 / hhi)


def entropy_concentration(weights: np.ndarray) -> float:
    """1 - normalized Shannon entropy, so higher = more concentrated.

    Raw Shannon entropy H = -sum(w_i * ln(w_i)) is a diffuseness measure
    (higher = more spread out), the opposite convention from HHI/CR-k. This
    flips it to `1 - H/ln(N)` so all measures in this module agree on
    direction: 0 = maximally diffuse, 1 = single-name concentration. Only
    positive weights contribute to H (0 * ln(0) is defined as 0).
    """
    w = _normalized_weights(weights)
    n = w.size
    if n <= 1:
        return 1.0
    nonzero = w[w > 0]
    h = float(-np.sum(nonzero * np.log(nonzero)))
    h_max = np.log(n)
    return float(1.0 - h / h_max)


MEASURES = {
    "hhi": herfindahl_index,
    "effective_n": effective_number_of_constituents,
    "entropy_concentration": entropy_concentration,
}

# +1: higher value = more concentrated (aggregation-ready sign as-is).
# -1: higher value = LESS concentrated (must be sign-flipped, e.g. negated
# or inverted, before combining with +1 measures in any z-score/PCA
# aggregation in src/csi/). cr_k measures are all +1 for any k.
CONCENTRATION_DIRECTION = {
    "hhi": 1,
    "effective_n": -1,
    "entropy_concentration": 1,
}


def concentration_direction(measure_name: str) -> int:
    """Aggregation sign for a measure name (handles dynamic cr_<k> columns)."""
    if measure_name in CONCENTRATION_DIRECTION:
        return CONCENTRATION_DIRECTION[measure_name]
    if measure_name.startswith("cr_"):
        return 1
    raise KeyError(f"no known concentration-direction sign for '{measure_name}'")


def compute_concentration_panel(
    weights_panel: pd.DataFrame,
    date_col: str = "date",
    entity_col: str = "entity_id",
    weight_col: str = "weight",
    cr_k_values: tuple[int, ...] = DEFAULT_CR_K,
) -> pd.DataFrame:
    """Compute every measure in this module, per date, from a long weights panel.

    `weights_panel` is expected in the shape produced by
    src/universe/build_constituent_panel.py: one row per (date, entity_id)
    with a `weight` column. Output has one row per date.
    """
    required = {date_col, entity_col, weight_col}
    missing = required - set(weights_panel.columns)
    if missing:
        raise ValueError(f"weights_panel is missing columns: {missing}")

    records = []
    for date, group in weights_panel.groupby(date_col, sort=True):
        w = group[weight_col].to_numpy()
        row = {
            date_col: date,
            "n_constituents": w.size,
            "hhi": herfindahl_index(w),
            "effective_n": effective_number_of_constituents(w),
            "entropy_concentration": entropy_concentration(w),
        }
        for k in cr_k_values:
            row[f"cr_{k}"] = concentration_ratio(w, k)
        records.append(row)

    return pd.DataFrame.from_records(records).sort_values(date_col).reset_index(drop=True)
