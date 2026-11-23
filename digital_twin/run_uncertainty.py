"""Stage 2 of the EV-DT experiment: uncertainty propagation and screening.

Latin-hypercube Monte-Carlo propagation of the eighteen uncertain parameters
(fourteen exogenous, plus device switching energy and on-state resistance, the
policy elasticity of adoption and the displaced-fuel emission factor) through
the full multi-year model, for three representative policy packages in each
archetype, followed by Morris elementary-effect screening of the same space.
All packages see the same design, so draws are matched across packages.

Runtime is of the order of one hour; the script is intended to be launched in
the background.

Usage:  py -3 run_uncertainty.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evdt import engine, scenarios as sc, uncertainty as unc

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

N_MC = 100
MORRIS_TRAJECTORIES = 8
MC_POLICIES = ("S0", "S4", "S5")
TRACK = ("final_ev_share", "final_wbg_share", "final_wait_min", "final_reliability",
         "mean_loss_fraction", "mean_voltage_deviation", "final_transformer_loading",
         "mean_renewable_utilisation", "mean_eta_traction", "mean_eta_charging",
         "cumulative_conversion_loss_twh", "final_soh")


def merge() -> None:
    """Combine the per-archetype parts written by ``--arch`` runs."""
    parts = {"mc": [], "morris": []}
    for akey in sc.ARCHETYPE_ORDER:
        parts["mc"].append(pd.read_csv(RESULTS / f"_part_mc_{akey}.csv"))
        parts["morris"].append(pd.read_csv(RESULTS / f"_part_morris_{akey}.csv"))
    df_mc = pd.concat(parts["mc"], ignore_index=True)
    df_mc.to_csv(RESULTS / "monte_carlo_samples.csv", index=False)
    pd.concat(parts["morris"], ignore_index=True).to_csv(
        RESULTS / "sensitivity_morris.csv", index=False)
    stat_rows = []
    for (akey, pkey), grp in df_mc.groupby(["archetype", "policy"], sort=False):
        rows = grp.to_dict("records")
        for key in ("npv_musd", "bcr", "payback_years",
                    "cumulative_emissions_saved_mt", *TRACK):
            if key in grp.columns:
                stat_rows.append({"archetype": akey, "policy": pkey, "metric": key,
                                  **unc.summarise_mc(rows, key)})
    pd.DataFrame(stat_rows).to_csv(RESULTS / "monte_carlo_summary.csv", index=False)
    (RESULTS / "uncertainty_meta.json").write_text(json.dumps({
        "n_monte_carlo": N_MC, "morris_trajectories": MORRIS_TRAJECTORIES,
        "policies": list(MC_POLICIES),
        "parameters": [{"key": p.key, "label": p.label, "lo": p.lo, "hi": p.hi,
                        "kind": p.kind} for p in unc.UNCERTAIN]}, indent=1),
        encoding="utf-8")
    for f in RESULTS.glob("_part_*"):
        if f.name.startswith(("_part_mc_", "_part_morris_")):
            f.unlink()
    print("merged", len(df_mc), "Monte-Carlo rows")


def run_arch(akey: str) -> None:
    """Monte Carlo and Morris for one archetype (parallel execution)."""
    t0 = time.perf_counter()
    arch = sc.ARCHETYPES[akey]
    packages = sc.policy_packages(akey)
    mc_rows, morris_rows = [], []
    for pkey in MC_POLICIES:
        print(f"[MC] {akey}/{pkey} ...", flush=True)
        out = unc.monte_carlo(arch, packages[pkey], sc.HORIZON,
                              simulate_fn=engine.simulate_horizon,
                              summary_fn=engine.horizon_summary,
                              n=N_MC, seed=4242, keys=TRACK)
        for i, row in enumerate(out["rows"]):
            mc_rows.append({"archetype": akey, "policy": pkey, "sample": i,
                            **{k: v for k, v in row.items()
                               if isinstance(v, (int, float))}})
        design = pd.DataFrame(out["design"], columns=out["parameters"])
        design.insert(0, "policy", pkey)
        design.insert(0, "archetype", akey)
        design.to_csv(RESULTS / f"mc_design_{akey}_{pkey}.csv", index=False)
    pd.DataFrame(mc_rows).to_csv(RESULTS / f"_part_mc_{akey}.csv", index=False)
    for target in ("npv_musd", "cumulative_emissions_saved_mt"):
        print(f"[Morris] {akey}/{target} ...", flush=True)
        res = unc.morris_effects(arch, packages["S5"], sc.HORIZON,
                                 simulate_fn=engine.simulate_horizon,
                                 summary_fn=engine.horizon_summary,
                                 target=target, trajectories=MORRIS_TRAJECTORIES,
                                 levels=8)
        for j, name in enumerate(res["parameters"]):
            morris_rows.append({"archetype": akey, "target": target, "parameter": name,
                                "label": res["labels"][j],
                                "mu_star": float(res["mu_star"][j]),
                                "sigma": float(res["sigma"][j])})
    pd.DataFrame(morris_rows).to_csv(RESULTS / f"_part_morris_{akey}.csv", index=False)
    print(f"{akey} done in {time.perf_counter() - t0:.0f} s", flush=True)


def main() -> None:
    if "--arch" in sys.argv:
        run_arch(sys.argv[sys.argv.index("--arch") + 1])
        return
    if "--merge" in sys.argv:
        merge()
        return
    t0 = time.perf_counter()
    mc_rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        packages = sc.policy_packages(akey)
        for pkey in MC_POLICIES:
            print(f"[MC] {akey}/{pkey} ...", flush=True)
            out = unc.monte_carlo(
                arch, packages[pkey], sc.HORIZON,
                simulate_fn=engine.simulate_horizon,
                summary_fn=engine.horizon_summary,
                n=N_MC, seed=4242, keys=TRACK)
            for i, row in enumerate(out["rows"]):
                mc_rows.append({"archetype": akey, "policy": pkey, "sample": i,
                                **{k: v for k, v in row.items()
                                   if isinstance(v, (int, float))}})
            design = pd.DataFrame(out["design"], columns=out["parameters"])
            design.insert(0, "policy", pkey)
            design.insert(0, "archetype", akey)
            design.to_csv(RESULTS / f"mc_design_{akey}_{pkey}.csv", index=False)
    df_mc = pd.DataFrame(mc_rows)
    df_mc.to_csv(RESULTS / "monte_carlo_samples.csv", index=False)

    # distributional summary
    stat_rows = []
    for (akey, pkey), grp in df_mc.groupby(["archetype", "policy"], sort=False):
        rows = grp.to_dict("records")
        for key in ("npv_musd", "bcr", "payback_years",
                    "cumulative_emissions_saved_mt", *TRACK):
            if key not in grp.columns:
                continue
            stat_rows.append({"archetype": akey, "policy": pkey, "metric": key,
                              **unc.summarise_mc(rows, key)})
    pd.DataFrame(stat_rows).to_csv(RESULTS / "monte_carlo_summary.csv", index=False)
    print(f"[MC] done at {time.perf_counter()-t0:.0f} s", flush=True)

    # --- Morris screening --------------------------------------------------
    morris_rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pkg = sc.policy_packages(akey)["S5"]
        for target in ("npv_musd", "cumulative_emissions_saved_mt"):
            print(f"[Morris] {akey}/{target} ...", flush=True)
            res = unc.morris_effects(arch, pkg, sc.HORIZON,
                                     simulate_fn=engine.simulate_horizon,
                                     summary_fn=engine.horizon_summary,
                                     target=target,
                                     trajectories=MORRIS_TRAJECTORIES, levels=8)
            for j, name in enumerate(res["parameters"]):
                morris_rows.append({"archetype": akey, "target": target,
                                    "parameter": name, "label": res["labels"][j],
                                    "mu_star": float(res["mu_star"][j]),
                                    "sigma": float(res["sigma"][j])})
    pd.DataFrame(morris_rows).to_csv(RESULTS / "sensitivity_morris.csv", index=False)

    (RESULTS / "uncertainty_meta.json").write_text(json.dumps({
        "n_monte_carlo": N_MC, "morris_trajectories": MORRIS_TRAJECTORIES,
        "policies": list(MC_POLICIES),
        "parameters": [{"key": p.key, "label": p.label, "lo": p.lo, "hi": p.hi,
                        "kind": p.kind} for p in unc.UNCERTAIN],
        "runtime_s": time.perf_counter() - t0}, indent=1), encoding="utf-8")
    print(f"total {time.perf_counter()-t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
