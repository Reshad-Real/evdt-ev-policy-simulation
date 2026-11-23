"""Environment layer: temperature, solar resource, supply availability, price.

All series are hourly over a calendar year (8760 points) and are generated from
a seeded random stream so that a scenario is exactly reproducible.  Ambient
temperature drives battery ageing and charge acceptance, converter derating and
HVAC load; the solar series drives renewable supply; the availability series
represents the load shedding that characterises weak grids (docs_reference:
ldc-minigrid-rel, bd-temp-demand, meth-temp-trip, meth-heat-range).
"""
from __future__ import annotations

import numpy as np

from .config import HOURS_PER_YEAR


def hour_of_year() -> np.ndarray:
    return np.arange(HOURS_PER_YEAR, dtype=float)


def day_of_year() -> np.ndarray:
    return np.floor(hour_of_year() / 24.0)


def hour_of_day() -> np.ndarray:
    return np.mod(hour_of_year(), 24.0)


def temperature_series(mean_c: float, seasonal_amplitude: float,
                       diurnal_amplitude: float, rng: np.random.Generator,
                       peak_day: int = 200, noise_sigma: float = 1.6,
                       ar_phi: float = 0.86) -> np.ndarray:
    """Hourly dry-bulb temperature [C].

    Deterministic seasonal and diurnal harmonics plus a first-order
    autoregressive weather residual, which reproduces the persistence of warm
    and cool spells that matters for battery ageing and converter derating.
    """
    d, h = day_of_year(), hour_of_day()
    seasonal = seasonal_amplitude * np.cos(2.0 * np.pi * (d - peak_day) / 365.0)
    diurnal = diurnal_amplitude * np.cos(2.0 * np.pi * (h - 15.0) / 24.0)
    eps = rng.normal(0.0, noise_sigma, HOURS_PER_YEAR)
    resid = np.empty(HOURS_PER_YEAR)
    resid[0] = eps[0]
    for i in range(1, HOURS_PER_YEAR):
        resid[i] = ar_phi * resid[i - 1] + eps[i]
    resid *= noise_sigma / max(np.std(resid), 1e-9)
    return mean_c + seasonal + diurnal + resid


def clear_sky_index(rng: np.random.Generator, mean_kt: float = 0.55,
                    ar_phi: float = 0.72) -> np.ndarray:
    """Persistent hourly clearness index in (0.05, 0.85)."""
    eps = rng.normal(0.0, 0.16, HOURS_PER_YEAR)
    z = np.empty(HOURS_PER_YEAR)
    z[0] = eps[0]
    for i in range(1, HOURS_PER_YEAR):
        z[i] = ar_phi * z[i - 1] + eps[i]
    z = z / max(np.std(z), 1e-9)
    return np.clip(mean_kt + 0.20 * z, 0.05, 0.85)


def solar_series(ghi_mean: float, latitude: float, rng: np.random.Generator,
                 tilt_gain: float = 1.08) -> np.ndarray:
    """Hourly plane-of-array irradiance normalised to a 1 kW peak PV array [pu].

    ``ghi_mean`` is the annual mean daily global horizontal irradiation
    [kWh/m2/day]; the shape follows a clear-sky solar geometry modulated by a
    persistent clearness index.
    """
    d, h = day_of_year(), hour_of_day()
    decl = 23.45 * np.sin(2.0 * np.pi * (284.0 + d) / 365.0)
    lat = np.radians(latitude)
    dec = np.radians(decl)
    omega = np.radians(15.0 * (h - 12.0))
    cos_z = (np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(omega))
    cos_z = np.clip(cos_z, 0.0, None)
    kt = clear_sky_index(rng, mean_kt=np.clip(ghi_mean / 8.0, 0.30, 0.72))
    poa = cos_z * kt * tilt_gain
    # normalise so that the annual mean daily energy matches ghi_mean
    daily = poa.reshape(365, 24).sum(axis=1).mean()
    if daily > 1e-9:
        poa *= ghi_mean / daily
    return np.clip(poa, 0.0, 1.25)


def pv_generation(capacity_kw: float, poa_pu: np.ndarray, temperature_c: np.ndarray,
                  temp_coeff: float = -0.0037, noct: float = 45.0,
                  inverter_eff: float = 0.975,
                  soiling_and_wiring: float = 0.94) -> np.ndarray:
    """Hourly PV generation [kW] including cell-temperature derating."""
    t_cell = temperature_c + (noct - 20.0) / 0.8 * poa_pu
    derate = 1.0 + temp_coeff * (t_cell - 25.0)
    return np.clip(capacity_kw * poa_pu * derate * inverter_eff * soiling_and_wiring,
                   0.0, None)


def wind_series(capacity_kw: float, rng: np.random.Generator,
                capacity_factor: float = 0.24) -> np.ndarray:
    """Hourly wind generation [kW] from a persistent Weibull-like resource."""
    eps = rng.normal(0.0, 1.0, HOURS_PER_YEAR)
    z = np.empty(HOURS_PER_YEAR)
    z[0] = eps[0]
    for i in range(1, HOURS_PER_YEAR):
        z[i] = 0.93 * z[i - 1] + eps[i]
    z = (z - z.mean()) / max(z.std(), 1e-9)
    u = np.clip(6.5 + 2.6 * z, 0.0, None)                    # wind speed proxy
    cp = np.clip((u ** 3 - 3.0 ** 3) / (12.0 ** 3 - 3.0 ** 3), 0.0, 1.0)
    cp = np.where(u > 25.0, 0.0, cp)
    cp *= capacity_factor / max(cp.mean(), 1e-9)
    return capacity_kw * np.clip(cp, 0.0, 1.0)


def base_demand_profile(peak_mw: float, rng: np.random.Generator,
                        temperature_c: np.ndarray, cooling_sensitivity: float = 0.021,
                        weekend_factor: float = 0.90) -> np.ndarray:
    """Non-EV feeder demand [MW] with a temperature-sensitive cooling component."""
    h, d = hour_of_day(), day_of_year()
    shape = (0.60
             + 0.16 * np.cos(2.0 * np.pi * (h - 11.0) / 24.0)
             + 0.24 * np.exp(-0.5 * ((h - 19.5) / 2.4) ** 2)
             + 0.07 * np.exp(-0.5 * ((h - 8.0) / 1.8) ** 2))
    weekend = np.where(np.mod(d, 7.0) >= 5.0, weekend_factor, 1.0)
    cooling = 1.0 + cooling_sensitivity * np.clip(temperature_c - 24.0, 0.0, None)
    noise = 1.0 + rng.normal(0.0, 0.025, HOURS_PER_YEAR)
    profile = shape * weekend * cooling * noise
    return peak_mw * profile / profile.max()


def availability_series(availability: float, rng: np.random.Generator,
                        mean_outage_hours: float = 2.6) -> np.ndarray:
    """Binary supply-availability mask reproducing load shedding on weak grids.

    Outages are clustered rather than independent, because clustering is what
    makes charging unreliable in practice.
    """
    if availability >= 0.9995:
        return np.ones(HOURS_PER_YEAR)
    target_out = (1.0 - availability) * HOURS_PER_YEAR
    n_events = max(int(round(target_out / max(mean_outage_hours, 1.0))), 1)
    mask = np.ones(HOURS_PER_YEAR)
    # outages concentrate in the evening peak and in the hot season
    weights = (0.45 + 0.55 * np.exp(-0.5 * ((hour_of_day() - 19.0) / 3.0) ** 2))
    weights *= (0.60 + 0.40 * np.clip(np.cos(2.0 * np.pi
                                             * (day_of_year() - 150.0) / 365.0), 0, 1))
    weights /= weights.sum()
    starts = rng.choice(HOURS_PER_YEAR, size=n_events, replace=True, p=weights)
    durations = np.maximum(rng.poisson(mean_outage_hours, n_events), 1)
    for s, dur in zip(starts, durations):
        mask[s:min(s + int(dur), HOURS_PER_YEAR)] = 0.0
    return mask


def price_series(retail_price: float, rng: np.random.Generator,
                 tou_enabled: bool = False, peak_ratio: float = 1.55,
                 offpeak_ratio: float = 0.62,
                 volatility: float = 0.06) -> np.ndarray:
    """Hourly retail energy price [USD/kWh].

    Without a time-of-use tariff the price is flat; with one it is stepped by
    period, which is the lever that shifts uncontrolled charging off the peak.
    """
    h = hour_of_day()
    if not tou_enabled:
        shape = np.ones(HOURS_PER_YEAR)
    else:
        shape = np.full(HOURS_PER_YEAR, 1.0)
        shape[(h >= 17) & (h < 23)] = peak_ratio
        shape[(h >= 23) | (h < 6)] = offpeak_ratio
    noise = 1.0 + rng.normal(0.0, volatility, HOURS_PER_YEAR)
    return np.clip(retail_price * shape * noise, 0.01, None)


def marginal_emission_factor(base_factor: float, renewable_kw: np.ndarray,
                             demand_kw: np.ndarray,
                             floor_ratio: float = 0.10) -> np.ndarray:
    """Hourly grid emission factor [kgCO2/kWh].

    Hours in which renewable output covers a large share of demand are supplied
    by low-carbon plant; the residual is served by the marginal thermal unit.
    """
    share = np.clip(renewable_kw / np.maximum(demand_kw, 1e-6), 0.0, 1.0)
    return base_factor * np.clip(1.0 - 0.92 * share, floor_ratio, 1.0)
