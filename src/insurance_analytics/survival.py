"""Cox proportional hazards with Breslow ties and right censoring."""

import numpy as np
from scipy.optimize import minimize


class CoxPH:
    def __init__(self, penalty: float = 0.01):
        if penalty < 0:
            raise ValueError("Penalty must be nonnegative")
        self.penalty = penalty

    def fit(self, x, time, event):
        x, time, event = np.asarray(x, float), np.asarray(time, float), np.asarray(event)
        if x.ndim != 2 or time.shape != (len(x),) or event.shape != time.shape:
            raise ValueError("Invalid survival shapes")
        if not np.isfinite(x).all() or not np.isfinite(time).all() or (time <= 0).any():
            raise ValueError("Features must be finite and durations positive")
        if not np.isin(event, [0, 1]).all() or event.sum() == 0:
            raise ValueError("Need binary events and at least one observed death")
        self.mean_ = x.mean(axis=0)
        self.scale_ = x.std(axis=0)
        self.scale_[self.scale_ == 0] = 1
        z = (x - self.mean_) / self.scale_
        times = np.unique(time[event == 1])
        # Small research implementation; explicit risk sets favor auditability over scale.
        risk = [time >= t for t in times]
        deaths = [(time == t) & (event == 1) for t in times]

        def objective(beta):
            eta = z @ beta
            value = self.penalty * np.dot(beta, beta) / 2
            gradient = self.penalty * beta
            for r, d in zip(risk, deaths, strict=True):
                shift = eta[r].max()
                weights = np.exp(eta[r] - shift)
                count = d.sum()
                value += count * (shift + np.log(weights.sum())) - eta[d].sum()
                gradient = gradient + count * (weights @ z[r]) / weights.sum() - z[d].sum(axis=0)
            return value, gradient

        fit = minimize(
            objective, np.zeros(z.shape[1]), jac=True, method="BFGS", options={"gtol": 1e-6}
        )
        if not fit.success and np.linalg.norm(fit.jac) > 1e-4:
            raise RuntimeError(f"Cox fit failed: {fit.message}")
        self.coef_ = fit.x
        eta = z @ self.coef_
        self.event_times_ = times
        self.baseline_cumulative_hazard_ = np.cumsum(
            [d.sum() / np.exp(eta[r]).sum() for r, d in zip(risk, deaths, strict=True)]
        )
        return self

    def predict_survival(self, x, times):
        x, times = np.asarray(x, float), np.asarray(times, float)
        if x.ndim != 2 or x.shape[1] != len(self.coef_) or not np.isfinite(x).all():
            raise ValueError("Invalid features")
        if times.ndim != 1 or not np.isfinite(times).all() or (times < 0).any():
            raise ValueError("Invalid prediction times")
        indices = np.searchsorted(self.event_times_, times, side="right") - 1
        baseline = np.where(
            indices >= 0, self.baseline_cumulative_hazard_[np.maximum(indices, 0)], 0
        )
        risk = np.exp(np.clip(((x - self.mean_) / self.scale_) @ self.coef_, -50, 50))
        return np.exp(-risk[:, None] * baseline)


def concordance_index(time, event, risk) -> float | None:
    time, event, risk = np.asarray(time), np.asarray(event), np.asarray(risk)
    if time.shape != event.shape or time.shape != risk.shape or time.ndim != 1:
        raise ValueError("Arrays must have matching one-dimensional shapes")
    concordant = comparable = 0
    for i in np.flatnonzero(event):
        later = time > time[i]
        comparable += later.sum()
        concordant += (risk[i] > risk[later]).sum() + 0.5 * (risk[i] == risk[later]).sum()
    return float(concordant / comparable) if comparable else None
