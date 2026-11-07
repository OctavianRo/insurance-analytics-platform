"""Reference-fixed PSI, missingness, KS tests with FDR and delayed-label metrics."""

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from .contracts import require_columns, unique
from .differentials import benjamini_hochberg
from .underwriting import evaluate


def population_stability_index(reference, current, bins=10):
    r, c = np.asarray(reference, float), np.asarray(current, float)
    if r.ndim != 1 or c.ndim != 1 or bins < 2:
        raise ValueError("Invalid PSI inputs")
    r, c = r[np.isfinite(r)], c[np.isfinite(c)]
    if not len(r) or not len(c):
        return None
    edges = np.unique(np.quantile(r, np.linspace(0, 1, bins + 1)))
    # Extend both tails to capture observations outside the reference range.
    if len(edges) == 1:
        edges = np.array([-np.inf, edges[0] - 1e-9, edges[0] + 1e-9, np.inf])
    else:
        edges[0], edges[-1] = -np.inf, np.inf
    rp = np.histogram(r, edges)[0] + 0.5
    cp = np.histogram(c, edges)[0] + 0.5
    rp, cp = rp / rp.sum(), cp / cp.sum()
    return float(np.sum((cp - rp) * np.log(cp / rp)))


def drift_report(reference: pd.DataFrame, current: pd.DataFrame, features: list[str]):
    require_columns(reference, features)
    require_columns(current, features)
    rows = []
    for feature in features:
        r, c = reference[feature].to_numpy(float), current[feature].to_numpy(float)
        rf, cf = r[np.isfinite(r)], c[np.isfinite(c)]
        p = float(ks_2samp(rf, cf).pvalue) if len(rf) and len(cf) else 1.0
        psi = population_stability_index(r, c)
        rows.append(
            {
                "feature": feature,
                "psi": psi,
                "p_value": p,
                "reference_missing": float((~np.isfinite(r)).mean()),
                "current_missing": float((~np.isfinite(c)).mean()),
                "insufficient_data": not len(rf) or not len(cf),
            }
        )
    result = pd.DataFrame(rows)
    result["psi"] = pd.to_numeric(result["psi"], errors="coerce")
    result["q_value"] = benjamini_hochberg(result.p_value)
    result["alert"] = (
        (result.psi.fillna(0) >= 0.2)
        | (result.q_value < 0.05)
        | result.insufficient_data
        | ((result.current_missing - result.reference_missing).abs() > 0.1)
    )
    return result


def delayed_performance(predictions, labels, as_of):
    unique(predictions, ["application_id"])
    unique(labels, ["application_id"])
    require_columns(predictions, ["probability", "scored_at"])
    require_columns(labels, ["outcome", "available_at"])
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    available = pd.to_datetime(labels.available_at, utc=True, errors="raise")
    scored = pd.to_datetime(predictions.scored_at, utc=True, errors="raise")
    joined = predictions.loc[scored <= cutoff].merge(
        labels.loc[available <= cutoff], on="application_id", validate="one_to_one"
    )
    return (
        evaluate(joined.outcome, joined.probability)
        if len(joined)
        else {"n": 0, "status": "awaiting_labels"}
    )


def evidently_report(reference, current, output):
    """Optional Evidently 0.7+ HTML report, kept out of the lightweight core."""
    from evidently import Report
    from evidently.presets import DataDriftPreset

    report = Report([DataDriftPreset()]).run(reference_data=reference, current_data=current)
    report.save_html(str(output))
