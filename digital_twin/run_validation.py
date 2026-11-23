"""Stage 4 of the EV-DT experiment: verification and validation.

Four independent checks are performed.

1. *Conservation.*  The energy balance of the twin is audited: plug-side energy
   must equal battery-side energy plus power-conversion losses, and the network
   solution must satisfy Kirchhoff's laws to numerical precision.
2. *Numerical cross-validation.*  The vectorised matrix power flow is compared
   against an independently coded node-by-node backward/forward sweep, and the
   analytic Erlang-C waiting time is compared against a discrete-event
   simulation of the same queue.
3. *Predictive skill.*  The charging-demand forecaster and the extended Kalman
   filter are scored on held-out data, which quantifies the two capabilities
   that distinguish a digital twin from an offline model.
4. *Plausibility.*  Key model outputs are compared against the ranges commonly
   reported in the reviewed literature.  These are indicative consensus bands
   compiled from the cited review articles, not measurements from a single
   experiment; the check establishes that the twin operates in a physically
   credible regime rather than reproducing any one dataset.

Usage:  py -3 run_validation.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evdt import battery as bat, charging as chg, engine, environment as env
from evdt import grid as gridmod, learning, powerelectronics as pe, scenarios as sc
from evdt.config import BATTERY_LIBRARY, DEVICE_LIBRARY

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
def check_energy_balance() -> list[dict]:
    rows = []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pkg = sc.policy_packages(akey)["S5"]
        state = engine.TwinState()
        for year in (2030, 2035, 2040):
            r = engine.simulate_year(arch, pkg, year, state, seed=1)
            plug = r["plug_energy_gwh"]
            batt = r["battery_energy_gwh"]
            loss = r["conversion_loss_gwh"]
            rows.append({
                "archetype": akey, "year": year,
                "plug_gwh": plug, "battery_gwh": batt, "conversion_loss_gwh": loss,
                "residual_gwh": plug - batt - loss,
                "relative_residual": abs(plug - batt - loss) / max(plug, 1e-9),
            })
    return rows


def check_power_flow() -> list[dict]:
    """Matrix formulation versus an independent node-by-node sweep, plus a
    Kirchhoff power-balance residual."""
    rng = np.random.default_rng(5)
    feeder = gridmod.build_feeder()
    temp = env.temperature_series(25.0, 6.0, 6.0, rng)
    rows = []
    for peak in (3.0, 6.0, 9.0):
        base = env.base_demand_profile(peak, rng, temp)
        p, q = gridmod.allocate_demand(feeder, base)
        pf = gridmod.power_flow(feeder, p, q)

        # independent implementation
        cfg = feeder.cfg
        zb = cfg.base_voltage ** 2 / cfg.base_power
        rp, xp = feeder.r / zb, feeder.x / zb
        sp = (p * 1e6 + 1j * q * 1e6) / cfg.base_power
        n, h = p.shape
        v = np.full((n, h), 1.02, dtype=complex)
        for _ in range(40):
            vprev = v.copy()
            i_node = np.conj(sp / np.where(np.abs(v) < 1e-6, 1e-6, v))
            i_br = i_node.copy()
            for node in feeder.order[::-1]:
                pa = feeder.parent[node]
                if pa >= 0:
                    i_br[pa] += i_br[node]
            v = v.copy()
            v[0, :] = 1.02
            for node in feeder.order:
                pa = feeder.parent[node]
                if pa >= 0:
                    v[node] = v[pa] - (rp[node] + 1j * xp[node]) * i_br[node]
            if np.max(np.abs(v - vprev)) < 1e-10:
                break
        max_dv = float(np.max(np.abs(np.abs(v) - pf["v_pu"])))
        # Kirchhoff: injected power at the head = load + losses
        head_mw = float(np.mean(np.real(v[0] * np.conj(i_br[0])) * cfg.base_power / 1e6))
        balance = head_mw - float(np.mean(base)) - float(np.mean(pf["losses_mw"]))
        # the interpolated annual solution used by the engine
        lk = gridmod.power_flow_lookup(feeder, base)
        rows.append({"peak_mw": peak, "max_voltage_difference_pu": max_dv,
                     "power_balance_residual_mw": balance,
                     "relative_balance_residual": abs(balance) / max(float(np.mean(base)), 1e-9),
                     "mean_losses_mw": float(np.mean(pf["losses_mw"])),
                     "lookup_max_voltage_error_pu": float(np.max(np.abs(
                         lk["v_min_pu"] - pf["v_min_pu"]))),
                     "lookup_relative_loss_error": float(abs(lk["losses_mw"].sum()
                                                             - pf["losses_mw"].sum())
                                                         / pf["losses_mw"].sum())})
    return rows


# IEEE 33-bus test feeder (Baran and Wu, IEEE Trans. Power Del., 1989):
# (from, to, R ohm, X ohm, P kW, Q kvar at the receiving bus).
IEEE33 = [
    (1, 2, 0.0922, 0.0470, 100, 60), (2, 3, 0.4930, 0.2511, 90, 40),
    (3, 4, 0.3660, 0.1864, 120, 80), (4, 5, 0.3811, 0.1941, 60, 30),
    (5, 6, 0.8190, 0.7070, 60, 20), (6, 7, 0.1872, 0.6188, 200, 100),
    (7, 8, 0.7114, 0.2351, 200, 100), (8, 9, 1.0300, 0.7400, 60, 20),
    (9, 10, 1.0440, 0.7400, 60, 20), (10, 11, 0.1966, 0.0650, 45, 30),
    (11, 12, 0.3744, 0.1238, 60, 35), (12, 13, 1.4680, 1.1550, 60, 35),
    (13, 14, 0.5416, 0.7129, 120, 80), (14, 15, 0.5910, 0.5260, 60, 10),
    (15, 16, 0.7463, 0.5450, 60, 20), (16, 17, 1.2890, 1.7210, 60, 20),
    (17, 18, 0.7320, 0.5740, 90, 40), (2, 19, 0.1640, 0.1565, 90, 40),
    (19, 20, 1.5042, 1.3554, 90, 40), (20, 21, 0.4095, 0.4784, 90, 40),
    (21, 22, 0.7089, 0.9373, 90, 40), (3, 23, 0.4512, 0.3083, 90, 50),
    (23, 24, 0.8980, 0.7091, 420, 200), (24, 25, 0.8960, 0.7011, 420, 200),
    (6, 26, 0.2030, 0.1034, 60, 25), (26, 27, 0.2842, 0.1447, 60, 25),
    (27, 28, 1.0590, 0.9337, 60, 20), (28, 29, 0.8042, 0.7006, 120, 70),
    (29, 30, 0.5075, 0.2585, 200, 600), (30, 31, 0.9744, 0.9630, 150, 70),
    (31, 32, 0.3105, 0.3619, 210, 100), (32, 33, 0.3410, 0.5302, 60, 40),
]
IEEE33_PUBLISHED = {"losses_kw": 202.67, "v_min_pu": 0.9131, "v_min_bus": 18}


def check_ieee33() -> dict:
    """The power-flow solver of Eq. (10) on the published IEEE 33-bus case.

    This is an external benchmark, not a self-consistency check: the published
    losses and minimum voltage were obtained by other authors with other
    solvers, and the complex conjugation of the current injection,
    ``i = conj(s / v)``, is exercised on a case whose answer is known.
    """
    from evdt.config import FeederConfig
    n = 33
    parent = np.full(n, -1, dtype=int)
    r = np.zeros(n); x = np.zeros(n); p = np.zeros(n); q = np.zeros(n)
    for f, t, rr, xx, pp, qq in IEEE33:
        parent[t - 1] = f - 1
        r[t - 1], x[t - 1], p[t - 1], q[t - 1] = rr, xx, pp, qq
    depth = np.zeros(n, dtype=int)
    for i in range(1, n):
        depth[i] = depth[parent[i]] + 1
    order = np.argsort(depth, kind="stable")
    path = np.zeros((n, n))
    for node in order:
        if parent[node] >= 0:
            path[node] = path[parent[node]]
            path[node, node] = 1.0
    cfg = FeederConfig(n_nodes=n, base_voltage=12.66e3, base_power=10e6)
    feeder = gridmod.Feeder(parent, r, x, np.ones(n) / n, order, cfg,
                            np.ones(n), path)
    pf = gridmod.power_flow(feeder, p[:, None] / 1e3, q[:, None] / 1e3,
                            v_slack_pu=1.0, tol=1e-10, max_iter=100)
    v = pf["v_pu"][:, 0]
    out = {"losses_kw": float(pf["losses_mw"][0] * 1e3),
           "v_min_pu": float(v.min()), "v_min_bus": int(np.argmin(v) + 1),
           "published_losses_kw": IEEE33_PUBLISHED["losses_kw"],
           "published_v_min_pu": IEEE33_PUBLISHED["v_min_pu"]}
    out["losses_relative_error"] = abs(out["losses_kw"] - IEEE33_PUBLISHED["losses_kw"]) \
        / IEEE33_PUBLISHED["losses_kw"]
    out["v_min_abs_error_pu"] = abs(out["v_min_pu"] - IEEE33_PUBLISHED["v_min_pu"])
    return out


#: Published base-case results of the benchmark feeders (constant-power
#: loads, source at 1.0 pu; IEEE 34: MV part only, calibrated at 33 kV).
BENCHMARK_PUBLISHED = {
    "ieee33": (202.67, 0.9131, "Baran and Wu (1989)"),
    "ieee69": (225.0, 0.9092, "Baran and Wu (1989); Das (2008)"),
    "in_rural28": (68.82, 0.9123, "Das, Nagi and Kothari (1994)"),
}


def check_benchmark_feeders() -> list[dict]:
    """Every benchmark feeder used by the archetypes, solved with the
    published bus loads by the model's power flow, against the published
    losses and minimum voltage; the calibrated IEEE 34 medium-voltage feeder
    against the Tanzanian 33 kV feeder it is calibrated to (Shinyanga-Bariadi,
    4.5 MW, 0.862 pu at the end, Mhagama et al. 2021); SimBench grids are
    reported for reference."""
    from evdt.config import FeederConfig
    rows = []
    from evdt import scenarios as sc
    z34 = next(t.z_scale for t in sc.FEEDERS_LDC if t.key == "ieee34_mv")
    cases = [("ieee33", 1.0, None, None), ("ieee69", 1.0, None, None),
             ("in_rural28", 1.0, None, None),
             # as the engine loads it: nodal shares at power factor 0.95
             ("ieee34_mv", z34, 33.0, 4.5),
             ("simbench_mv_urban", 1.0, None, None), ("simbench_mv_semiurb", 1.0, None, None),
             ("simbench_mv_rural", 1.0, None, None)]
    for key, zs, kv, total_mw in cases:
        b = gridmod.load_benchmark(key)
        ld = pd.read_csv(gridmod.FEEDER_DATA / f"{key}_loads.csv", comment="#")
        n = b["load_kw"].size
        base_kv = kv or float(b["meta"]["base_kv"])
        fd = gridmod.feeder_from_data(b["from"], b["to"], b["r"], b["x"], b["load_kw"],
                                      FeederConfig(n_nodes=n, base_voltage=base_kv * 1e3,
                                                   base_power=10e6), zs)
        if total_mw is None:                   # published loads
            p = np.zeros(n)
            q = np.zeros(n)
            for bus, pk, qk in zip(ld.bus.astype(int), ld.p_kw, ld.q_kvar):
                p[bus - 1] += pk
                q[bus - 1] += qk
            p_mw, q_mw = p[:, None] / 1e3, q[:, None] / 1e3
        else:
            p_mw, q_mw = gridmod.allocate_demand(fd, np.array([total_mw]))
            p = p_mw[:, 0] * 1e3
        pf = gridmod.power_flow(fd, p_mw, q_mw, v_slack_pu=1.0, tol=1e-10, max_iter=200)
        loss_kw = float(pf["losses_mw"][0] * 1e3)
        vmin = float(pf["v_pu"][:, 0].min())
        pub = BENCHMARK_PUBLISHED.get(key)
        if key == "ieee34_mv":
            pub = (np.nan, 0.862, "Tanzanian 33 kV feeder (calibration target)")
        rows.append({"feeder": key, "base_kv": base_kv, "load_kw": float(p.sum()),
                     "losses_kw": loss_kw, "v_min_pu": vmin,
                     "published_losses_kw": pub[0] if pub else np.nan,
                     "published_v_min_pu": pub[1] if pub else np.nan,
                     "source": pub[2] if pub else b["meta"]["source"]})
    return rows


def check_queue_model(n_replications: int = 40, horizon_h: float = 4000.0) -> list[dict]:
    """Erlang-C waiting time versus a discrete-event M/M/c simulation."""
    rng = np.random.default_rng(21)
    rows = []
    for servers, rho in ((4, 0.55), (8, 0.70), (12, 0.80), (20, 0.88), (6, 0.35)):
        service_h = 0.6
        arrival_rate = rho * servers / service_h
        analytic, _ = chg.waiting_time(servers, arrival_rate, service_h)
        waits = []
        for _ in range(n_replications):
            t = 0.0
            free_at = np.zeros(servers)
            total_wait, n_customers = 0.0, 0
            while t < horizon_h:
                t += rng.exponential(1.0 / arrival_rate)
                j = int(np.argmin(free_at))
                start = max(t, free_at[j])
                total_wait += start - t
                free_at[j] = start + rng.exponential(service_h)
                n_customers += 1
            waits.append(total_wait / max(n_customers, 1))
        sim = float(np.mean(waits))
        rows.append({"servers": servers, "utilisation": rho,
                     "analytic_wait_min": analytic * 60.0,
                     "simulated_wait_min": sim * 60.0,
                     "simulated_sd_min": float(np.std(waits) * 60.0),
                     "absolute_error_min": abs(analytic - sim) * 60.0,
                     "relative_error": abs(analytic - sim) / max(sim, 1e-9)})
    return rows


def check_forecasting() -> tuple[list[dict], pd.DataFrame]:
    rows, frames = [], []
    for akey in sc.ARCHETYPE_ORDER:
        arch = sc.ARCHETYPES[akey]
        pkg = sc.policy_packages(akey)["S5"]
        out = engine.simulate_horizon(arch, pkg, sc.HORIZON, seed=3,
                                      keep_series_for=2035)
        s = out["series"]
        demand = np.asarray(s["ev_mw"]) + np.asarray(s["base_mw"])
        f = learning.ChargingDemandForecaster(horizon=24, seed=0)
        met = f.fit_evaluate(demand, np.asarray(s["temperature_c"]),
                             np.asarray(s["price"]))
        rows.append({"archetype": akey, **met})
        obs, pred = f.predictions()
        frames.append(pd.DataFrame({"archetype": akey, "hour": np.arange(len(obs)),
                                    "observed_mw": obs, "predicted_mw": pred}))
    return rows, pd.concat(frames, ignore_index=True)


def check_state_estimation() -> tuple[dict, pd.DataFrame]:
    """Extended Kalman filter tracking of a synthetic but noisy cell trajectory."""
    rng = np.random.default_rng(77)
    n = 1400
    capacity_ah = 120.0
    current = np.zeros(n)
    for i in range(n):
        phase = i % 200
        if phase < 90:
            current[i] = rng.uniform(8.0, 42.0)       # driving
        elif phase < 130:
            current[i] = 0.0                          # parked
        else:
            current[i] = -rng.uniform(15.0, 55.0)     # charging
    soc = np.empty(n)
    soc[0] = 0.72
    r0_true = 0.070 + np.linspace(0.0, 0.022, n)      # slow ohmic growth
    for i in range(1, n):
        soc[i] = float(np.clip(soc[i - 1] - current[i] * (1.0 / 60.0) / capacity_ah,
                               0.05, 1.0))
    v_true = np.array([learning.StateEstimator._ocv(s) for s in soc]) - current * r0_true
    v_meas = v_true + rng.normal(0.0, 0.012, n)

    ekf = learning.StateEstimator(capacity_ah, r0_init=0.060, dt_h=1.0 / 60.0)
    est = ekf.run(current, v_meas)
    err_soc = learning.synchronisation_error(soc, est[:, 0])
    err_r0 = learning.synchronisation_error(r0_true, est[:, 1])
    frame = pd.DataFrame({"step": np.arange(n), "soc_true": soc,
                          "soc_estimated": est[:, 0], "r0_true": r0_true,
                          "r0_estimated": est[:, 1], "current_a": current,
                          "voltage_measured": v_meas})
    return {"soc_mae": err_soc["mae"], "soc_rmse": err_soc["rmse"],
            "soc_max_abs": err_soc["max_abs"], "soc_final_abs": err_soc["final_abs"],
            "r0_mae": err_r0["mae"], "r0_rmse": err_r0["rmse"],
            "initial_offset": 0.010, "n_steps": n}, frame


def check_converters_vs_literature() -> list[dict]:
    """Converter model against published measurements of comparable hardware.

    These are comparisons with similar, not identical, equipment, so they test
    whether the model reproduces the level and the direction of published
    results rather than any one product.
    """
    from evdt.config import VEHICLE_LIBRARY, device_for
    from evdt import mobility as mob
    rows = []

    from dataclasses import replace as _replace

    def peak(dev_key, kw, link, f_sw=None, t_c=65.0):
        # perturbed() applies pe.SILICON_LOSS_MULT, used by the silicon-loss bracket
        dev = pe.perturbed(device_for(dev_key, link))
        conv = pe.traction_inverter(kw, link, dev)
        if f_sw:
            conv = _replace(conv, switching_frequency=f_sw)
        return max(pe.solve_converter(conv, dev, f * conv.rated_power, t_c).efficiency
                   for f in np.linspace(0.02, 1.0, 99))

    # ratings and switching frequencies as reported by ORNL (Accord: not
    # stated; the model's 8 kHz)
    for kw, link, f_sw, src in (
            (80.0, 375.0, 5000.0, "ORNL, 2012 Nissan LEAF inverter (DOE AMR 2013), 5 kHz"),
            (60.0, 650.0, 5000.0, "ORNL, 2010 Toyota Prius inverter (ORNL/TM-2010/253), 5 kHz"),
            (124.0, 700.0, None, "ORNL, 2014 Honda Accord inverter (DOE AMR 2016)")):
        rows.append({"quantity": f"Si IGBT traction inverter, peak efficiency, {link:.0f} V",
                     "published": ">0.99", "published_low": 0.99, "published_high": 1.0,
                     "model": peak("Si-IGBT", kw, link, f_sw),
                     "source": src, "use": "comparison"})
    # Drive-cycle range gain on standard cycles for a Chevrolet Bolt-like car
    # (1750 kg test mass, Cd 0.308, 2.4 m2), battery energy = traction (inverter
    # input) - regeneration (inverter output) + 300 W auxiliaries
    car = _replace(VEHICLE_LIBRARY["passenger_car"], mass=1750.0, frontal_area=2.4,
                   drag_coefficient=0.308)
    gains = {}
    for cyc in ("udds", "hwfet", "wltc3b"):
        m = pe.mission_of(car, cyc)
        p_ac, v, dt = pe._cycle_power(m, False)
        e_mot = float(np.sum(np.clip(p_ac, 0, None)) * dt)
        e_reg = float(np.sum(np.clip(-p_ac, 0, None)) * dt)
        e_aux = 300.0 * v.size * dt

        def battery(eta):
            return e_mot / eta - e_reg * eta + e_aux

        base = pe.cycle_efficiency("Si-IGBT", 150.0, 400.0, m, 40.0)
        for key in ("Si-IGBT", "SiC-MOSFET"):
            e = pe.cycle_efficiency(key, 150.0, 800.0, m, 40.0)
            gains[(key, cyc)] = battery(base) / battery(e) - 1.0
    for key, pub in (("Si-IGBT", 0.012), ("SiC-MOSFET", 0.050)):
        # EPA combined label weighting: 55 % city (UDDS), 45 % highway (HWFET)
        comb = 0.55 * gains[(key, "udds")] + 0.45 * gains[(key, "hwfet")]
        rows.append({"quantity": f"Drive-cycle range gain, {key} at 800 V vs Si IGBT at "
                                 "400 V, EPA combined (UDDS "
                                 f"{100 * gains[(key, 'udds')]:+.1f} %, HWFET "
                                 f"{100 * gains[(key, 'hwfet')]:+.1f} %, WLTC "
                                 f"{100 * gains[(key, 'wltc3b')]:+.1f} %)",
                     "published": f"+{100 * pub:.1f} %",
                     "published_low": pub - 0.01, "published_high": pub + 0.01,
                     "model": comb,
                     "source": "Allca-Pekarovic et al., IEEE TTE 2024 (validated loss "
                               "models, Chevrolet Bolt); within: +/-1 percentage point",
                     "use": "comparison"})
    ll = pd.read_csv(RESULTS / "light_load_fit.csv")
    held = ll[ll.set == "held out"]
    rows.append({"quantity": "Si IGBT inverter efficiency at light load, 2010 Prius map at "
                             f"225 V (held out, {len(held)} points), mean absolute error",
                 "published": "map contours 88-98 %", "published_low": 0.0,
                 "published_high": 0.02,
                 "model": float(np.mean(np.abs(held.model - held.measured))),
                 "source": "ORNL/TM-2010/253 efficiency maps; ripple fitted at 650/500 V",
                 "use": "comparison"})
    from evdt.config import CHARGER_DEVICE_LIBRARY, charger_device_for
    sic, gan = CHARGER_DEVICE_LIBRARY["SiC-MOSFET"], CHARGER_DEVICE_LIBRARY["GaN-HEMT"]
    pfc = pe.obc_pfc_stage(6.6, sic)
    rows.append({"quantity": "SiC totem-pole PFC stage, 6.6 kW, peak efficiency",
                 "published": "0.985", "published_low": 0.985, "published_high": 0.985,
                 "model": max(pe.solve_converter(pfc, sic, f * pfc.rated_power, 50.0).efficiency
                              for f in np.linspace(0.05, 1, 60)),
                 "source": "Liu et al., ECCE 2016 (SiC AC/DC stage above 300 kHz)",
                 "use": "comparison"})
    rows.append({"quantity": "Wide-bandgap on-board charger, 6.6 kW, AC path",
                 "published": ">0.96", "published_low": 0.96, "published_high": 1.0,
                 "model": pe.charging_path_efficiency("GaN-HEMT", "ac", 6.6, 400.0, 50.0)["path"],
                 "source": "Liu et al., ECCE 2016 (complete SiC+GaN charger)",
                 "use": "comparison"})
    for key, pub, lo in (("SiC-MOSFET", ">0.97", 0.97), ("Si-IGBT", ">0.94", 0.94)):
        d = charger_device_for(key, 800.0)
        iso = pe.dcfc_isolation(30.0, 800.0, d)
        rows.append({"quantity": f"DC fast-charger isolated stage, {key}, peak efficiency",
                     "published": pub, "published_low": lo, "published_high": 1.0,
                     "model": max(pe.solve_converter(iso, d, f * iso.rated_power,
                                                     50.0).efficiency
                                  for f in np.linspace(0.05, 1, 60)),
                     "source": "Piasecki et al., Energies 2021 (SiC DAB vs Si SAB modules)",
                     "use": "comparison"})
    for r in rows:
        r["within"] = bool(r["published_low"] - 1e-9 <= r["model"] <= r["published_high"] + 1e-9)
    return rows


def plausibility_bands() -> list[dict]:
    """Model outputs against indicative ranges from the reviewed literature."""
    cs = pd.read_csv(RESULTS / "converter_converter_summary.csv")
    rec = pd.read_csv(RESULTS / "scenario_records.csv")

    def conv(topology: str, device: str, col: str = "weighted_efficiency") -> float:
        m = cs[(cs.topology == topology) & (cs.device == device)]
        return float(m[col].iloc[0]) if len(m) else float("nan")

    dev35 = rec[(rec.archetype == "developed") & (rec.policy == "S5") & (rec.year == 2035)]
    bd35 = rec[(rec.archetype == "developing") & (rec.policy == "S5") & (rec.year == 2035)]
    seg = pd.read_csv(RESULTS / "segment_economics.csv")

    def whkm(arch, s):
        q = seg[(seg.archetype == arch) & (seg.policy == "S5") & (seg.year == 2035)
                & (seg.segment == s)]
        return float(q.wh_per_km.iloc[0]) if len(q) else float("nan")
    pack = BATTERY_LIBRARY["NMC"]

    entries = [
        ("Traction inverter, Si IGBT, weighted efficiency", "-",
         conv("traction_inverter_400V", "Si-IGBT"), 0.960, 0.985,
         "pe-traction-inv-review, pe-loss-rt"),
        ("Traction inverter, SiC MOSFET, weighted efficiency", "-",
         conv("traction_inverter_400V", "SiC-MOSFET"), 0.975, 0.993,
         "pe-sic-loss-datasheet, pe-sic-module-thermal"),
        ("On-board charger PFC stage, GaN, weighted efficiency", "-",
         conv("obc_pfc_11kW", "GaN-HEMT"), 0.965, 0.992, "pe-obc-totem, pe-gan-ev"),
        ("DC fast charger front end, SiC, weighted efficiency", "-",
         conv("dcfc_afe_150kW", "SiC-MOSFET"), 0.960, 0.990, "pe-sic-fcs, pe-hv-station"),
        ("Traction inverter power density, SiC", "kW/L",
         conv("traction_inverter_400V", "SiC-MOSFET", "kw_per_litre"), 8.0, 40.0,
         "pe-traction-inv-review, pe-gan-dcdc-opt"),
        ("Passenger-car specific consumption (developed, 2035)", "Wh/km",
         float(dev35.energy_per_km_wh.iloc[0]), 110.0, 220.0,
         "meth-driving-energy, meth-temp-trip"),
        ("Electric two-wheeler consumption (developing, 2035)", "Wh/km",
         whkm("developing", "two_wheeler"), 20.0, 60.0,
         "ldc-ssa-moto-model, dev-in-2w"),
        ("Electric three-wheeler consumption (developing, 2035)", "Wh/km",
         whkm("developing", "three_wheeler"), 50.0, 140.0, "bd-3w"),
        ("Low-voltage (60 V) drive inverter, weighted efficiency", "-",
         conv("lv_drive_4kW_60V", "Si-LV"), 0.93, 0.985, "pe-48v-module, ldc-ssa-moto-model"),
        ("Distribution network loss fraction (developed, 2035)", "-",
         float(dev35.loss_fraction.iloc[0]), 0.02, 0.09, "grid-infra-impact"),
        ("Distribution network loss fraction (developing, 2035)", "-",
         float(bd35.loss_fraction.iloc[0]), 0.02, 0.14, "grid-infra-impact, ldc-minigrid-rel"),
        # statutory band (the earlier upper bound of 1.00 assumed a heavily
        # loaded feeder; lightly loaded MV feeders fed at 1.02 pu stay near 1)
        ("Minimum feeder voltage (developed, 2035)", "pu",
         float(dev35.v_min_pu.iloc[0]), 0.94, 1.06, "grid-der-standards"),
        ("Voltage total harmonic distortion at PCC", "-",
         float(dev35.thd_v.iloc[0]), 0.0, 0.05, "grid-harmonic-std"),
        ("NMC pack years to 80 % state of health at 25 C", "yr",
         bat.years_to_eol(pack, 220.0, 25.0, 0.58, 0.50, 0.65), 8.0, 16.0,
         "batt-fade-realveh, batt-calendar"),
        ("Additional annual fade from vehicle-to-grid duty", "%/yr",
         bat.v2g_marginal_degradation(pack, 900.0, 28.0) * 100.0, 0.05, 1.20,
         "batt-v2g-degr, batt-v2g-degr-model"),
    ]
    rows = []
    for label, unit, value, lo, hi, refs in entries:
        rows.append({"quantity": label, "unit": unit, "model_value": value,
                     "band_low": lo, "band_high": hi,
                     "within_band": bool(lo <= value <= hi), "references": refs})
    return rows


def main() -> None:
    t0 = time.perf_counter()
    print("[1/5] energy balance ...", flush=True)
    eb = check_energy_balance()
    pd.DataFrame(eb).to_csv(RESULTS / "validation_energy_balance.csv", index=False)

    print("[2/5] power flow cross-validation ...", flush=True)
    pf = check_power_flow()
    pd.DataFrame(pf).to_csv(RESULTS / "validation_power_flow.csv", index=False)

    print("[3/5] queueing model ...", flush=True)
    qm = check_queue_model()
    pd.DataFrame(qm).to_csv(RESULTS / "validation_queue.csv", index=False)

    print("[4/5] forecasting and state estimation ...", flush=True)
    fc_rows, fc_frame = check_forecasting()
    pd.DataFrame(fc_rows).to_csv(RESULTS / "validation_forecasting.csv", index=False)
    fc_frame.to_csv(RESULTS / "validation_forecast_series.csv", index=False)
    ekf_stats, ekf_frame = check_state_estimation()
    ekf_frame.to_csv(RESULTS / "validation_ekf_series.csv", index=False)

    print("[5/5] plausibility bands ...", flush=True)
    pb = plausibility_bands()
    pd.DataFrame(pb).to_csv(RESULTS / "validation_plausibility.csv", index=False)

    print("[+] external benchmarks: IEEE 33-bus and published converter data", flush=True)
    ieee = check_ieee33()
    pd.DataFrame([ieee]).to_csv(RESULTS / "validation_ieee33.csv", index=False)
    lit = check_converters_vs_literature()
    pd.DataFrame(lit).to_csv(RESULTS / "validation_converter_literature.csv", index=False)
    bench = check_benchmark_feeders()
    pd.DataFrame(bench).to_csv(RESULTS / "validation_benchmark_feeders.csv", index=False)

    summary = {
        "ieee33": ieee,
        "power_flow_lookup_max_voltage_error_pu":
            max(r["lookup_max_voltage_error_pu"] for r in pf),
        "energy_balance_max_relative_residual":
            max(r["relative_residual"] for r in eb),
        "power_flow_max_voltage_difference_pu":
            max(r["max_voltage_difference_pu"] for r in pf),
        "power_flow_max_relative_balance_residual":
            max(r["relative_balance_residual"] for r in pf),
        "queue_max_relative_error": max(r["relative_error"] for r in qm),
        "forecast_r2_mean": float(np.mean([r["r2"] for r in fc_rows])),
        "forecast_mape_mean": float(np.mean([r["mape"] for r in fc_rows])),
        "ekf": ekf_stats,
        "plausibility_pass": sum(r["within_band"] for r in pb),
        "plausibility_total": len(pb),
        "runtime_s": time.perf_counter() - t0,
    }
    (RESULTS / "validation_summary.json").write_text(json.dumps(summary, indent=1),
                                                     encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
