import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from insurance_analytics.api import app
from insurance_analytics.dashboard import create_dashboard
from insurance_analytics.monitoring import (
    delayed_performance,
    drift_report,
    population_stability_index,
)


def test_psi_identical_shifted_and_constant():
    rng = np.random.default_rng(1)
    ref = rng.normal(size=2000)
    assert population_stability_index(ref, ref) == pytest.approx(0)
    assert population_stability_index(ref, ref + 3) > 0.2
    assert population_stability_index(np.ones(100), np.ones(100) * 2) > 0.2
    assert population_stability_index([np.nan], [1]) is None


def test_missing_data_triggers_alert():
    ref = pd.DataFrame({"x": range(100)})
    report = drift_report(ref, ref.assign(x=np.nan), ["x"])
    assert report.alert.iloc[0] and report.insufficient_data.iloc[0]


def test_delayed_labels_and_future_predictions_excluded():
    predictions = pd.DataFrame(
        {
            "application_id": ["a", "b", "c"],
            "scored_at": ["2025-01-01", "2025-01-01", "2026-01-01"],
            "probability": [0.1, 0.9, 0.5],
        }
    )
    labels = pd.DataFrame(
        {
            "application_id": ["a", "b", "c"],
            "outcome": [0, 1, 0],
            "available_at": ["2025-02-01", "2025-04-01", "2025-02-01"],
        }
    )
    report = delayed_performance(predictions, labels, "2025-03-01")
    assert report["n"] == 1 and report["roc_auc"] is None
    assert delayed_performance(predictions, labels, "2024-01-01")["status"] == "awaiting_labels"


def test_api_scores_and_rejects_bad_input():
    client = TestClient(app)
    assert client.get("/health").json()["data_source"] == "synthetic"
    body = {"applicants": [{"age": 40, "bmi": 25, "smoker": 0, "rx_count": 1, "channel": "broker"}]}
    response = client.post("/v1/underwriting/score", json=body)
    assert response.status_code == 200
    assert 0 <= response.json()["probabilities"][0] <= 1
    body["applicants"][0]["age"] = -1
    assert client.post("/v1/underwriting/score", json=body).status_code == 422
    assert client.post("/v1/underwriting/score", json={"applicants": []}).status_code == 422
    assert client.post("/v1/mortality/apv", json={"qx": [1.2]}).status_code == 422
    assert (
        client.post("/v1/mortality/apv", json={"qx": [0.1], "interest": 0, "benefit": 100}).json()[
            "apv"
        ]
        == 10
    )
    assert len(client.get("/v1/premiums").json()) > 0
    assert len(client.get("/v1/mortality").json()) == 3


def test_dashboard_serves_layout_and_callbacks():
    dashboard = create_dashboard()
    client = dashboard.server.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/_dash-layout").status_code == 200
    assert len(client.get("/_dash-dependencies").json) == 3


def test_dashboard_callbacks_compute_under_concurrent_requests():
    from concurrent.futures import ThreadPoolExecutor

    dashboard = create_dashboard()
    callbacks = [v["callback"].__wrapped__ for v in dashboard.callback_map.values()]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(
                lambda pair: pair[0](*pair[1]),
                zip(callbacks, [(1.0, "All"), (4,), ("Aster",)], strict=True),
            )
        )
    assert len(results) == 3
    assert "19 deaths" in results[0][0].children
    assert len(results[0][1].data[0].y) > 0
    assert len(results[1][0].data) > 0
    assert len(results[2][0].data) > 0
