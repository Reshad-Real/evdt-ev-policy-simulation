"""Parameter libraries and country-archetype configurations for EV-DT.

Numerical values in this module are *representative* engineering parameters that
lie inside the ranges reported in the peer-reviewed sources listed in
``docs_reference`` for each block.  They are not measurements of any single
commercial product; the digital twin is calibrated at system level (see
``evdt.engine.validate``) rather than at device level.

Every dataclass is JSON-serialisable so that a complete experiment can be
archived alongside its results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
BOLTZMANN_EV = 8.617333262e-5     # eV / K
GAS_CONSTANT = 8.314462618        # J / (mol K)
KELVIN = 273.15
HOURS_PER_YEAR = 8760


# ---------------------------------------------------------------------------
# Power semiconductor devices
# ---------------------------------------------------------------------------
@dataclass
class Device:
    """Analytic loss/thermal/reliability parameters of a power switch.

    Conduction is described either by an on-state resistance (unipolar devices:
    Si MOSFET, SiC MOSFET, GaN HEMT) or by a threshold-plus-resistance model
    (bipolar devices: Si IGBT).  Switching energies are datasheet-style values
    referred to (``v_ref``, ``i_ref``) and scaled with voltage and current.

    docs_reference: pe-sic-loss-datasheet, pe-sic-loss-dynamic, pe-loss-rt,
                    pe-sic-switching, pe-gan-ev, pe-wbg-defects
    """
    name: str
    technology: str                 # 'Si-IGBT' | 'Si-MOSFET' | 'SiC-MOSFET' | 'GaN-HEMT'
    v_rating: float                 # V
    i_rating: float                 # A
    r_on_25: float                  # Ohm, on-state resistance at 25 C (unipolar)
    r_on_tc: float                  # 1/K, linear temperature coefficient of r_on
    v_ce0: float                    # V, on-state threshold (bipolar only)
    r_ce: float                     # Ohm, slope resistance (bipolar only)
    e_on: float                     # J at (v_ref, i_ref)
    e_off: float                    # J at (v_ref, i_ref)
    e_rr: float                     # J, reverse-recovery energy of the freewheeling path
    v_ref: float                    # V
    i_ref: float                    # A
    i_exponent: float               # current-scaling exponent of switching energy
    e_tc: float                     # 1/K, temperature coefficient of switching energy
    r_th_jc: float                  # K/W, junction-to-case
    f_sw_max: float                 # Hz, practical maximum switching frequency
    cost_per_a: float               # USD per ampere of rated current (die + package)
    activation_energy: float        # eV, power-cycling Arrhenius term
    pc_coefficient: float           # LESIT-type pre-factor A
    pc_exponent: float              # LESIT-type exponent on delta-Tj
    trl: int                        # technology readiness level, 1-9
    # Share of the reference switching energy that does not vanish with current
    # (diode recovery and tail of bipolar devices, output-capacitance energy of
    # unipolar ones); datasheet E(I) curves have this intercept, which governs
    # losses at the light loads of urban driving.
    e_offset_fraction: float = 0.0
    # Reverse conduction in the freewheeling interval of a bridge leg.  IGBT:
    # antiparallel PiN diode, threshold v_f0 [V] and slope r_f [Ohm] at hot
    # junction.  MOSFET/HEMT: body diode or reverse-channel drop v_sd [V],
    # which conducts only during the dead times (synchronous rectification).
    v_f0: float = 0.0
    r_f: float = 0.0
    v_sd: float = 0.0
    # Part number(s) the parameters were fitted to and the fitting conditions.
    source: str = ""
    # True when r_th_jc is the module's junction-to-coolant resistance (liquid-
    # cooled automotive modules state only that), so no cooler term is added.
    rth_to_fluid: bool = False


DEVICE_LIBRARY: dict[str, Device] = {
    "Si-IGBT": Device(
        name="Si IGBT + Si PiN diode (750 V / 600 A class)", technology="Si-IGBT",
        v_rating=750.0, i_rating=600.0,
        r_on_25=0.0, r_on_tc=0.0, v_ce0=0.90, r_ce=1.85e-3,
        e_on=18.0e-3, e_off=14.0e-3, e_rr=8.0e-3,
        v_ref=400.0, i_ref=300.0, i_exponent=1.05, e_tc=1.8e-3,
        r_th_jc=0.085, f_sw_max=12e3, cost_per_a=0.055,
        activation_energy=0.30, pc_coefficient=3.70e8, pc_exponent=4.30, trl=9,
        e_offset_fraction=0.30),
    "Si-MOSFET": Device(
        name="Si super-junction MOSFET (650 V / 90 A class)", technology="Si-MOSFET",
        v_rating=650.0, i_rating=90.0,
        r_on_25=18.0e-3, r_on_tc=8.0e-3, v_ce0=0.0, r_ce=0.0,
        e_on=2.20e-3, e_off=0.15e-3, e_rr=5.00e-3,
        v_ref=400.0, i_ref=60.0, i_exponent=1.10, e_tc=1.5e-3,
        r_th_jc=0.29, f_sw_max=100e3, cost_per_a=0.075,
        activation_energy=0.32, pc_coefficient=3.20e8, pc_exponent=4.20, trl=9,
        e_offset_fraction=0.30),
    "SiC-MOSFET": Device(
        name="SiC MOSFET (1200 V / 300 A class)", technology="SiC-MOSFET",
        v_rating=1200.0, i_rating=300.0,
        r_on_25=4.6e-3, r_on_tc=5.6e-3, v_ce0=0.0, r_ce=0.0,
        e_on=5.6e-3, e_off=3.9e-3, e_rr=0.35e-3,
        v_ref=600.0, i_ref=300.0, i_exponent=1.02, e_tc=0.9e-3,
        r_th_jc=0.055, f_sw_max=100e3, cost_per_a=0.185,
        activation_energy=0.36, pc_coefficient=1.75e8, pc_exponent=4.05, trl=9,
        e_offset_fraction=0.08),
    "GaN-HEMT": Device(
        name="GaN HEMT (650 V / 60 A class)", technology="GaN-HEMT",
        v_rating=650.0, i_rating=60.0,
        r_on_25=25.0e-3, r_on_tc=6.5e-3, v_ce0=0.0, r_ce=0.0,
        e_on=0.062e-3, e_off=0.028e-3, e_rr=0.0,
        v_ref=400.0, i_ref=30.0, i_exponent=1.00, e_tc=0.6e-3,
        r_th_jc=0.55, f_sw_max=500e3, cost_per_a=0.240,
        activation_energy=0.40, pc_coefficient=1.30e7, pc_exponent=3.85, trl=8,
        e_offset_fraction=0.05),
}

# 1200 V-class variants used when the DC link exceeds what the 750 V device
# can block with the 1.2 voltage margin.  A silicon IGBT on an 800 V link is a
# 1200 V part in practice, not two 750 V parts in series; using the series
# stack instead would penalise the incumbent unfairly.
HV_VARIANTS: dict[str, Device] = {
    "Si-IGBT": Device(
        name="Si IGBT + Si PiN diode (1200 V / 600 A class)", technology="Si-IGBT",
        v_rating=1200.0, i_rating=600.0,
        r_on_25=0.0, r_on_tc=0.0, v_ce0=1.05, r_ce=2.40e-3,
        e_on=30.0e-3, e_off=36.0e-3, e_rr=16.0e-3,
        v_ref=600.0, i_ref=300.0, i_exponent=1.05, e_tc=1.8e-3,
        r_th_jc=0.075, f_sw_max=10e3, cost_per_a=0.070,
        activation_energy=0.30, pc_coefficient=3.70e8, pc_exponent=4.30, trl=9,
        e_offset_fraction=0.30),
}

# Low-voltage devices for the 48-72 V drives of two- and three-wheelers, which
# dominate the developing and least-developed fleets.  The 650-1200 V devices
# above are not used in these vehicles; a wide-bandgap requirement acts on them
# through 100 V-class GaN, whose advantage at these currents is much smaller.
LV_DEVICE_LIBRARY: dict[str, Device] = {
    "Si-LV": Device(
        name="Si trench MOSFET (100 V / 300 A class)", technology="Si-LV",
        v_rating=100.0, i_rating=300.0,
        r_on_25=1.6e-3, r_on_tc=7.0e-3, v_ce0=0.0, r_ce=0.0,
        e_on=0.12e-3, e_off=0.08e-3, e_rr=0.06e-3,
        v_ref=48.0, i_ref=100.0, i_exponent=1.10, e_tc=1.5e-3,
        r_th_jc=0.40, f_sw_max=100e3, cost_per_a=0.008,
        activation_energy=0.32, pc_coefficient=3.20e8, pc_exponent=4.20, trl=9,
        e_offset_fraction=0.20),
    "GaN-LV": Device(
        name="GaN HEMT (100 V / 100 A class)", technology="GaN-LV",
        v_rating=100.0, i_rating=100.0,
        r_on_25=1.4e-3, r_on_tc=7.5e-3, v_ce0=0.0, r_ce=0.0,
        e_on=0.010e-3, e_off=0.006e-3, e_rr=0.0,
        v_ref=48.0, i_ref=50.0, i_exponent=1.00, e_tc=0.6e-3,
        r_th_jc=0.30, f_sw_max=1e6, cost_per_a=0.030,
        activation_energy=0.40, pc_coefficient=1.30e7, pc_exponent=3.85, trl=8,
        e_offset_fraction=0.05),
}

# Third revision: the high-voltage slots are fitted to named automotive power
# modules by fit_devices.py (configs/device_library.json); the values above are
# the representative parameters of the earlier versions and remain in use for
# the silicon super-junction MOSFET and the 100 V devices, and whenever the
# fitted library is absent.  Representative body-diode drops of those devices:
DEVICE_LIBRARY["Si-MOSFET"].v_sd = 0.9
LV_DEVICE_LIBRARY["Si-LV"].v_sd = 0.8
LV_DEVICE_LIBRARY["GaN-LV"].v_sd = 2.0
# Charger stages (on-board PFC and DAB, DC-charger front end and isolated
# stage, auxiliary DC/DC) use discrete parts, not the traction power modules:
# with a 450-820 A module an 11 kW PFC stage would be grossly oversized.  The
# fitted library below supplies them under "CHG:" (400 V side) and "CHG-HV:"
# (800 V DC chargers); the representative class remains only for the silicon
# IGBT of on-board chargers.
CHARGER_DEVICE_LIBRARY: dict[str, Device] = {k: replace(v) for k, v in DEVICE_LIBRARY.items()}
CHARGER_HV_VARIANTS: dict[str, Device] = {k: replace(v) for k, v in HV_VARIANTS.items()}
#: Representative parameters of every slot, kept unchanged as the prior of
#: the datasheet fits (fit_devices.py) so that refitting never starts from
#: its own output.
REPRESENTATIVE = {
    "traction": {k: replace(v) for k, v in DEVICE_LIBRARY.items()},
    "traction_hv": {k: replace(v) for k, v in HV_VARIANTS.items()},
    "lv": {k: replace(v) for k, v in LV_DEVICE_LIBRARY.items()},
    "charger": {k: replace(v) for k, v in CHARGER_DEVICE_LIBRARY.items()},
    "charger_hv": {k: replace(v) for k, v in CHARGER_HV_VARIANTS.items()},
}

_DEVICE_FIT = Path(__file__).resolve().parents[1] / "configs" / "device_library.json"
DEVICES_FITTED = _DEVICE_FIT.exists()
#: effective PWM ripple of traction drives fitted by fit_devices.py (see
#: powerelectronics.traction_inverter); 0 without the fitted library
TRACTION_RIPPLE_PU_10K = 0.0
if DEVICES_FITTED:
    for _k, _v in json.loads(_DEVICE_FIT.read_text(encoding="utf-8")).items():
        if _k == "_traction_ripple_pu_10k":
            TRACTION_RIPPLE_PU_10K = float(_v)
        elif _k.startswith("_"):
            continue
        elif _k.startswith("HV:"):
            HV_VARIANTS[_k[3:]] = Device(**_v)
        elif _k.startswith("LV:"):
            LV_DEVICE_LIBRARY[_k[3:]] = Device(**_v)
        elif _k.startswith("CHG-HV:"):
            CHARGER_HV_VARIANTS[_k[7:]] = Device(**_v)
        elif _k.startswith("CHG:"):
            CHARGER_DEVICE_LIBRARY[_k[4:]] = Device(**_v)
        else:
            DEVICE_LIBRARY[_k] = Device(**_v)

#: Validity of the device models.  Loss parameters are referred to datasheet
#: characterisation conditions and are used only inside these bounds; outside
#: them a result is flagged rather than reported.
DEVICE_VALIDITY = {
    "t_junction_c": (25.0, 175.0),
    "current_fraction_of_rating": (0.05, 1.0),
    "voltage_fraction_of_v_ref": (0.5, 1.5),
    # LESIT/CIPS-type power-cycling laws are fitted on tests with junction
    # swings of roughly 30-130 K; damage from smaller swings is extrapolation.
    "power_cycling_delta_tj_k": (30.0, 130.0),
}


def charger_device_for(key: str, dc_link: float) -> Device:
    """Device class fitted in a charger stage at a given DC-link voltage."""
    dev = CHARGER_DEVICE_LIBRARY[key]
    if key in CHARGER_HV_VARIANTS and dc_link * 1.2 > dev.v_rating:
        return CHARGER_HV_VARIANTS[key]
    return dev


def device_for(key: str, dc_link: float) -> Device:
    """Device actually fitted for a technology at a given DC-link voltage."""
    if key in LV_DEVICE_LIBRARY:
        return LV_DEVICE_LIBRARY[key]
    dev = DEVICE_LIBRARY[key]
    if key in HV_VARIANTS and dc_link * 1.2 > dev.v_rating:
        return HV_VARIANTS[key]
    return dev


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------
@dataclass
class Converter:
    """A power-conversion stage of the EV or of the charging infrastructure.

    docs_reference: pe-traction-inv-review, pe-bidir-dcdc-review, pe-obc-totem,
                    pe-dab-compare, pe-sst-review, pe-hv-station, pe-anpc-pq
    """
    name: str
    role: str                     # 'traction-inverter' | 'dcdc' | 'obc-pfc' |
                                  # 'dcfc-afe' | 'dcfc-dcdc' | 'sst'
    rated_power: float            # W
    dc_link_voltage: float        # V
    n_switches: int               # high-frequency commutating switch positions
    switching_frequency: float    # Hz
    modulation_index: float       # -
    power_factor: float           # -
    passive_loss_coeff: float     # fraction of rated power lost in magnetics at rated load
    passive_loss_fixed: float     # fraction of rated power lost as no-load/core/aux
    ac_resistance_pu: float       # per-unit winding resistance (copper loss basis)
    cooling_r_th: float           # K/W, case-to-ambient per switch
    specific_cost: float          # USD/kW of the complete stage excluding dies
    bidirectional: bool = False
    n_switches_slow: int = 0      # line-frequency positions (conduction loss only)
    commutation: str = "hard"     # 'hard' | 'zvs' (resonant or dual-active-bridge)
    e_rr_scale: float = 1.0       # 0 when the freewheeling path is a Schottky diode
    series_diode_drop: float = 0.0  # V, rectifier bridge in the conduction path
    slow_leg_r_on: float = 5.0e-3   # Ohm, low-frequency leg (dedicated low-Rds Si)
    # PWM ripple of the phase current (three-phase bridges): peak-to-peak
    # ripple as a fraction of the rated peak current at 10 kHz switching; it
    # scales with 1/f_sw and, for a machine run off its design voltage, with
    # v_dc / ripple_v_design (0: the design voltage is the link voltage).
    ripple_pu_10k: float = 0.0
    ripple_v_design: float = 0.0


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------
@dataclass
class BatteryPack:
    """Cell-chemistry-level parameters aggregated to pack level.

    docs_reference: batt-phys-aging, batt-calendar, batt-coupled-degr,
                    batt-fade-realveh, batt-v2g-degr
    """
    chemistry: str                # 'NMC' | 'LFP'
    nominal_voltage: float        # V
    capacity_kwh: float           # kWh, beginning of life
    cell_series: int
    cell_parallel: int
    r_internal_25: float          # Ohm, pack DC resistance at 25 C, 50 % SOC
    r_temp_coeff: float           # 1/K
    coulombic_efficiency: float
    calendar_a: float             # 1/sqrt(day), Arrhenius pre-factor
    calendar_ea: float            # J/mol
    calendar_soc_beta: float      # SOC sensitivity of calendar ageing
    cycle_b: float                # per (equivalent full cycle)^z
    cycle_z: float                # throughput exponent
    cycle_dod_gamma: float        # depth-of-discharge sensitivity
    cycle_crate_delta: float      # C-rate sensitivity
    cycle_ea: float               # J/mol
    eol_soh: float                # end-of-life state of health
    specific_cost: float          # USD/kWh at pack level, reference year
    recycling_value: float        # USD/kWh recovered at end of life


BATTERY_LIBRARY: dict[str, BatteryPack] = {
    "NMC": BatteryPack(
        chemistry="NMC", nominal_voltage=400.0, capacity_kwh=50.0,
        cell_series=96, cell_parallel=3, r_internal_25=0.075, r_temp_coeff=-0.011,
        coulombic_efficiency=0.995,
        calendar_a=2.55e5, calendar_ea=49500.0, calendar_soc_beta=1.05,
        cycle_b=1.42e-3, cycle_z=0.58, cycle_dod_gamma=0.72,
        cycle_crate_delta=0.24, cycle_ea=24000.0,
        eol_soh=0.80, specific_cost=118.0, recycling_value=22.0),
    "LFP": BatteryPack(
        chemistry="LFP", nominal_voltage=400.0, capacity_kwh=50.0,
        cell_series=110, cell_parallel=3, r_internal_25=0.092, r_temp_coeff=-0.013,
        coulombic_efficiency=0.997,
        calendar_a=1.48e5, calendar_ea=51500.0, calendar_soc_beta=0.72,
        cycle_b=0.92e-3, cycle_z=0.55, cycle_dod_gamma=0.55,
        cycle_crate_delta=0.19, cycle_ea=26000.0,
        eol_soh=0.80, specific_cost=98.0, recycling_value=13.0),
}


# ---------------------------------------------------------------------------
# Vehicle segments
# ---------------------------------------------------------------------------
@dataclass
class VehicleSegment:
    """Road-load and duty-cycle description of one vehicle segment.

    docs_reference: meth-driving-energy, meth-temp-trip, meth-cold-range,
                    meth-heat-range, ldc-ssa-moto-model, bd-3w
    """
    name: str
    mass: float                   # kg, kerb + average payload
    frontal_area: float           # m^2
    drag_coefficient: float
    rolling_resistance: float
    drivetrain_efficiency: float  # mechanical path only (gearbox + bearings)
    motor_peak_power: float       # W
    battery_kwh: float            # kWh
    battery_chemistry: str
    auxiliary_power: float        # W, average cabin/electronics load at 25 C
    hvac_peak_power: float        # W, peak thermal-comfort load
    annual_km: float              # km/year
    mean_trip_km: float           # km
    trips_per_day: float
    obc_power: float              # W, on-board charger rating
    dc_capable: bool
    dc_power_max: float           # W
    v2g_capable_default: bool
    purchase_price: float         # USD, glider + drivetrain excluding battery
    ice_price: float              # USD, comparable internal-combustion vehicle
    ice_l_per_100km: float        # litres/100 km of the comparable ICE vehicle
    maintenance_ev: float         # USD/km
    maintenance_ice: float        # USD/km
    ownership_years: int          # analysis period for total cost of ownership
    fuel: str = "gasoline"        # fuel of the displaced vehicle
    drive_voltage: float = 400.0  # nominal traction DC link [V]
    # Cycle-average efficiency of the traction motor.  The first submission's
    # Eq. (7) carried this term but the code omitted it, which understated
    # specific consumption by about a tenth.
    motor_efficiency: float = 0.90


VEHICLE_LIBRARY: dict[str, VehicleSegment] = {
    "two_wheeler": VehicleSegment(
        name="Electric two-wheeler", mass=185.0, frontal_area=0.62,
        drag_coefficient=0.85, rolling_resistance=0.014, drivetrain_efficiency=0.93,
        motor_peak_power=4.0e3, battery_kwh=3.2, battery_chemistry="LFP",
        auxiliary_power=60.0, hvac_peak_power=0.0,
        annual_km=9500.0, mean_trip_km=9.0, trips_per_day=3.2,
        obc_power=1.5e3, dc_capable=False, dc_power_max=0.0,
        v2g_capable_default=False, purchase_price=760.0,
        ice_price=1150.0, ice_l_per_100km=2.4,
        maintenance_ev=0.006, maintenance_ice=0.014, ownership_years=7,
        fuel="gasoline", drive_voltage=60.0, motor_efficiency=0.85),
    "three_wheeler": VehicleSegment(
        name="Electric three-wheeler (paratransit)", mass=720.0, frontal_area=2.10,
        drag_coefficient=0.72, rolling_resistance=0.016, drivetrain_efficiency=0.91,
        motor_peak_power=7.5e3, battery_kwh=8.5, battery_chemistry="LFP",
        auxiliary_power=140.0, hvac_peak_power=0.0,
        annual_km=32000.0, mean_trip_km=6.5, trips_per_day=18.0,
        obc_power=3.3e3, dc_capable=False, dc_power_max=0.0,
        v2g_capable_default=False, purchase_price=2150.0,
        ice_price=3250.0, ice_l_per_100km=5.1,
        maintenance_ev=0.011, maintenance_ice=0.026, ownership_years=7,
        fuel="gasoline", drive_voltage=60.0, motor_efficiency=0.85),
    "passenger_car": VehicleSegment(
        name="Battery-electric passenger car", mass=1780.0, frontal_area=2.28,
        drag_coefficient=0.28, rolling_resistance=0.0092, drivetrain_efficiency=0.955,
        motor_peak_power=150.0e3, battery_kwh=60.0, battery_chemistry="NMC",
        auxiliary_power=320.0, hvac_peak_power=4200.0,
        annual_km=14500.0, mean_trip_km=17.0, trips_per_day=2.6,
        obc_power=11.0e3, dc_capable=True, dc_power_max=150.0e3,
        v2g_capable_default=True, purchase_price=17800.0,
        ice_price=21500.0, ice_l_per_100km=7.4,
        maintenance_ev=0.030, maintenance_ice=0.062, ownership_years=10),
    "light_commercial": VehicleSegment(
        name="Electric light commercial vehicle", mass=2650.0, frontal_area=3.60,
        drag_coefficient=0.33, rolling_resistance=0.0105, drivetrain_efficiency=0.945,
        motor_peak_power=120.0e3, battery_kwh=72.0, battery_chemistry="LFP",
        auxiliary_power=380.0, hvac_peak_power=4800.0,
        annual_km=38000.0, mean_trip_km=24.0, trips_per_day=6.0,
        obc_power=11.0e3, dc_capable=True, dc_power_max=120.0e3,
        v2g_capable_default=True, purchase_price=24500.0,
        ice_price=28500.0, ice_l_per_100km=9.6,
        maintenance_ev=0.038, maintenance_ice=0.079, ownership_years=9,
        fuel="diesel"),
    "bus": VehicleSegment(
        name="Electric city bus", mass=15500.0, frontal_area=7.20,
        drag_coefficient=0.62, rolling_resistance=0.0072, drivetrain_efficiency=0.94,
        motor_peak_power=250.0e3, battery_kwh=310.0, battery_chemistry="LFP",
        auxiliary_power=2100.0, hvac_peak_power=18000.0,
        annual_km=62000.0, mean_trip_km=14.0, trips_per_day=22.0,
        obc_power=22.0e3, dc_capable=True, dc_power_max=250.0e3,
        v2g_capable_default=True, purchase_price=192000.0,
        ice_price=205000.0, ice_l_per_100km=33.0,
        maintenance_ev=0.190, maintenance_ice=0.335, ownership_years=12,
        fuel="diesel", drive_voltage=650.0),
}


# ---------------------------------------------------------------------------
# Chargers
# ---------------------------------------------------------------------------
@dataclass
class ChargerClass:
    """One class of electric-vehicle supply equipment.

    docs_reference: pe-hv-station, grid-infra-impact, dev-in-standards,
                    cyb-ocpp-interop, grid-pv-ev-standards
    """
    name: str
    rated_power: float            # W per connector
    connectors: int               # connectors per site
    coupling: str                 # 'ac' | 'dc'
    standard: str
    capex_per_site: float         # USD
    opex_fraction: float          # of capex per year
    site_civil_cost: float        # USD, grid connection + civil works
    utilisation_target: float     # design-point utilisation
    harmonic_current_pu: float    # THDi of the front end at rated load


CHARGER_LIBRARY: dict[str, ChargerClass] = {
    "ac_slow": ChargerClass("AC slow (residential/kerbside)", 3.7e3, 1, "ac",
                            "IEC 61851 Mode 2/3", 620.0, 0.05, 380.0, 0.09, 0.09),
    "ac_fast": ChargerClass("AC semi-fast (workplace/public)", 11.0e3, 2, "ac",
                            "IEC 61851 Mode 3, Type 2", 3900.0, 0.06, 2600.0, 0.14, 0.06),
    "dc_50": ChargerClass("DC fast 50 kW", 50.0e3, 2, "dc",
                          "IEC 61851-23 / CCS2", 31000.0, 0.075, 18500.0, 0.13, 0.045),
    "dc_150": ChargerClass("DC rapid 150 kW", 150.0e3, 2, "dc",
                           "CCS2 / high-power charging", 78000.0, 0.075, 42000.0, 0.11, 0.035),
    "dc_350": ChargerClass("DC ultra-fast 350 kW", 350.0e3, 2, "dc",
                           "CCS2 HPC / 800 V", 168000.0, 0.08, 96000.0, 0.085, 0.030),
}


# ---------------------------------------------------------------------------
# Distribution feeder
# ---------------------------------------------------------------------------
@dataclass
class FeederConfig:
    """Radial medium-voltage feeder used as the network twin.

    The topology is a 33-node radial test feeder abstraction; branch impedances
    and the base load are scaled to the archetype under study.

    docs_reference: grid-tx-loading, grid-infra-impact, grid-harmonic-std,
                    ldc-minigrid-rel
    """
    n_nodes: int = 33
    base_voltage: float = 11.0e3        # V line-to-line
    base_power: float = 10.0e6          # VA
    r_per_km: float = 0.220             # Ohm/km (185 mm2 aluminium class)
    x_per_km: float = 0.140             # Ohm/km
    mean_branch_km: float = 0.30
    transformer_mva: float = 8.0        # MVA at the head of the feeder
    transformer_impedance: float = 0.075
    transformer_no_load_loss: float = 9.5e3    # W
    transformer_load_loss: float = 48.0e3      # W at rated load
    hot_spot_rise_rated: float = 78.0   # K, IEEE C57.91 style
    ambient_design: float = 30.0        # C
    voltage_limit_low: float = 0.94     # pu, statutory
    voltage_limit_high: float = 1.06
    thd_limit: float = 0.05             # IEEE 519 style limit at PCC


@dataclass
class FeederType:
    """One class of medium-voltage feeder in an archetype's distribution system.

    The national network is represented by a few feeder types, each solved
    on a benchmark feeder (``data/feeders/<key>_*``) and multiplied by the
    number of such feeders implied by ``demand_share`` of the national peak.
    ``ev_intensity`` is the charging energy per unit of base demand relative
    to the national average (urban feeders above one, rural below); the
    shares are renormalised so that the national charging energy is kept.
    ``key = "synthetic33"`` is the single abstract feeder of the first
    version.
    """
    key: str
    label: str
    demand_share: float
    ev_intensity: float = 1.0
    #: peak base demand of one feeder of this type [MW]; None: the
    #: benchmark's published load
    peak_mw: float | None = None
    #: multiplier on the benchmark's branch impedances [ohm]: re-basing to
    #: another voltage with per-unit impedance kept, (kV_new/kV_old)^2, times
    #: the calibration of electrical length to national km per feeder
    z_scale: float = 1.0
    #: operating voltage [kV]; None: the benchmark's own
    base_kv: float | None = None
    source: str = ""


# ---------------------------------------------------------------------------
# Country archetype
# ---------------------------------------------------------------------------
@dataclass
class Archetype:
    """A national or sub-national context in which policies are evaluated."""
    key: str
    label: str
    representative_countries: list[str]
    population_million: float
    vehicle_stock_million: float          # all motorised road vehicles, base year
    segment_shares: dict[str, float]      # share of the motorised stock by segment
    base_ev_share: float                  # EV share of stock in the base year
    grid_emission_factor: float           # kgCO2/kWh, base year
    grid_emission_trend: float            # annual multiplicative change
    renewable_share: float                # base-year VRE share of generation
    grid_availability: float              # fraction of hours supply is available
    transformer_headroom: float           # pu spare capacity at the feeder head
    network_losses: float                 # technical + non-technical loss fraction
    electricity_price: float              # USD/kWh, residential retail
    industrial_price: float               # USD/kWh
    fuel_price: float                     # USD/litre gasoline-equivalent
    ice_consumption: float                # litre/100 km fleet average
    discount_rate: float
    capital_cost_premium: float           # multiplier on infrastructure capex
    wacc: float
    urban_share: float
    charger_density_base: float           # public connectors per 1000 EVs
    dc_share_base: float                  # existing DC share of public connectors
    wbg_share_base: float                 # SiC/GaN share of new power converters
    workforce_index: float                # 0-1 power-electronics workforce capability
    manufacturing_index: float            # 0-1 domestic PE manufacturing capability
    digital_maturity: float               # 0-1 metering/IoT/DT readiness
    import_duty: float                    # duty on imported EVs / converters
    solar_ghi: float                      # kWh/m2/day annual mean
    mean_temperature: float               # C, annual mean
    temperature_amplitude: float          # C, seasonal half-amplitude
    diurnal_amplitude: float              # C
    battery_chemistry_pref: str
    value_of_lost_load: float             # USD/kWh
    value_of_time: float                  # USD/hour, queueing cost
    social_carbon_price: float            # USD/tCO2
    # --- system scaling -----------------------------------------------------
    peak_demand_per_capita_kw: float      # national peak demand per head
    feeder_peak_mw: float                 # design peak of the representative feeder
    vehicle_stock_growth: float           # annual growth of the motorised stock
    market_potential: float               # ceiling on the EV share of the stock
    bass_p: float                         # innovation coefficient
    bass_q: float                         # imitation coefficient
    mean_speed_kmh: float                 # fleet average operating speed
    maintenance_ev: float                 # USD/km, electric
    maintenance_ice: float                # USD/km, internal combustion
    # --- calibrated, archetype-specific segment data ------------------------
    # Per-segment overrides of VehicleSegment fields (annual_km,
    # ice_l_per_100km, fuel) taken from national statistics, plus
    # ``displacement``: the share of electric vehicle-km that replaces
    # internal-combustion vehicle-km.  It is below one where electric
    # three-wheelers largely replaced pedal rickshaws rather than engines.
    segment_overrides: dict = field(default_factory=dict)
    # Base-year conditions of the reference package to which the adoption
    # multipliers are normalised (set by the calibration, see calibrate.py).
    parity_ref: float = 1.0
    adequacy_ref: float = 1.0
    awareness_ref: float | None = None
    # Mean service life of the fleet [years].  The electric share of the
    # stock cannot grow faster than it would if every new registration were
    # electric; this caps the diffusion path (assumed values).
    fleet_lifetime_y: float = 15.0
    # --- adoption in sales-share space (second revision) -------------------
    # Electric share of new registrations in the base year (None: inferred
    # from the stock share, see mobility.initial_sales_share).
    base_sales_share: float | None = None
    # Elasticity of the sales-share ceiling to the ownership-cost ratio,
    # estimated from the German purchase-premium history (calibrate.py).
    price_elasticity: float = 1.0
    # Parity, adequacy and awareness of the reference package S0 in each year
    # ({"2026": {...}, ...}); policy multipliers are taken relative to them.
    reference_path: dict = field(default_factory=dict)
    # --- distribution network (third revision) ------------------------------
    # Feeder types representing the national distribution system; empty: the
    # single synthetic 33-node feeder.
    feeder_types: list = field(default_factory=list)
    # --- economics by fuel (third revision) ----------------------------------
    # Retail price of diesel and CNG relative to gasoline (fuel_price), and
    # local air-pollution damage per litre of each displaced fuel [USD];
    # empty: one price and economics.HEALTH_USD_PER_LITRE for every fuel.
    fuel_price_ratio: dict = field(default_factory=dict)
    health_cost_per_litre: dict = field(default_factory=dict)
    # Multiplier on charger hardware, installation and grid-connection cost.
    charger_cost_mult: float = 1.0
    # Standard drive cycle per segment for the traction-inverter efficiency
    # (key of powerelectronics.standard_cycle); segments without one use the
    # synthetic urban cycle at the archetype's mean speed.
    drive_cycles: dict = field(default_factory=dict)
    # --- multipliers used only by the uncertainty analysis ------------------
    device_esw_mult: float = 1.0          # switching energies
    device_ron_mult: float = 1.0          # on-state resistances
    adoption_elasticity: float = 1.0      # exponents of the policy multipliers
    fuel_co2_mult: float = 1.0            # fuel emission factors
    programme_cost_mult: float = 1.0      # resource cost of policy programmes


def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def dump_config(obj: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_jsonable(obj), indent=1), encoding="utf-8")


def library_snapshot() -> dict[str, Any]:
    """Everything needed to reproduce a run, as plain JSON."""
    return {
        "devices": {k: asdict(v) for k, v in DEVICE_LIBRARY.items()},
        "batteries": {k: asdict(v) for k, v in BATTERY_LIBRARY.items()},
        "vehicles": {k: asdict(v) for k, v in VEHICLE_LIBRARY.items()},
        "chargers": {k: asdict(v) for k, v in CHARGER_LIBRARY.items()},
        "feeder": asdict(FeederConfig()),
    }
