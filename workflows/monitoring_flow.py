"""Daily monitoring job; use scheduler only after configuring real data adapters."""

from metaflow import FlowSpec, Parameter, retry, step


class MonitoringFlow(FlowSpec):
    output = Parameter("output", default="artifacts/monitoring")

    @step
    def start(self):
        from insurance_analytics.synthetic import applications

        self.reference = applications(seed=42)
        self.current = applications(seed=84)
        self.current["bmi"] += 4
        self.next(self.report)

    @retry(times=2)
    @step
    def report(self):
        from pathlib import Path

        from insurance_analytics.monitoring import drift_report, evidently_report

        directory = Path(self.output)
        directory.mkdir(parents=True, exist_ok=True)
        self.drift = drift_report(self.reference, self.current, ["age", "bmi", "a1c", "rx_count"])
        self.drift.to_csv(directory / "drift.csv", index=False)
        evidently_report(
            self.reference[["age", "bmi", "a1c", "rx_count"]],
            self.current[["age", "bmi", "a1c", "rx_count"]],
            directory / "evidently.html",
        )
        self.next(self.end)

    @step
    def end(self):
        print({"alerts": int(self.drift.alert.sum()), "output": self.output})


if __name__ == "__main__":
    MonitoringFlow()
