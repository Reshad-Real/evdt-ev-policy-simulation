"""Country archetypes and the policy packages evaluated for each of them.

Archetype parameters are order-of-magnitude representative values for the three
development classes used in the study.  They are deliberately *archetypal*: the
purpose of the twin is to establish which policy mechanisms dominate in each
context and how large the effects are, not to forecast a single named country.
The developing archetype is parameterised on Bangladesh, which is the primary
case study (docs_reference: bd-energy-access, bd-energy-sust, bd-3w, bd-lcc,
bd-temp-demand, bd-policy-coherence).
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .config import Archetype, FeederType
from .policy import PolicyPackage

# ---------------------------------------------------------------------------
# Distribution feeder types (third revision; data/feeders/FEEDERS.md)
# ---------------------------------------------------------------------------
# Weights are shares of national base demand: Germany, Eurostat degree of
# urbanisation 2024 (cities / towns and suburbs / rural); Bangladesh, energy
# sold FY2024-25 by DPDC+DESCO / BPDB zones+WZPDCL+NESCO / BREB; least-
# developed, Tanzania (TANESCO 2023: Dar es Salaam and Coast / other towns /
# rural, the last with an assumed 0.4 consumption ratio).  IEEE feeders are
# re-based with per-unit impedance kept, (kV_new/kV_old)^2, and calibrated to
# national kilometres of 11 kV line per feeder (Dhaka 4.5 km, district towns
# 12 km, PBS 52 km; Dar es Salaam 11 km, Ethiopian town feeders 34 km); the
# rural 33 kV feeder reproduces a 180 km, 4.5 MW Tanzanian feeder ending at
# 0.862 pu.  Peaks per feeder: Bangladesh from utility totals; Germany the
# coincident peak of the SimBench time series; otherwise the benchmark load.
FEEDERS_DE = [
    FeederType("simbench_mv_urban", "urban", 0.389, peak_mw=21.0,
               source="SimBench 1-MV-urban--0-sw"),
    FeederType("simbench_mv_semiurb", "semi-urban", 0.424, peak_mw=13.4,
               source="SimBench 1-MV-semiurb--0-sw"),
    FeederType("simbench_mv_rural", "rural", 0.186, peak_mw=7.5,
               source="SimBench 1-MV-rural--0-sw"),
]
FEEDERS_BD = [
    FeederType("ieee69", "urban (DPDC, DESCO)", 0.203, peak_mw=2.34,
               z_scale=0.755 * 0.10, base_kv=11.0, source="IEEE 69-bus at 11 kV, 4.5 km"),
    FeederType("ieee33", "semi-urban (BPDB zones, WZPDCL, NESCO)", 0.221, peak_mw=1.58,
               z_scale=0.755 * 0.26, base_kv=11.0, source="IEEE 33-bus at 11 kV, 12 km"),
    FeederType("in_rural28", "rural (BREB/PBS)", 0.576, peak_mw=1.62, z_scale=0.59,
               source="Indian 28-bus rural 11 kV, 52 km"),
]
FEEDERS_LDC = [
    FeederType("ieee69", "urban (Dar es Salaam, Addis Ababa)", 0.448,
               z_scale=0.755 * 0.25, base_kv=11.0, source="IEEE 69-bus at 11 kV, 11 km"),
    FeederType("ieee33", "secondary towns", 0.453, z_scale=1.404 * 0.39, base_kv=15.0,
               source="IEEE 33-bus at 15 kV, 34 km"),
    FeederType("ieee34_mv", "rural 33 kV", 0.099, z_scale=0.577, base_kv=33.0,
               source="IEEE 34-node MV part at 33 kV, calibrated"),
]

# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------
# Least-developed archetype: structural, not a named country.  Its vehicle
# density (23 per 1000 people) lies between Ethiopia and Tanzania; its grid
# factor is Tanzania's lifecycle intensity (Ember 2024, 0.345 kg/kWh), the
# conservative choice against the hydro-dominated grids of Ethiopia and Nepal.
# No historical EV series exists that could calibrate its adoption, so its
# Bass coefficients are priors, tested by the adoption-structure sensitivity.
UNDERDEVELOPED = Archetype(
    key="underdeveloped",
    label="Least-developed economy",
    representative_countries=["Ethiopia", "United Republic of Tanzania", "Malawi",
                              "Uganda", "Mozambique", "Nepal (rural)"],
    population_million=62.0, vehicle_stock_million=1.40,
    segment_shares={"two_wheeler": 0.44, "three_wheeler": 0.26,
                    "passenger_car": 0.16, "light_commercial": 0.10, "bus": 0.04},
    base_ev_share=0.004,
    grid_emission_factor=0.345, grid_emission_trend=0.985, renewable_share=0.22,
    grid_availability=0.880, transformer_headroom=0.72, network_losses=0.190,
    # Economics re-sourced in the third revision, Tanzania first (its grid
    # factor is used), Ethiopia as the range (Supplementary Table S10):
    # TANESCO/EWURA T1 general tariff 0.115 and T3-MV 0.062 USD/kWh; Dar es
    # Salaam petrol cap Dec 2025 1.08 USD/L (diesel 1.09); World Bank PADs
    # (Ethiopia 2024) discount rate 0.10 and ASCENT financial rate 0.10;
    # VoLL 0.18 USD/kWh (World Bank PRIME-1, Ethiopia, the only LDC value);
    # value of time 0.45 USD/h (Dar es Salaam bus/BRT users); World Bank
    # shadow carbon price 2025, low value 45 USD/t; Ethiopia's duty on fully
    # built EVs 0.20; IMF air-pollution damage per litre (Tanzania).
    electricity_price=0.115, industrial_price=0.062, fuel_price=1.08,
    ice_consumption=8.4, discount_rate=0.100, capital_cost_premium=1.35, wacc=0.100,
    urban_share=0.34, charger_density_base=1.5, dc_share_base=0.05, wbg_share_base=0.02,
    workforce_index=0.14, manufacturing_index=0.04, digital_maturity=0.12,
    import_duty=0.20, solar_ghi=5.6, mean_temperature=24.5,
    temperature_amplitude=4.5, diurnal_amplitude=7.0,
    battery_chemistry_pref="LFP", value_of_lost_load=0.18, value_of_time=0.45,
    social_carbon_price=45.0,
    peak_demand_per_capita_kw=0.038, feeder_peak_mw=4.0,
    vehicle_stock_growth=0.061, market_potential=0.55,
    # prior effective coefficients, replaced by the two-wheeler panel means
    bass_p=0.0026, bass_q=0.073, mean_speed_kmh=24.0,
    maintenance_ev=0.021, maintenance_ice=0.046, fleet_lifetime_y=18.0,
    fuel_price_ratio={"gasoline": 1.0, "diesel": 1.009},
    health_cost_per_litre={"gasoline": 0.0045, "diesel": 0.0139},
    drive_cycles={"passenger_car": "wltc3b:low+medium",
                  "light_commercial": "wltc3b:low+medium",
                  "two_wheeler": "idc", "three_wheeler": "idc"},
    feeder_types=FEEDERS_LDC,
    segment_overrides={
        # India ex-showroom prices as the traded reference (no Tanzanian or
        # Ethiopian list prices): e-motorcycle 1,152 USD with 2.5 kWh, Honda
        # Shine 125 960 USD; L5 e-auto 3,751 USD with 9.2 kWh, petrol auto
        # 2,424 USD.  Glider = price - battery (99 USD/kWh) - model converter.
        # Maintenance: Uganda boda-boda (2W), India (3W, cars, buses).
        "two_wheeler": {"purchase_price": 770.0, "ice_price": 960.0,
                        "maintenance_ev": 0.0040, "maintenance_ice": 0.0074},
        "three_wheeler": {"purchase_price": 2620.0, "ice_price": 2424.0,
                          "maintenance_ev": 0.0035, "maintenance_ice": 0.0053},
        # no LDC car or van prices: German net list prices (ID.3 / Golf,
        # E-Transit Custom / Transit Custom) as the traded reference
        "passenger_car": {"purchase_price": 23565.0, "ice_price": 30971.0,
                          "maintenance_ev": 0.0017, "maintenance_ice": 0.0029},
        "light_commercial": {"purchase_price": 48118.0, "ice_price": 50059.0,
                             "maintenance_ev": 0.0017, "maintenance_ice": 0.0029,
                             "fuel": "diesel"},
        "bus": {"maintenance_ev": 0.092, "maintenance_ice": 0.229},
    })

# Developing archetype: Bangladesh.  The stock is the BRTA-registered motorised
# fleet (about 6.45 million in July 2025) less heavy trucks, which are not
# modelled; shares follow the BRTA January 2024 categories (motorcycles 74.5 %
# of the non-truck fleet, cars and microbuses about 9 %, the remainder grouped).
# Battery easy-bikes are outside the registration system and the 2023 EV
# policy and are not part of the modelled fleet.  Registered EVs numbered 396
# in March 2025, so the base electric share is effectively zero.  Grid factor:
# Ember 2025 lifecycle intensity; network losses: BPDB FY2024-25 T&D loss.
DEVELOPING = Archetype(
    key="developing",
    label="Developing economy (Bangladesh case)",
    representative_countries=["Bangladesh", "India", "Pakistan", "Sri Lanka",
                              "Viet Nam", "Indonesia", "Philippines"],
    population_million=173.0, vehicle_stock_million=6.30,
    segment_shares={"two_wheeler": 0.745, "three_wheeler": 0.058,
                    "passenger_car": 0.110, "light_commercial": 0.072, "bus": 0.015},
    base_ev_share=0.0001,
    grid_emission_factor=0.696, grid_emission_trend=0.988, renewable_share=0.045,
    grid_availability=0.955, transformer_headroom=0.85, network_losses=0.101,
    # Economics re-sourced in the third revision (Supplementary Table S10):
    # BPDB average tariff 0.079 USD/kWh (2024; the BERC LT-D3 charging tariff
    # is the same, 0.079) and LT-C1/MT-3 0.088; octane 1.01, diesel 0.845 and
    # CNG 0.33 USD per litre gasoline equivalent (Nov-Dec 2025); World Bank
    # PAD VoLL 0.50 USD/kWh; value of time 0.95 USD/h (geometric mean of the
    # World Bank WeCARE range 0.52-1.71); World Bank shadow carbon price 2025,
    # low value 45 USD/t; built-up e-motorcycle duty 0.37 (FY2025-26); IMF
    # air-pollution damage per litre.
    electricity_price=0.079, industrial_price=0.088, fuel_price=1.01,
    ice_consumption=7.6, discount_rate=0.100, capital_cost_premium=1.18, wacc=0.115,
    urban_share=0.41, charger_density_base=3.0, dc_share_base=0.10, wbg_share_base=0.05,
    workforce_index=0.27, manufacturing_index=0.11, digital_maturity=0.26,
    import_duty=0.37, solar_ghi=4.8, mean_temperature=26.2,
    temperature_amplitude=6.0, diurnal_amplitude=6.5,
    battery_chemistry_pref="LFP", value_of_lost_load=0.50, value_of_time=0.95,
    social_carbon_price=45.0,
    fuel_price_ratio={"gasoline": 1.0, "diesel": 0.837, "cng": 0.327},
    # no IMF value for CNG: the gasoline value, an upper bound
    health_cost_per_litre={"gasoline": 0.123, "diesel": 0.254, "cng": 0.123},
    # standard cycles: congested urban WLTC phases for cars and vans; the
    # Indian Driving Cycle (2W/3W type approval) for two- and three-wheelers
    drive_cycles={"passenger_car": "wltc3b:low+medium",
                  "light_commercial": "wltc3b:low+medium",
                  "two_wheeler": "idc", "three_wheeler": "idc"},
    feeder_types=FEEDERS_BD,
    peak_demand_per_capita_kw=0.105, feeder_peak_mw=5.5,
    vehicle_stock_growth=0.072, market_potential=0.72,
    bass_p=0.0060, bass_q=0.36, mean_speed_kmh=21.0,
    maintenance_ev=0.019, maintenance_ice=0.042, fleet_lifetime_y=12.0,
    segment_overrides={
        # Indian motorcycles: 7,255-12,800 km/yr and about 50 km/L
        # (Goel et al., Transp. Res. D, 2015); no Bangladeshi survey found.
        # Prices: India ex-showroom as the traded reference (Bangladeshi
        # retail prices include duties the model adds separately): e-motorcycle
        # 1,152 USD with 2.5 kWh, Honda Shine 125 960 USD; maintenance IEA
        # India.  Glider = price - battery (99 USD/kWh) - model converter.
        "two_wheeler": {"annual_km": 9500.0, "ice_l_per_100km": 2.0,
                        "purchase_price": 775.0, "ice_price": 960.0,
                        "maintenance_ev": 0.0020, "maintenance_ice": 0.0045},
        # CNG auto-rickshaws, about 75 km/day (2009 Dhaka inventory); CNG in
        # litres of gasoline equivalent.  L5 e-auto 3,751 USD with 9.2 kWh
        # against a CNG auto at 2,771 USD (India); maintenance India.
        "three_wheeler": {"annual_km": 27400.0, "fuel": "cng",
                          "purchase_price": 2631.0, "ice_price": 2771.0,
                          "maintenance_ev": 0.0035, "maintenance_ice": 0.0060},
        # no Bangladeshi car or van prices: German net list prices as the
        # traded reference; maintenance India (cars; vans by proxy)
        "passenger_car": {"purchase_price": 23781.0, "ice_price": 30971.0,
                          "maintenance_ev": 0.0017, "maintenance_ice": 0.0029},
        "light_commercial": {"purchase_price": 48275.0, "ice_price": 50059.0,
                             "maintenance_ev": 0.0017, "maintenance_ice": 0.0029},
        # Indore (India) 9-10 m buses; purchase prices not sourced
        "bus": {"maintenance_ev": 0.092, "maintenance_ice": 0.229},
    })

# Developed archetype: Germany.  Stock on 1 January 2025 (KBA): 49.34 M cars,
# 5.06 M motorcycles, about 3.0 M light commercial vehicles (KBA 2025 vehicle-km
# of vans, 54.9 bn km, over 18,355 km per van) and 85,559 buses; heavy trucks
# and tractors are not modelled.  Base electric share: battery-electric share
# of the car stock at the end of 2025 (KBA, 1 January 2026).  Mileages: KBA;
# car fuel use: UBA fleet average 2024; van and motorcycle fuel use calibrated
# so that the modelled segments reproduce the 2024 CRF inventory categories
# 1.A.3.b.ii and 1.A.3.b.iv.  Grid factor: Ember 2025 lifecycle intensity.
DEVELOPED = Archetype(
    key="developed",
    label="Developed economy (Germany case)",
    representative_countries=["Germany", "United States of America", "Norway",
                              "Japan", "Republic of Korea", "China (urban)",
                              "Singapore", "Netherlands"],
    population_million=84.0, vehicle_stock_million=57.49,
    segment_shares={"two_wheeler": 0.088, "three_wheeler": 0.00,
                    "passenger_car": 0.8585, "light_commercial": 0.052, "bus": 0.0015},
    base_ev_share=0.0411,
    grid_emission_factor=0.33, grid_emission_trend=0.955, renewable_share=0.42,
    grid_availability=0.9993, transformer_headroom=1.00, network_losses=0.052,
    # Economics re-sourced in the third revision (Supplementary Table S10):
    # charging electricity 0.41 USD/kWh, three quarters at the BDEW home-
    # charging tariff (0.343) and a quarter at public AC/DC prices (ADAC,
    # about 0.6); BDEW industry 0.199; E10 1.91 and diesel 1.82 USD/L (2025);
    # BVWP 2030 discount rate 1.7 %; WACC 5.5 % (Fraunhofer ISE 2024, nominal);
    # VoLL 13.25 USD/kWh (ACER 2024, DE-LU); UBA Methodenkonvention 3.2
    # carbon cost 300 EUR2024/t = 325 USD/t (1 % pure time preference);
    # air-pollution cost per litre from UBA MK 4.0 per-vkm values net of the
    # BEV's non-exhaust emissions.  Value of time not re-sourced (BVWP).
    electricity_price=0.410, industrial_price=0.199, fuel_price=1.91,
    ice_consumption=6.6, discount_rate=0.017, capital_cost_premium=1.00, wacc=0.055,
    urban_share=0.78, charger_density_base=14.0, dc_share_base=0.22, wbg_share_base=0.26,
    workforce_index=0.82, manufacturing_index=0.68, digital_maturity=0.79,
    import_duty=0.06, solar_ghi=3.1, mean_temperature=10.5,
    temperature_amplitude=9.5, diurnal_amplitude=5.0,
    battery_chemistry_pref="NMC", value_of_lost_load=13.25, value_of_time=24.0,
    social_carbon_price=325.0,
    fuel_price_ratio={"gasoline": 1.0, "diesel": 0.953},
    health_cost_per_litre={"gasoline": 0.070, "diesel": 0.45},
    drive_cycles={"passenger_car": "wltc3b", "light_commercial": "wltc3b",
                  "two_wheeler": "wmtc_class2-2"},
    feeder_types=FEEDERS_DE,
    # Agora Verkehrswende public charging cost per point incl. grid
    # connection, against the library values (about 1.7 times)
    charger_cost_mult=1.70,
    peak_demand_per_capita_kw=0.950, feeder_peak_mw=6.5,
    vehicle_stock_growth=0.004, market_potential=0.95,
    bass_p=0.0180, bass_q=0.42, mean_speed_kmh=38.0,
    maintenance_ev=0.030, maintenance_ice=0.062, fleet_lifetime_y=16.0,
    segment_overrides={
        # Net list prices (ADAC): ID.3 Pure 31,650 USD with 55 kWh against
        # Golf 1.5 TSI 30,971; E-Transit Custom 57,348 with 71 kWh against
        # Transit Custom automatic 50,059; 12 m e-bus 655,400 against diesel
        # 350,300 (PwC E-Bus-Radar).  Glider = price - battery (99 USD/kWh) -
        # model converter.  Maintenance: mean of ADAC and IEA (cars), ADAC
        # (vans, net of VAT), IEA heavy-duty proxy (buses).
        "passenger_car": {"annual_km": 10616.0, "ice_l_per_100km": 7.4,
                          "purchase_price": 24123.0, "ice_price": 30971.0,
                          "maintenance_ev": 0.036, "maintenance_ice": 0.048},
        "light_commercial": {"annual_km": 18355.0, "ice_l_per_100km": 8.2,
                             "purchase_price": 48540.0, "ice_price": 50059.0,
                             "maintenance_ev": 0.064, "maintenance_ice": 0.068},
        "two_wheeler": {"annual_km": 2172.0, "ice_l_per_100km": 4.5},
        "bus": {"annual_km": 55346.0, "ice_l_per_100km": 43.6,
                "purchase_price": 621187.0, "ice_price": 350300.0,
                "maintenance_ev": 0.19, "maintenance_ice": 0.26},
    })

ARCHETYPES: dict[str, Archetype] = {
    "underdeveloped": UNDERDEVELOPED,
    "developing": DEVELOPING,
    "developed": DEVELOPED,
}

# Adoption coefficients fitted by calibrate.py to historical data, together
# with the base-year reference conditions the policy multipliers are
# normalised to.  When the file is absent (before the first calibration run)
# the archetypes keep the prior values above.
_CALIBRATED = Path(__file__).resolve().parents[1] / "configs" / "calibrated_adoption.json"
CALIBRATED = _CALIBRATED.exists()
if CALIBRATED:
    for _k, _v in json.loads(_CALIBRATED.read_text(encoding="utf-8")).items():
        if _k in ARCHETYPES:
            ARCHETYPES[_k] = replace(ARCHETYPES[_k], **_v)
    UNDERDEVELOPED, DEVELOPING, DEVELOPED = (ARCHETYPES["underdeveloped"],
                                             ARCHETYPES["developing"],
                                             ARCHETYPES["developed"])


# ---------------------------------------------------------------------------
# Policy packages
# ---------------------------------------------------------------------------
_ZERO = {
    "purchase_incentive": 0.0, "duty_relief": 0.0, "tou_tariff": 0.0,
    "charger_rollout": 2.0, "dc_share": 0.02, "ultrafast_share": 0.0,
    "bus_electrification": 0.0, "wbg_mandate": 0.0, "efficiency_standard": 0.0,
    "hv_architecture": 0.0, "grid_code": 0.0, "grid_investment": 0.0,
    "renewable_target": 0.0, "smart_charging": 0.0, "v2g_enablement": 0.0,
    "local_manufacturing": 0.0, "workforce": 0.0, "recycling": 0.0,
    "digital_twin": 0.0, "cybersecurity": 0.0,
}


def _pkg(key: str, label: str, arch: str, desc: str, overrides: dict,
         start: int = 2026, full: int = 2032) -> PolicyPackage:
    targets = dict(_ZERO)
    targets.update(overrides)
    return PolicyPackage(key, label, arch, desc, targets, start, full)


# --- Underdeveloped economies ----------------------------------------------
# Ambition is bounded by fiscal space, foreign-exchange availability and the
# thinness of the technical workforce; phase-in is slower.
_UD = {
    "S0": {},
    "S1": {"purchase_incentive": 0.10, "duty_relief": 0.75, "charger_rollout": 9.0,
           "dc_share": 0.06, "bus_electrification": 0.10},
    "S2": {"wbg_mandate": 0.35, "efficiency_standard": 0.60, "grid_code": 0.55,
           "workforce": 0.65, "recycling": 0.30},
    "S3": {"grid_investment": 0.45, "renewable_target": 0.55, "smart_charging": 0.35,
           "digital_twin": 0.50, "cybersecurity": 0.30, "tou_tariff": 0.40},
    "S4": {"purchase_incentive": 0.08, "duty_relief": 0.55, "charger_rollout": 10.0,
           "dc_share": 0.08, "wbg_mandate": 0.30, "efficiency_standard": 0.50,
           "grid_code": 0.45, "grid_investment": 0.35, "renewable_target": 0.45,
           "smart_charging": 0.30, "workforce": 0.50, "digital_twin": 0.35,
           "recycling": 0.25, "bus_electrification": 0.12, "tou_tariff": 0.35},
    "S5": {"purchase_incentive": 0.18, "duty_relief": 1.00, "charger_rollout": 18.0,
           "dc_share": 0.14, "ultrafast_share": 0.05, "wbg_mandate": 0.60,
           "efficiency_standard": 0.85, "hv_architecture": 0.25, "grid_code": 0.80,
           "grid_investment": 0.75, "renewable_target": 0.85, "smart_charging": 0.60,
           "v2g_enablement": 0.10, "local_manufacturing": 0.35, "workforce": 0.85,
           "recycling": 0.55, "digital_twin": 0.75, "cybersecurity": 0.55,
           "bus_electrification": 0.35, "tou_tariff": 0.70},
    "S6": {"purchase_incentive": 0.15, "duty_relief": 1.00, "charger_rollout": 26.0,
           "dc_share": 0.20, "ultrafast_share": 0.12, "wbg_mandate": 0.85,
           "efficiency_standard": 1.00, "hv_architecture": 0.50, "grid_code": 1.00,
           "grid_investment": 0.90, "renewable_target": 1.00, "smart_charging": 0.80,
           "v2g_enablement": 0.25, "local_manufacturing": 0.55, "workforce": 1.00,
           "recycling": 0.80, "digital_twin": 1.00, "cybersecurity": 0.80,
           "bus_electrification": 0.60, "tou_tariff": 0.90},
}

# --- Developing economies (Bangladesh-centred) ------------------------------
_DG = {
    "S0": {},
    "S1": {"purchase_incentive": 0.15, "duty_relief": 0.80, "charger_rollout": 16.0,
           "dc_share": 0.14, "bus_electrification": 0.20, "tou_tariff": 0.30},
    "S2": {"wbg_mandate": 0.55, "efficiency_standard": 0.80, "hv_architecture": 0.30,
           "grid_code": 0.75, "workforce": 0.75, "local_manufacturing": 0.45,
           "recycling": 0.55},
    "S3": {"grid_investment": 0.65, "renewable_target": 0.70, "smart_charging": 0.60,
           "v2g_enablement": 0.20, "digital_twin": 0.75, "cybersecurity": 0.55,
           "tou_tariff": 0.70},
    "S4": {"purchase_incentive": 0.10, "duty_relief": 0.55, "charger_rollout": 15.0,
           "dc_share": 0.14, "wbg_mandate": 0.40, "efficiency_standard": 0.60,
           "grid_code": 0.55, "grid_investment": 0.45, "renewable_target": 0.50,
           "smart_charging": 0.45, "workforce": 0.55, "local_manufacturing": 0.30,
           "digital_twin": 0.45, "recycling": 0.40, "bus_electrification": 0.20,
           "tou_tariff": 0.50, "cybersecurity": 0.35},
    "S5": {"purchase_incentive": 0.22, "duty_relief": 1.00, "charger_rollout": 32.0,
           "dc_share": 0.26, "ultrafast_share": 0.15, "wbg_mandate": 0.80,
           "efficiency_standard": 1.00, "hv_architecture": 0.55, "grid_code": 1.00,
           "grid_investment": 0.85, "renewable_target": 0.90, "smart_charging": 0.80,
           "v2g_enablement": 0.35, "local_manufacturing": 0.70, "workforce": 0.95,
           "recycling": 0.80, "digital_twin": 0.90, "cybersecurity": 0.80,
           "bus_electrification": 0.55, "tou_tariff": 0.90},
    "S6": {"purchase_incentive": 0.16, "duty_relief": 1.00, "charger_rollout": 45.0,
           "dc_share": 0.34, "ultrafast_share": 0.28, "wbg_mandate": 0.95,
           "efficiency_standard": 1.00, "hv_architecture": 0.85, "grid_code": 1.00,
           "grid_investment": 1.00, "renewable_target": 1.00, "smart_charging": 0.92,
           "v2g_enablement": 0.50, "local_manufacturing": 0.90, "workforce": 1.00,
           "recycling": 1.00, "digital_twin": 1.00, "cybersecurity": 1.00,
           "bus_electrification": 0.85, "tou_tariff": 1.00},
}

# --- Developed economies -----------------------------------------------------
_DV = {
    "S0": {},
    "S1": {"purchase_incentive": 0.10, "duty_relief": 0.50, "charger_rollout": 30.0,
           "dc_share": 0.30, "ultrafast_share": 0.20, "bus_electrification": 0.30,
           "tou_tariff": 0.50},
    "S2": {"wbg_mandate": 0.85, "efficiency_standard": 1.00, "hv_architecture": 0.85,
           "grid_code": 0.90, "workforce": 0.80, "local_manufacturing": 0.70,
           "recycling": 0.75},
    "S3": {"grid_investment": 0.75, "renewable_target": 0.85, "smart_charging": 0.88,
           "v2g_enablement": 0.45, "digital_twin": 0.90, "cybersecurity": 0.85,
           "tou_tariff": 0.85},
    "S4": {"purchase_incentive": 0.06, "duty_relief": 0.40, "charger_rollout": 28.0,
           "dc_share": 0.28, "ultrafast_share": 0.18, "wbg_mandate": 0.55,
           "efficiency_standard": 0.70, "hv_architecture": 0.45, "grid_code": 0.65,
           "grid_investment": 0.45, "renewable_target": 0.55, "smart_charging": 0.60,
           "v2g_enablement": 0.20, "local_manufacturing": 0.45, "workforce": 0.55,
           "digital_twin": 0.55, "recycling": 0.50, "bus_electrification": 0.35,
           "tou_tariff": 0.65, "cybersecurity": 0.55},
    "S5": {"purchase_incentive": 0.14, "duty_relief": 0.70, "charger_rollout": 52.0,
           "dc_share": 0.42, "ultrafast_share": 0.38, "wbg_mandate": 0.92,
           "efficiency_standard": 1.00, "hv_architecture": 0.90, "grid_code": 1.00,
           "grid_investment": 0.85, "renewable_target": 0.95, "smart_charging": 0.90,
           "v2g_enablement": 0.50, "local_manufacturing": 0.85, "workforce": 0.95,
           "recycling": 0.90, "digital_twin": 0.95, "cybersecurity": 0.95,
           "bus_electrification": 0.70, "tou_tariff": 0.95},
    "S6": {"purchase_incentive": 0.05, "duty_relief": 0.60, "charger_rollout": 72.0,
           "dc_share": 0.55, "ultrafast_share": 0.52, "wbg_mandate": 0.95,
           "efficiency_standard": 1.00, "hv_architecture": 1.00, "grid_code": 1.00,
           "grid_investment": 1.00, "renewable_target": 1.00, "smart_charging": 0.95,
           "v2g_enablement": 0.60, "local_manufacturing": 1.00, "workforce": 1.00,
           "recycling": 1.00, "digital_twin": 1.00, "cybersecurity": 1.00,
           "bus_electrification": 0.90, "tou_tariff": 1.00},
}

_LABELS = {
    "S0": ("No policy (business as usual)",
           "Counterfactual with no new intervention beyond existing practice."),
    "S1": ("Policy A: fiscal and access",
           "Purchase incentives, tariff relief and a basic public charging "
           "programme, with no technology or network conditions attached."),
    "S2": ("Policy B: power electronics and standards",
           "Wide-bandgap converter requirement, minimum converter efficiency "
           "standard, grid-code enforcement, workforce and industrial measures."),
    "S3": ("Policy C: grid and digital integration",
           "Distribution reinforcement, renewable capacity aligned to charging, "
           "smart charging, vehicle-to-grid, national digital twin and "
           "cybersecurity, without purchase subsidies."),
    "S4": ("Conservative integrated package",
           "Moderate settings across all six policy domains, sized to a "
           "constrained public budget."),
    "S5": ("Aggressive integrated package",
           "High settings across all six domains, representing a strongly "
           "resourced national programme."),
    "S6": ("Frontier package",
           "Maximum feasible settings with an accelerated phase-in, representing "
           "the technological frontier attainable by the mid-2030s."),
}

_WINDOWS = {
    "underdeveloped": {"S0": (2026, 2032), "S1": (2026, 2034), "S2": (2027, 2036),
                       "S3": (2027, 2036), "S4": (2026, 2035), "S5": (2026, 2034),
                       "S6": (2026, 2033)},
    "developing": {"S0": (2026, 2032), "S1": (2026, 2032), "S2": (2026, 2034),
                   "S3": (2026, 2034), "S4": (2026, 2033), "S5": (2026, 2032),
                   "S6": (2026, 2031)},
    "developed": {"S0": (2026, 2032), "S1": (2026, 2030), "S2": (2026, 2031),
                  "S3": (2026, 2031), "S4": (2026, 2031), "S5": (2026, 2030),
                  "S6": (2026, 2029)},
}

_TARGET_SETS = {"underdeveloped": _UD, "developing": _DG, "developed": _DV}


def policy_packages(archetype: str) -> dict[str, PolicyPackage]:
    """Return the seven policy packages defined for an archetype."""
    targets = _TARGET_SETS[archetype]
    windows = _WINDOWS[archetype]
    out = {}
    for key, overrides in targets.items():
        label, desc = _LABELS[key]
        start, full = windows[key]
        out[key] = _pkg(key, label, archetype, desc, overrides, start, full)
    return out


POLICY_ORDER = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
ARCHETYPE_ORDER = ["underdeveloped", "developing", "developed"]
HORIZON = list(range(2025, 2041))

