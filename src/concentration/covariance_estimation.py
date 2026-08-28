"""Phase-2 covariance estimation for risk concentration (and, in a future
build, dependence concentration - both are meant to reuse the SAME Sigma_t
estimated here, per docs/methodology_notes/csi_construction.md's explicit
instruction not to use two independently-chosen estimation windows for the
two measures).

Point-in-time top-N subset selection reuses the global top-k/top-N
convention already frozen in csi_construction.md ("Top-k subset selection
and reselection convention"): anchored at each calendar month's first
available trading date, held fixed for the whole month.

Sigma_t is estimated from a TRAILING WINDOW_TRADING_DAYS-day window of
DAILY returns ending at the month-END date, not the month-start anchor
date - the subset composition and the estimation window deliberately use
two different dates: the subset is "who's eligible this month" (frozen at
month-start), the covariance is "what does their risk look like as of the
most recent available data" (month-end), matching how
build_concentration_panel.py already treats CR-k (cohort selected at
month-start, evaluated at month-end).

252 trading days (~12 months), not the ~60-90 day figure csi_construction.md
mentions for return-space concentration: that figure was never a decided
value for THIS use (verified - no "Decision" block for it exists), and the
two measures face different problems. Return-space concentration's R^2
regression degrades gracefully with a short window; an N x N covariance
matrix does not - with N=100 and a 60-90 day window, T < N and the sample
covariance is singular by construction, before any shrinkage is even
applied. 252 days gives T/N ~ 2.5, a defensible ratio for Ledoit-Wolf
shrinkage (see below) without making the window so long the measure goes
stale relative to the CSI's monthly cadence.

Shrinkage: Ledoit & Wolf (2004, "Honey, I Shrunk the Sample Covariance
Matrix", Journal of Portfolio Management) - constant-correlation-matrix
target, NOT the identity-matrix target implemented by
sklearn.covariance.LedoitWolf. That class implements a DIFFERENT 2004
Ledoit-Wolf paper ("A Well-Conditioned Estimator for Large-Dimensional
Covariance Matrices", Journal of Multivariate Analysis) - shrinking toward
scaled identity would compress each name's own variance toward a common
scale, which is exactly the individual-risk-level information this measure
needs to keep. The constant-correlation target instead preserves each
name's own sample variance on the diagonal and shrinks only the
off-diagonal correlation structure toward the sample average pairwise
correlation. Implemented directly here (not via scikit-learn, which is not
a dependency of this project and would give the wrong target regardless) -
a direct port of the reference algorithm publicly circulated as
`covCor.m`.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

N_SUBSET = 100
WINDOW_TRADING_DAYS = 252


def select_topN_subset(panel: pd.DataFrame, as_of_date, n: int = N_SUBSET) -> list:
    """Top-`n` permnos by `weight` as of `as_of_date` (exact date match).

    Callers pass the calendar month's first available trading date, per
    the frozen top-k/top-N subset selection convention in
    docs/methodology_notes/csi_construction.md - this function itself does
    not know or care which date semantics the caller intends, it just
    ranks whatever single date it's given.
    """
    day = panel.loc[panel["date"] == as_of_date]
    if day.empty:
        raise ValueError(f"no panel rows found for as_of_date={as_of_date}")
    return day.set_index("permno")["weight"].nlargest(n).index.tolist()


class ReturnMatrixResult(NamedTuple):
    returns: pd.DataFrame  # T x N_included, index=date, columns=permno
    included: list
    excluded_insufficient_history: list
    n_window_dates: int


def build_return_matrix(
    panel: pd.DataFrame,
    subset_permnos: list,
    window_end_date,
    window_days: int = WINDOW_TRADING_DAYS,
) -> ReturnMatrixResult:
    """Trailing `window_days`-trading-day return matrix for
    `subset_permnos`, ending at `window_end_date` (inclusive) - uses only
    rows with date <= window_end_date, so this is point-in-time safe by
    construction.

    Names in `subset_permnos` without a COMPLETE (no-NaN) return series
    over the full window are EXCLUDED (complete-case), not
    pairwise-imputed: a pairwise-complete covariance matrix is not
    guaranteed positive semi-definite, which would break the Ledoit-Wolf
    shrinkage target's assumptions. This is most commonly a recent index
    entrant or recent IPO - src/universe/build_constituent_panel.py only
    retains a return observation while a permno is an actual index
    constituent, so a name that joined the index partway through the
    window structurally has no earlier row here to draw on, regardless of
    its actual pre-entry trading history.
    """
    sub = panel.loc[
        (panel["permno"].isin(subset_permnos)) & (panel["date"] <= window_end_date)
    ]
    wide = sub.pivot(index="date", columns="permno", values="ret").sort_index()
    wide = wide.tail(window_days)

    n_window_dates = len(wide)
    complete = wide.dropna(axis=1, how="any")
    # A subset name entirely absent from `wide` (e.g. zero rows before
    # window_end_date - a brand-new listing) is also "excluded", not just
    # one with some NaNs within an otherwise-present column.
    included = [p for p in subset_permnos if p in complete.columns]
    excluded = [p for p in subset_permnos if p not in included]

    return ReturnMatrixResult(
        returns=complete[included],
        included=included,
        excluded_insufficient_history=excluded,
        n_window_dates=n_window_dates,
    )


def ledoit_wolf_constant_correlation(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage toward a constant-correlation target (Ledoit &
    Wolf 2004, JPM - see module docstring for why this is NOT
    sklearn.covariance.LedoitWolf's target). Direct port of the reference
    `covCor.m` algorithm (Ledoit and Wolf's own published MATLAB code).

    `returns`: T x N array, T observations (rows) on N names (columns), no
    NaNs (caller's responsibility - see build_return_matrix's complete-case
    filtering).

    Returns (sigma, shrinkage_intensity). `sigma` is guaranteed symmetric,
    and because the target is a full-rank constant-correlation matrix,
    `sigma` is guaranteed invertible even when T < N (unlike the raw
    sample covariance matrix, which is singular whenever T < N) - this is
    the whole point of using shrinkage here rather than the sample
    covariance matrix directly. `sigma`'s diagonal always equals the
    sample variances exactly, regardless of the shrinkage intensity: the
    target's diagonal is defined to equal the sample variance too, so the
    convex combination leaves the diagonal unchanged - only the
    off-diagonal correlation structure is actually shrunk.
    """
    x = np.asarray(returns, dtype=float)
    t, n = x.shape
    if t < 2:
        raise ValueError("need at least 2 observations to estimate a covariance matrix")
    if n < 2:
        raise ValueError("need at least 2 names to estimate a covariance matrix")
    x = x - x.mean(axis=0, keepdims=True)

    sample = (x.T @ x) / t
    var = np.diag(sample).copy()
    sqrtvar = np.sqrt(var)
    outer_sqrtvar = np.outer(sqrtvar, sqrtvar)

    r_bar = (np.sum(sample / outer_sqrtvar) - n) / (n * (n - 1))
    target = r_bar * outer_sqrtvar
    np.fill_diagonal(target, var)

    y = x**2
    phi_mat = (y.T @ y) / t - sample**2
    phi = phi_mat.sum()

    term1 = ((x**3).T @ x) / t
    help_ = (x.T @ x) / t
    help_diag = np.diag(help_)
    term2 = help_diag[:, None] * sample
    term3 = help_ * var[:, None]
    term4 = var[:, None] * sample
    theta_mat = term1 - term2 - term3 + term4
    np.fill_diagonal(theta_mat, 0.0)
    rho = np.trace(phi_mat) + r_bar * np.sum(
        (1.0 / sqrtvar)[:, None] * sqrtvar[None, :] * theta_mat
    )

    gamma = np.sum((sample - target) ** 2)
    kappa = (phi - rho) / gamma
    shrinkage = float(np.clip(kappa / t, 0.0, 1.0))

    sigma = shrinkage * target + (1 - shrinkage) * sample
    return sigma, shrinkage


class SigmaEstimate(NamedTuple):
    sigma: pd.DataFrame  # indexed/columned by permno, included names only
    weights: pd.Series  # actual point-in-time weight, included names only
    subset_permnos: list  # nominal top-N cohort, before history exclusion
    included: list
    excluded_insufficient_history: list
    shrinkage_intensity: float
    n_window_dates: int


def estimate_sigma_t(
    panel: pd.DataFrame,
    subset_anchor_date,
    window_end_date,
    n: int = N_SUBSET,
    window_days: int = WINDOW_TRADING_DAYS,
) -> SigmaEstimate:
    """Orchestrates subset selection (anchored at `subset_anchor_date`,
    normally the calendar month's first trading date) + trailing-window
    return matrix (ending at `window_end_date`, normally month-end) +
    Ledoit-Wolf shrinkage, and pairs the result with each included name's
    ACTUAL point-in-time weight at `window_end_date` (not renormalized to
    sum to 1 over the subset - see risk_measures.risk_contributions for
    why that's safe: the risk-share identity holds regardless of scale by
    Euler's theorem).
    """
    subset = select_topN_subset(panel, subset_anchor_date, n)
    rm = build_return_matrix(panel, subset, window_end_date, window_days)

    if rm.excluded_insufficient_history:
        logger.info(
            "%s: %d of %d nominal top-%d names excluded from Sigma_t "
            "(insufficient trailing return history): %s",
            window_end_date,
            len(rm.excluded_insufficient_history),
            n,
            n,
            rm.excluded_insufficient_history,
        )

    sigma_array, shrinkage = ledoit_wolf_constant_correlation(rm.returns.to_numpy())
    sigma = pd.DataFrame(sigma_array, index=rm.included, columns=rm.included)

    end_day = panel.loc[panel["date"] == window_end_date].set_index("permno")["weight"]
    weights = end_day.reindex(rm.included)
    missing_weight = weights.isna()
    if missing_weight.any():
        # A name with a complete return window but no weight observation
        # exactly at window_end_date (e.g. delisted between its last
        # return row and month-end) - dropped from the returned estimate
        # entirely rather than silently feeding a NaN weight downstream.
        dropped = weights[missing_weight].index.tolist()
        logger.warning(
            "%s: %d name(s) had a complete return window but no weight "
            "observation at window_end_date, dropped: %s",
            window_end_date,
            len(dropped),
            dropped,
        )
        keep = weights.dropna().index.tolist()
        weights = weights.loc[keep]
        sigma = sigma.loc[keep, keep]

    return SigmaEstimate(
        sigma=sigma,
        weights=weights,
        subset_permnos=subset,
        included=weights.index.tolist(),
        excluded_insufficient_history=rm.excluded_insufficient_history,
        shrinkage_intensity=shrinkage,
        n_window_dates=rm.n_window_dates,
    )
