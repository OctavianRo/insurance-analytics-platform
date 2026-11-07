"""RFP study ingestion with explicit reject quarantine and reconciled exposure."""

from dataclasses import dataclass
from hashlib import sha256

import numpy as np
import pandas as pd

from .contracts import require_columns, unique


@dataclass
class StudyResult:
    accepted: pd.DataFrame
    rejected: pd.DataFrame
    manifest: dict


def prepare_study(frame: pd.DataFrame, start: str, end: str) -> StudyResult:
    """Dates are [start, end); exposure uses ACT/365.25; one row per policy."""
    require_columns(frame, ["policy_id", "issue_date", "exit_date", "death_date", "sum_assured"])
    unique(frame, ["policy_id"])
    left, right = pd.Timestamp(start), pd.Timestamp(end)
    if pd.isna(left) or pd.isna(right) or left >= right:
        raise ValueError("Study start must precede end")
    data = frame.copy()
    reasons = pd.Series("", index=data.index)
    for column in ["issue_date", "exit_date", "death_date"]:
        source = data[column]
        parsed = pd.to_datetime(source, errors="coerce")
        reasons.loc[source.notna() & parsed.isna()] += f"invalid_{column};"
        data[column] = parsed
    reasons.loc[data.issue_date.isna()] += "missing_issue_date;"
    amount = pd.to_numeric(data.sum_assured, errors="coerce")
    reasons.loc[~np.isfinite(amount) | (amount <= 0)] += "invalid_sum_assured;"
    data["sum_assured"] = amount
    reasons.loc[data.exit_date.notna() & (data.exit_date < data.issue_date)] += "exit_before_issue;"
    reasons.loc[data.death_date.notna() & (data.death_date < data.issue_date)] += (
        "death_before_issue;"
    )
    reasons.loc[
        data.exit_date.notna() & data.death_date.notna() & (data.death_date > data.exit_date)
    ] += "death_after_exit;"
    rejected = data.loc[reasons != ""].assign(reject_reason=reasons[reasons != ""])
    accepted = data.loc[reasons == ""].copy()
    entry = accepted.issue_date.clip(lower=left)
    end_dates = pd.concat(
        [
            accepted.exit_date.fillna(right),
            accepted.death_date.fillna(right),
            pd.Series(right, index=accepted.index),
        ],
        axis=1,
    ).min(axis=1)
    accepted["exposure"] = ((end_dates - entry).dt.total_seconds() / (365.25 * 86400)).clip(lower=0)
    accepted["deaths"] = ((accepted.death_date >= entry) & (accepted.death_date < right)).astype(
        int
    )
    accepted["in_study"] = (accepted.exposure > 0) | (accepted.deaths == 1)
    digest = sha256(frame.to_csv(index=False).encode()).hexdigest()
    manifest = {
        "source_sha256": digest,
        "input_rows": len(frame),
        "accepted_rows": len(accepted),
        "rejected_rows": len(rejected),
        "study_start": start,
        "study_end_exclusive": end,
        "exposure": float(accepted.exposure.sum()),
        "deaths": int(accepted.deaths.sum()),
    }
    assert manifest["accepted_rows"] + manifest["rejected_rows"] == manifest["input_rows"]
    return StudyResult(accepted, rejected, manifest)


def cause_of_death_summary(frame: pd.DataFrame, suppression: int = 10):
    """Keep unknown causes visible; exclude no records silently. ICD-10 chapter grouping."""
    require_columns(frame, ["year", "icd10", "deaths"])
    from .contracts import finite

    finite(frame, ["deaths"], nonnegative=True)
    if (frame.deaths % 1 != 0).any() or suppression < 1:
        raise ValueError("Need integer deaths and positive suppression threshold")
    code = frame.icd10.fillna("").astype(str).str.strip().str.upper()
    category = np.select(
        [code.str.match(r"^I\d{2}"), code.str.match(r"^C\d{2}"), code.str.match(r"^[VWXY]\d{2}")],
        ["circulatory", "neoplasms", "external"],
        default="other_or_unknown",
    )
    result = (
        frame.assign(cause=category)
        .groupby(["year", "cause"], dropna=False)
        .deaths.sum()
        .reset_index()
    )
    # This simple cell suppression is for the standalone demo; no complementary totals are published.
    result["suppressed"] = result.deaths < suppression
    result.loc[result.suppressed, "deaths"] = np.nan
    return result
