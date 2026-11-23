"""Uncertainty quantification: Latin-hypercube Monte Carlo and global sensitivity.

Two complementary analyses are provided.  Monte-Carlo propagation perturbs the
exogenous parameters of an archetype (fuel and electricity prices, grid carbon
intensity, technology cost trajectories, temperature, adoption behaviour,
network strength) and reports the resulting distribution of every indicator, so
that policy rankings can be reported with confidence intervals rather than as
point estimates.  Global sensitivity analysis uses the Morris elementary-effect
screening design followed by a variance-based Sobol decomposition evaluated on
the surrogate, which identifies the parameters and levers that actually drive
the outcome (docs_reference: meth-gsa, ai-prob-forecast).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .config import Archetype


# ---------------------------------------------------------------------------
# Uncertain parameter space
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class UncertainParameter:
    key: str
    label: str
    lo: float
    hi: float
    kind: str = "multiplicative"   # 'multiplicative' | 'absolute'


UNCERTAIN: tuple[UncertainParameter, ...] = (
    UncertainParameter("fuel_price", "Fossil fuel price", 0.62, 1.55),
    UncertainParameter("electricity_price", "Retail electricity price", 0.70, 1.45),
    UncertainParameter("grid_emission_factor", "Grid carbon intensity", 0.65, 1.30),
    UncertainParameter("grid_availability", "Supply availability", 0.94, 1.02),
    UncertainParameter("mean_temperature", "Mean ambient temperature", -3.5, 4.5,
                       "absolute"),
    UncertainParameter("capital_cost_premium", "Infrastructure cost premium", 0.80, 1.35),
    UncertainParameter("discount_rate", "Social discount rate", 0.75, 1.35),
    UncertainParameter("bass_q", "Word-of-mouth adoption coefficient", 0.65, 1.45),
    UncertainParameter("market_potential", "Market potential ceiling", 0.80, 1.12),
    UncertainParameter("transformer_headroom", "Network spare capacity", 0.82, 1.18),
    UncertainParameter("solar_ghi", "Solar resource", 0.88, 1.12),
    UncertainParameter("social_carbon_price", "Social carbon price", 0.45, 1.85),
    UncertainParameter("value_of_time", "Value of travel time", 0.65, 1.50),
    UncertainParameter("vehicle_stock_growth", "Vehicle stock growth", 0.70, 1.35),
    # Added in the revision: device-parameter and model-structure uncertainty.
    UncertainParameter("device_esw_mult", "Device switching energies", 0.75, 1.30),
    UncertainParameter("device_ron_mult", "Device on-state resistances", 0.85, 1.20),
    UncertainParameter("adoption_elasticity", "Policy elasticity of adoption", 0.50, 1.50),
    UncertainParameter("fuel_co2_mult", "Displaced-fuel emission factor", 0.93, 1.07),
    UncertainParameter("programme_cost_mult", "Programme resource cost", 0.50, 1.50),
)


def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """Latin-hypercube design on the unit cube."""
    cut = np.linspace(0.0, 1.0, n + 1)
    u = rng.random((n, d))
    a, b = cut[:n, None], cut[1:n + 1, None]
    pts = u * (b - a) + a
    for j in range(d):
        pts[:, j] = pts[rng.permutation(n), j]
    return pts


def perturb(arch: Archetype, unit: np.ndarray) -> Archetype:
    """Apply a unit-cube sample to the archetype's uncertain parameters."""
    updates = {}
    for u, par in zip(unit, UNCERTAIN):
        base = getattr(arch, par.key)
        if par.kind == "absolute":
            updates[par.key] = base + par.lo + u * (par.hi - par.lo)
        else:
            updates[par.key] = base * (par.lo + u * (par.hi - par.lo))
    updates["grid_availability"] = float(np.clip(updates["grid_availability"],
                                                 0.5, 0.9995))
    updates["market_potential"] = float(np.clip(updates["market_potential"], 0.05, 1.0))
    return replace(arch, **updates)


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------
def monte_carlo(arch: Archetype, package, horizon, simulate_fn, summary_fn,
                n: int = 256, seed: int = 12345,
                keys: tuple[str, ...] = ()) -> dict:
    """Propagate parameter uncertainty through the full multi-year twin."""
    rng = np.random.default_rng(seed)
    design = latin_hypercube(n, len(UNCERTAIN), rng)
    rows = []
    for i in range(n):
        a = perturb(arch, design[i])
        out = simulate_fn(a, package, horizon, seed=seed + i)
        s = summary_fn(out["records"], a)
        last = out["records"][-1]
        rec = {**s}
        # ``keys`` may name either horizon-summary fields (already present) or
        # final-year record fields; never overwrite a summary field with a
        # missing record field.
        for k in keys:
            if k not in rec and k in last:
                rec[k] = last[k]
        rows.append(rec)
    return {"design": design, "rows": rows,
            "parameters": [p.key for p in UNCERTAIN]}


def summarise_mc(rows: list[dict], key: str) -> dict[str, float]:
    v = np.array([r.get(key, np.nan) for r in rows], dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"mean": np.nan, "std": np.nan, "p05": np.nan, "p50": np.nan,
                "p95": np.nan, "cv": np.nan, "n": 0}
    return {"mean": float(v.mean()), "std": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "p05": float(np.percentile(v, 5)), "p50": float(np.percentile(v, 50)),
            "p95": float(np.percentile(v, 95)),
            "cv": float(v.std(ddof=1) / abs(v.mean())) if v.size > 1 and abs(v.mean()) > 1e-9 else 0.0,
            "n": int(v.size)}


# ---------------------------------------------------------------------------
# Morris elementary effects
# ---------------------------------------------------------------------------
def morris_design(d: int, trajectories: int, levels: int,
                  rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Morris one-at-a-time trajectories on a discrete grid."""
    delta = levels / (2.0 * (levels - 1))
    grid = np.linspace(0.0, 1.0 - delta, max(levels // 2, 1))
    points, moves = [], []
    for _ in range(trajectories):
        base = rng.choice(grid, size=d)
        order = rng.permutation(d)
        signs = rng.choice([-1.0, 1.0], size=d)
        x = base.copy()
        traj = [x.copy()]
        mv = []
        for j in order:
            step = signs[j] * delta
            if x[j] + step > 1.0 or x[j] + step < 0.0:
                step = -step
            x = x.copy()
            x[j] += step
            traj.append(x.copy())
            mv.append((j, step))
        points.append(np.array(traj))
        moves.append(mv)
    return np.array(points), np.array(moves, dtype=object)


def morris_effects(arch: Archetype, package, horizon, simulate_fn, summary_fn,
                   target: str = "npv_musd", trajectories: int = 12,
                   levels: int = 8, seed: int = 999) -> dict:
    """Elementary-effect screening of the uncertain parameter space."""
    rng = np.random.default_rng(seed)
    d = len(UNCERTAIN)
    points, moves = morris_design(d, trajectories, levels, rng)
    ee: dict[int, list[float]] = {j: [] for j in range(d)}
    run = 0
    for traj, mv in zip(points, moves):
        vals = []
        for x in traj:
            a = perturb(arch, x)
            out = simulate_fn(a, package, horizon, seed=seed + run)
            vals.append(summary_fn(out["records"], a).get(target, np.nan))
            run += 1
        for i, (j, step) in enumerate(mv):
            ee[j].append((vals[i + 1] - vals[i]) / step)
    mu_star = np.array([np.mean(np.abs(ee[j])) if ee[j] else 0.0 for j in range(d)])
    sigma = np.array([np.std(ee[j]) if len(ee[j]) > 1 else 0.0 for j in range(d)])
    order = np.argsort(-mu_star)
    return {"parameters": [p.key for p in UNCERTAIN],
            "labels": [p.label for p in UNCERTAIN],
            "mu_star": mu_star, "sigma": sigma, "order": order,
            "n_runs": run, "target": target}


# ---------------------------------------------------------------------------
# Variance-based sensitivity on a surrogate
# ---------------------------------------------------------------------------
def sobol_indices(surrogate, d: int, n: int = 4096, seed: int = 2024,
                  n_boot: int = 0) -> dict[str, np.ndarray]:
    """Janon (2014) first-order and Jansen (1999) total Sobol indices.

    Evaluated on the surrogate emulator, which makes the required ``n*(d+2)``
    model evaluations affordable.  A and B are the two halves of a scrambled
    Sobol' sequence in 2d dimensions.  With ``n_boot`` > 0 the rows are
    resampled to give 95 % bootstrap intervals (``S1_lo`` ... ``ST_hi``).
    """
    from scipy.stats import qmc
    m = int(np.ceil(np.log2(max(n, 2))))
    ab0 = qmc.Sobol(2 * d, scramble=True, seed=seed).random_base2(m)
    a, b = ab0[:, :d], ab0[:, d:]
    n = a.shape[0]
    ya = surrogate(a).ravel()
    yb = surrogate(b).ravel()
    yab = np.empty((d, n))
    for j in range(d):
        ab = a.copy()
        ab[:, j] = b[:, j]
        yab[j] = surrogate(ab).ravel()

    def estimate(idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ya_, yb_, yab_ = ya[idx], yb[idx], yab[:, idx]
        var = float(np.var(np.concatenate([ya_, yb_])))
        # first order: Janon et al. (2014), asymptotically efficient; f(B) and
        # f(A_B^j) share only column j
        mean_j = 0.5 * np.mean(yb_[None, :] + yab_, axis=1)
        num = np.mean(yb_[None, :] * yab_, axis=1) - mean_j ** 2
        den = np.mean(0.5 * (yb_[None, :] ** 2 + yab_ ** 2), axis=1) - mean_j ** 2
        s1 = num / np.maximum(den, 1e-12)
        # total: Jansen (1999)
        st = 0.5 * np.mean((ya_[None, :] - yab_) ** 2, axis=1) / max(var, 1e-12)
        return s1, st

    s1, st = estimate(np.arange(n))
    out = {"S1": np.clip(s1, 0.0, 1.0), "ST": np.clip(st, 0.0, 1.5),
           "variance": float(np.var(np.concatenate([ya, yb])))}
    if n_boot > 0:
        rng = np.random.default_rng(seed + 1)
        boot = [estimate(rng.integers(0, n, n)) for _ in range(n_boot)]
        s1b = np.array([b_[0] for b_ in boot])
        stb = np.array([b_[1] for b_ in boot])
        out.update({"S1_lo": np.percentile(s1b, 2.5, axis=0),
                    "S1_hi": np.percentile(s1b, 97.5, axis=0),
                    "ST_lo": np.percentile(stb, 2.5, axis=0),
                    "ST_hi": np.percentile(stb, 97.5, axis=0)})
    return out
