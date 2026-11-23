"""Battery layer: equivalent-circuit behaviour, charge acceptance and ageing.

Degradation is represented by the widely used additive decomposition into a
calendar term driven by time, temperature and resting state of charge, and a
cycling term driven by charge throughput, depth of discharge, C-rate and
temperature (docs_reference: batt-phys-aging, batt-calendar, batt-coupled-degr,
batt-fade-realveh).  The same formulation is reused to price the incremental
degradation caused by vehicle-to-grid dispatch (docs_reference: batt-v2g-degr,
batt-v2g-degr-model).
"""
from __future__ import annotations

import numpy as np

from .config import GAS_CONSTANT, KELVIN, BatteryPack

# Open-circuit voltage shape, normalised to the nominal pack voltage.
_OCV_SOC = np.array([0.00, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50,
                     0.60, 0.70, 0.80, 0.90, 0.95, 1.00])
_OCV_NMC = np.array([0.790, 0.845, 0.874, 0.906, 0.928, 0.945, 0.960,
                     0.977, 0.997, 1.019, 1.043, 1.056, 1.068])
_OCV_LFP = np.array([0.855, 0.905, 0.928, 0.949, 0.958, 0.963, 0.967,
                     0.971, 0.976, 0.983, 0.997, 1.014, 1.041])


def open_circuit_voltage(pack: BatteryPack, soc: np.ndarray | float) -> np.ndarray:
    """Pack open-circuit voltage [V]."""
    shape = _OCV_LFP if pack.chemistry == "LFP" else _OCV_NMC
    return pack.nominal_voltage * np.interp(np.clip(soc, 0.0, 1.0), _OCV_SOC, shape)


def internal_resistance(pack: BatteryPack, soc: np.ndarray | float,
                        temperature_c: np.ndarray | float,
                        soh: np.ndarray | float = 1.0) -> np.ndarray:
    """Pack DC resistance [Ohm], rising at low temperature, low SOC and low SOH."""
    soc = np.clip(np.asarray(soc, dtype=float), 0.02, 1.0)
    t = np.asarray(temperature_c, dtype=float)
    r_t = pack.r_internal_25 * np.exp(pack.r_temp_coeff * (t - 25.0) * -1.0)
    r_soc = 1.0 + 0.55 * np.exp(-9.0 * soc) + 0.16 * np.maximum(soc - 0.9, 0.0) / 0.1
    r_soh = 1.0 + 1.9 * np.maximum(1.0 - np.asarray(soh, dtype=float), 0.0)
    return r_t * r_soc * r_soh


def charge_acceptance(pack: BatteryPack, soc: np.ndarray | float,
                      temperature_c: np.ndarray | float,
                      p_offered: np.ndarray | float,
                      soh: np.ndarray | float = 1.0) -> np.ndarray:
    """Power the pack can actually absorb [W] under CC-CV and thermal limits.

    The constant-current phase is limited by the C-rate ceiling; above the
    taper point the accepted power falls approximately linearly to a trickle,
    and cold or hot cells are derated further.
    """
    soc = np.clip(np.asarray(soc, dtype=float), 0.0, 1.0)
    t = np.asarray(temperature_c, dtype=float)
    cap_kwh = pack.capacity_kwh * np.asarray(soh, dtype=float)
    c_max = 2.6 if pack.chemistry == "LFP" else 3.0
    p_cc = c_max * cap_kwh * 1e3

    taper_start = 0.60
    taper = np.where(soc <= taper_start, 1.0,
                     np.clip(1.0 - 0.92 * (soc - taper_start) / (1.0 - taper_start),
                             0.06, 1.0))
    # Temperature derating: lithium plating risk below 10 C, thermal limit above 45 C
    cold = np.clip((t - (-5.0)) / 20.0, 0.12, 1.0)
    hot = np.clip((55.0 - t) / 12.0, 0.25, 1.0)
    limit = p_cc * taper * np.minimum(cold, hot)
    return np.minimum(np.asarray(p_offered, dtype=float), limit)


def round_trip_efficiency(pack: BatteryPack, c_rate: np.ndarray | float,
                          temperature_c: np.ndarray | float,
                          soh: np.ndarray | float = 1.0) -> np.ndarray:
    """DC round-trip efficiency of the pack at a given C-rate."""
    c = np.abs(np.asarray(c_rate, dtype=float))
    r = internal_resistance(pack, 0.55, temperature_c, soh)
    v = open_circuit_voltage(pack, 0.55)
    i = c * pack.capacity_kwh * 1e3 / v
    loss_frac = np.clip(i * r / v, 0.0, 0.30)
    return np.clip(pack.coulombic_efficiency * (1.0 - loss_frac), 0.70, 0.995)


# ---------------------------------------------------------------------------
# Ageing
# ---------------------------------------------------------------------------
def calendar_fade(pack: BatteryPack, days: np.ndarray | float,
                  temperature_c: np.ndarray | float,
                  mean_soc: np.ndarray | float) -> np.ndarray:
    r"""Calendar capacity fade [fraction of nominal].

    :math:`Q_{cal} = a\,e^{-E_a/RT}\,e^{\beta\,\mathrm{SOC}}\,t^{0.5}`
    """
    t_k = np.asarray(temperature_c, dtype=float) + KELVIN
    k = (pack.calendar_a * np.exp(-pack.calendar_ea / (GAS_CONSTANT * t_k))
         * np.exp(pack.calendar_soc_beta * (np.asarray(mean_soc, dtype=float) - 0.5)))
    return k * np.power(np.maximum(np.asarray(days, dtype=float), 0.0), 0.5)


def cycle_fade(pack: BatteryPack, efc: np.ndarray | float,
               dod: np.ndarray | float, c_rate: np.ndarray | float,
               temperature_c: np.ndarray | float) -> np.ndarray:
    r"""Cycling capacity fade [fraction of nominal] for ``efc`` equivalent full
    cycles at depth of discharge ``dod``, rate ``c_rate`` and temperature ``T``.

    :math:`Q_{cyc} = b\,e^{\gamma(\mathrm{DOD}-0.5)}\,e^{\delta\,C}\,
    e^{-E_a/R}(1/T_\mathrm{ref}-1/T)\,N^{z}`
    """
    t_k = np.asarray(temperature_c, dtype=float) + KELVIN
    arr = np.exp(-pack.cycle_ea / GAS_CONSTANT * (1.0 / t_k - 1.0 / (25.0 + KELVIN)))
    k = (pack.cycle_b
         * np.exp(pack.cycle_dod_gamma * (np.asarray(dod, dtype=float) - 0.5))
         * np.exp(pack.cycle_crate_delta * np.abs(np.asarray(c_rate, dtype=float)))
         * arr)
    return k * np.power(np.maximum(np.asarray(efc, dtype=float), 0.0), pack.cycle_z)


def state_of_health(pack: BatteryPack, days: np.ndarray | float,
                    efc: np.ndarray | float, temperature_c: np.ndarray | float,
                    mean_soc: np.ndarray | float, dod: np.ndarray | float,
                    c_rate: np.ndarray | float) -> np.ndarray:
    """Combined state of health, ``SOH = 1 - Q_cal - Q_cyc``."""
    q = (calendar_fade(pack, days, temperature_c, mean_soc)
         + cycle_fade(pack, efc, dod, c_rate, temperature_c))
    return np.clip(1.0 - q, 0.0, 1.0)


def years_to_eol(pack: BatteryPack, efc_per_year: float, temperature_c: float,
                 mean_soc: float, dod: float, c_rate: float,
                 horizon: int = 30) -> float:
    """Years until the pack reaches its end-of-life state of health."""
    years = np.arange(1, horizon + 1, dtype=float)
    soh = state_of_health(pack, years * 365.0, years * efc_per_year,
                          temperature_c, mean_soc, dod, c_rate)
    below = np.flatnonzero(soh <= pack.eol_soh)
    if below.size == 0:
        return float(horizon)
    i = int(below[0])
    if i == 0:
        return 1.0
    y0, y1 = years[i - 1], years[i]
    s0, s1 = soh[i - 1], soh[i]
    return float(y0 + (s0 - pack.eol_soh) * (y1 - y0) / max(s0 - s1, 1e-9))


def v2g_marginal_degradation(pack: BatteryPack, v2g_kwh_per_year: float,
                             temperature_c: float, dod_v2g: float = 0.18,
                             c_rate_v2g: float = 0.35) -> float:
    """Extra annual capacity fade attributable to vehicle-to-grid throughput."""
    efc = v2g_kwh_per_year / max(pack.capacity_kwh, 1e-9) / 2.0
    return float(cycle_fade(pack, efc, dod_v2g, c_rate_v2g, temperature_c))


def degradation_cost(pack: BatteryPack, fade_fraction: float,
                     pack_price: float | None = None) -> float:
    """Monetised value of a given capacity fade [USD]."""
    price = pack.specific_cost if pack_price is None else pack_price
    usable = max(1.0 - pack.eol_soh, 1e-6)
    return float(price * pack.capacity_kwh * fade_fraction / usable)


def second_life_energy(pack: BatteryPack, retired_packs: float,
                       soh_at_retirement: float = 0.80,
                       reuse_fraction: float = 0.55) -> float:
    """Stationary storage capacity recovered from retired packs [kWh]."""
    return float(retired_packs * pack.capacity_kwh * soh_at_retirement * reuse_fraction)
