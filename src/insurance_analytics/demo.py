"""Run every project and emit reproducible, auditable artifacts."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import pandas as pd
import plotly.express as px

from . import synthetic
from .deltas import DeltaStore
from .differentials import detect
from .embeddings import MortalityEmbedding
from .etl import cause_of_death_summary, prepare_study
from .monitoring import drift_report
from .mortality import Assumptions, death_benefit_apv, prepare, summarize
from .reporting import premium_report
from .survival import CoxPH, concordance_index
from .underwriting import acceleration_policy, train


def run(output="artifacts/demo", backend="logistic"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    apps = synthetic.applications()
    study = prepare(synthetic.experience(), Assumptions())
    impairment = train(apps, backend=backend)
    acceleration = train(apps, target="requires_full_review", backend=backend)
    holdout = apps.loc[apps.application_id.isin(impairment.test_ids)].copy()
    holdout["probability"] = impairment.predict(holdout)
    shifted = apps.iloc[-600:].copy()
    shifted["bmi"] += 4
    shifted["a1c"] += 0.8
    drift = drift_report(apps.iloc[:2000], shifted, ["age", "bmi", "a1c", "rx_count"])
    _, leaves = detect(study.iloc[:2800], study.iloc[2800:])
    embedding_data = study.assign(
        age_band=(study.age // 10).astype(str), duration_band=(study.duration // 5).astype(str)
    )
    network = MortalityEmbedding().fit(embedding_data.iloc[:2800])
    embedding_holdout = embedding_data.iloc[2800:].copy()
    embedding_holdout["predicted_deaths"] = network.predict(embedding_holdout)
    features = ["age", "smoker"]
    development, test = study.iloc[:2800], study.iloc[2800:]
    cox = CoxPH().fit(development[features], development.exposure, development.deaths)
    risk = 1 - cox.predict_survival(test[features], [1])[:, 0]
    premiums = premium_report(synthetic.premium_transactions())
    raw = pd.DataFrame(
        {
            "policy_id": ["S1", "S2", "S3"],
            "issue_date": ["2024-06-01", "2025-03-01", "bad-date"],
            "exit_date": [None] * 3,
            "death_date": [None, "2025-09-01", None],
            "sum_assured": [100000, 250000, 300000],
        }
    )
    prepared = prepare_study(raw, "2025-01-01", "2026-01-01")
    causes = cause_of_death_summary(
        pd.DataFrame(
            {"year": [2025] * 4, "icd10": ["I21", "C34", "V01", None], "deaths": [30, 25, 12, 4]}
        )
    )
    ledger = DeltaStore(output / "decisions.sqlite")
    events = [
        {
            "event_id": "e1",
            "application_id": "SYN-1",
            "version": 1,
            "values": {"decision": "refer", "risk_class": "pending", "channel": "broker"},
        },
        {
            "event_id": "e2",
            "application_id": "SYN-1",
            "version": 2,
            "values": {"decision": "reviewed", "risk_class": "standard"},
        },
    ]
    new_deltas = sum(ledger.apply(e) for e in events)
    tables = {
        "mortality_by_client": summarize(study, ["client"]),
        "drift": drift,
        "differentials": leaves,
        "premiums": premiums,
        "predictions": holdout,
        "embedding_holdout": embedding_holdout,
        "study_accepted": prepared.accepted,
        "study_rejected": prepared.rejected,
        "cause_of_death": causes,
    }
    for name, table in tables.items():
        table.to_csv(output / f"{name}.csv", index=False)
    summary = {
        "data_source": "synthetic",
        "seed": 42,
        "impairment": impairment.metrics,
        "acceleration": acceleration.metrics,
        "acceleration_policy": acceleration_policy(
            acceleration, apps.loc[apps.application_id.isin(acceleration.test_ids)]
        ),
        "mortality": json.loads(summarize(study).to_json(orient="records"))[0],
        "term_apv_per_unit": death_benefit_apv([0.01, 0.012, 0.014, 0.016, 0.018]),
        "survival_holdout_concordance": concordance_index(test.exposure, test.deaths, risk),
        "embedding": {
            "initial_loss": network.loss_[0],
            "final_loss": network.loss_[-1],
            "holdout_actual": int(embedding_holdout.deaths.sum()),
            "holdout_predicted": float(embedding_holdout.predicted_deaths.sum()),
        },
        "study_ingestion": prepared.manifest,
        "new_decision_deltas": new_deltas,
        "drift_alerts": int(drift.alert.sum()),
        "differential_review_flags": int(leaves.review_flag.sum()),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    chart = px.bar(
        tables["mortality_by_client"],
        x="client",
        y="ae_count",
        title="Synthetic mortality A/E by client",
    ).to_html(include_plotlyjs=True, full_html=False)
    (output / "report.html").write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Insurance analytics</title></head><body><h1>Insurance analytics study</h1><p>Synthetic data · Independent portfolio implementation</p>"
        + chart
        + "<h2>Model drift</h2>"
        + drift.to_html(index=False)
        + "<h2>Premium reporting (integer cents)</h2>"
        + premiums.to_html(index=False)
        + "</body></html>"
    )
    files = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in output.iterdir()
        if p.is_file() and p.suffix in {".csv", ".json", ".html"} and p.name != "manifest.json"
    }
    manifest = {
        "files": files,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ["insurance-analytics-platform", "numpy", "pandas", "scikit-learn", "scipy"]
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return summary
