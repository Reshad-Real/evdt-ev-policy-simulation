"""Orchestration engine: the coupled annual and multi-year simulation.

``simulate_year`` closes the loop between the policy levers, the power-electronic
device layer, the vehicle and battery layer, the charging infrastructure and the
distribution network, and returns the hourly state trajectories and a condensed
indicator set.  ``simulate_horizon`` propagates the coupled system year by year,
carrying forward the state that makes the problem path-dependent: battery state
of health, cumulative wide-bandgap deployment (which feeds the technology
learning curve), installed charging assets, network reinforcement and the solar
capacity procured for charging.

Power electronics can be represented in three ways, selected by ``pe_mode``:

``"device"``    the device-level models of :mod:`evdt.powerelectronics`, solved
                for each vehicle segment at its own rating, DC-link voltage and
                coolant temperature (the model proposed in the paper);
``"lookup"``    one load-weighted efficiency per semiconductor technology at a
                single reference condition (150 kW, 400 V, 40 C), blended by the
                technology mix - the table a conventional model could carry;
``"constant"``  one fleet efficiency fixed at its base-year value, on which no
                policy lever acts - the usual assumption of policy models.

Comparing the three under identical lever settings isolates what the
device-level representation contributes.

The network is represented by a few feeder types per archetype (urban,
semi-urban, rural benchmark feeders; ``Archetype.feeder_types``), each solved
at hourly resolution and multiplied by the number of such feeders implied by
its share of the national peak demand.  ``feeder_concentration`` scales the
charging load placed on the studied feeders relative to the national average,
to examine geographically concentrated demand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from . import battery as bat
from . import charging as chg
from . import economics as eco
from . import environment as env
from . import grid as gridmod
from . import mobility as mob
from . import policy as pol
from . import powerelectronics as pe
from .config import (BATTERY_LIBRARY, CHARGER_DEVICE_LIBRARY, DEVICE_LIBRARY, FeederConfig,
                     HOURS_PER_YEAR, VEHICLE_LIBRARY, Archetype, device_for)

PE_MODES = ("device", "lookup", "constant")
LV_SEGMENTS = ("two_wheeler", "three_wheeler")
COOLANT_RISE_K = 25.0          # converter coolant above ambient air
REFERENCE_SESSIONS = 3000.0    # sessions per DC connector-year (lookup mode)


# ---------------------------------------------------------------------------
# State carried between years
# ---------------------------------------------------------------------------
@dataclass
class TwinState:
    """Path-dependent state of the national simulation."""
    soh: float = 1.0
    cumulative_wbg: float = 0.0
    installed_connectors: dict[str, float] = field(default_factory=dict)
    cumulative_capex: float = 0.0
    reinforcement: float = 0.0
    pv_aligned_mw: float = 0.0
    # adoption state, stepped one year at a time (second revision)
    adopt_year: int | None = None
    adopt_f: float = 0.0               # adopted fraction of potential buyers
    adopt_x: float = 0.0               # electric share of the stock
    adopt_s: float = 0.0               # electric share of new registrations
    reference_log: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fuel prices and air-pollution damage by fuel
# ---------------------------------------------------------------------------
def fuel_price_of(arch: Archetype, fuel: str) -> float:
    """Retail price of the displaced fuel [USD per litre, CNG per litre of
    gasoline equivalent]: ``fuel_price`` is the gasoline price and
    ``fuel_price_ratio`` the other fuels relative to it, so the uncertainty
    analysis scales all fuels together."""
    return arch.fuel_price * (arch.fuel_price_ratio or {}).get(fuel, 1.0)


def health_cost_of(arch: Archetype, fuel: str) -> float:
    """Local air-pollution damage of one litre of the displaced fuel [USD]."""
    return (arch.health_cost_per_litre or {}).get(fuel, eco.HEALTH_USD_PER_LITRE)


# ---------------------------------------------------------------------------
# Feeder types of the distribution network
# ---------------------------------------------------------------------------
def feeder_types(arch: Archetype) -> list[dict]:
    """The archetype's feeder types with their peak base demand [MW].

    Without ``feeder_types`` the archetype is represented by the single
    synthetic 33-node feeder of the first version.
    """
    if not arch.feeder_types:
        return [{"key": "synthetic33", "label": "representative", "share": 1.0,
                 "intensity": 1.0, "peak_mw": arch.feeder_peak_mw}]
    out = []
    for t in arch.feeder_types:
        t = t if isinstance(t, dict) else t.__dict__
        if t["key"] == "synthetic33":
            peak = t.get("peak_mw") or arch.feeder_peak_mw
        else:
            peak = t.get("peak_mw") or gridmod.load_benchmark(t["key"])["peak_mw"]
        out.append({"key": t["key"], "label": t["label"], "share": t["demand_share"],
                    "intensity": t.get("ev_intensity", 1.0), "peak_mw": float(peak),
                    "z_scale": float(t.get("z_scale", 1.0)),
                    "base_kv": t.get("base_kv")})
    total = sum(t["share"] for t in out)
    for t in out:
        t["share"] /= total
    return out


@lru_cache(maxsize=512)
def _type_feeder(key: str, tx_mva: float, imp_mult: float, z_scale: float,
                 base_kv: float | None) -> gridmod.Feeder:
    if key == "synthetic33":
        return gridmod.build_feeder(FeederConfig(transformer_mva=tx_mva,
                                                 r_per_km=0.220 * imp_mult,
                                                 x_per_km=0.140 * imp_mult))
    b = gridmod.load_benchmark(key)
    kv = float(base_kv) if base_kv else float(b["meta"]["base_kv"])
    cfg = FeederConfig(n_nodes=b["load_kw"].size, base_voltage=kv * 1e3,
                       transformer_mva=tx_mva)
    return gridmod.feeder_from_data(b["from"], b["to"], b["r"], b["x"], b["load_kw"],
                                    cfg, imp_mult * z_scale, b["i_max_a"])


def build_type_feeder(t: dict, tx_mva: float, imp_mult: float) -> gridmod.Feeder:
    """Feeder of one type with the year's transformer rating and impedance."""
    return _type_feeder(t["key"], round(float(tx_mva), 4), round(float(imp_mult), 4),
                        round(float(t.get("z_scale", 1.0)), 6), t.get("base_kv"))


# ---------------------------------------------------------------------------
# Segment data with archetype overrides
# ---------------------------------------------------------------------------
def segment(arch: Archetype, key: str):
    """Vehicle segment with the archetype's calibrated overrides applied."""
    from dataclasses import replace
    seg = VEHICLE_LIBRARY[key]
    ov = {k: v for k, v in arch.segment_overrides.get(key, {}).items()
          if k != "displacement"}
    return replace(seg, **ov) if ov else seg


def displacement(arch: Archetype, key: str) -> float:
    return float(arch.segment_overrides.get(key, {}).get("displacement", 1.0))


def lv_mix(mix: dict[str, float]) -> dict[str, float]:
    """Technology shares of the 100 V devices in two- and three-wheeler drives."""
    wbg = mix["SiC-MOSFET"] + mix["GaN-HEMT"]
    return {"Si-LV": 1.0 - wbg, "GaN-LV": wbg}


# ---------------------------------------------------------------------------
# Efficiency representations
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _lookup_table() -> dict[str, dict[str, float]]:
    """Per-technology efficiencies at the single reference condition."""
    out = {}
    for k in DEVICE_LIBRARY:
        out[k] = {
            "traction": pe.powertrain_efficiency(k, 150.0, 400.0, 40.0)["traction_chain"],
            "ac": pe.charging_path_efficiency(k, "ac", 11.0, 400.0, 40.0)["path"],
            "dc": pe.charging_path_efficiency(k, "dc", 150.0, 800.0, 40.0)["path"],
            "fail": pe.charger_session_failure_rate(k, REFERENCE_SESSIONS, 40.0),
        }
    return out


def _blend(values: dict[str, float], shares: dict[str, float]) -> float:
    tot = sum(shares.values())
    return sum(values[k] * s for k, s in shares.items()) / max(tot, 1e-12)


def _standard(eta: float, intensity: float) -> float:
    """Efficiency after a minimum-efficiency conformity standard.

    A standard removes the poorest designs without changing the technology, so
    it is represented as a reduction of up to 16 % in the residual loss.
    """
    s = float(np.clip(intensity, 0.0, 1.0))
    return float(1.0 - (1.0 - eta) * (1.0 - 0.16 * s))


def base_mix(arch: Archetype) -> dict[str, float]:
    """Technology mix of the reference package in the base year."""
    levels = {k: lev.lo for k, lev in pol.LEVERS.items()}
    return pol.device_mix(arch, levels, 2025)


def efficiencies(arch: Archetype, mix: dict[str, float], dc_link: float,
                 t_air: float, std: float, segments: list[str],
                 pe_mode: str = "device") -> dict:
    """Traction and charging-path efficiency by segment, and the DC path."""
    if pe_mode not in PE_MODES:
        raise ValueError(pe_mode)
    if pe_mode in ("lookup", "constant"):
        tab = _lookup_table()
        m = base_mix(arch) if pe_mode == "constant" else mix
        tr = _blend({k: v["traction"] for k, v in tab.items()}, m)
        ac = _blend({k: v["ac"] for k, v in tab.items()}, m)
        dc = _blend({k: v["dc"] for k, v in tab.items()}, m)
        if pe_mode == "lookup":
            tr, ac, dc = _standard(tr, std), _standard(ac, std), _standard(dc, std)
        return {"traction": {s: tr for s in segments}, "ac": {s: ac for s in segments},
                "dc": dc}

    esw, ron = arch.device_esw_mult, arch.device_ron_mult
    t_c = t_air + COOLANT_RISE_K
    mlv = lv_mix(mix)
    tr, ac = {}, {}
    for s in segments:
        seg = segment(arch, s)
        kw = seg.motor_peak_power / 1e3
        # traction efficiency is the energy efficiency over the segment's
        # standard drive cycle (Archetype.drive_cycles), or else over a
        # synthetic urban cycle at the archetype's mean speed (two- and
        # three-wheelers run slower), not a fixed load weighting
        speed = arch.mean_speed_kmh * (0.72 if s in LV_SEGMENTS else 1.0)
        mission = pe.mission_of(seg, (arch.drive_cycles or {}).get(s) or speed)
        if s in LV_SEGMENTS:
            vals = {k: pe.powertrain_efficiency_fast(k, kw, seg.drive_voltage, t_c,
                                                     esw, ron, mission)["traction_chain"]
                    for k in mlv}
            tr[s] = _standard(_blend(vals, mlv), std)
        else:
            link = dc_link if s != "bus" else max(seg.drive_voltage, dc_link)
            vals = {k: pe.powertrain_efficiency_fast(k, kw, link, t_c, esw,
                                                     ron, mission)["traction_chain"]
                    for k in mix}
            tr[s] = _standard(_blend(vals, mix), std)
        vals = {k: pe.charging_path_efficiency_fast(k, "ac", seg.obc_power / 1e3, 400.0,
                                                    t_c, esw, ron)["path"] for k in mix}
        ac[s] = _standard(_blend(vals, mix), std)
    vals = {k: pe.charging_path_efficiency_fast(k, "dc", 150.0, dc_link, t_c, esw,
                                                ron)["path"] for k in mix}
    return {"traction": tr, "ac": ac, "dc": _standard(_blend(vals, mix), std)}


def converter_failure(arch: Archetype, mix: dict[str, float], sessions: float,
                      t_air: float, dc_link: float, pe_mode: str) -> float:
    """Annual wear-out failure probability of a DC charger front end."""
    if pe_mode in ("lookup", "constant"):
        tab = _lookup_table()
        m = base_mix(arch) if pe_mode == "constant" else mix
        return _blend({k: v["fail"] for k, v in tab.items()}, m)
    vals = {k: pe.charger_session_failure_rate(k, sessions, t_air + COOLANT_RISE_K,
                                               150.0, dc_link, arch.device_esw_mult,
                                               arch.device_ron_mult)
            for k in mix}
    return _blend(vals, mix)


def _segment_converter_cost(arch, s, seg, mix, dc_link, year, state, p) -> float:
    """Installed traction-inverter plus charger cost of one vehicle [USD]."""
    cost = 0.0
    lf_si = (1.0 - 0.02) ** (year - 2025)
    lf_wbg = eco.wbg_price_multiplier(year, state.cumulative_wbg)
    if s in LV_SEGMENTS:
        for k, share in lv_mix(mix).items():
            dev = device_for(k, seg.drive_voltage)
            inv = pe.lv_traction_inverter(seg.motor_peak_power / 1e3, seg.drive_voltage, dev)
            lf = lf_wbg if k == "GaN-LV" else lf_si
            cost += share * pe.converter_cost(inv, dev, lf, p["local_manufacturing"],
                                              p["import_duty"])
    else:
        link = dc_link if s != "bus" else max(seg.drive_voltage, dc_link)
        for k, share in mix.items():
            dev = device_for(k, link)
            inv = pe.traction_inverter(seg.motor_peak_power / 1e3, link, dev)
            lf = lf_wbg if k in ("SiC-MOSFET", "GaN-HEMT") else lf_si
            cost += share * pe.converter_cost(inv, dev, lf, p["local_manufacturing"],
                                              p["import_duty"])
    for k, share in mix.items():
        dev = CHARGER_DEVICE_LIBRARY[k]
        obc = pe.obc_pfc_stage(seg.obc_power / 1e3, dev)
        lf = lf_wbg if k in ("SiC-MOSFET", "GaN-HEMT") else lf_si
        cost += share * pe.converter_cost(obc, dev, lf, p["local_manufacturing"],
                                          p["import_duty"])
    return cost


def _daily_to_annual(daily_shape: np.ndarray, annual_energy: float) -> np.ndarray:
    """Tile a 24-hour shape to a year and scale it to the annual energy."""
    tiled = np.tile(daily_shape, 365)
    s = tiled.sum()
    return tiled * (annual_energy / s) if s > 1e-9 else tiled


def _crf(rate: float, years: int) -> float:
    """Capital recovery factor."""
    return rate / (1.0 - (1.0 + rate) ** (-years)) if rate > 0 else 1.0 / years


# ---------------------------------------------------------------------------
# Adoption, stepped one year at a time
# ---------------------------------------------------------------------------
BASE_YEAR = 2025


def reference_conditions(arch: Archetype, year: int) -> dict:
    """Parity, adequacy and awareness of the reference package S0 in ``year``."""
    path = arch.reference_path or {}
    if path:
        key = str(year)
        if key not in path:
            ys = sorted(int(k) for k in path)
            key = str(min(ys, key=lambda y: abs(y - year)))
        return path[key]
    return {"parity": arch.parity_ref, "adequacy": arch.adequacy_ref,
            "awareness": arch.awareness_ref}


def base_sales_share(arch: Archetype) -> float:
    if arch.base_sales_share is not None:
        return float(arch.base_sales_share)
    return mob.initial_sales_share(arch.base_ev_share, arch.bass_q, arch.fleet_lifetime_y,
                                   arch.vehicle_stock_growth)


def adoption_step(arch: Archetype, state: TwinState, year: int, parity: float,
                  adequacy: float, awareness: float, supply: float,
                  form: str = "ceiling", reference_run: bool = False
                  ) -> tuple[float, float]:
    """Advance adoption to ``year``; return (stock share, sales share).

    The state carries the adopted fraction and the stock share from the
    previous year, so each policy acts from the year it is in force.  If the
    state starts later than the base year (single-year calls), the missing
    years are stepped with this year's conditions.
    """
    m0 = float(np.clip(arch.market_potential * supply, 0.0, 1.0))
    if state.adopt_year is None:
        s0 = base_sales_share(arch)
        state.adopt_f = float(np.clip(s0 / max(m0, 1e-9), 1e-9, 0.999))
        state.adopt_x = float(arch.base_ev_share)
        state.adopt_s = s0
        state.adopt_year = BASE_YEAR
    if reference_run:
        state.reference_log[str(year)] = {"parity": float(parity),
                                          "adequacy": float(adequacy),
                                          "awareness": float(awareness)}
        pm = qm = mm = 1.0
    else:
        pm, qm, mm = mob.adoption_multipliers(
            parity, adequacy, awareness, reference_conditions(arch, year),
            arch.price_elasticity, arch.adoption_elasticity,
            "hazard" if form == "hazard" else "ceiling")
    while state.adopt_year < year:
        state.adopt_f = mob.bass_step(state.adopt_f, arch.bass_p * pm, arch.bass_q * qm)
        state.adopt_s = float(np.clip(m0 * mm * state.adopt_f, 0.0, 1.0))
        state.adopt_x = mob.turnover_step(state.adopt_x, state.adopt_s,
                                          arch.fleet_lifetime_y, arch.vehicle_stock_growth)
        state.adopt_year += 1
    return state.adopt_x, state.adopt_s


# ---------------------------------------------------------------------------
# Single-year simulation
# ---------------------------------------------------------------------------
def simulate_year(arch: Archetype, package: pol.PolicyPackage, year: int,
                  state: TwinState, seed: int = 0, return_series: bool = False,
                  pe_mode: str = "device", queue_mode: str = "site",
                  feeder_concentration: float = 1.0,
                  adoption_form: str = "ceiling",
                  reference_run: bool = False) -> dict:
    """Simulate one calendar year of the coupled system.

    ``reference_run`` (calibration only): adoption follows the fitted
    diffusion with all policy multipliers at one, and the year's parity,
    adequacy and awareness are logged as the reference path.
    """
    rng = np.random.default_rng(seed + year * 1009)
    levels = package.resolve(year)
    p = pol.apply(arch, levels, year)
    mix = p["device_mix"]
    dc_link = p["dc_link_voltage"]
    segs = [k for k, v in arch.segment_shares.items() if v > 0.0]

    # ---------------- environment ----------------------------------------
    temp = env.temperature_series(arch.mean_temperature, arch.temperature_amplitude,
                                  arch.diurnal_amplitude, rng)
    t_mean = float(temp.mean())
    poa = env.solar_series(arch.solar_ghi, 23.0, rng)
    availability = env.availability_series(p["availability"], rng)
    price = env.price_series(arch.electricity_price, rng, p["tou_enabled"])

    # ---------------- system scaling -------------------------------------
    # national peak base demand [MW], served by the feeder types below
    d_nat_mw = arch.population_million * 1e6 * arch.peak_demand_per_capita_kw / 1e3
    base_shape = env.base_demand_profile(1.0, rng, temp)       # peak 1 MW
    total_stock = (arch.vehicle_stock_million * 1e6
                   * (1.0 + arch.vehicle_stock_growth) ** (year - 2025))

    # ---------------- power electronics ----------------------------------
    eff = efficiencies(arch, mix, dc_link, t_mean, p["efficiency_standard"], segs,
                       pe_mode)
    dcf = p["dc_fraction"]

    # ---------------- segment-resolved ownership economics ---------------
    segment_econ: dict[str, dict[str, float]] = {}
    seg_data = {}
    for s in segs:
        seg = segment(arch, s)
        seg_data[s] = seg
        speed = arch.mean_speed_kmh * (0.72 if s in LV_SEGMENTS else 1.0)
        # wheel energy over the same drive cycle as the traction efficiency
        mission = pe.mission_of(seg, (arch.drive_cycles or {}).get(s) or speed)
        wheel = pe.cycle_wheel_energy(mission, s in LV_SEGMENTS, mob.regen_recovery(seg))
        wh_km = mob.specific_consumption(seg, temp, speed, eff["traction"][s],
                                         wheel_wh_km=wheel)
        conv = _segment_converter_cost(arch, s, seg, mix, dc_link, year, state, p)
        price_ev = eco.ev_purchase_price(seg.purchase_price, seg.battery_kwh, year,
                                         conv, p["purchase_incentive"],
                                         p["import_duty"], p["local_manufacturing"])
        price_ice = seg.ice_price * (1.0 + 0.4 * arch.import_duty)
        if seg.dc_capable:
            inv_eta = (1.0 - dcf) / eff["ac"][s] + dcf / eff["dc"]
        else:
            inv_eta = 1.0 / eff["ac"][s]
        t_ev = eco.total_cost_of_ownership(
            price_ev, seg.annual_km, wh_km, arch.electricity_price,
            seg.ownership_years, arch.discount_rate,
            seg.maintenance_ev * (0.7 + 0.3 * arch.capital_cost_premium), 0.30,
            charging_efficiency=1.0 / inv_eta)
        t_ice = eco.ice_total_cost_of_ownership(
            price_ice, seg.annual_km, seg.ice_l_per_100km, fuel_price_of(arch, seg.fuel),
            seg.ownership_years, arch.discount_rate,
            seg.maintenance_ice * (0.7 + 0.3 * arch.capital_cost_premium))
        # resource (pre-tax, pre-subsidy) prices for the social account
        res_ev = eco.ev_purchase_price(seg.purchase_price, seg.battery_kwh, year,
                                       conv, 0.0, 0.0, 0.0)
        segment_econ[s] = {"share": arch.segment_shares[s], "wh_per_km": wh_km,
                           "eta_traction": eff["traction"][s],
                           "inv_charging_eta": inv_eta,
                           "converter_cost": conv,
                           "price_ev": price_ev, "price_ice": price_ice,
                           "resource_price_ev": res_ev,
                           "resource_price_ice": seg.ice_price,
                           "tco_ev": t_ev, "tco_ice": t_ice,
                           "parity": eco.price_parity(t_ev, t_ice)}

    parity = float(np.clip(sum(v["share"] * v["parity"] for v in segment_econ.values())
                           / max(sum(v["share"] for v in segment_econ.values()), 1e-9),
                           0.3, 2.5))
    car_econ = segment_econ.get("passenger_car", next(iter(segment_econ.values())))

    # ---------------- adoption -------------------------------------------
    charger_adequacy = float(np.clip(p["connectors_per_1000"] / 28.0, 0.05, 1.8))
    ev_share_lda, sales_share = adoption_step(
        arch, state, year, parity, charger_adequacy, p["awareness"],
        p["supply_constraint"], adoption_form, reference_run)
    # Public-transport electrification is a fleet procurement: it sets the
    # electric share of the bus fleet directly and adds to the electric stock,
    # rather than re-weighting the composition of the private electric fleet.
    seg_share_ev = {s: ev_share_lda for s in segs}
    if "bus" in seg_share_ev:
        seg_share_ev["bus"] = max(ev_share_lda, p["bus_electrification"])
    stock_by_segment = {s: total_stock * arch.segment_shares[s] * seg_share_ev[s]
                        for s in segs}
    ev_stock = float(sum(stock_by_segment.values()))
    ev_share = ev_stock / max(total_stock, 1e-9)

    # ---------------- energy demand and emissions accounting -------------
    battery_energy_kwh = plug_energy_kwh = 0.0
    daily_shape = np.zeros(24)
    fleet_battery_kwh = v_km_total = 0.0
    fuel_avoided_l = co2_avoided_kg = 0.0
    fuel_saving = health = 0.0
    maint_saving = elec_kwh_displacing = capital_eac = 0.0
    ac_energy = dc_energy = ac_batt = 0.0
    seg_out = {}
    for s, n in stock_by_segment.items():
        if n <= 0.0:
            continue
        seg = seg_data[s]
        e = segment_econ[s]
        delta = displacement(arch, s)
        e_batt = n * seg.annual_km * e["wh_per_km"] / 1e3
        e_plug = e_batt * e["inv_charging_eta"]
        battery_energy_kwh += e_batt
        plug_energy_kwh += e_plug
        if seg.dc_capable:
            dc_energy += e_batt * dcf / eff["dc"]
            ac_energy += e_batt * (1.0 - dcf) / eff["ac"][s]
            ac_batt += e_batt * (1.0 - dcf)
        else:
            ac_energy += e_plug
            ac_batt += e_batt
        fleet_battery_kwh += n * seg.battery_kwh
        v_km_total += n * seg.annual_km
        litres = n * delta * seg.annual_km * seg.ice_l_per_100km / 100.0
        fuel_avoided_l += litres
        fuel_saving += litres * fuel_price_of(arch, seg.fuel)
        health += litres * health_cost_of(arch, seg.fuel)
        co2_avoided_kg += litres * eco.fuel_co2_wtw(seg.fuel) * arch.fuel_co2_mult
        cap_prem = 0.7 + 0.3 * arch.capital_cost_premium
        maint_saving += (n * delta * seg.annual_km
                         * (seg.maintenance_ice - seg.maintenance_ev) * cap_prem)
        elec_kwh_displacing += e_plug * delta
        capital_eac += (n * delta * (e["resource_price_ev"] - e["resource_price_ice"])
                        * _crf(arch.discount_rate, seg.ownership_years))
        daily_shape += mob.arrival_shape(s, arch.urban_share > 0.5) * e_batt
        seg_out[s] = {"ev_stock": n, "battery_gwh": e_batt / 1e6,
                      "plug_gwh": e_plug / 1e6, "eta_traction": e["eta_traction"],
                      "co2_avoided_kt": litres * eco.fuel_co2_wtw(seg.fuel)
                      * arch.fuel_co2_mult / 1e6}
    if daily_shape.sum() > 0:
        daily_shape /= daily_shape.sum()
    conversion_loss_kwh = plug_energy_kwh - battery_energy_kwh
    eta_path = battery_energy_kwh / max(plug_energy_kwh, 1e-9)
    eta_traction_fleet = (sum(seg_out[s]["eta_traction"] * seg_out[s]["battery_gwh"]
                              for s in seg_out)
                          / max(sum(v["battery_gwh"] for v in seg_out.values()), 1e-12)
                          if seg_out else eff["traction"][segs[0]])

    # ---------------- hourly charging profile ----------------------------
    price_day = price[:24]
    if p["flexibility"] > 0.0:
        shape24 = mob.smart_profile(1.0, "passenger_car", price_day, p["flexibility"],
                                    arch.urban_share > 0.5)
        blended = 0.45 * daily_shape + 0.55 * shape24
    else:
        blended = daily_shape
    blended = blended / max(blended.sum(), 1e-9)
    ev_kwh_hourly = _daily_to_annual(blended, plug_energy_kwh)
    ev_mw_national = ev_kwh_hourly / 1e3

    portfolio = chg.design_portfolio(ev_stock, p["connectors_per_1000"], dcf,
                                     p["ultrafast_fraction"], p["home_access"])
    thd_i = chg.harmonic_injection(
        portfolio, wbg_share=mix["SiC-MOSFET"] + mix["GaN-HEMT"]) * p["harmonic_factor"]

    # ---------------- distribution network, by feeder type ---------------
    # Each type k serves a share of the national peak with n_k identical
    # feeders; the charging load on a feeder of type k is the national
    # profile times its charging share over n_k.  Pre-existing renewable
    # plant is allocated with base demand, capacity procured for charging
    # with charging peak; only the latter is a policy cost.
    types = feeder_types(arch)
    w_ev = np.array([t["share"] * t["intensity"] for t in types])
    w_ev = w_ev / max(w_ev.sum(), 1e-12)
    tx_ratio = 8.0 * arch.transformer_headroom / arch.feeder_peak_mw   # MVA per MW
    nat = {"base": np.zeros(HOURS_PER_YEAR), "pv": np.zeros(HOURS_PER_YEAR),
           "v2g": np.zeros(HOURS_PER_YEAR), "feeder": np.zeros(HOURS_PER_YEAR)}
    per_type = []
    for t, e_k in zip(types, w_ev):
        pk = t["peak_mw"]
        n_k = t["share"] * d_nat_mw / pk
        base_k = pk * base_shape
        ev_k = ev_mw_national * e_k / max(n_k, 1e-9)
        ev_s_k = ev_k * feeder_concentration
        pv_aligned_k = levels["renewable_target"] * float(np.max(ev_k)) * 3.1
        pv_k = env.pv_generation((arch.renewable_share * pk * 2.35 + pv_aligned_k) * 1e3,
                                 poa, temp) / 1e3
        v2g_k = np.zeros(HOURS_PER_YEAR)
        if p["v2g_participation"] > 0.0:
            day_net = (base_k + ev_k - pv_k).reshape(365, 24).mean(axis=0)
            connected_kwh_day = fleet_battery_kwh * e_k / max(n_k, 1e-9) * 0.55 / 365.0
            v2g_day = mob.v2g_dispatch(connected_kwh_day, price_day, day_net,
                                       p["v2g_participation"])
            v2g_k = np.minimum(np.tile(v2g_day, 365) / 1e3, 0.35 * base_k)
        floor = 0.004 * pk
        feeder_k = np.maximum(base_k + ev_k - pv_k - v2g_k, floor)
        studied_k = np.maximum(base_k + ev_s_k - pv_k - v2g_k, floor)
        tx_orig = tx_ratio * pk
        fd = build_type_feeder(t, tx_orig * p["transformer_multiplier"],
                               p["impedance_multiplier"])
        pf_k = gridmod.power_flow_lookup(fd, studied_k)
        ind_k = gridmod.network_indicators(fd, pf_k, studied_k / 0.95, temp,
                                           ev_s_k / 0.95, thd_i, availability,
                                           float(studied_k.sum()))
        per_type.append({"key": t["key"], "n": n_k, "pk": pk, "tx_orig": tx_orig,
                         "ind": ind_k, "pf": pf_k, "ev": ev_k, "ev_s": ev_s_k,
                         "pv": pv_k, "base": base_k, "studied": studied_k,
                         "pv_aligned": pv_aligned_k})
        nat["base"] += n_k * base_k
        nat["pv"] += n_k * pv_k
        nat["v2g"] += n_k * v2g_k
        nat["feeder"] += n_k * feeder_k
    n_feeders = float(sum(x["n"] for x in per_type))
    omega = np.array([x["n"] * x["pk"] for x in per_type])
    omega = omega / omega.sum()                     # base-demand weights

    def wmean(key: str) -> float:
        return float(sum(o * x["ind"][key] for o, x in zip(omega, per_type)))

    demand_studied = float(sum(x["n"] * x["studied"].sum() for x in per_type))
    losses_nat_mwh = float(sum(x["n"] * x["ind"]["losses_mwh"] for x in per_type))
    ens_nat_mwh = float(sum(x["n"] * x["ind"]["energy_not_served_mwh"] for x in per_type))
    indicators = {k: wmean(k) for k in (
        "voltage_deviation_mean_pu", "undervoltage_hours_frac",
        "transformer_loading_peak_pu", "transformer_ageing_pu", "line_loading_p95_pu",
        "thd_v_mean", "thd_violation_frac", "resilience_index", "load_factor",
        "peak_demand_mva")}
    indicators["loss_fraction"] = losses_nat_mwh / max(demand_studied, 1e-9)
    indicators["v_min_pu"] = float(min(x["ind"]["v_min_pu"] for x in per_type))
    indicators["reliability_index"] = float(np.clip(1.0 - ens_nat_mwh
                                                    / max(demand_studied, 1e-9), 0.0, 1.0))
    tx_loading_original = float(sum(o * x["ind"]["peak_demand_mva"] / x["tx_orig"]
                                    for o, x in zip(omega, per_type)))
    tx_loading_worst = float(max(x["ind"]["transformer_loading_peak_pu"]
                                 for x in per_type))
    ev_mw_feeder = ev_mw_national / max(n_feeders, 1e-9)     # average feeder
    base_mw = nat["base"] / max(n_feeders, 1e-9)
    pv_mw = nat["pv"] / max(n_feeders, 1e-9)
    v2g_mw = nat["v2g"] / max(n_feeders, 1e-9)
    feeder_load_mw = nat["feeder"] / max(n_feeders, 1e-9)
    pv_aligned_nat_mw = float(sum(x["n"] * x["pv_aligned"] for x in per_type))
    tx_orig_nat_mva = float(sum(x["n"] * x["tx_orig"] for x in per_type))
    main_type = per_type[int(np.argmax(omega))]
    pf = main_type["pf"]

    # ---------------- charging service -----------------------------------
    eta_ac_fleet = ac_batt / ac_energy if ac_energy > 0 else 0.95
    service = chg.service_performance(
        portfolio, battery_energy_kwh, {"ac": eta_ac_fleet, "dc": eff["dc"]},
        peak_concentration=float(np.clip(0.085 * (1.0 - 0.42 * p["flexibility"]),
                                         0.030, 0.12)),
        queue_mode=queue_mode)
    # Power-cycling wear-out of charger front ends is not modelled: session
    # swings (9-27 K, see converter_reliability.csv) lie below the range on
    # which power-cycling laws are fitted, so any failure rate derived from
    # them would be an extrapolation.  Availability is governed by supply,
    # repair time and cyber-induced failures.
    fail_rate = 0.0
    fail_rate_total = float(np.clip(p["cyber_risk"], 0.0, 1.0))
    availability_service = chg.reliability_of_service(
        portfolio, p["availability"], fail_rate_total, p["maintenance_quality"])

    # ---------------- battery ageing -------------------------------------
    pack = BATTERY_LIBRARY[arch.battery_chemistry_pref]
    efc = battery_energy_kwh / max(fleet_battery_kwh, 1e-9)
    dod = 0.42 + 0.18 * dcf
    c_rate = 0.30 + 1.15 * dcf + 0.55 * p["ultrafast_fraction"]
    soh_year = float(bat.state_of_health(pack, (year - 2024) * 365.0,
                                         efc * (year - 2024), t_mean + 4.0,
                                         0.58, dod, c_rate))
    v2g_kwh_per_vehicle = (float(nat["v2g"].sum()) * 1e3
                           / max(ev_stock, 1.0)) if ev_stock > 0 else 0.0
    v2g_fade = bat.v2g_marginal_degradation(pack, v2g_kwh_per_vehicle, t_mean + 4.0)
    soh_year = float(np.clip(soh_year - v2g_fade, 0.0, 1.0))

    # ---------------- renewable utilisation and charging emissions -------
    pv_total = float(nat["pv"].sum())
    pv_to_ev = float(sum(x["n"] * np.minimum(x["pv"], x["ev"]).sum() for x in per_type))
    renewable_utilisation = pv_to_ev / max(float(ev_mw_national.sum()), 1e-9)
    curtailment = float(np.clip(
        sum(x["n"] * np.maximum(x["pv"] - x["base"] - x["ev"], 0.0).sum() for x in per_type)
        / max(pv_total, 1e-9), 0.0, 1.0))
    ef_hourly = env.marginal_emission_factor(
        arch.grid_emission_factor * arch.grid_emission_trend ** (year - 2025),
        nat["pv"] * 1e3, (nat["base"] + ev_mw_national) * 1e3)
    ef_charging = float(np.average(ef_hourly, weights=np.maximum(ev_mw_national, 1e-12)))
    emissions_charging_t = plug_energy_kwh * ef_charging / 1e3
    emissions_avoided_t = co2_avoided_kg / 1e3
    net_emissions_saved_t = emissions_avoided_t - emissions_charging_t

    # ---------------- social cost-benefit account ------------------------
    cap = chg.portfolio_capex(portfolio,
                              arch.capital_cost_premium * arch.charger_cost_mult
                              * eco.charger_price_multiplier(year, p["local_manufacturing"]),
                              0.0, p["local_manufacturing"])
    new_connectors = max(portfolio.total_connectors()
                         - sum(state.installed_connectors.values()), 0.0)
    charging_capex = cap["capex_usd"] * (new_connectors
                                         / max(portfolio.total_connectors(), 1e-9))
    reinforcement_mva = (max(levels["grid_investment"] - state.reinforcement, 0.0)
                         * 0.55 * tx_orig_nat_mva)
    grid_capex = reinforcement_mva * 1e3 * 165.0 * arch.capital_cost_premium
    state.reinforcement = max(state.reinforcement, levels["grid_investment"])
    pv_new_mw = max(pv_aligned_nat_mw - state.pv_aligned_mw, 0.0)
    pv_capex = pv_new_mw * 1e3 * 780.0 * arch.capital_cost_premium
    state.pv_aligned_mw = max(state.pv_aligned_mw, pv_aligned_nat_mw)
    programme_cost = (package.annual_public_cost(year, total_stock / 1e6, transfers=False)
                      * arch.programme_cost_mult)
    fiscal_transfer = package.annual_public_cost(year, total_stock / 1e6, transfers=True)

    v2g_capable_kwh = fleet_battery_kwh * p["v2g_participation"]
    v2g_degradation_cost = (v2g_fade / max(1.0 - pack.eol_soh, 1e-6)
                            * v2g_capable_kwh * eco.battery_price(year))
    electricity_cost = elec_kwh_displacing * arch.electricity_price

    # Energy not served: only the share attributable to charging load is
    # charged against the policy.
    ev_load_share = float(np.clip(sum(x["n"] * x["ev_s"].sum() for x in per_type)
                                  / max(demand_studied, 1e-9), 0.0, 1.0))
    ens_total_mwh = ens_nat_mwh
    reliability_cost = ens_total_mwh * ev_load_share * 1e3 * arch.value_of_lost_load
    public_share = float(np.clip(1.0 - p["home_access"], 0.02, 0.98))
    public_sessions = plug_energy_kwh * public_share / 25.0
    queue_cost = (service["wait_mean_min"] / 60.0 * arch.value_of_time * public_sessions
                  * (1.0 + 0.5 * service.get("rationed_fraction", 0.0)))

    carbon = net_emissions_saved_t * arch.social_carbon_price
    benefits = fuel_saving + maint_saving + health + carbon - reliability_cost - queue_cost
    costs = (capital_eac + electricity_cost + charging_capex + cap["opex_usd_per_year"]
             + grid_capex + pv_capex + programme_cost + v2g_degradation_cost)

    # private perspective, reported but not added to the social account
    cons_saving = sum(eco.consumer_savings(segment_econ[s]["tco_ice"],
                                           segment_econ[s]["tco_ev"], n,
                                           seg_data[s].ownership_years)
                      for s, n in stock_by_segment.items() if n > 0)

    result = {
        "year": year, "archetype": arch.key, "policy": package.key,
        "pe_mode": pe_mode,
        "ev_share": ev_share, "ev_share_private": ev_share_lda,
        "ev_stock": ev_stock, "total_stock": total_stock,
        "n_feeders": n_feeders,
        # energy
        "battery_energy_gwh": battery_energy_kwh / 1e6,
        "plug_energy_gwh": plug_energy_kwh / 1e6,
        "conversion_loss_gwh": conversion_loss_kwh / 1e6,
        "grid_losses_gwh": losses_nat_mwh / 1e3,
        "energy_per_km_wh": car_econ["wh_per_km"],
        "fleet_energy_per_km_wh": battery_energy_kwh * 1e3 / max(v_km_total, 1e-9),
        "conversion_loss_ratio": conversion_loss_kwh / max(plug_energy_kwh, 1e-9),
        "vehicle_km_billion": v_km_total / 1e9,
        # power electronics
        "eta_traction": eta_traction_fleet,
        "eta_traction_car": eff["traction"].get("passenger_car", np.nan),
        "eta_traction_lv": float(np.mean([eff["traction"][s] for s in segs
                                          if s in LV_SEGMENTS])) if any(
            s in LV_SEGMENTS for s in segs) else np.nan,
        "eta_dc_path": eff["dc"], "eta_charging_path": eta_path,
        "wbg_share": mix["SiC-MOSFET"] + mix["GaN-HEMT"],
        "sic_share": mix["SiC-MOSFET"], "gan_share": mix["GaN-HEMT"],
        "dc_link_voltage": dc_link,
        "converter_cost_usd": car_econ["converter_cost"],
        "converter_failure_rate": fail_rate,
        # charging service
        "connectors_total": portfolio.total_connectors(),
        "connectors_per_1000ev": p["connectors_per_1000"],
        "installed_charging_mw": portfolio.installed_power_mw(),
        "wait_mean_min": service["wait_mean_min"],
        "charger_utilisation": service["utilisation_mean"],
        "charger_availability": availability_service,
        "saturation_index": service["saturation_index"],
        "rationed_fraction": service["rationed_fraction"],
        "sessions_per_dc_connector": service["sessions_per_dc_connector"],
        # network
        "peak_demand_mva": indicators["peak_demand_mva"],
        "national_peak_mw": float(np.max(nat["feeder"])),
        "loss_fraction": indicators["loss_fraction"],
        "voltage_deviation_pu": indicators["voltage_deviation_mean_pu"],
        "v_min_pu": indicators["v_min_pu"],
        "undervoltage_hours_frac": indicators["undervoltage_hours_frac"],
        "transformer_loading_pu": indicators["transformer_loading_peak_pu"],
        "transformer_loading_original_pu": tx_loading_original,
        "transformer_loading_worst_type_pu": tx_loading_worst,
        **{f"tx_loading__{x['key']}": x["ind"]["transformer_loading_peak_pu"]
           for x in per_type},
        **{f"v_min__{x['key']}": x["ind"]["v_min_pu"] for x in per_type},
        **{f"undervoltage__{x['key']}": x["ind"]["undervoltage_hours_frac"]
           for x in per_type},
        "transformer_ageing_pu": indicators["transformer_ageing_pu"],
        "line_loading_pu": indicators["line_loading_p95_pu"],
        "thd_v": indicators["thd_v_mean"],
        "thd_violation_frac": indicators["thd_violation_frac"],
        "reliability_index": indicators["reliability_index"],
        "resilience_index": indicators["resilience_index"],
        "energy_not_served_gwh": ens_total_mwh / 1e3,
        "ev_load_share": ev_load_share,
        "load_factor": indicators["load_factor"],
        # battery and renewables
        "soh": soh_year, "battery_fade_pct": (1.0 - soh_year) * 100.0,
        "v2g_energy_gwh": float(nat["v2g"].sum()) / 1e3,
        "renewable_utilisation": renewable_utilisation,
        "curtailment": curtailment,
        "pv_aligned_gw": pv_aligned_nat_mw / 1e3,
        # emissions
        "emission_factor_kg_kwh": ef_charging,
        "emissions_charging_kt": emissions_charging_t / 1e3,
        "emissions_avoided_kt": emissions_avoided_t / 1e3,
        "net_emissions_saved_kt": net_emissions_saved_t / 1e3,
        "emissions_intensity_g_km": emissions_charging_t * 1e6 / max(v_km_total, 1e-9),
        "fuel_avoided_ml": fuel_avoided_l / 1e6,
        # social cost-benefit components [MUSD/yr]
        "b_fuel_musd": fuel_saving / 1e6, "b_maintenance_musd": maint_saving / 1e6,
        "b_health_musd": health / 1e6, "b_carbon_musd": carbon / 1e6,
        "b_reliability_musd": -reliability_cost / 1e6, "b_queue_musd": -queue_cost / 1e6,
        "c_vehicle_capital_musd": capital_eac / 1e6,
        "c_electricity_musd": electricity_cost / 1e6,
        "c_charging_capex_musd": charging_capex / 1e6,
        "c_charging_opex_musd": cap["opex_usd_per_year"] / 1e6,
        "c_grid_capex_musd": grid_capex / 1e6, "c_pv_capex_musd": pv_capex / 1e6,
        "c_programme_musd": programme_cost / 1e6,
        "c_v2g_degradation_musd": v2g_degradation_cost / 1e6,
        "benefits_musd": benefits / 1e6, "costs_musd": costs / 1e6,
        "fiscal_transfer_musd": fiscal_transfer / 1e6,
        "consumer_savings_musd": cons_saving / 1e6,
        # economics, consumer view
        "ev_price_usd": car_econ["price_ev"], "ice_price_usd": car_econ["price_ice"],
        "tco_ev_usd": car_econ["tco_ev"], "tco_ice_usd": car_econ["tco_ice"],
        "price_parity": parity,
        "ev_sales_share": sales_share,
        "charger_adequacy": charger_adequacy,
        "segment_economics": segment_econ, "segment_outputs": seg_out,
        # institutional
        "local_manufacturing": p["local_manufacturing"],
        "workforce_index": p["workforce_index"],
        "digital_maturity": p["digital_maturity"],
        "recycled_content": p["recycled_content"],
        "availability": p["availability"],
    }

    state.cumulative_wbg += result["wbg_share"] * ev_stock / 1e7
    state.installed_connectors = dict(portfolio.connectors)
    state.cumulative_capex += charging_capex + grid_capex + pv_capex
    state.soh = soh_year

    if return_series:
        result["series"] = {
            "temperature_c": temp, "base_mw": base_mw, "ev_mw": ev_mw_feeder,
            "pv_mw": pv_mw, "v2g_mw": v2g_mw, "feeder_mw": feeder_load_mw,
            "price": price, "availability": availability,
            "v_min_pu": pf["v_min_pu"], "losses_mw": pf["losses_mw"],
            "emission_factor": ef_hourly,
        }
    return result


# ---------------------------------------------------------------------------
# Multi-year horizon
# ---------------------------------------------------------------------------
def simulate_horizon(arch: Archetype, package: pol.PolicyPackage,
                     years: range | list[int], seed: int = 0,
                     keep_series_for: int | None = None, **kw) -> dict:
    """Propagate the coupled system across a multi-year horizon."""
    state = TwinState()
    records, series = [], None
    for y in years:
        want = keep_series_for is not None and y == keep_series_for
        r = simulate_year(arch, package, y, state, seed, return_series=want, **kw)
        if want:
            series = r.pop("series")
        records.append(r)
    return {"records": records, "series": series, "state": state}


COST_KEYS = ("c_vehicle_capital_musd", "c_electricity_musd", "c_charging_capex_musd",
             "c_charging_opex_musd", "c_grid_capex_musd", "c_pv_capex_musd",
             "c_programme_musd", "c_v2g_degradation_musd")
BENEFIT_KEYS = ("b_fuel_musd", "b_maintenance_musd", "b_health_musd", "b_carbon_musd",
                "b_reliability_musd", "b_queue_musd")


def horizon_summary(records: list[dict], arch: Archetype) -> dict:
    """Discounted, horizon-level aggregation of an annual record list.

    Cash flows are discounted to 2025 at the archetype's real social discount
    rate. Network indicators are taken in the final year, 2040, so that a
    package is judged on the system it leaves rather than on the base year.
    """
    r0 = records[0]["year"]
    d = arch.discount_rate

    def disc(key: str) -> float:
        return float(sum(rec[key] / (1.0 + d) ** (rec["year"] - r0) for rec in records))

    benefits = np.array([rec["benefits_musd"] for rec in records])
    costs = np.array([rec["costs_musd"] for rec in records])
    net = benefits - costs
    last = records[-1]
    out = {
        "npv_musd": eco.npv(net, d),
        "bcr": eco.benefit_cost_ratio(benefits, costs, d),
        "payback_years": eco.discounted_payback(net, d),
        "discounted_cost_musd": disc("costs_musd"),
        "discounted_benefit_musd": disc("benefits_musd"),
        "discounted_fiscal_transfer_musd": disc("fiscal_transfer_musd"),
        "cumulative_emissions_saved_mt": sum(rec["net_emissions_saved_kt"]
                                             for rec in records) / 1e3,
        "cumulative_gross_avoided_mt": sum(rec["emissions_avoided_kt"]
                                           for rec in records) / 1e3,
        "cumulative_charging_emissions_mt": sum(rec["emissions_charging_kt"]
                                                for rec in records) / 1e3,
        "cumulative_energy_twh": sum(rec["plug_energy_gwh"] for rec in records) / 1e3,
        "cumulative_conversion_loss_twh": sum(rec["conversion_loss_gwh"]
                                              for rec in records) / 1e3,
        "cumulative_losses_twh": sum(rec["grid_losses_gwh"] for rec in records) / 1e3,
        "final_ev_share": last["ev_share"],
        "final_ev_stock_million": last["ev_stock"] / 1e6,
        "final_wbg_share": last["wbg_share"],
        "final_wait_min": last["wait_mean_min"],
        "final_reliability": last["reliability_index"],
        "final_soh": last["soh"],
        "final_transformer_loading": last["transformer_loading_pu"],
        "final_transformer_loading_original": last["transformer_loading_original_pu"],
        "final_v_min_pu": last["v_min_pu"],
        "final_charger_availability": last["charger_availability"],
        "mean_loss_fraction": float(np.mean([rec["loss_fraction"] for rec in records])),
        "mean_voltage_deviation": float(np.mean([rec["voltage_deviation_pu"]
                                                 for rec in records])),
        "max_transformer_loading_2030_2040": float(np.max(
            [rec["transformer_loading_pu"] for rec in records if rec["year"] >= 2030])),
        "mean_renewable_utilisation": float(np.mean([rec["renewable_utilisation"]
                                                     for rec in records])),
        "mean_eta_traction": float(np.mean([rec["eta_traction"] for rec in records])),
        "mean_eta_charging": float(np.mean([rec["eta_charging_path"]
                                            for rec in records])),
        "mean_conversion_loss_ratio": float(np.mean([rec["conversion_loss_ratio"]
                                                     for rec in records])),
    }
    for k in COST_KEYS + BENEFIT_KEYS:
        out[f"pv_{k}"] = disc(k)
    return out
