"""Machine-learning and state-estimation layer of the digital twin.

Three functions distinguish a digital twin from a conventional simulation
model, and all three are implemented here:

``ChargingDemandForecaster``
    a gradient-boosted regression that predicts hour-ahead and day-ahead
    charging demand from calendar, weather and price features, so that the twin
    can anticipate rather than merely reproduce the physical system
    (docs_reference: ai-demand-dl, ai-demand-review, ai-prob-forecast);

``StateEstimator``
    an extended Kalman filter that reconciles the twin's internal battery state
    with noisy telemetry, which is the synchronisation mechanism that keeps a
    twin aligned with its physical counterpart (docs_reference: dt-batt-state,
    dt-batt-soc, ai-dl-soc);

``PolicySurrogate``
    a Gaussian-process emulator of the full simulator, trained on a
    Latin-hypercube design, which makes global sensitivity analysis and
    multi-objective search computationally feasible (docs_reference: meth-gsa,
    ai-smartgrid-review).
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from .config import HOURS_PER_YEAR


# ---------------------------------------------------------------------------
# Demand forecasting
# ---------------------------------------------------------------------------
def _calendar_features(temperature: np.ndarray, price: np.ndarray) -> np.ndarray:
    h = np.arange(HOURS_PER_YEAR, dtype=float)
    hod = np.mod(h, 24.0)
    dow = np.mod(np.floor(h / 24.0), 7.0)
    doy = np.floor(h / 24.0)
    return np.column_stack([
        np.sin(2 * np.pi * hod / 24), np.cos(2 * np.pi * hod / 24),
        np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
        np.sin(2 * np.pi * doy / 365), np.cos(2 * np.pi * doy / 365),
        (dow >= 5).astype(float), temperature, price,
    ])


class ChargingDemandForecaster:
    """Day-ahead charging-demand forecaster with lagged autoregressive inputs."""

    def __init__(self, horizon: int = 24, seed: int = 0) -> None:
        self.horizon = horizon
        self.model = HistGradientBoostingRegressor(
            max_iter=260, learning_rate=0.06, max_depth=7,
            min_samples_leaf=24, l2_regularization=0.6, random_state=seed)
        self.metrics: dict[str, float] = {}

    def _design(self, demand: np.ndarray, temperature: np.ndarray,
                price: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        base = _calendar_features(temperature, price)
        lags = [24, 25, 48, 168]
        cols = [base]
        for lag in lags:
            shifted = np.concatenate([np.full(lag, demand[:lag].mean()), demand[:-lag]])
            cols.append(shifted[:, None])
        roll = np.convolve(demand, np.ones(24) / 24.0, mode="full")[:HOURS_PER_YEAR]
        roll = np.concatenate([np.full(24, demand[:24].mean()), roll[:-24]])
        cols.append(roll[:, None])
        x = np.hstack(cols)
        return x[self.horizon:], demand[self.horizon:]

    def fit_evaluate(self, demand: np.ndarray, temperature: np.ndarray,
                     price: np.ndarray, train_fraction: float = 0.75
                     ) -> dict[str, float]:
        """Train on the first part of the year and score on the held-out tail."""
        x, y = self._design(np.asarray(demand, float), np.asarray(temperature, float),
                            np.asarray(price, float))
        cut = int(len(y) * train_fraction)
        self.model.fit(x[:cut], y[:cut])
        pred = self.model.predict(x[cut:])
        obs = y[cut:]
        denom = max(float(np.mean(np.abs(obs))), 1e-9)
        self.metrics = {
            "mae": float(mean_absolute_error(obs, pred)),
            "mape": float(np.mean(np.abs(obs - pred)) / denom),
            "r2": float(r2_score(obs, pred)),
            "rmse": float(np.sqrt(np.mean((obs - pred) ** 2))),
            "n_train": int(cut), "n_test": int(len(obs)),
        }
        self._last = (obs, pred)
        return self.metrics

    def predictions(self) -> tuple[np.ndarray, np.ndarray]:
        return self._last


# ---------------------------------------------------------------------------
# State estimation
# ---------------------------------------------------------------------------
class StateEstimator:
    r"""Extended Kalman filter on the joint state :math:`x = [\mathrm{SOC}, R_0]`.

    The measurement is terminal voltage under a known current; tracking the
    ohmic resistance jointly with the state of charge is what allows the twin
    to detect degradation from ordinary operating data.
    """

    def __init__(self, capacity_ah: float, r0_init: float = 0.075,
                 dt_h: float = 1.0) -> None:
        self.capacity_ah = capacity_ah
        self.dt = dt_h
        self.x = np.array([0.80, r0_init])
        self.P = np.diag([1e-2, 1e-4])
        self.Q = np.diag([1e-6, 1e-9])
        self.R = np.array([[4e-4]])

    @staticmethod
    def _ocv(soc: float) -> float:
        s = float(np.clip(soc, 0.0, 1.0))
        return 3.30 + 0.92 * s - 0.55 * (1.0 - s) ** 3 + 0.13 * s ** 2

    @staticmethod
    def _docv(soc: float) -> float:
        s = float(np.clip(soc, 0.0, 1.0))
        return 0.92 + 1.65 * (1.0 - s) ** 2 + 0.26 * s

    def step(self, current_a: float, voltage_meas: float) -> np.ndarray:
        """One predict/update cycle; positive current discharges the cell."""
        soc, r0 = self.x
        soc_pred = float(np.clip(soc - current_a * self.dt / self.capacity_ah, 0.0, 1.0))
        x_pred = np.array([soc_pred, r0])
        F = np.array([[1.0, 0.0], [0.0, 1.0]])
        P_pred = F @ self.P @ F.T + self.Q

        v_pred = self._ocv(soc_pred) - current_a * r0
        H = np.array([[self._docv(soc_pred), -current_a]])
        S = H @ P_pred @ H.T + self.R
        K = P_pred @ H.T @ np.linalg.inv(S)
        innovation = np.array([voltage_meas - v_pred])
        self.x = x_pred + (K @ innovation).ravel()
        self.x[0] = float(np.clip(self.x[0], 0.0, 1.0))
        self.x[1] = float(np.clip(self.x[1], 1e-4, 1.0))
        self.P = (np.eye(2) - K @ H) @ P_pred
        return self.x.copy()

    def run(self, current: np.ndarray, voltage: np.ndarray) -> np.ndarray:
        out = np.empty((len(current), 2))
        for i, (ii, vv) in enumerate(zip(current, voltage)):
            out[i] = self.step(float(ii), float(vv))
        return out


def synchronisation_error(true_state: np.ndarray, estimated: np.ndarray
                          ) -> dict[str, float]:
    """Twin-to-plant synchronisation error statistics."""
    err = np.asarray(estimated) - np.asarray(true_state)
    return {"mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(np.mean(err ** 2))),
            "max_abs": float(np.max(np.abs(err))),
            "final_abs": float(abs(err[-1]))}


# ---------------------------------------------------------------------------
# Surrogate model
# ---------------------------------------------------------------------------
class PolicySurrogate:
    """Gaussian-process emulator mapping lever vectors onto simulator outputs.

    One process per target, each with a squared-exponential kernel that has
    its own length scale for every lever (automatic relevance determination)
    plus a white-noise term, fitted to the standardised target by maximum
    marginal likelihood.  The outputs are smooth functions of the levers with
    interactions between a few of them, which a GP captures from a few hundred
    simulations where a random forest does not: on the second-revision design
    the forest reached a test R^2 of 0.64-0.70 for NPV in two archetypes and
    the GP 0.99 (Supplementary Table S11).
    """

    def __init__(self, seed: int = 0, n_restarts: int = 3) -> None:
        self.seed = seed
        self.n_restarts = n_restarts
        self.models: list = []
        self.scales: list[tuple[float, float]] = []
        self.metrics: dict[str, float] = {}
        self.targets: list[str] = []

    def _new_model(self, d: int):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import (RBF, ConstantKernel,
                                                      WhiteKernel)
        # A length scale far above the unit lever range marks a lever the
        # target does not depend on; the upper bound only has to allow that.
        kernel = (ConstantKernel(1.0, (1e-3, 1e3))
                  * RBF(length_scale=np.ones(d), length_scale_bounds=(1e-2, 1e5))
                  + WhiteKernel(1e-3, (1e-10, 1e-1)))
        return GaussianProcessRegressor(kernel, normalize_y=False,
                                        n_restarts_optimizer=self.n_restarts,
                                        random_state=self.seed)

    def fit(self, x: np.ndarray, y: np.ndarray, targets: list[str],
            train_fraction: float = 0.8) -> dict[str, float]:
        self.targets = targets
        y = np.atleast_2d(y)
        n = len(x)
        cut = int(n * train_fraction)
        idx = np.random.default_rng(0).permutation(n)
        tr, te = idx[:cut], idx[cut:]
        if te.size == 0:                 # scored on an external test set instead
            te = idx[:0]
        self.models, self.scales, self.metrics = [], [], {}
        for j, t in enumerate(targets):
            yj = y[:, j]
            finite = np.isfinite(yj)
            tr_j = tr[finite[tr]]
            te_j = te[finite[te]]
            if tr_j.size < 5 or np.ptp(yj[tr_j]) < 1e-12:
                # degenerate target: constant predictor
                c = float(np.nanmean(yj)) if np.isfinite(yj).any() else 0.0
                self.models.append(c)
                self.scales.append((c, 1.0))
                self.metrics[f"r2_{t}"] = float("nan")
                continue
            mu, sd = float(np.mean(yj[tr_j])), float(np.std(yj[tr_j]))
            m = self._new_model(x.shape[1])
            import warnings
            from sklearn.exceptions import ConvergenceWarning
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                m.fit(x[tr_j], (yj[tr_j] - mu) / sd)
            self.models.append(m)
            self.scales.append((mu, sd))
            # The coefficient of determination is undefined when the held-out
            # observations carry essentially no variance; reporting the raw
            # value there produces a meaningless large negative number.
            if te_j.size < 3:
                self.metrics[f"r2_{t}"] = float("nan")
            else:
                obs = yj[te_j]
                scale = max(abs(float(np.mean(yj[tr_j]))), 1e-12)
                if float(np.std(obs)) / scale < 1e-6:
                    self.metrics[f"r2_{t}"] = float("nan")
                else:
                    self.metrics[f"r2_{t}"] = float(r2_score(
                        obs, self._predict_one(j, x[te_j])))
        vals = [v for v in self.metrics.values() if np.isfinite(v)]
        self.metrics["r2_mean"] = float(np.mean(vals)) if vals else float("nan")
        return self.metrics

    def _predict_one(self, j: int, x: np.ndarray) -> np.ndarray:
        m = self.models[j]
        if not hasattr(m, "predict"):
            return np.full(x.shape[0], float(m))
        mu, sd = self.scales[j]
        return m.predict(x) * sd + mu

    def predict(self, x: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(x)
        return np.column_stack([self._predict_one(j, x) for j in range(len(self.models))])

    def importances(self, feature_names: list[str]) -> dict[str, float]:
        """Mean inverse ARD length scale across targets (larger: more relevant)."""
        inv = []
        for m in self.models:
            if hasattr(m, "kernel_"):
                ls = np.atleast_1d(m.kernel_.k1.k2.length_scale)
                inv.append(1.0 / ls)
        imp = np.mean(inv, axis=0) if inv else np.zeros(len(feature_names))
        imp = imp / max(float(np.sum(imp)), 1e-12)
        return {n: float(v) for n, v in zip(feature_names, imp)}
