"""NumPy entity embeddings with Poisson loss and an expected-deaths offset.

Each categorical field has a learned embedding; concatenated embeddings feed a tanh
hidden layer and a log-rate output. Unknown levels map to a frozen zero embedding.
"""

import numpy as np
import pandas as pd

from .contracts import finite, require_columns


class MortalityEmbedding:
    def __init__(
        self,
        columns=("age_band", "duration_band", "smoker"),
        dim=3,
        hidden=8,
        learning_rate=0.03,
        epochs=250,
        seed=42,
    ):
        if dim < 1 or hidden < 1 or epochs < 1 or learning_rate <= 0:
            raise ValueError("Invalid neural network configuration")
        self.columns = tuple(columns)
        self.dim, self.hidden = dim, hidden
        self.learning_rate, self.epochs, self.seed = learning_rate, epochs, seed

    def _encode(self, frame):
        require_columns(frame, self.columns)
        return [
            frame[c].astype(str).map(self.vocabulary_[c]).fillna(0).to_numpy(int)
            for c in self.columns
        ]

    def _forward(self, ids):
        x = np.concatenate([e[i] for e, i in zip(self.embeddings_, ids, strict=True)], axis=1)
        h = np.tanh(x @ self.w1_ + self.b1_)
        eta = h @ self.w2_ + self.b2_
        return x, h, eta

    def fit(self, frame: pd.DataFrame):
        require_columns(frame, self.columns)
        finite(frame, ["deaths", "expected_deaths"], nonnegative=True)
        if (frame.expected_deaths <= 0).any() or (frame.deaths % 1 != 0).any():
            raise ValueError("Need positive expected deaths and integer observed deaths")
        rng = np.random.default_rng(self.seed)
        self.vocabulary_ = {
            c: {v: i + 1 for i, v in enumerate(sorted(frame[c].astype(str).unique()))}
            for c in self.columns
        }
        self.embeddings_ = [
            rng.normal(0, 0.1, (len(self.vocabulary_[c]) + 1, self.dim)) for c in self.columns
        ]
        for e in self.embeddings_:
            e[0] = 0
        self.w1_ = rng.normal(0, 0.1, (len(self.columns) * self.dim, self.hidden))
        self.b1_ = np.zeros(self.hidden)
        self.w2_ = rng.normal(0, 0.1, self.hidden)
        self.b2_ = float(np.log((frame.deaths.sum() + 0.5) / (frame.expected_deaths.sum() + 0.5)))
        ids = self._encode(frame)
        observed, offset = frame.deaths.to_numpy(), frame.expected_deaths.to_numpy()
        self.loss_ = []
        for _ in range(self.epochs):
            x, h, eta = self._forward(ids)
            if np.max(np.abs(eta)) > 50:
                raise RuntimeError("Embedding optimization diverged; reduce learning rate")
            mu = offset * np.exp(eta)
            self.loss_.append(float(np.mean(mu - observed * (np.log(offset) + eta))))
            g = (mu - observed) / len(frame)
            dw2, db2 = h.T @ g, g.sum()
            dh = g[:, None] * self.w2_ * (1 - h * h)
            dx = dh @ self.w1_.T
            dw1, db1 = x.T @ dh, dh.sum(axis=0)
            for j, (e, index) in enumerate(zip(self.embeddings_, ids, strict=True)):
                de = np.zeros_like(e)
                np.add.at(de, index, dx[:, j * self.dim : (j + 1) * self.dim])
                de[0] = 0
                e -= self.learning_rate * de
            self.w1_ -= self.learning_rate * dw1
            self.b1_ -= self.learning_rate * db1
            self.w2_ -= self.learning_rate * dw2
            self.b2_ -= self.learning_rate * db2
        return self

    def predict(self, frame):
        finite(frame, ["expected_deaths"], nonnegative=True)
        _, _, eta = self._forward(self._encode(frame))
        return frame.expected_deaths.to_numpy() * np.exp(np.clip(eta, -50, 50))
