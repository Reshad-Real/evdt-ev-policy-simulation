"""Stage 3: surrogate modelling, variance-based sensitivity and multi-objective
policy optimisation.

A Latin-hypercube design over the twenty-dimensional lever space is evaluated
with the full model; a Gaussian-process surrogate (one per output, ARD kernel)
is fitted to it and scored on an independent Latin-hypercube test set that
played no part in fitting, against the random forest of the previous version.
First-order and total Sobol indices, with bootstrap intervals, are then
estimated on the surrogate, and NSGA-II searches the same space for the Pareto
frontier between
net present value, additional abatement and peak transformer loading.  Frontier
members are re-evaluated with the full model and the error of each objective is
reported separately.

Usage:  py -3 run_optimization.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evdt import engine, learning, optimization as opt, policy as pol, scenarios as sc  # noqa: E402
from evdt.uncertainty import latin_hypercube, sobol_indices  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

N_DESIGN = 300
N_TEST = 60
POP_SIZE = 88
GENERATIONS = 55
N_VERIFY = 30
SEED = 909
ARCH_SEED = {"underdeveloped": 1, "developing": 2, "developed": 3}

LEVER_KEYS = list(pol.LEVERS.keys())
TARGETS = ["npv_musd", "cumulative_emissions_saved_mt", "final_transformer_loading",
           "final_wait_min", "mean_loss_fraction", "final_ev_share",
           "final_wbg_share", "mean_eta_traction"]
OBJECTIVES = ["npv_musd", "cumulative_emissions_saved_mt", "final_transformer_loading"]


#: Worker processes per archetype for the design and test simulations
#: (``--workers N``); results do not depend on it.
WORKERS = (int(sys.argv[sys.argv.index("--workers") + 1])
           if "--workers" in sys.argv else 1)


def evaluate_vector(arch, vector: np.ndarray, seed: int) -> dict:
    pkg = pol.package_from_vector("opt", "optimised package", arch.key, vector)
    out = engine.simulate_horizon(arch, pkg, sc.HORIZON, seed=seed)
    return engine.horizon_summary(out["records"], arch)


def _evaluate_key(akey: str, vector: np.ndarray) -> dict:
    return evaluate_vector(sc.ARCHETYPES[akey], vector, SEED)


def evaluate(arch, x: np.ndarray, label: str) -> np.ndarray:
    """Full simulations of a set of lever vectors, cached on disk so that a
    failure after this point does not discard the evaluations."""
    cache = RESULTS / f"_opt_cache_{arch.key}_{label}.npz"
    if cache.exists():
        c = np.load(cache)
        if c["x"].shape == x.shape and np.allclose(c["x"], x):
            print(f"    {label}: {x.shape[0]} evaluations read from cache", flush=True)
            return c["y"]
    rows = []
    if WORKERS > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(WORKERS) as ex:
            for i, s in enumerate(ex.map(_evaluate_key, [arch.key] * len(x), list(x),
                                         chunksize=4)):
                rows.append([s[t] for t in TARGETS])
                if (i + 1) % 50 == 0:
                    print(f"    {label}: {i + 1}/{x.shape[0]}", flush=True)
    else:
        for i, xi in enumerate(x):
            s = evaluate_vector(arch, xi, SEED)
            rows.append([s[t] for t in TARGETS])
            if (i + 1) % 50 == 0:
                print(f"    {label}: {i + 1}/{x.shape[0]}", flush=True)
    y = np.array(rows)
    np.savez(cache, x=x, y=y)
    return y


PARTS = ("design", "test", "surrogate", "sobol", "pareto", "hist")


def main() -> None:
    t0 = time.perf_counter()
    if "--merge" in sys.argv:
        frames = {p: pd.concat([pd.read_csv(RESULTS / f"_opt_{p}_{a}.csv")
                                for a in sc.ARCHETYPE_ORDER], ignore_index=True)
                  for p in PARTS}
        finish(frames, t0)
        for f in RESULTS.glob("_opt_*.csv"):
            f.unlink()
        return
    only = sys.argv[sys.argv.index("--arch") + 1] if "--arch" in sys.argv else None
    design_rows, surrogate_rows, sobol_rows, pareto_rows, hist_rows = [], [], [], [], []
    test_rows = []

    for akey in sc.ARCHETYPE_ORDER:
        if only and akey != only:
            continue
        arch = sc.ARCHETYPES[akey]
        rng = np.random.default_rng(SEED + ARCH_SEED[akey])
        x = latin_hypercube(N_DESIGN, len(LEVER_KEYS), rng)
        anchors = np.array([pol.lever_vector(p, 2035)
                            for p in sc.policy_packages(akey).values()])
        x = np.vstack([x, anchors])
        x_test = latin_hypercube(N_TEST, len(LEVER_KEYS),
                                 np.random.default_rng(SEED + 100 + ARCH_SEED[akey]))
        print(f"[design] {akey}: {x.shape[0]} + {N_TEST} test simulations", flush=True)
        y = evaluate(arch, x, "design")
        y_test = evaluate(arch, x_test, "test")
        for i in range(x.shape[0]):
            row = {"archetype": akey, "sample": i, "set": "design"}
            row.update({f"lever_{k}": float(v) for k, v in zip(LEVER_KEYS, x[i])})
            row.update({t: float(v) for t, v in zip(TARGETS, y[i])})
            design_rows.append(row)

        print(f"[surrogate] {akey} ...", flush=True)
        surrogate = learning.PolicySurrogate(seed=SEED)
        surrogate.fit(x, y, TARGETS, train_fraction=1.0)
        pred = surrogate.predict(x_test)
        met = {"archetype": akey, "n_train": int(x.shape[0]), "n_test": N_TEST}
        for j, t in enumerate(TARGETS):
            obs, pr = y_test[:, j], pred[:, j]
            ss = float(np.sum((obs - obs.mean()) ** 2))
            met[f"r2_{t}"] = (1.0 - float(np.sum((obs - pr) ** 2)) / ss
                              if ss > 1e-12 else float("nan"))
            scale = float(np.ptp(obs)) if np.ptp(obs) > 0 else 1.0
            met[f"nrmse_{t}"] = float(np.sqrt(np.mean((obs - pr) ** 2))) / scale
            for i in range(N_TEST):
                test_rows.append({"archetype": akey, "target": t, "sample": i,
                                  "observed": float(obs[i]), "predicted": float(pr[i])})
        surrogate_rows.append(met)

        # Baseline for the response to reviewers: the random forest of the
        # previous version, scored on the same test set.
        from sklearn.ensemble import RandomForestRegressor
        for t in OBJECTIVES:
            j = TARGETS.index(t)
            rf = RandomForestRegressor(380, min_samples_leaf=2, max_features=0.55,
                                       n_jobs=-1, random_state=SEED).fit(x, y[:, j])
            obs = y_test[:, j]
            met[f"r2_rf_{t}"] = 1.0 - float(np.sum((obs - rf.predict(x_test)) ** 2)
                                            / max(np.sum((obs - obs.mean()) ** 2), 1e-12))

        for target_name in ("npv_musd", "cumulative_emissions_saved_mt"):
            j = TARGETS.index(target_name)
            s = sobol_indices(lambda z: surrogate.predict(z)[:, j], len(LEVER_KEYS),
                              n=16384, seed=17, n_boot=200)
            for k, name in enumerate(LEVER_KEYS):
                sobol_rows.append({"archetype": akey, "target": target_name,
                                   "lever": name, "label": pol.LEVERS[name].label,
                                   "domain": pol.LEVERS[name].domain,
                                   "S1": float(s["S1"][k]), "ST": float(s["ST"][k]),
                                   "S1_lo": float(s["S1_lo"][k]),
                                   "S1_hi": float(s["S1_hi"][k]),
                                   "ST_lo": float(s["ST_lo"][k]),
                                   "ST_hi": float(s["ST_hi"][k])})

        print(f"[nsga2] {akey} ...", flush=True)
        jo = [TARGETS.index(o) for o in OBJECTIVES]

        def objectives(population: np.ndarray) -> np.ndarray:
            pr = surrogate.predict(population)
            return np.column_stack([-pr[:, jo[0]], -pr[:, jo[1]], pr[:, jo[2]]])

        res = opt.nsga2(objectives, len(LEVER_KEYS), 3, POP_SIZE, GENERATIONS, seed=SEED)
        for h in res["history"]:
            hist_rows.append({"archetype": akey, **h})
        front_x, front_f = res["pareto_x"], res["pareto_f"]
        knee = opt.knee_point(front_f[:, :2])
        # Verify an evenly spread subset of the frontier, ordered along NPV, plus
        # the knee, with the full model.
        order = np.argsort(front_f[:, 0])
        pick = order[np.unique(np.linspace(0, order.size - 1,
                                           min(N_VERIFY, order.size)).round().astype(int))]
        verify_idx = set(pick.tolist()) | {int(knee)}
        for i in range(front_x.shape[0]):
            row = {"archetype": akey, "member": i, "is_knee": bool(i == knee),
                   "npv_musd_surrogate": float(-front_f[i, 0]),
                   "emissions_mt_surrogate": float(-front_f[i, 1]),
                   "transformer_loading_surrogate": float(front_f[i, 2])}
            row.update({f"lever_{k}": float(v) for k, v in zip(LEVER_KEYS, front_x[i])})
            if i in verify_idx:
                s = evaluate_vector(arch, front_x[i], SEED)
                row.update({f"verified_{t}": float(s[t]) for t in TARGETS})
            pareto_rows.append(row)

    frames = {"design": pd.DataFrame(design_rows), "test": pd.DataFrame(test_rows),
              "surrogate": pd.DataFrame(surrogate_rows), "sobol": pd.DataFrame(sobol_rows),
              "pareto": pd.DataFrame(pareto_rows), "hist": pd.DataFrame(hist_rows)}
    if only:
        for p, df in frames.items():
            df.to_csv(RESULTS / f"_opt_{p}_{only}.csv", index=False)
        print(f"{only} done in {time.perf_counter() - t0:.0f} s", flush=True)
        return
    finish(frames, t0)


def finish(frames: dict, t0: float) -> None:
    frames["design"].to_csv(RESULTS / "lever_design.csv", index=False)
    frames["test"].to_csv(RESULTS / "surrogate_test_predictions.csv", index=False)
    frames["surrogate"].to_csv(RESULTS / "surrogate_performance.csv", index=False)
    frames["sobol"].to_csv(RESULTS / "sensitivity_sobol.csv", index=False)
    pf = frames["pareto"]
    pf.to_csv(RESULTS / "pareto_front.csv", index=False)
    frames["hist"].to_csv(RESULTS / "nsga2_history.csv", index=False)

    # per-objective verification errors of the frontier
    err_rows = []
    pairs = {"npv_musd": "npv_musd_surrogate",
             "cumulative_emissions_saved_mt": "emissions_mt_surrogate",
             "final_transformer_loading": "transformer_loading_surrogate"}
    v = pf.dropna(subset=["verified_npv_musd"])
    for akey, grp in v.groupby("archetype", sort=False):
        for obj, scol in pairs.items():
            full = grp[f"verified_{obj}"].to_numpy()
            sur = grp[scol].to_numpy()
            span = float(np.ptp(full)) if np.ptp(full) > 0 else 1.0
            err = (sur - full) / span
            rel = np.abs(sur - full) / np.maximum(np.abs(full), 1e-9)
            err_rows.append({"archetype": akey, "objective": obj, "n_verified": len(full),
                             "median_abs_error_norm": float(np.median(np.abs(err))),
                             "p90_abs_error_norm": float(np.percentile(np.abs(err), 90)),
                             "median_abs_rel_error": float(np.median(rel)),
                             "bias_norm": float(np.mean(err)),
                             "spearman": float(pd.Series(full).corr(pd.Series(sur),
                                                                    method="spearman"))})
    pd.DataFrame(err_rows).to_csv(RESULTS / "pareto_verification.csv", index=False)
    (RESULTS / "optimization_meta.json").write_text(json.dumps({
        "n_design": N_DESIGN, "n_anchor": 7, "n_test": N_TEST, "pop_size": POP_SIZE,
        "generations": GENERATIONS, "n_verify": N_VERIFY, "levers": LEVER_KEYS,
        "targets": TARGETS, "objectives": OBJECTIVES, "seed": SEED,
        "runtime_s": time.perf_counter() - t0}, indent=1), encoding="utf-8")
    print(f"total {time.perf_counter()-t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
