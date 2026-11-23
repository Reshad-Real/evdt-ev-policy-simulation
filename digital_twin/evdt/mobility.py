"""Mobility layer: fleet composition, adoption dynamics and vehicle energy use.

Adoption is modelled as a Bass-type diffusion process whose innovation and
imitation coefficients are modulated by policy levers (purchase-price parity,
charger availability, information programmes), which is the standard structure
used in the EV-diffusion literature (docs_reference: meth-abm-diffusion,
meth-abm-v2g, pol-infra-income, dev-consumer-ready).  Vehicle energy use is
computed from a physical road-load model with an explicit temperature-dependent
auxiliary and thermal-comfort term (docs_reference: meth-driving-energy,
meth-temp-trip, meth-cold-range, meth-heat-range).
"""
from __future__ import annotations

import numpy as np

from .config import HOURS_PER_YEAR, VEHICLE_LIBRARY, VehicleSegment

GRAVITY = 9.81
AIR_DENSITY = 1.20


# ---------------------------------------------------------------------------
# Energy consumption
# ---------------------------------------------------------------------------
def road_load_energy(seg: VehicleSegment, mean_speed_kmh: float,
                     stop_density: float = 2.2) -> float:
    """Tractive energy at the wheels [Wh/km] for a representative duty cycle.

    ``stop_density`` is the number of stop-start events per kilometre, which
    sets the kinetic-energy term after regenerative-braking recovery.
    """
    v = mean_speed_kmh / 3.6
    f_roll = seg.rolling_resistance * seg.mass * GRAVITY
    f_aero = 0.5 * AIR_DENSITY * seg.drag_coefficient * seg.frontal_area * v ** 2
    e_steady = (f_roll + f_aero) / 3.6                       # Wh/km
    e_kinetic = 0.5 * seg.mass * v ** 2 / 3600.0 * stop_density
    regen_recovery = 0.62 if seg.motor_peak_power > 10e3 else 0.35
    return e_steady + e_kinetic * (1.0 - regen_recovery)


def auxiliary_energy(seg: VehicleSegment, temperature_c, mean_speed_kmh: float) -> float:
    """Auxiliary and thermal-comfort energy [Wh/km].

    Cabin conditioning is proportional to the deviation from the comfort band
    and inversely proportional to speed, so it dominates urban duty cycles in
    hot and cold climates.  ``temperature_c`` may be a scalar or the hourly
    series; with a series the load is averaged over daytime driving hours
    (06-22 h), because evaluating it at the annual mean would remove almost all
    cooling in a hot climate whose mean sits near the comfort band.
    """
    hours_per_km = 1.0 / max(mean_speed_kmh, 5.0)
    t = np.asarray(temperature_c, dtype=float)
    if t.ndim and t.size >= 24:
        hod = np.arange(t.size) % 24
        t = t[(hod >= 6) & (hod < 22)]
    frac = np.minimum(0.030 * np.maximum(18.0 - t, 0.0)
                      + 0.038 * np.maximum(t - 26.0, 0.0), 1.0)
    hvac = seg.hvac_peak_power * float(np.mean(frac))
    return (seg.auxiliary_power + hvac) * hours_per_km


def regen_recovery(seg: VehicleSegment) -> float:
    """Share of braking energy recovered: traction machines above 10 kW
    recover most of it, small hub motors with limited regeneration less."""
    return 0.62 if seg.motor_peak_power > 10e3 else 0.35


def specific_consumption(seg: VehicleSegment, temperature_c,
                         mean_speed_kmh: float, powertrain_efficiency: float,
                         battery_efficiency: float = 0.97,
                         stop_density: float = 2.2,
                         wheel_wh_km: float | None = None) -> float:
    """Battery-terminal energy use [Wh/km].

    ``wheel_wh_km`` is the net wheel energy over the segment's drive cycle
    (``powerelectronics.cycle_wheel_energy``); without it the mean-speed
    road-load estimate is used.  The auxiliary load is spread over the time on
    the road at the archetype's operating speed.
    """
    wheel = (road_load_energy(seg, mean_speed_kmh, stop_density)
             if wheel_wh_km is None else float(wheel_wh_km))
    aux = auxiliary_energy(seg, temperature_c, mean_speed_kmh)
    return (wheel / (seg.drivetrain_efficiency * seg.motor_efficiency
                     * powertrain_efficiency) + aux) / battery_efficiency


def fleet_specific_consumption(shares: dict[str, float], temperature_c: float,
                               mean_speed_kmh: dict[str, float],
                               powertrain_efficiency: float) -> dict[str, float]:
    """Per-segment specific consumption [Wh/km] for the whole fleet."""
    return {k: specific_consumption(VEHICLE_LIBRARY[k], temperature_c,
                                    mean_speed_kmh.get(k, 28.0), powertrain_efficiency)
            for k in shares}


# ---------------------------------------------------------------------------
# Adoption dynamics
# ---------------------------------------------------------------------------
def bass_continuation(t: np.ndarray, p: float, q: float, f0: float) -> np.ndarray:
    r"""Exact solution of the Bass equation :math:`\dot f=(p+qf)(1-f)` from
    :math:`f(0)=f_0`, as a fraction of the market potential.

    With :math:`A=(1-f_0)/(1+(q/p)f_0)`,
    :math:`f(t)=(1-Ae^{-(p+q)t})/(1+(q/p)Ae^{-(p+q)t})`, which continues a
    diffusion already under way instead of restarting it at the base year.
    """
    p = max(p, 1e-9)
    f0 = float(np.clip(f0, 0.0, 0.999999))
    a = (1.0 - f0) / (1.0 + (q / p) * f0)
    e = a * np.exp(-(p + q) * np.asarray(t, dtype=float))
    return (1.0 - e) / (1.0 + (q / p) * e)


def bass_diffusion(years: np.ndarray, p: float, q: float, m: float,
                   n0: float = 0.0) -> np.ndarray:
    """Share of the stock adopted, continuing from ``n0`` in ``years[0]``.

    The first submission offset a curve that started from zero adoption in the
    base year, which restarts diffusion and understates growth in a market that
    is already mid-transition; the exact continuation is used instead, so that
    coefficients fitted to historical data carry over unchanged.
    """
    t = years - years[0]
    if m <= n0:
        return np.full(t.shape, float(n0))
    return np.clip(m * bass_continuation(t, p, q, n0 / m), 0.0, m)


#: Exponents of the policy multipliers in the base formulation of Eq. (8).
PARITY_EXP_P, PARITY_EXP_Q, ADEQUACY_EXP_Q = 0.70, 0.45, 0.60
ADOPTION_FORMS = ("bass", "potential")


def adoption_trajectory(years: np.ndarray, base_share: float,
                        market_potential: float, innovation: float,
                        imitation: float, price_parity: float,
                        charger_adequacy: float, awareness: float,
                        supply_constraint: float = 1.0, elasticity: float = 1.0,
                        form: str = "bass", parity_ref: float = 1.0,
                        adequacy_ref: float = 1.0,
                        awareness_ref: float | None = None) -> np.ndarray:
    """EV share of the vehicle stock over ``years``.

    The Bass coefficients are scaled by three policy-sensitive multipliers:

    ``price_parity``      total-cost-of-ownership advantage relative to the
                          incumbent (1.0 means parity);
    ``charger_adequacy``  public charging provision relative to the level at
                          which range anxiety stops binding;
    ``awareness``         effect of information, procurement and demonstration
                          programmes on the innovation coefficient.

    ``supply_constraint`` caps the attainable share where domestic assembly,
    import quotas or foreign-exchange availability bind.

    ``elasticity`` scales all three exponents (structural sensitivity), and
    ``form="potential"`` is the alternative structure in which policy acts on
    the market ceiling rather than on the diffusion speed: p and q keep their
    calibrated values and the ceiling scales with parity and adequacy.

    ``parity_ref``, ``adequacy_ref`` and ``awareness_ref`` are the conditions of
    the reference package in the base year.  The multipliers are normalised to
    them, so ``innovation`` and ``imitation`` are the effective coefficients
    fitted to historical data and are reproduced exactly when nothing changes.
    """
    price_gain = float(np.clip(price_parity, 0.45, 2.2)) / max(parity_ref, 1e-6)
    charge_gain = float(np.clip(charger_adequacy, 0.10, 1.8)) / max(adequacy_ref, 1e-6)
    aw = 0.35 + 0.65 * awareness
    if awareness_ref is not None:
        aw /= 0.35 + 0.65 * awareness_ref
    e = float(elasticity)
    if form == "potential":
        m_eff = float(np.clip(market_potential * supply_constraint
                              * min(price_gain, 1.6) ** (0.8 * e)
                              * min(charge_gain, 1.6) ** (0.3 * e), base_share, 1.0))
        return bass_diffusion(years, innovation * aw, imitation, m_eff, base_share)
    p_eff = innovation * aw * price_gain ** (PARITY_EXP_P * e)
    q_eff = (imitation * charge_gain ** (ADEQUACY_EXP_Q * e)
             * price_gain ** (PARITY_EXP_Q * e))
    m_eff = float(np.clip(market_potential * supply_constraint, base_share, 1.0))
    return bass_diffusion(years, p_eff, q_eff, m_eff, base_share)


# ---------------------------------------------------------------------------
# Adoption in sales-share space (revision 2)
# ---------------------------------------------------------------------------
# The first revision applied the Bass equation to the electric share of the
# stock and recomputed the whole path from the base year each year with that
# year's conditions.  A policy then acted retroactively, and the stock could
# jump faster than fleet turnover allows.  Adoption is now stepped forward one
# year at a time in the space where buyers decide: the electric share of new
# registrations.  The stock follows from turnover, so it can never outrun it.
#
#   F(t+1) = Bass step of F(t) with p = p^ a,  q = q^ k^(0.6 e)      (diffusion)
#   s(t)   = min(1, m0 (pi/pi_ref)^(beta e) F(t))                      (sales share)
#   x(t)   = [x(t-1)(1 - 1/L) + s(t)(g + 1/L)] / (1 + g)              (stock share)
#
# F is the share of new-vehicle buyers who know, can obtain and would consider
# an electric vehicle; it diffuses at the fitted rates, sped up or slowed by
# charging provision (k) and awareness (a) relative to the reference package.
# The ownership-cost ratio pi relative to the reference package in the same
# year scales the ceiling of the sales share (a price-dependent market
# potential, Kalish 1985), so a subsidy raises sales at once and its removal
# lowers them, as observed in Germany in 2024.  beta is estimated from the
# German purchase-premium history (calibrate.py).

def bass_step(f: float, p: float, q: float, dt: float = 1.0) -> float:
    """One exact Bass step of the adopted fraction ``f`` over ``dt`` years."""
    return float(bass_continuation(np.array([dt]), p, q, f)[0])


def turnover_step(x: float, sales_share: float, lifetime_y: float, growth: float) -> float:
    """Electric share of the stock after a year in which ``sales_share`` of new
    registrations were electric (vintage-free turnover)."""
    r = 1.0 / max(lifetime_y, 1.0)
    return float((x * (1.0 - r) + float(np.clip(sales_share, 0.0, 1.0)) * (growth + r))
                 / (1.0 + growth))


def adoption_multipliers(parity: float, adequacy: float, awareness: float,
                         ref: dict, beta: float, elasticity: float = 1.0,
                         form: str = "ceiling") -> tuple[float, float, float]:
    """Multipliers on (p, q, ceiling) relative to the reference package.

    ``form="ceiling"`` (base): the ownership-cost ratio scales the ceiling of
    the sales share.  ``form="hazard"`` (alternative structure): the same
    elasticity acts on the diffusion coefficients instead, so price changes
    speed diffusion up or slow it down but never lower sales at once
    (generalised Bass model, Bass et al. 1994).
    """
    price_gain = float(np.clip(parity, 0.30, 2.5)) / max(float(ref["parity"]), 1e-6)
    charge_gain = (charging_availability(adequacy)
                   / max(charging_availability(ref["adequacy"]), 1e-6))
    aw = 0.35 + 0.65 * float(awareness)
    if ref.get("awareness") is not None:
        aw /= 0.35 + 0.65 * float(ref["awareness"])
    e = float(elasticity)
    level = price_gain ** (float(beta) * e) * charge_gain ** (ADEQUACY_EXP_Q * e)
    if form == "hazard":
        return aw ** e * level, level, 1.0
    return aw ** e, 1.0, level


#: Adequacy at which the effect of public charging is half saturated
#: (0.5, i.e. 14 public connectors per thousand electric vehicles; assumed).
ADEQUACY_HALF = 0.5


def charging_availability(adequacy: float) -> float:
    """Saturating effect of public charging provision on the sales ceiling.

    Ratios of raw provision would grow without bound where the reference is
    near zero (Bangladesh starts at about 3 connectors per thousand EVs); the
    effect of more connectors per vehicle saturates instead.  With exponent
    0.6 the implied elasticity of sales to provision is about 0.5 at low
    provision, below the 0.8 estimated for the early US market (Li et al.).
    """
    k = float(np.clip(adequacy, 0.05, 1.8))
    return k / (k + ADEQUACY_HALF)


def initial_sales_share(stock_share: float, q: float, lifetime_y: float,
                        growth: float) -> float:
    """Base-year sales share consistent with a stock share in early, roughly
    exponential diffusion at rate ``q`` (used where no sales series exists)."""
    r = 1.0 / max(lifetime_y, 1.0)
    return float(min(stock_share * (q + growth + r) / (growth + r), 1.0))


def turnover_cap(path: np.ndarray, lifetime_y: float, growth: float) -> np.ndarray:
    """Limit a stock-share path to what fleet turnover permits.

    If every vehicle registered were electric, the share would evolve as
    ``x(t+1) = [x(t)(1 - 1/L) + (g + 1/L)] / (1 + g)``; a diffusion path can
    never exceed that, whatever the policy.
    """
    out = np.array(path, dtype=float)
    r = 1.0 / max(lifetime_y, 1.0)
    for t in range(1, out.size):
        cap = (out[t - 1] * (1.0 - r) + (growth + r)) / (1.0 + growth)
        out[t] = min(out[t], cap)
    return out


def stock_rollover(total_stock: np.ndarray, ev_share: np.ndarray,
                   segment_shares: dict[str, float]) -> dict[str, np.ndarray]:
    """Electric vehicle stock by segment over the horizon."""
    ev_stock = total_stock * ev_share
    return {k: ev_stock * s for k, s in segment_shares.items()}


def retirements(stock_by_year: np.ndarray, mean_life: float = 12.0) -> np.ndarray:
    """Vehicles reaching end of life each year, from a survival-weighted stock."""
    out = np.zeros_like(stock_by_year)
    additions = np.diff(np.concatenate(([0.0], stock_by_year)))
    for i, add in enumerate(additions):
        eol = int(round(i + mean_life))
        if 0 <= eol < out.size:
            out[eol] += max(add, 0.0)
    return out


# ---------------------------------------------------------------------------
# Charging demand shapes
# ---------------------------------------------------------------------------
def _normalise(x: np.ndarray) -> np.ndarray:
    s = x.sum()
    return x / s if s > 1e-12 else np.full_like(x, 1.0 / x.size)


def arrival_shape(segment: str, urban: bool = True) -> np.ndarray:
    """Normalised 24-hour distribution of charging-session start times.

    Shapes reflect the duty of each segment: commuter cars plug in on return
    home, commercial fleets charge overnight at depots, and paratransit
    three-wheelers top up between shifts during the day.
    """
    h = np.arange(24, dtype=float)
    if segment == "passenger_car":
        x = (0.55 * np.exp(-0.5 * ((h - 18.5) / 2.1) ** 2)
             + 0.20 * np.exp(-0.5 * ((h - 8.5) / 1.6) ** 2)
             + 0.12 * np.exp(-0.5 * ((h - 12.5) / 2.4) ** 2) + 0.03)
    elif segment == "two_wheeler":
        x = (0.40 * np.exp(-0.5 * ((h - 20.0) / 2.6) ** 2)
             + 0.30 * np.exp(-0.5 * ((h - 13.0) / 3.0) ** 2) + 0.05)
    elif segment == "three_wheeler":
        x = (0.34 * np.exp(-0.5 * ((h - 13.0) / 2.6) ** 2)
             + 0.30 * np.exp(-0.5 * ((h - 22.5) / 2.8) ** 2)
             + 0.20 * np.exp(-0.5 * ((h - 3.0) / 2.4) ** 2) + 0.05)
    elif segment == "light_commercial":
        x = (0.50 * np.exp(-0.5 * ((h - 21.0) / 2.4) ** 2)
             + 0.18 * np.exp(-0.5 * ((h - 12.0) / 2.0) ** 2) + 0.05)
    else:  # bus
        x = (0.62 * np.exp(-0.5 * ((h - 1.5) / 2.6) ** 2)
             + 0.18 * np.exp(-0.5 * ((h - 13.0) / 1.8) ** 2) + 0.04)
    if not urban:
        x = 0.75 * x + 0.25 * np.roll(x, 1)
    return _normalise(x)


def uncontrolled_profile(daily_energy_kwh: float, segment: str,
                         urban: bool = True) -> np.ndarray:
    """Hourly charging energy [kWh] under plug-in-on-arrival behaviour."""
    return daily_energy_kwh * arrival_shape(segment, urban)


def smart_profile(daily_energy_kwh: float, segment: str, price: np.ndarray,
                  flexibility: float, urban: bool = True) -> np.ndarray:
    """Hourly charging energy [kWh] with price-responsive smart charging.

    A fraction ``flexibility`` of the daily energy is reallocated in proportion
    to the inverse of the hourly price within the vehicle's connected window;
    the inflexible remainder keeps the uncontrolled shape.
    """
    base = uncontrolled_profile(daily_energy_kwh, segment, urban)
    if flexibility <= 0.0:
        return base
    connected = (arrival_shape(segment, urban) > 0.01).astype(float)
    connected = np.maximum(connected, 0.15)
    weight = _normalise(connected / np.maximum(price, 1e-6) ** 1.8)
    return (1.0 - flexibility) * base + flexibility * daily_energy_kwh * weight


def v2g_dispatch(connected_kwh: float, price: np.ndarray, net_load: np.ndarray,
                 participation: float, max_discharge_frac: float = 0.20,
                 efficiency: float = 0.90) -> np.ndarray:
    """Hourly vehicle-to-grid export [kWh] (positive = discharge to the grid).

    Export is concentrated in the highest net-load hours, subject to a cap on
    the fraction of connected energy that may be discharged per day.
    """
    if participation <= 0.0:
        return np.zeros(24)
    score = _normalise(np.clip(net_load - np.median(net_load), 0.0, None)
                       * np.clip(price / np.maximum(price.mean(), 1e-9), 0.2, 3.0))
    budget = connected_kwh * participation * max_discharge_frac
    return budget * score * efficiency
