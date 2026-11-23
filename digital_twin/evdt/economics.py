"""Economic and environmental accounting layer.

Provides technology learning curves, vehicle and infrastructure cost build-ups,
total cost of ownership against the incumbent internal-combustion alternative,
discounted cost-benefit analysis with payback and benefit-cost ratio, and the
emission accounting that converts delivered charging energy into avoided
greenhouse-gas emissions (docs_reference: econ-tco-asean, econ-moo-mcdm,
chg-multistage-pv, env-wtw-2021, env-wtw-2022, env-lca-battery, bd-lcc).
"""
from __future__ import annotations

import numpy as np

# Reference year for all cost trajectories.
BASE_YEAR = 2025

# Tank-to-wheel CO2 per litre (IPCC 2006 default carbon contents; CNG per litre
# of gasoline equivalent) and the well-to-tank uplift that adds fuel extraction,
# refining and distribution.  The displaced-vehicle emission is the product.
# Gasoline 2.32 and diesel 2.70 kg/L: US EPA GHG Emission Factors Hub 2025
# (combustion); CNG per litre of gasoline equivalent: IPCC 2006 default
# 56.1 kg/GJ at 32.1 MJ/L.  Well-to-tank uplifts from JEC WTW v5 (COG1 17.0 and
# COD1 18.9 gCO2e/MJ over 73.4 and 73.2 g/MJ); for CNG the gasoline uplift is
# assumed, as no comparable pathway value was retrieved.
FUEL_TTW_KG_PER_L = {"gasoline": 2.32, "diesel": 2.70, "cng": 1.80}
FUEL_WTT_UPLIFT = {"gasoline": 1.23, "diesel": 1.26, "cng": 1.23}
# Retained for backward compatibility of the supplementary scripts.
FUEL_CO2_PER_LITRE = FUEL_TTW_KG_PER_L["gasoline"]
FUEL_UPSTREAM_FACTOR = FUEL_WTT_UPLIFT["gasoline"]
# Air-quality damage avoided per litre of fuel not burned [USD/L].
HEALTH_USD_PER_LITRE = 0.19


def fuel_co2_wtw(fuel: str) -> float:
    """Well-to-wheel CO2 of one litre of the displaced fuel [kg]."""
    return FUEL_TTW_KG_PER_L[fuel] * FUEL_WTT_UPLIFT[fuel]


# ---------------------------------------------------------------------------
# Learning curves
# ---------------------------------------------------------------------------
def learning_curve(cumulative_ratio: float | np.ndarray,
                   learning_rate: float) -> np.ndarray:
    """Wright's law cost multiplier for a given cumulative production ratio."""
    b = -np.log2(1.0 - learning_rate)
    return np.power(np.maximum(np.asarray(cumulative_ratio, dtype=float), 1e-6), -b)


def battery_price(year: int, base_price: float = 99.0,
                  annual_decline: float = 0.055, floor: float = 58.0) -> float:
    """Pack-level battery price [USD/kWh]; 2025 value: BNEF battery price
    survey 2025, average across segments (97-99 USD/kWh)."""
    return float(max(base_price * (1.0 - annual_decline) ** (year - BASE_YEAR), floor))


def wbg_price_multiplier(year: int, deployment_share: float,
                         learning_rate: float = 0.19) -> float:
    """Cost of a wide-bandgap die relative to its 2025 level.

    Wide-bandgap device cost falls with cumulative deployment; a national
    mandate therefore lowers the cost of the very technology it requires, which
    is the compounding effect that the policy simulations quantify
    (docs_reference: pe-sic-wafer, pe-gan-ev).
    """
    years = max(year - BASE_YEAR, 0)
    autonomous = (1.0 - 0.045) ** years
    cumulative = 1.0 + 5.5 * float(np.clip(deployment_share, 0.0, 1.0)) * years / 15.0
    return float(max(autonomous * learning_curve(cumulative, learning_rate), 0.34))


def charger_price_multiplier(year: int, local_manufacturing: float,
                             learning_rate: float = 0.13) -> float:
    """Charging-hardware cost relative to 2025, including localisation savings."""
    years = max(year - BASE_YEAR, 0)
    autonomous = (1.0 - 0.035) ** years
    localisation = 1.0 - 0.17 * float(np.clip(local_manufacturing, 0.0, 1.0))
    return float(max(autonomous * localisation, 0.42))


# ---------------------------------------------------------------------------
# Vehicle economics
# ---------------------------------------------------------------------------
def ev_purchase_price(glider_price: float, battery_kwh: float, year: int,
                      converter_cost: float, incentive: float = 0.0,
                      import_duty: float = 0.0,
                      local_manufacturing: float = 0.0) -> float:
    """Delivered EV price to the consumer [USD]."""
    batt = battery_kwh * battery_price(year)
    base = glider_price + batt + converter_cost
    duty = base * import_duty * (1.0 - float(np.clip(local_manufacturing, 0.0, 1.0)))
    return float(max((base + duty) * (1.0 - float(np.clip(incentive, 0.0, 0.6))), 0.0))


def ice_total_cost_of_ownership(price: float, annual_km: float,
                                litres_per_100km: float, fuel_price: float,
                                years: int, discount_rate: float,
                                maintenance_per_km: float,
                                residual_fraction: float = 0.33) -> float:
    """Discounted total cost of ownership of the comparable ICE vehicle [USD]."""
    running = (annual_km * litres_per_100km / 100.0 * fuel_price
               + annual_km * maintenance_per_km)
    annuity = sum(1.0 / (1.0 + discount_rate) ** t for t in range(1, years + 1))
    residual = price * residual_fraction / (1.0 + discount_rate) ** years
    return float(price + running * annuity - residual)


def total_cost_of_ownership(price: float, annual_km: float, wh_per_km: float,
                            energy_price: float, years: int, discount_rate: float,
                            maintenance_per_km: float, residual_fraction: float,
                            battery_replacement: float = 0.0,
                            charging_efficiency: float = 0.92) -> float:
    """Discounted total cost of ownership [USD]."""
    r = discount_rate
    energy_cost = annual_km * wh_per_km / 1e3 / max(charging_efficiency, 1e-6) * energy_price
    running = energy_cost + annual_km * maintenance_per_km
    annuity = sum(1.0 / (1.0 + r) ** t for t in range(1, years + 1))
    residual = price * residual_fraction / (1.0 + r) ** years
    replacement = battery_replacement / (1.0 + r) ** max(years - 2, 1)
    return float(price + running * annuity + replacement - residual)


def ice_running_cost(annual_km: float, litres_per_100km: float,
                     fuel_price: float, maintenance_per_km: float) -> float:
    return float(annual_km * litres_per_100km / 100.0 * fuel_price
                 + annual_km * maintenance_per_km)


def price_parity(tco_ev: float, tco_ice: float) -> float:
    """Ratio used to drive adoption: >1 means the EV is cheaper to own."""
    return float(np.clip(tco_ice / max(tco_ev, 1e-6), 0.30, 2.5))


# ---------------------------------------------------------------------------
# Emissions
# ---------------------------------------------------------------------------
def charging_emissions(energy_kwh: np.ndarray | float,
                       emission_factor: np.ndarray | float) -> float:
    """Operational emissions of charging [tCO2]."""
    return float(np.sum(np.asarray(energy_kwh) * np.asarray(emission_factor)) / 1e3)


def avoided_emissions(vehicle_km: float, litres_per_100km: float,
                      occupancy_factor: float = 1.0) -> float:
    """Tailpipe plus upstream emissions displaced by electrification [tCO2]."""
    litres = vehicle_km * litres_per_100km / 100.0 * occupancy_factor
    return float(litres * FUEL_CO2_PER_LITRE * FUEL_UPSTREAM_FACTOR / 1e3)


def embodied_battery_emissions(battery_kwh: float, intensity_kg_per_kwh: float = 66.0,
                               recycled_content: float = 0.0) -> float:
    """Manufacturing emissions of a battery pack [tCO2].

    Recycled cathode material displaces primary production and reduces the
    embodied intensity (docs_reference: batt-recycle-review, env-lca-battery).
    """
    reduction = 1.0 - 0.28 * float(np.clip(recycled_content, 0.0, 1.0))
    return float(battery_kwh * intensity_kg_per_kwh * reduction / 1e3)


def converter_loss_emissions(loss_kwh: float, emission_factor: float) -> float:
    """Emissions attributable to power-conversion losses [tCO2]."""
    return float(loss_kwh * emission_factor / 1e3)


# ---------------------------------------------------------------------------
# Cost-benefit analysis
# ---------------------------------------------------------------------------
def npv(cashflows: np.ndarray, discount_rate: float) -> float:
    t = np.arange(cashflows.size, dtype=float)
    return float(np.sum(cashflows / (1.0 + discount_rate) ** t))


def discounted_payback(cashflows: np.ndarray, discount_rate: float) -> float:
    """Years until the discounted cumulative cash flow first turns positive."""
    t = np.arange(cashflows.size, dtype=float)
    disc = cashflows / (1.0 + discount_rate) ** t
    cum = np.cumsum(disc)
    pos = np.flatnonzero(cum > 0.0)
    if pos.size == 0:
        return float("inf")
    i = int(pos[0])
    if i == 0:
        return 0.0
    prev = cum[i - 1]
    return float(i - 1 + abs(prev) / max(abs(cum[i] - prev), 1e-9))


def benefit_cost_ratio(benefits: np.ndarray, costs: np.ndarray,
                       discount_rate: float) -> float:
    t = np.arange(benefits.size, dtype=float)
    b = float(np.sum(benefits / (1.0 + discount_rate) ** t))
    c = float(np.sum(costs / (1.0 + discount_rate) ** t))
    return float(b / max(c, 1e-9))


def levelised_cost_of_charging(capex: float, opex_per_year: float,
                               energy_per_year_kwh: float, energy_price: float,
                               lifetime: int, discount_rate: float) -> float:
    """Levelised cost of delivering one kilowatt-hour of charging [USD/kWh]."""
    ann = sum(1.0 / (1.0 + discount_rate) ** t for t in range(1, lifetime + 1))
    cost = capex + (opex_per_year + energy_per_year_kwh * energy_price) * ann
    energy = energy_per_year_kwh * ann
    return float(cost / max(energy, 1e-9))


def national_savings(fuel_litres_avoided: float, fuel_import_price: float,
                     emissions_avoided_t: float, carbon_price: float,
                     health_benefit_per_litre: float = 0.19,
                     energy_not_served_mwh: float = 0.0,
                     value_of_lost_load: float = 0.0) -> dict[str, float]:
    """Macro-level benefits of the policy [USD/year]."""
    fuel = fuel_litres_avoided * fuel_import_price
    health = fuel_litres_avoided * health_benefit_per_litre
    carbon = emissions_avoided_t * carbon_price
    reliability_cost = energy_not_served_mwh * 1e3 * value_of_lost_load
    return {"fuel_import_savings": fuel, "health_benefit": health,
            "carbon_benefit": carbon, "reliability_cost": reliability_cost,
            "total": fuel + health + carbon - reliability_cost}


def consumer_savings(tco_ice: float, tco_ev: float, n_vehicles: float,
                     ownership_years: int) -> float:
    """Aggregate discounted household saving over the ownership period [USD]."""
    return float(max(tco_ice - tco_ev, -1e12) * n_vehicles / max(ownership_years, 1))
