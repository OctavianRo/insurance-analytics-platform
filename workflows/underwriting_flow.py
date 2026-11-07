"""Run: python workflows/underwriting_flow.py run

Metaflow orchestrates isolated steps; MLflow records data lineage, metrics and model.
Only synthetic data is used. Set MLFLOW_TRACKING_URI for a team tracking server.
"""

import hashlib
import os

from metaflow import FlowSpec, Parameter, retry, step


class UnderwritingFlow(FlowSpec):
    backend = Parameter("backend", default="logistic", help="logistic or xgboost")

    @step
    def start(self):
        from insurance_analytics.synthetic import applications

        self.data = applications()
        self.data_hash = hashlib.sha256(self.data.to_csv(index=False).encode()).hexdigest()
        self.next(self.fit)

    @retry(times=2)
    @step
    def fit(self):
        import mlflow

        from insurance_analytics.underwriting import train

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
        mlflow.set_experiment("synthetic-underwriting")
        self.model = train(self.data, backend=self.backend)
        with mlflow.start_run() as run:
            mlflow.set_tags({"data_source": "synthetic", "data_sha256": self.data_hash})
            mlflow.log_params({"backend": self.backend, "seed": 42, "split": "temporal-80-20"})
            mlflow.log_metrics(
                {k: v for k, v in self.model.metrics.items() if isinstance(v, (int, float))}
            )
            import mlflow.sklearn

            mlflow.sklearn.log_model(
                self.model.estimator,
                name="underwriting",
                skops_trusted_types=[
                    "numpy.dtype",
                    "sklearn.calibration._CalibratedClassifier",
                    "sklearn.calibration._SigmoidCalibration",
                    "sklearn.model_selection._split.StratifiedKFold",
                    "xgboost.sklearn.XGBClassifier",
                    "xgboost.core.Booster",
                ],
                input_example=self.data.iloc[:2][
                    ["age", "bmi", "smoker", "rx_count", "a1c", "channel"]
                ],
            )
            self.mlflow_run_id = run.info.run_id
        self.next(self.end)

    @step
    def end(self):
        print({"mlflow_run_id": self.mlflow_run_id, "metrics": self.model.metrics})


if __name__ == "__main__":
    UnderwritingFlow()
