import numpy as np
import pandas as pd
import pytest

from insurance_analytics.differentials import benjamini_hochberg, detect
from insurance_analytics.embeddings import MortalityEmbedding
from insurance_analytics.mortality import prepare
from insurance_analytics.survival import CoxPH, concordance_index
from insurance_analytics.synthetic import experience


def test_cox_recovers_risk_direction_and_survival_decreases():
    rng = np.random.default_rng(4)
    x = rng.normal(size=(1000, 1))
    event_time = rng.exponential(1 / (0.6 * np.exp(0.8 * x[:, 0])))
    censor = rng.uniform(0.2, 3, len(x))
    time = np.minimum(event_time, censor)
    event = (event_time <= censor).astype(int)
    model = CoxPH().fit(x, time, event)
    assert model.coef_[0] > 0.5
    curves = model.predict_survival([[-1], [1]], [0, 0.5, 1, 2])
    assert np.all(np.diff(curves, axis=1) <= 0)
    assert (curves[:, 0] == 1).all()
    assert curves[1, -1] < curves[0, -1]
    assert concordance_index(time, event, x[:, 0]) > 0.6


def test_cox_breslow_ties_and_no_events():
    model = CoxPH().fit([[0], [1], [2], [3]], [1, 1, 2, 3], [1, 1, 1, 0])
    assert np.isfinite(model.predict_survival([[1]], [0, 1, 2])).all()
    with pytest.raises(ValueError, match="observed death"):
        CoxPH().fit([[0], [1]], [1, 2], [0, 0])
    assert concordance_index([1, 1], [1, 0], [0.1, 0.2]) is None


def test_bh_matches_known_example():
    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.2]) == pytest.approx(
        [0.04, 0.053333333, 0.053333333, 0.2]
    )


def test_discovery_overlap_rejected_and_credibility_bounded():
    study = prepare(experience(1000))
    with pytest.raises(ValueError, match="disjoint"):
        detect(study, study)
    _, report = detect(study.iloc[:700], study.iloc[700:], min_leaf=50)
    assert report.credibility.between(0, 1).all()
    assert report.actual.sum() == study.iloc[700:].deaths.sum()


def test_embedding_learns_category_signal_and_unknown_fallback():
    rng = np.random.default_rng(7)
    group = np.tile(["low", "high"], 500)
    rate = np.where(group == "high", 3.0, 0.3)
    data = pd.DataFrame({"group": group, "deaths": rng.poisson(rate), "expected_deaths": 1.0})
    model = MortalityEmbedding(columns=["group"], epochs=1000, learning_rate=0.1).fit(data)
    assert model.loss_[-1] < model.loss_[0] - 0.1
    means = pd.Series(model.predict(data)).groupby(group).mean()
    assert means["high"] > 3 * means["low"]
    unknown = pd.DataFrame({"group": ["new"], "expected_deaths": [1.0]})
    assert np.isfinite(model.predict(unknown)).all()
