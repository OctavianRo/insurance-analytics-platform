"""Seeded, entirely fictional records. No real pricing tables or medical records."""

import numpy as np
import pandas as pd
from scipy.special import expit


def applications(n: int = 3000, seed: int = 42) -> pd.DataFrame:
    if n < 20:
        raise ValueError("Generate at least 20 applications")
    rng = np.random.default_rng(seed)
    age = rng.integers(20, 76, n)
    bmi = rng.normal(27, 5, n).clip(15, 48)
    smoker = rng.binomial(1, 0.18, n)
    rx = rng.poisson(1.6, n)
    a1c = rng.normal(5.5 + 0.045 * (bmi - 25), 0.6, n).clip(3.5, 12)
    p = expit(
        -3.4 + 0.04 * (age - 40) + 0.14 * (bmi - 25) + 0.8 * smoker + 0.3 * rx + 0.8 * (a1c - 5.5)
    )
    impaired = rng.binomial(1, p)
    # Independently observed synthetic need for full review; not the inverse impairment label.
    review = rng.binomial(1, expit(-3 + 2 * impaired + 0.3 * rx + 0.7 * smoker))
    result = pd.DataFrame(
        {
            "application_id": [f"SYN-{i:07d}" for i in range(n)],
            "applied_at": pd.date_range("2024-01-01", periods=n, freq="h"),
            "age": age,
            "bmi": bmi,
            "smoker": smoker,
            "rx_count": rx,
            "a1c": a1c,
            "channel": rng.choice(["direct", "broker", "partner"], n),
            "impaired": impaired,
            "requires_full_review": review,
        }
    )
    result.loc[rng.random(n) < 0.05, "a1c"] = np.nan
    return result


def experience(n: int = 4000, seed: int = 43) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.integers(25, 86, n)
    duration = rng.integers(1, 21, n)
    smoker = rng.binomial(1, 0.16, n)
    exposure = rng.uniform(0.1, 1, n)
    qx = np.minimum(0.4, 0.0007 * np.exp(0.075 * (age - 35)) * (1 + 1.3 * smoker))
    hazard = -np.log1p(-qx) * np.where(duration < 3, 0.8, 1.0)
    death_time = rng.exponential(1 / hazard)
    observed = np.minimum(death_time, exposure)
    return pd.DataFrame(
        {
            "policy_id": [f"POL-{i:07d}" for i in range(n)],
            "study_year": 2025,
            "age": age,
            "duration": duration,
            "smoker": smoker,
            "sex": rng.choice(["F", "M"], n),
            "exposure": observed,
            "deaths": (death_time <= exposure).astype(int),
            "expected_rate": hazard,
            "sum_assured": rng.integers(50, 1001, n) * 1000,
            "client": rng.choice(["Aster", "Birch", "Cedar"], n),
        }
    )


def premium_transactions(seed: int = 44) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 240
    return pd.DataFrame(
        {
            "transaction_id": [f"TX-{i:05d}" for i in range(n)],
            "policy_id": [f"POL-{i % 80:07d}" for i in range(n)],
            "accounting_date": pd.date_range("2025-01-01", periods=n, freq="D"),
            "client": rng.choice(["Aster", "Birch", "Cedar"], n),
            "currency": "USD",
            "gross_premium": rng.integers(10000, 300000, n) / 100,
            "ceded_share": rng.choice([0.25, 0.5, 0.75], n),
            "sum_assured": rng.integers(50, 1001, n) * 1000,
        }
    )
