"""Discover CART A/E pockets on development data; test fixed leaves on holdout."""

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.tree import DecisionTreeRegressor

from .contracts import finite
from .mortality import full_credibility_deaths, poisson_ratio_interval


def benjamini_hochberg(pvalues):
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid p-values")
    if not len(p):
        return p
    order = np.argsort(p)
    adjusted = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    result = np.empty_like(p)
    result[order] = np.minimum(adjusted, 1)
    return result


def detect(
    development: pd.DataFrame,
    holdout: pd.DataFrame,
    features=None,
    confidence=0.95,
    relative_error=0.2,
    min_leaf=100,
):
    features = features or ["age", "duration", "smoker"]
    for data in (development, holdout):
        finite(data, features + ["deaths", "expected_deaths"], nonnegative=True)
        if (data.expected_deaths <= 0).any() or (data.deaths % 1 != 0).any():
            raise ValueError("Positive expectations and integer deaths are required")
    if "policy_id" in development and "policy_id" in holdout:
        if set(development.policy_id) & set(holdout.policy_id):
            raise ValueError("Discovery and confirmation policies must be disjoint")
    tree = DecisionTreeRegressor(max_depth=3, min_samples_leaf=min_leaf, random_state=42)
    tree.fit(
        development[features],
        development.deaths / development.expected_deaths,
        sample_weight=development.expected_deaths,
    )
    assigned = holdout.assign(leaf=tree.apply(holdout[features]))
    rows = []
    full = full_credibility_deaths(relative_error, confidence)
    for leaf, group in assigned.groupby("leaf"):
        actual, expected = int(group.deaths.sum()), float(group.expected_deaths.sum())
        low, high = poisson_ratio_interval(actual, expected, confidence)
        p = min(1.0, 2 * min(poisson.cdf(actual, expected), poisson.sf(actual - 1, expected)))
        rows.append(
            {
                "leaf": int(leaf),
                "rows": len(group),
                "actual": actual,
                "expected": expected,
                "ae": actual / expected,
                "ae_lower": low,
                "ae_upper": high,
                "credibility": min(1.0, np.sqrt(actual / full)),
                "p_value": p,
            }
        )
    result = pd.DataFrame(rows)
    result["q_value"] = benjamini_hochberg(result.p_value)
    result["review_flag"] = (result.q_value < 1 - confidence) & (result.credibility >= 1)
    return tree, result
