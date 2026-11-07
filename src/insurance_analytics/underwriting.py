"""Temporal holdout, fold-local preprocessing, calibrated underwriting models."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .contracts import binary, finite, require_columns, unique

NUMERIC = ["age", "bmi", "smoker", "rx_count", "a1c"]
CATEGORICAL = ["channel"]
FEATURES = NUMERIC + CATEGORICAL


@dataclass
class TrainedModel:
    estimator: object
    target: str
    metrics: dict
    train_ids: tuple
    test_ids: tuple

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        validate_features(frame)
        return self.estimator.predict_proba(frame[FEATURES])[:, 1]


def validate_features(frame):
    require_columns(frame, FEATURES)
    finite(frame, ["age", "bmi", "smoker", "rx_count"], nonnegative=True)
    if not frame.smoker.isin([0, 1]).all():
        raise ValueError("smoker must be binary")
    a1c = frame.a1c.dropna().to_numpy(dtype=float)
    if not np.isfinite(a1c).all() or (a1c <= 0).any():
        raise ValueError("a1c must be positive or missing")
    if frame.channel.isna().any():
        raise ValueError("channel is required")


def build_pipeline(backend: str = "logistic") -> Pipeline:
    preprocessing = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                NUMERIC,
            ),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL,
            ),
        ]
    )
    if backend == "logistic":
        model = LogisticRegression(max_iter=1000, random_state=42)
    elif backend == "xgboost":
        from xgboost import XGBClassifier

        model = XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=1,
            random_state=42,
            eval_metric="logloss",
        )
    else:
        raise ValueError("Backend must be logistic or xgboost")
    return Pipeline([("preprocess", preprocessing), ("model", model)])


def evaluate(y, probabilities) -> dict:
    y = np.asarray(y)
    p = np.asarray(probabilities, dtype=float)
    if len(y) == 0 or p.shape != y.shape or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid probabilities")
    if not np.isin(y, [0, 1]).all():
        raise ValueError("Labels must be binary")
    return {
        "n": len(y),
        "prevalence": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "average_precision": float(average_precision_score(y, p)) if y.sum() else None,
        "brier": float(brier_score_loss(y, p)),
    }


def train(frame: pd.DataFrame, target: str = "impaired", backend: str = "logistic") -> TrainedModel:
    if target not in {"impaired", "requires_full_review"}:
        raise ValueError("Unsupported target")
    validate_features(frame)
    unique(frame, ["application_id"])
    binary(frame, target)
    require_columns(frame, ["applied_at"])
    ordered = frame.assign(applied_at=pd.to_datetime(frame.applied_at, errors="raise")).sort_values(
        "applied_at"
    )
    if ordered.applied_at.isna().any():
        raise ValueError("Missing application timestamp")
    cutoff = ordered.applied_at.iloc[int(len(ordered) * 0.8)]
    development = ordered[ordered.applied_at < cutoff]
    test = ordered[ordered.applied_at >= cutoff]
    counts = development[target].value_counts()
    if test.empty or len(counts) != 2 or counts.min() < 5:
        raise ValueError("Need five development records per class and a nonempty temporal holdout")
    estimator = CalibratedClassifierCV(
        build_pipeline(backend),
        method="sigmoid",
        cv=StratifiedKFold(3, shuffle=True, random_state=42),
    )
    estimator.fit(development[FEATURES], development[target])
    metrics = evaluate(test[target], estimator.predict_proba(test[FEATURES])[:, 1])
    metrics.update(
        {
            "backend": backend,
            "target": target,
            "holdout_start": str(cutoff),
            "training_rows": len(development),
        }
    )
    return TrainedModel(
        estimator, target, metrics, tuple(development.application_id), tuple(test.application_id)
    )


def acceleration_policy(model: TrainedModel, frame: pd.DataFrame, threshold: float = 0.1):
    """Simulation of referral routing; never a binding eligibility determination."""
    if model.target != "requires_full_review" or not 0 <= threshold <= 1:
        raise ValueError("Acceleration requires a review-target model and a probability threshold")
    p = model.predict(frame)
    candidate = p <= threshold
    result = {
        "threshold": threshold,
        "candidate_rate": float(candidate.mean()),
        "candidates": int(candidate.sum()),
        "rows": len(frame),
    }
    if "requires_full_review" in frame:
        binary(frame, "requires_full_review")
        result["missed_review_rate_among_candidates"] = (
            float(frame.loc[candidate, "requires_full_review"].mean()) if candidate.any() else None
        )
    return result
