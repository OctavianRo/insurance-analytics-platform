import json

import pandas as pd
import pytest

from insurance_analytics.deltas import DeltaStore
from insurance_analytics.etl import cause_of_death_summary, prepare_study
from insurance_analytics.reporting import premium_report


def event(event_id="e1", version=1, values=None):
    return {
        "event_id": event_id,
        "application_id": "app-1",
        "version": version,
        "values": values or {"decision": "refer", "channel": "broker"},
    }


def test_delta_replay_is_durable_and_null_change_is_recorded(tmp_path):
    path = tmp_path / "ledger.sqlite"
    store = DeltaStore(path)
    assert store.apply(event()) == 2
    assert DeltaStore(path).apply(event()) == 0
    assert store.apply(event("e2", 2, {"decision": None})) == 1
    with store.connect() as db:
        row = db.execute("SELECT payload FROM current").fetchone()
        assert json.loads(row[0]) == {"decision": None, "channel": "broker"}
        assert db.execute("SELECT COUNT(*) FROM deltas").fetchone()[0] == 3


def test_conflicting_and_stale_events_rollback(tmp_path):
    store = DeltaStore(tmp_path / "ledger.sqlite")
    store.apply(event())
    with pytest.raises(ValueError, match="Conflicting"):
        store.apply(event(values={"decision": "other"}))
    with pytest.raises(ValueError, match="Stale"):
        store.apply(event("e2", 1))
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_study_dates_quarantine_and_conservation():
    raw = pd.DataFrame(
        {
            "policy_id": ["a", "b", "c", "d"],
            "issue_date": ["2024-01-01", "2025-07-01", "bad", "2024-01-01"],
            "exit_date": [None] * 4,
            "death_date": [None, "2025-10-01", None, "2026-01-01"],
            "sum_assured": [100] * 4,
        }
    )
    result = prepare_study(raw, "2025-01-01", "2026-01-01")
    assert len(result.accepted) == 3 and len(result.rejected) == 1
    assert result.accepted.deaths.sum() == 1  # exclusive end date
    assert result.accepted.loc[result.accepted.policy_id == "a", "exposure"].iloc[
        0
    ] == pytest.approx(365 / 365.25)
    assert (
        result.manifest["input_rows"]
        == result.manifest["accepted_rows"] + result.manifest["rejected_rows"]
    )


def test_cause_unknown_and_suppression():
    raw = pd.DataFrame(
        {"year": [2025, 2025, 2025], "icd10": ["I21", "C34", None], "deaths": [20, 3, 12]}
    )
    result = cause_of_death_summary(raw)
    assert "other_or_unknown" in result.cause.values
    assert result.loc[result.cause == "neoplasms", "deaths"].isna().all()
    assert result.loc[result.cause == "circulatory", "deaths"].iloc[0] == 20


def transactions():
    return pd.DataFrame(
        {
            "transaction_id": ["t1", "t2", "t3"],
            "policy_id": ["p1"] * 3,
            "accounting_date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "client": ["A"] * 3,
            "currency": ["USD"] * 3,
            "gross_premium": [0.05, 0.05, -0.05],
            "ceded_share": [0.5] * 3,
            "sum_assured": [100, 100, 200],
        }
    )


def test_money_rounding_reversals_and_volume_deduplication():
    report = premium_report(transactions()).iloc[0]
    assert report.gross_cents == 5
    assert report.ceded_cents == 3  # +2.5 -> +3, -2.5 -> -3
    assert report.policies == 1 and report.transactions == 3
    assert report.ceded_volume == 100  # final snapshot only


def test_currencies_never_mix_and_duplicate_transactions_fail():
    raw = transactions()
    raw.loc[1, "currency"] = "EUR"
    assert len(premium_report(raw)) == 2
    with pytest.raises(ValueError):
        premium_report(pd.concat([raw, raw.iloc[:1]], ignore_index=True))
