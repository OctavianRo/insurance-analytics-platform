import numpy as np
import pytest

from insurance_analytics.synthetic import applications
from insurance_analytics.underwriting import acceleration_policy, train


@pytest.fixture(scope="module")
def apps():
    return applications(1500)


@pytest.fixture(scope="module")
def fitted(apps):
    return train(apps)


def test_temporal_holdout_and_signal(apps, fitted):
    assert set(fitted.train_ids).isdisjoint(fitted.test_ids)
    before = apps.loc[apps.application_id.isin(fitted.train_ids), "applied_at"]
    after = apps.loc[apps.application_id.isin(fitted.test_ids), "applied_at"]
    assert before.max() < after.min()
    assert fitted.metrics["roc_auc"] > 0.65
    assert 0 < fitted.metrics["brier"] < 0.25


def test_unseen_channels_and_missing_lab_are_supported(apps, fitted):
    sample = apps.iloc[:5].copy()
    sample["channel"] = "new-channel"
    sample["a1c"] = np.nan
    p = fitted.predict(sample)
    assert np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()


def test_duplicate_applicant_rejected(apps):
    with pytest.raises(ValueError, match="unique"):
        train(apps.assign(application_id="same"))


def test_nonbinary_target_rejected(apps):
    with pytest.raises(ValueError, match="0 and 1"):
        train(apps.assign(impaired=2))


def test_acceleration_requires_dedicated_target(apps, fitted):
    with pytest.raises(ValueError):
        acceleration_policy(fitted, apps)
    model = train(apps, "requires_full_review")
    held = apps.loc[apps.application_id.isin(model.test_ids)]
    none = acceleration_policy(model, held, threshold=0)
    assert none["candidates"] == 0
    assert none["missed_review_rate_among_candidates"] is None


def test_xgboost_backend(apps):
    pytest.importorskip("xgboost")
    fitted = train(apps, backend="xgboost")
    assert fitted.metrics["roc_auc"] > 0.6
