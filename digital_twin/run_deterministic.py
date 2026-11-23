"""Stage 1 of the EV-DT experiment: deterministic scenario campaign.

Runs every policy package for every country archetype over the 2025-2040
horizon, ranks the policies with TOPSIS, computes incremental cost-benefit
statistics against the no-policy counterfactual, and exports the
power-electronic device and converter characterisations used in the manuscript.

Outputs are written to ``../results`` as CSV and JSON.

Usage:  py -3 run_deterministic.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evdt import battery as bat
from evdt import economics as eco
from evdt import engine, metrics, policy as pol
from evdt import powerelectronics as pe
from evdt import scenarios as sc
from evdt.config import (BATTERY_LIBRARY, CHARGER_DEVICE_LIBRARY, CHARGER_HV_VARIANTS,
                         CHARGER_LIBRARY,
                         DEVICE_LIBRARY, HV_VARIANTS, LV_DEVICE_LIBRARY,
                         VEHICLE_LIBRARY, charger_device_for, device_for,
                         library_snapshot)

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
SEED = 20260801


# ---------------------------------------------------------------------------
def summarise_run(arch, pkg, records: list[dict]) -> dict:
    """Horizon summary plus the final-year fields the indicator set reads."""
    summary = engine.horizon_summary(records, arch)
    summary.update({"archetype": arch.key, "policy": pkg.key,
                    "policy_label": pkg.label,
                    "policy_description": pkg.description})
    last = records[-1]
    for k in metrics.INDICATOR_KEYS:
        if k not in summary:
            summary[k] = last.get(k, np.nan)
    summary["technology_readiness"] = metrics.technology_readiness(last)
    summary.update({f"domain_{d}": v for d, v in pkg.domain_intensity(2035).items()})
    return summary


def run_scenarios(pe_mode: str = "device", **kw) -> tuple[pd.DataFrame, pd.DataFrame,
                                                          dict, pd.DataFrame]:
    records, summaries, segment_rows, series_store = [], [], [], {}
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        packages = sc.policy_packages(akey)
        for pkey in sc.POLICY_ORDER:
            pkg = packages[pkey]
            out = engine.simulate_horizon(arch, pkg, sc.HORIZON, seed=SEED,
                                          keep_series_for=2035, pe_mode=pe_mode, **kw)
            for rec in out["records"]:
                seg = rec.pop("segment_economics", {})
                seg_out = rec.pop("segment_outputs", {})
                for skey, sval in seg.items():
                    segment_rows.append({"archetype": akey, "policy": pkey,
                                         "year": rec["year"], "segment": skey,
                                         **sval, **seg_out.get(skey, {})})
                records.append(rec)
            summaries.append(summarise_run(arch, pkg, out["records"]))
            if pkey in ("S0", "S5") and out["series"] is not None:
                series_store[f"{akey}_{pkey}"] = out["series"]
    return (pd.DataFrame(records), pd.DataFrame(summaries), series_store,
            pd.DataFrame(segment_rows))


def rank_policies(df_sum: pd.DataFrame, weights=None) -> pd.DataFrame:
    """TOPSIS ranking and incremental cost-benefit statistics per archetype.

    The reference package S0 is the counterfactual against which the
    incremental economics and the additional abatement of every other package
    are measured; it is reported but excluded from the multi-criteria ranking,
    for which its incremental quantities are undefined by construction.
    """
    frames = []
    for akey, grp in df_sum.groupby("archetype", sort=False):
        rows = grp.to_dict("records")
        base = next(r for r in rows if r["policy"] == "S0")
        inc = metrics.incremental_assessment(rows, base)
        out = pd.DataFrame(inc)
        ranked = [r for r in inc if r["policy"] != "S0"]
        cc, rank = metrics.policy_score(ranked, weights)
        score_map = {r["policy"]: c for r, c in zip(ranked, cc)}
        rank_map = {r["policy"]: int(k) for r, k in zip(ranked, rank)}
        out["policy_score"] = out["policy"].map(score_map)
        out["policy_rank"] = out["policy"].map(rank_map)
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


def weight_sensitivity(df_sum: pd.DataFrame) -> dict:
    res = {}
    for akey, grp in df_sum.groupby("archetype", sort=False):
        rows = grp.to_dict("records")
        base = next(r for r in rows if r["policy"] == "S0")
        ranked = [r for r in metrics.incremental_assessment(rows, base)
                  if r["policy"] != "S0"]
        res[akey] = metrics.weight_sensitivity(ranked)
    res["weights"] = {i.key: {"label": i.label, "group": i.group,
                              "benefit": i.benefit, "weight": float(w)}
                      for i, w in zip(metrics.INDICATORS, metrics.base_weights())}
    return res


# ---------------------------------------------------------------------------
def converter_characterisation() -> dict[str, pd.DataFrame]:
    """Efficiency curves, power density, cost and reliability of every device."""
    eff_rows, summary_rows, pd_rows = [], [], []
    # (builder, DC link that selects the fitted device, device keys)
    hv = list(DEVICE_LIBRARY)
    lv = list(LV_DEVICE_LIBRARY)
    topologies = {
        "traction_inverter_400V": (lambda d: pe.traction_inverter(150.0, 400.0, d), 400.0, hv),
        "traction_inverter_800V": (lambda d: pe.traction_inverter(150.0, 800.0, d), 800.0, hv),
        "lv_drive_4kW_60V": (lambda d: pe.lv_traction_inverter(4.0, 60.0, d), 60.0, lv),
        "lv_drive_7p5kW_60V": (lambda d: pe.lv_traction_inverter(7.5, 60.0, d), 60.0, lv),
        "obc_pfc_11kW": (lambda d: pe.obc_pfc_stage(11.0, d), 400.0, hv),
        "obc_pfc_3p3kW": (lambda d: pe.obc_pfc_stage(3.3, d), 400.0, hv),
        "obc_dab_11kW": (lambda d: pe.obc_dab_stage(11.0, 400.0, d), 400.0, hv),
        "dcfc_afe_150kW": (lambda d: pe.dcfc_front_end(150.0, 800.0, d), 800.0, hv),
        "dcfc_iso_150kW": (lambda d: pe.dcfc_isolation(150.0, 800.0, d), 800.0, hv),
        "aux_dcdc_2p5kW": (lambda d: pe.auxiliary_dcdc(2.5, 400.0, d), 400.0, hv),
    }
    for tname, (builder, link, keys) in topologies.items():
        traction = "inverter" in tname or "drive" in tname
        for dkey in keys:
            # traction stages use the fitted power modules; charger and
            # auxiliary stages the fitted discrete parts (charger_device_for)
            dev = device_for(dkey, link) if traction or dkey in LV_DEVICE_LIBRARY \
                else charger_device_for(dkey, link)
            conv = builder(dev)
            loads, eff = pe.efficiency_curve(conv, dev, 40.0, n=50)
            for ll, ee in zip(loads, eff):
                eff_rows.append({"topology": tname, "device": dkey,
                                 "load_pu": ll, "efficiency": ee})
            op = pe.solve_converter(conv, dev, conv.rated_power, 40.0)
            duty = (pe.TRACTION_DUTY if "inverter" in tname else pe.CHARGING_DUTY)
            dens = pe.power_density(conv, dev, 40.0)
            ml = (op.n_series == 2 and dev.technology in pe.MULTILEVEL_TECH)
            summary_rows.append({
                "topology": tname, "device": dkey, "device_fitted": dev.name,
                "leg": "three-level" if ml else ("series" if op.n_series > 1
                                                 else "two-level"),
                "technology": dev.technology,
                "rated_kw": conv.rated_power / 1e3,
                "dc_link_v": conv.dc_link_voltage,
                "f_sw_khz": conv.switching_frequency / 1e3,
                "weighted_efficiency": pe.weighted_efficiency(conv, dev, duty, 40.0),
                "peak_efficiency": float(np.max(eff)),
                "efficiency_at_rated": op.efficiency,
                "p_cond_w": op.p_conduction, "p_sw_w": op.p_switching,
                "p_passive_w": op.p_passive, "p_total_w": op.p_total,
                "t_junction_c": op.t_junction,
                "n_parallel": op.n_parallel, "n_series": op.n_series,
                "kw_per_litre": dens["kw_per_litre"],
                "volume_litre": dens["volume_litre"],
                "cost_usd": pe.converter_cost(conv, dev),
                "cost_usd_per_kw": pe.converter_cost(conv, dev) / (conv.rated_power / 1e3),
                "trl": dev.trl,
            })
            pd_rows.append({"topology": tname, "device": dkey, **dens})

    # Power-cycling reliability on sub-hourly missions (0.1 s drive cycles for
    # traction inverters, one cycle per session for charger front ends).
    rel_rows = []
    missions = [("passenger_car", 150.0, 400.0, hv, 30.0, 25.0),
                ("passenger_car", 150.0, 800.0, hv, 30.0, 25.0),
                ("bus", 250.0, 650.0, hv, 18.0, 30.0),
                ("three_wheeler", 7.5, 60.0, lv, 18.0, 30.0),
                ("two_wheeler", 4.0, 60.0, lv, 22.0, 30.0)]
    for skey, kw, link, keys, speed, t_amb in missions:
        seg = VEHICLE_LIBRARY[skey]
        for dkey in keys:
            r = pe.traction_reliability(dkey, kw, link, seg.mass, seg.frontal_area,
                                        seg.drag_coefficient, seg.rolling_resistance,
                                        seg.drivetrain_efficiency * seg.motor_efficiency,
                                        seg.annual_km, speed, seg.trips_per_day, t_amb)
            rel_rows.append({"mission": f"{skey}_{int(link)}V", "converter":
                             "traction inverter", **r})
    for dkey in hv:
        dt_k, tm = pe._session_swing(dkey, 150.0, 800.0, 55.0, 1.0, 1.0)
        rel_rows.append({"mission": "dc_charger_150kW_session", "converter":
                         "DC charger front end", "device": dkey,
                         "device_fitted": charger_device_for(dkey, 800.0).name,
                         "delta_tj_fast_median_k": dt_k,
                         "delta_tj_fast_p95_k": dt_k, "delta_tj_fast_max_k": dt_k,
                         "share_cycles_in_calibrated_range": float(dt_k >= 30.0)})

    dev_rows = []
    for lib, cls in ((DEVICE_LIBRARY, "traction, high-voltage"),
                     (HV_VARIANTS, "traction, 1200 V variant"),
                     (CHARGER_DEVICE_LIBRARY, "charger stages"),
                     (CHARGER_HV_VARIANTS, "charger stages, 1200 V variant"),
                     (LV_DEVICE_LIBRARY, "100 V")):
        for k, d in lib.items():
            dev_rows.append({"key": k, "class": cls, **d.__dict__})
    freq_rows = [{"role": r, "technology": t, "f_sw_khz": f / 1e3}
                 for (r, t), f in pe.FREQUENCY_MAP.items()]

    return {"efficiency_curves": pd.DataFrame(eff_rows),
            "converter_summary": pd.DataFrame(summary_rows),
            "power_density": pd.DataFrame(pd_rows),
            "reliability": pd.DataFrame(rel_rows),
            "device_parameters": pd.DataFrame(dev_rows),
            "switching_frequencies": pd.DataFrame(freq_rows)}


def battery_characterisation() -> pd.DataFrame:
    rows = []
    for chem, pack in BATTERY_LIBRARY.items():
        for temp in (10.0, 25.0, 35.0, 45.0):
            for dc_share in (0.0, 0.35, 0.70):
                efc = 220.0
                dod = 0.45 + 0.15 * dc_share
                c_rate = 0.3 + 1.4 * dc_share
                years = np.arange(0, 16)
                soh = bat.state_of_health(pack, years * 365.0, years * efc,
                                          temp, 0.58, dod, c_rate)
                for y, s in zip(years, soh):
                    rows.append({"chemistry": chem, "temperature_c": temp,
                                 "dc_share": dc_share, "year": int(y),
                                 "soh": float(s)})
    return pd.DataFrame(rows)


def battery_eol_table() -> pd.DataFrame:
    rows = []
    for chem, pack in BATTERY_LIBRARY.items():
        for temp in (10.0, 25.0, 35.0, 45.0):
            for dc_share in (0.0, 0.35, 0.70):
                rows.append({
                    "chemistry": chem, "temperature_c": temp, "dc_share": dc_share,
                    "years_to_eol": bat.years_to_eol(
                        pack, 220.0, temp, 0.58, 0.45 + 0.15 * dc_share,
                        0.3 + 1.4 * dc_share),
                    "v2g_extra_fade_pct_per_year":
                        bat.v2g_marginal_degradation(pack, 900.0, temp) * 100.0,
                })
    return pd.DataFrame(rows)


def policy_lever_table() -> pd.DataFrame:
    rows = []
    for akey in sc.ARCHETYPE_ORDER:
        packages = sc.policy_packages(akey)
        for pkey, pkg in packages.items():
            levels = pkg.resolve(2035)
            for lk, lever in pol.LEVERS.items():
                span = max(lever.hi - lever.lo, 1e-9)
                rows.append({
                    "archetype": akey, "policy": pkey, "lever": lk,
                    "label": lever.label, "domain": lever.domain,
                    "unit": lever.unit, "value_2035": levels[lk],
                    "intensity": float(np.clip((levels[lk] - lever.lo) / span, 0, 1)),
                })
    return pd.DataFrame(rows)


def main() -> None:
    t0 = time.perf_counter()
    print("[1/6] scenario campaign ...", flush=True)
    df_rec, df_sum, series, df_seg = run_scenarios()
    df_rec.to_csv(RESULTS / "scenario_records.csv", index=False)
    df_seg.to_csv(RESULTS / "segment_economics.csv", index=False)

    print("[2/6] policy ranking ...", flush=True)
    df_rank = rank_policies(df_sum)
    df_rank.to_csv(RESULTS / "policy_ranking.csv", index=False)
    df_sum.to_csv(RESULTS / "horizon_summary.csv", index=False)
    (RESULTS / "topsis_weight_sensitivity.json").write_text(
        json.dumps(weight_sensitivity(df_sum), indent=1), encoding="utf-8")

    print("[3/6] hourly state trajectories ...", flush=True)
    for name, s in series.items():
        pd.DataFrame({k: np.asarray(v) for k, v in s.items()}).to_csv(
            RESULTS / f"series_{name}_2035.csv", index=False)

    print("[4/6] converter characterisation ...", flush=True)
    for name, frame in converter_characterisation().items():
        frame.to_csv(RESULTS / f"converter_{name}.csv", index=False)

    print("[5/6] battery characterisation ...", flush=True)
    battery_characterisation().to_csv(RESULTS / "battery_degradation.csv", index=False)
    battery_eol_table().to_csv(RESULTS / "battery_eol.csv", index=False)

    print("[6/6] policy lever settings ...", flush=True)
    policy_lever_table().to_csv(RESULTS / "policy_levers.csv", index=False)

    config_blob = json.dumps(
        {"library": library_snapshot(),
         "hv_variants": {k: v.__dict__ for k, v in HV_VARIANTS.items()},
         "lv_devices": {k: v.__dict__ for k, v in LV_DEVICE_LIBRARY.items()},
         "archetypes": {k: v.__dict__ for k, v in sc.ARCHETYPES.items()},
         "horizon": sc.HORIZON, "seed": SEED}, indent=1, default=str)
    (RESULTS / "model_configuration.json").write_text(config_blob, encoding="utf-8")
    archive = Path(__file__).resolve().parent / "configs" / "generated"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "model_configuration.json").write_text(config_blob, encoding="utf-8")

    print(f"done in {time.perf_counter()-t0:.1f} s -> {RESULTS}")


if __name__ == "__main__":
    main()
