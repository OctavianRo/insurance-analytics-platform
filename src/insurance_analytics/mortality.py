"""Experience analysis, exact Poisson intervals, and end-of-year death benefit APV."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

from .contracts import finite, require_columns


@dataclass(frozen=True)
class Assumptions:
    multiplier: float = 1.0
    annual_improvement: float = 0.01
    base_year: int = 2025

    def __post_init__(self):
        if not np.isfinite(self.multiplier) or self.multiplier <= 0:
            raise ValueError("Multiplier must be positive")
        if not 0 <= self.annual_improvement < 1:
            raise ValueError("Improvement must be in [0, 1)")


def prepare(frame: pd.DataFrame, assumptions: Assumptions | None = None) -> pd.DataFrame:
    assumptions = assumptions or Assumptions()
    finite(frame, ["exposure", "deaths", "expected_rate", "sum_assured"], nonnegative=True)
    finite(frame, ["study_year"])
    if not np.equal(frame.deaths, np.floor(frame.deaths)).all():
        raise ValueError("Deaths must be integer counts")
    if ((frame.exposure == 0) & (frame.deaths > 0)).any():
        raise ValueError("Deaths with zero exposure")
    result = frame.copy()
    result["adjusted_rate"] = (
        result.expected_rate
        * assumptions.multiplier
        * (1 - assumptions.annual_improvement) ** (result.study_year - assumptions.base_year)
    )
    result["expected_deaths"] = result.exposure * result.adjusted_rate
    result["actual_claims"] = result.deaths * result.sum_assured
    result["expected_claims"] = result.expected_deaths * result.sum_assured
    return result


def poisson_ratio_interval(actual: int, expected: float, confidence: float = 0.95):
    if actual < 0 or int(actual) != actual or not np.isfinite(expected) or expected < 0:
        raise ValueError("Invalid actual/expected counts")
    if not 0 < confidence < 1:
        raise ValueError("Confidence must be in (0, 1)")
    if expected == 0:
        return None, None
    alpha = 1 - confidence
    low = 0.0 if actual == 0 else chi2.ppf(alpha / 2, 2 * actual) / (2 * expected)
    high = chi2.ppf(1 - alpha / 2, 2 * (actual + 1)) / (2 * expected)
    return float(low), float(high)


def summarize(frame: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    require_columns(frame, ["expected_deaths", "actual_claims", "expected_claims"])
    columns = ["exposure", "deaths", "expected_deaths", "actual_claims", "expected_claims"]
    totals = (
        frame.groupby(by, dropna=False)[columns].sum().reset_index()
        if by
        else pd.DataFrame([frame[columns].sum()])
    )
    totals["ae_count"] = totals.deaths / totals.expected_deaths.replace(0, np.nan)
    totals["ae_amount"] = totals.actual_claims / totals.expected_claims.replace(0, np.nan)
    intervals = [
        poisson_ratio_interval(int(a), float(e))
        for a, e in zip(totals.deaths, totals.expected_deaths, strict=True)
    ]
    totals[["ae_lower", "ae_upper"]] = pd.DataFrame(intervals, index=totals.index)
    return totals


def full_credibility_deaths(relative_error: float = 0.1, confidence: float = 0.95) -> float:
    if not 0 < relative_error < 1 or not 0 < confidence < 1:
        raise ValueError("Error and confidence must be in (0, 1)")
    return float((norm.ppf((1 + confidence) / 2) / relative_error) ** 2)


def death_benefit_apv(qx, interest: float = 0.03, benefit: float = 1.0) -> float:
    """Term insurance: annual qx conditional on survival; benefit paid at year end."""
    qx = np.asarray(qx, dtype=float)
    if qx.ndim != 1 or not np.isfinite(qx).all() or ((qx < 0) | (qx > 1)).any():
        raise ValueError("qx must be a finite one-dimensional probability vector")
    if not np.isfinite(interest) or interest <= -1 or not np.isfinite(benefit) or benefit < 0:
        raise ValueError("Invalid interest or benefit")
    survival = np.r_[1.0, np.cumprod(1 - qx)[:-1]] if qx.size else np.array([])
    return float(benefit * np.sum(survival * qx / (1 + interest) ** np.arange(1, len(qx) + 1)))
