"""Stage 1b: the analyses added in response to the reviews of TTE-Reg-2026-08-3015.

1. Representation of power electronics.  Every package is re-run with the
   power electronics represented by a technology look-up table and by a single
   constant efficiency, under identical lever settings, so that what the
   device-level model contributes is measured rather than asserted.
2. Marginal value of each power-electronics instrument, alone, under the three
   representations.
3. Network ablation: the aggressive package without reinforcement, without
   flexibility, and without both, separating capacity added by construction
   from load actually moved.
4. Geographically concentrated charging: the studied feeder carries k times the
   national-average charging load.
5. Charging queues: site-level against nationally pooled M/M/c queues.
6. Adoption structure: elasticities halved and increased by half, and an
   alternative form in which price and charging act on the diffusion speed
   (hazard) instead of the sales ceiling.
7. Sequencing: the end state of the aggressive package reached access-first,
   system-first or simultaneously.
8. Decomposition of the charging emission intensity into timing, grid and
   efficiency effects.
9. Silicon-loss sensitivity: silicon losses scaled until the model reproduces
   the published drive-cycle gain of SiC, then instruments and rankings
   re-assessed.

Usage:  py -3 run_revision_analyses.py      (about 10 minutes)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evdt import engine, metrics, policy as pol, scenarios as sc  # noqa: E402
from evdt.policy import LEVERS, PolicyPackage  # noqa: E402
import run_deterministic as rd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SEED = rd.SEED
PE_LEVERS = ("wbg_mandate", "efficiency_standard", "hv_architecture")


def _run(arch, pkg, **kw) -> dict:
    out = engine.simulate_horizon(arch, pkg, sc.HORIZON, seed=SEED, **kw)
    return rd.summarise_run(arch, pkg, out["records"])


def _variant(pkg: PolicyPackage, key: str, label: str, targets: dict,
             phase_in: dict | None = None) -> PolicyPackage:
    return PolicyPackage(key, label, pkg.archetype, pkg.description, targets,
                         pkg.start_year, pkg.full_year, phase_in or {})


# ---------------------------------------------------------------------------
def pe_representation() -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = []
    dev = pd.read_csv(RESULTS / "horizon_summary.csv")
    dev["pe_mode"] = "device"
    frames.append(dev)
    for mode in ("lookup", "constant"):
        print(f"  pe_mode={mode}", flush=True)
        _, s, _, _ = rd.run_scenarios(pe_mode=mode)
        s["pe_mode"] = mode
        frames.append(s)
    allsum = pd.concat(frames, ignore_index=True)
    ranks = []
    for mode, grp in allsum.groupby("pe_mode", sort=False):
        r = rd.rank_policies(grp.drop(columns="pe_mode"))
        r["pe_mode"] = mode
        ranks.append(r)
    return allsum, pd.concat(ranks, ignore_index=True)


def pe_lever_marginal() -> pd.DataFrame:
    rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pk = sc.policy_packages(akey)
        s0 = pk["S0"]
        for mode in engine.PE_MODES:
            base = _run(arch, s0, pe_mode=mode)
            for lever in PE_LEVERS + ("all_pe",):
                tg = dict(s0.targets)
                if lever == "all_pe":
                    for k in PE_LEVERS:
                        tg[k] = max(pk["S2"].targets[k], 0.5)
                else:
                    tg[lever] = max(pk["S2"].targets[lever], 0.5)
                v = _variant(pk["S2"], f"S0+{lever}", lever, tg)
                s = _run(arch, v, pe_mode=mode)
                rows.append({
                    "archetype": akey, "pe_mode": mode, "lever": lever,
                    "target": tg.get(lever, np.nan),
                    "d_eta_traction_pp": 100 * (s["mean_eta_traction"]
                                                - base["mean_eta_traction"]),
                    "d_eta_charging_pp": 100 * (s["mean_eta_charging"]
                                                - base["mean_eta_charging"]),
                    "d_energy_twh": s["cumulative_energy_twh"]
                                    - base["cumulative_energy_twh"],
                    "d_conversion_loss_twh": s["cumulative_conversion_loss_twh"]
                                             - base["cumulative_conversion_loss_twh"],
                    "d_co2_mt": s["cumulative_emissions_saved_mt"]
                                - base["cumulative_emissions_saved_mt"],
                    "d_npv_musd": s["npv_musd"] - base["npv_musd"],
                    "d_ev_share_pp": 100 * (s["final_ev_share"] - base["final_ev_share"]),
                    "d_availability": s["final_charger_availability"]
                                      - base["final_charger_availability"],
                })
    return pd.DataFrame(rows)


def network_ablation() -> pd.DataFrame:
    rows = []
    flex = ("smart_charging", "tou_tariff", "v2g_enablement")
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pk = sc.policy_packages(akey)
        s5 = pk["S5"]
        variants = {"S0": pk["S0"], "S5": s5}
        t = dict(s5.targets); t["grid_investment"] = 0.0
        variants["S5 without reinforcement"] = _variant(s5, "S5-R", "", t)
        t = dict(s5.targets)
        for k in flex:
            t[k] = 0.0
        variants["S5 without flexibility"] = _variant(s5, "S5-F", "", t)
        t = dict(s5.targets); t["grid_investment"] = 0.0
        for k in flex:
            t[k] = 0.0
        variants["S5 without both"] = _variant(s5, "S5-RF", "", t)
        for name, pkg in variants.items():
            s = _run(arch, pkg)
            rows.append({"archetype": akey, "variant": name,
                         "tx_loading_2040_pu": s["final_transformer_loading"],
                         "tx_loading_vs_original_rating_pu":
                             s["final_transformer_loading_original"],
                         "v_min_2040_pu": s["final_v_min_pu"],
                         "ev_share_2040": s["final_ev_share"],
                         "npv_musd": s["npv_musd"]})
    return pd.DataFrame(rows)


def feeder_concentration() -> pd.DataFrame:
    rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pk = sc.policy_packages(akey)
        for pkey in ("S0", "S5"):
            for k in (1.0, 1.5, 2.0, 3.0):
                out = engine.simulate_horizon(arch, pk[pkey], sc.HORIZON, seed=SEED,
                                              feeder_concentration=k)
                last = out["records"][-1]
                rows.append({"archetype": akey, "policy": pkey, "concentration": k,
                             "tx_loading_2040_pu": last["transformer_loading_pu"],
                             "v_min_2040_pu": last["v_min_pu"],
                             "undervoltage_hours_frac": last["undervoltage_hours_frac"],
                             "ev_load_share": last["ev_load_share"]})
    return pd.DataFrame(rows)


def queue_modes() -> pd.DataFrame:
    rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pk = sc.policy_packages(akey)
        for pkey in ("S0", "S1", "S5"):
            for qm in ("site", "pooled"):
                out = engine.simulate_horizon(arch, pk[pkey], sc.HORIZON, seed=SEED,
                                              queue_mode=qm)
                last = out["records"][-1]
                rows.append({"archetype": akey, "policy": pkey, "queue_mode": qm,
                             "wait_2040_min": last["wait_mean_min"],
                             "saturation_2040": last["saturation_index"],
                             "rationed_2040": last["rationed_fraction"]})
    return pd.DataFrame(rows)


ADOPTION_VARIANTS = (("ceiling", 1.0, "base"), ("ceiling", 0.5, "elasticity x0.5"),
                     ("ceiling", 1.5, "elasticity x1.5"), ("hazard", 1.0, "hazard form"),
                     # transfer uncertainty (third revision): the developing and
                     # least-developed archetypes diffuse with the coefficients
                     # of one panel country instead of the panel means
                     ("ceiling", 1.0, "analog India"), ("ceiling", 1.0, "analog Indonesia"),
                     ("ceiling", 1.0, "analog Kenya"))


def _analog(arch, label: str):
    """Archetype with one panel country's Bass coefficients (developing and
    least-developed archetypes only)."""
    from dataclasses import replace
    if not label.startswith("analog ") or arch.key == "developed":
        return arch
    meta = json.loads((RESULTS / "calibration_panel.json").read_text(encoding="utf-8"))
    c = meta["coefficients"][label.split(" ", 1)[1]]
    return replace(arch, bass_p=c["p"], bass_q=c["q"])


def adoption_structure() -> pd.DataFrame:
    from dataclasses import replace
    rows = []
    for form, e, label in ADOPTION_VARIANTS:
        print(f"  adoption {label}", flush=True)
        summ = []
        for akey in sc.ARCHETYPE_ORDER:
            arch = _analog(replace(sc.ARCHETYPES[akey], adoption_elasticity=e), label)
            pk = sc.policy_packages(akey)
            for pkey in sc.POLICY_ORDER:
                summ.append(_run(arch, pk[pkey], adoption_form=form))
        rk = rd.rank_policies(pd.DataFrame(summ))
        rk["variant"] = label
        rows.append(rk)
    df = pd.concat(rows, ignore_index=True)
    base = df[df.variant == "base"].set_index(["archetype", "policy"])
    taus = []
    for label in df.variant.unique():
        for akey in sc.ARCHETYPE_ORDER:
            a = base.loc[akey].query("policy != 'S0'").policy_rank
            b = (df[(df.variant == label) & (df.archetype == akey)
                    & (df.policy != "S0")].set_index("policy").policy_rank)
            taus.append({"variant": label, "archetype": akey,
                         "kendall_tau": kendalltau(a.loc[b.index], b).statistic,
                         "same_first": bool(a.idxmin() == b.idxmin())})
    pd.DataFrame(taus).to_csv(RESULTS / "adoption_structure_rank_agreement.csv",
                              index=False)
    return df


def silicon_loss_sensitivity(bound: str = "upper") -> pd.DataFrame:
    """Bracket the converter model's two validation gaps from both sides.

    ``upper``: the validated loss models of Allca-Pekarovic et al. give +5.0 %
    range for an 800 V SiC inverter over a 400 V Si IGBT one, and the
    datasheet-fitted model gives somewhat less on the EPA cycles; every silicon
    loss parameter is scaled up until the model reproduces 5.0 %.
    ``lower``: the model understates the >99 % peak efficiency ORNL measured on
    production Si IGBT inverters; every silicon loss parameter is scaled down
    until all three benchmarked inverters reach 99.0 %.  Each variant improves
    one comparison and worsens the other, so together they bracket the device
    model; the power-electronics instruments and the package rankings are
    re-assessed under each.
    """
    from evdt import powerelectronics as pe
    import run_validation as rv

    def rows_at(k: float) -> list[dict]:
        pe.SILICON_LOSS_MULT = k
        pe.clear_caches()
        return rv.check_converters_vs_literature()

    def gain(rows) -> float:
        return next(r["model"] for r in rows if "SiC-MOSFET at 800 V" in r["quantity"])

    def peak_min(rows) -> float:
        # the three benchmarked silicon IGBT traction inverters only
        return min(r["model"] for r in rows
                   if r["quantity"].startswith("Si IGBT traction inverter, peak efficiency"))

    if bound == "upper":
        # silicon losses up until the SiC range gain reaches 5.0 %
        lo, hi = 1.0, 3.0
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            if gain(rows_at(mid)) < 0.050:
                lo = mid
            else:
                hi = mid
    else:
        # silicon losses down until the lowest benchmarked peak reaches 99.0 %
        lo, hi = 0.2, 1.0
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            if peak_min(rows_at(mid)) < 0.990:
                hi = mid
            else:
                lo = mid
    k = 0.5 * (lo + hi)
    rows = rows_at(k)
    g = gain(rows)
    peak = next(r["model"] for r in rows if "375 V" in r["quantity"])
    pmin = peak_min(rows)
    engine._lookup_table.cache_clear()
    out = []
    try:
        lev = pe_lever_marginal()
        _, summ, _, _ = rd.run_scenarios()
        rk = rd.rank_policies(summ)
    finally:
        pe.SILICON_LOSS_MULT = 1.0
        pe.clear_caches()
        engine._lookup_table.cache_clear()
    base_rk = pd.read_csv(RESULTS / "policy_ranking.csv").set_index(["archetype", "policy"])
    changes = int(sum(int(base_rk.loc[(r.archetype, r.policy), "policy_rank"])
                      != int(r.policy_rank)
                      for r in rk.itertuples() if r.policy != "S0"))
    lev["silicon_loss_mult"] = k
    lev["range_gain_sic800"] = g
    lev["igbt_peak_375v"] = peak
    lev["igbt_peak_min"] = pmin
    lev["rank_changes_vs_base"] = changes
    suffix = "" if bound == "upper" else "_low"
    rk.to_csv(RESULTS / f"silicon_sensitivity{suffix}_ranking.csv", index=False)
    return lev


def sequencing() -> pd.DataFrame:
    access = [k for k, v in LEVERS.items() if v.domain in ("fiscal", "infrastructure")]
    system = [k for k in LEVERS if k not in access]
    early, late = (2026, 2030), (2031, 2035)
    rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pk = sc.policy_packages(akey)
        s5 = pk["S5"]
        variants = {
            "simultaneous": _variant(s5, "SEQ-0", "", s5.targets,
                                     {k: (2026, 2033) for k in LEVERS}),
            "access first": _variant(s5, "SEQ-A", "", s5.targets,
                                     {**{k: early for k in access},
                                      **{k: late for k in system}}),
            "system first": _variant(s5, "SEQ-S", "", s5.targets,
                                     {**{k: early for k in system},
                                      **{k: late for k in access}}),
        }
        base = _run(arch, pk["S0"])
        for name, pkg in variants.items():
            s = _run(arch, pkg)
            d_cost = s["discounted_cost_musd"] - base["discounted_cost_musd"]
            d_ben = s["discounted_benefit_musd"] - base["discounted_benefit_musd"]
            rows.append({"archetype": akey, "sequence": name,
                         "ev_share_2040": s["final_ev_share"],
                         "d_co2_mt": s["cumulative_emissions_saved_mt"]
                                     - base["cumulative_emissions_saved_mt"],
                         "d_npv_musd": s["npv_musd"] - base["npv_musd"],
                         "incremental_bcr": d_ben / d_cost if d_cost > 0 else np.nan,
                         "tx_loading_2040_pu": s["final_transformer_loading"],
                         "wait_2040_min": s["final_wait_min"]})
    return pd.DataFrame(rows)


def intensity_decomposition() -> pd.DataFrame:
    """Charging emission intensity, S0 against S5, split into three effects.

    I = sum_h E_h f_h / km.  Moving from (E0, f0, k0) to (E1, f1, k1), the
    timing effect redistributes energy over hours at fixed grid factors, the
    grid effect changes the hourly factors at fixed timing, and the energy
    effect scales total energy per kilometre.  Shapley averaging over the
    orderings makes the three terms sum exactly to the total change.
    """
    rows = []
    rec = pd.read_csv(RESULTS / "scenario_records.csv")
    for akey in sc.ARCHETYPE_ORDER:
        res = {}
        for pkey in ("S0", "S5"):
            s = pd.read_csv(RESULTS / f"series_{akey}_{pkey}_2035.csv")
            r = rec[(rec.archetype == akey) & (rec.policy == pkey)
                    & (rec.year == 2035)].iloc[0]
            e = s.ev_mw.to_numpy()
            res[pkey] = {"shape": e / e.sum(), "f": s.emission_factor.to_numpy(),
                         "e_per_km": r.plug_energy_gwh * 1e9 / (r.vehicle_km_billion * 1e9),
                         "night": float(e[(np.arange(e.size) % 24 < 6)
                                          | (np.arange(e.size) % 24 >= 22)].sum() / e.sum()),
                         "solar": float(e[(np.arange(e.size) % 24 >= 9)
                                          & (np.arange(e.size) % 24 < 16)].sum() / e.sum())}

        def intensity(sh, f, k):
            # kg/kWh times Wh/km gives g/km
            return float(np.sum(sh * f) * k)

        a, b = res["S0"], res["S5"]
        comps = {"timing": ("shape",), "grid": ("f",), "energy": ("e_per_km",)}
        names = list(comps)
        import itertools
        contrib = {n: 0.0 for n in names}
        perms = list(itertools.permutations(names))
        for perm in perms:
            cur = {"shape": a["shape"], "f": a["f"], "e_per_km": a["e_per_km"]}
            prev = intensity(cur["shape"], cur["f"], cur["e_per_km"])
            for n in perm:
                cur[comps[n][0]] = b[comps[n][0]]
                now = intensity(cur["shape"], cur["f"], cur["e_per_km"])
                contrib[n] += (now - prev) / len(perms)
                prev = now
        i0 = intensity(a["shape"], a["f"], a["e_per_km"])
        i1 = intensity(b["shape"], b["f"], b["e_per_km"])
        rows.append({"archetype": akey, "intensity_S0_g_km": i0, "intensity_S5_g_km": i1,
                     "change_g_km": i1 - i0, "timing_effect": contrib["timing"],
                     "grid_effect": contrib["grid"], "energy_effect": contrib["energy"],
                     "night_share_S0": a["night"], "night_share_S5": b["night"],
                     "solar_share_S0": a["solar"], "solar_share_S5": b["solar"]})
    return pd.DataFrame(rows)


def main() -> None:
    t0 = time.perf_counter()
    print("[1/8] power-electronics representation ...", flush=True)
    allsum, ranks = pe_representation()
    allsum.to_csv(RESULTS / "pe_mode_summary.csv", index=False)
    ranks.to_csv(RESULTS / "pe_mode_ranking.csv", index=False)
    print("[2/8] marginal power-electronics instruments ...", flush=True)
    pe_lever_marginal().to_csv(RESULTS / "pe_lever_marginal.csv", index=False)
    print("[3/8] network ablation ...", flush=True)
    network_ablation().to_csv(RESULTS / "network_ablation.csv", index=False)
    print("[4/8] concentrated charging ...", flush=True)
    feeder_concentration().to_csv(RESULTS / "feeder_concentration.csv", index=False)
    print("[5/8] queue formulation ...", flush=True)
    queue_modes().to_csv(RESULTS / "queue_mode_comparison.csv", index=False)
    print("[6/8] adoption structure ...", flush=True)
    adoption_structure().to_csv(RESULTS / "adoption_structure_sensitivity.csv",
                                index=False)
    print("[7/8] sequencing ...", flush=True)
    sequencing().to_csv(RESULTS / "sequencing.csv", index=False)
    print("[8/9] emission-intensity decomposition ...", flush=True)
    intensity_decomposition().to_csv(RESULTS / "emission_intensity_decomposition.csv",
                                     index=False)
    print("[9/9] silicon-loss brackets (SiC drive-cycle gain; IGBT peak) ...", flush=True)
    silicon_loss_sensitivity("upper").to_csv(RESULTS / "silicon_sensitivity.csv", index=False)
    silicon_loss_sensitivity("lower").to_csv(RESULTS / "silicon_sensitivity_low.csv",
                                             index=False)
    print(f"done in {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
