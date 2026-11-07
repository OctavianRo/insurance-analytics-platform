import numpy as np
import pandas as pd
import pytest

from insurance_analytics.mortality import (
    Assumptions,
    death_benefit_apv,
    full_credibility_deaths,
    poisson_ratio_interval,
    prepare,
    summarize,
)
from insurance_analytics.synthetic import experience


def test_apv_matches_two_year_hand_calculation():
    assert death_benefit_apv([0.1, 0.2], 0.05, 100) == pytest.approx(10 / 1.05 + 18 / 1.05**2)


def test_certain_death_and_empty_term():
    assert death_benefit_apv([1, 1], 0, 100) == 100
    assert death_benefit_apv([]) == 0
    assert death_benefit_apv([0, 0]) == 0


@pytest.mark.parametrize("qx,interest", [([1.1], 0), ([-0.1], 0), ([np.nan], 0), ([0.1], -1)])
def test_invalid_apv(qx, interest):
    with pytest.raises(ValueError):
        death_benefit_apv(qx, interest)


def test_zero_actual_interval_retains_upper_uncertainty():
    low, high = poisson_ratio_interval(0, 10)
    assert low == 0
    assert high == pytest.approx(-np.log(0.025) / 10)
    assert poisson_ratio_interval(0, 0) == (None, None)


def test_grouped_study_reconciles_and_assumptions_are_monotone():
    data = experience(500)
    base = prepare(data)
    doubled = prepare(data, Assumptions(multiplier=2))
    grouped = summarize(base, ["client"])
    assert grouped.deaths.sum() == data.deaths.sum()
    assert grouped.expected_deaths.sum() == pytest.approx(base.expected_deaths.sum())
    assert doubled.expected_deaths.sum() == pytest.approx(2 * base.expected_deaths.sum())
    improved = prepare(data.assign(study_year=2026))
    assert improved.expected_deaths.sum() == pytest.approx(0.99 * base.expected_deaths.sum())


def test_no_exposure_cannot_hide_deaths():
    frame = pd.DataFrame(
        {
            "exposure": [0],
            "deaths": [1],
            "expected_rate": [0.1],
            "sum_assured": [100],
            "study_year": [2025],
        }
    )
    with pytest.raises(ValueError):
        prepare(frame)
    assert full_credibility_deaths() == pytest.approx(384.145882, rel=1e-6)
