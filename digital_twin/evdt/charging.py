"""Charging-infrastructure layer: portfolio sizing, queueing and utilisation.

Public charging is represented as a set of service systems, one per charger
class, each analysed with the Erlang-C (M/M/c) formula to obtain the
probability of queueing and the expected waiting time (docs_reference:
chg-wait-longtrip, chg-queue-firefly, chg-siting-uncert).  The energy delivered
by each class is limited by the power-electronic conversion efficiency of that
class, which links this layer to :mod:`evdt.powerelectronics`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import gammaincc, gammaln

from .config import CHARGER_LIBRARY, ChargerClass


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------
def erlang_b(servers: int, offered_load: float) -> float:
    r"""Erlang-B blocking probability, evaluated in closed form.

    Using :math:`\sum_{k=0}^{c} a^k/k! = e^{a}\,Q(c+1, a)` with :math:`Q` the
    regularised upper incomplete gamma function,

    .. math:: \log B = c\log a - \log \Gamma(c+1) - a - \log Q(c+1, a),

    which is O(1) rather than O(c). The recursive form is retained for very
    small server counts, where it is both exact and cheap, and because the
    gamma-function route loses accuracy as ``a`` approaches zero.
    """
    c = max(int(servers), 1)
    a = max(float(offered_load), 0.0)
    if a <= 1e-12:
        return 0.0
    if c <= 256:
        inv_b = 1.0
        for i in range(1, c + 1):
            inv_b = 1.0 + inv_b * i / a
        return float(1.0 / inv_b)
    q = float(gammaincc(c + 1.0, a))
    if q <= 0.0:
        return 0.0
    log_b = c * math.log(a) - gammaln(c + 1.0) - a - math.log(q)
    return float(np.clip(math.exp(min(log_b, 0.0)), 0.0, 1.0))


def erlang_c(servers: int, offered_load: float) -> float:
    """Probability that an arriving session has to wait (Erlang-C)."""
    c = max(int(servers), 1)
    a = max(float(offered_load), 0.0)
    if a >= c:
        return 1.0
    b = erlang_b(c, a)
    rho = a / c
    denom = 1.0 - rho * (1.0 - b)
    return float(np.clip(b / max(denom, 1e-12), 0.0, 1.0))


#: Waiting beyond this point is not experienced as a queue but as rationing:
#: drivers abandon the session, defer the trip or fall back to another fuel.
#: Capping the statistic keeps saturated cases comparable and prevents an
#: unbounded queueing term from dominating the welfare accounting.
MAX_WAIT_HOURS = 2.0


def waiting_time(servers: int, arrival_rate: float, service_time_h: float
                 ) -> tuple[float, float]:
    """Expected waiting time in queue [h] and the saturation index.

    The saturation index is ``rho = a / c``; values above one mean the offered
    load exceeds the service capacity, in which case the reported waiting time
    is capped at :data:`MAX_WAIT_HOURS` and the excess demand is interpreted as
    rationed rather than queued.
    """
    c = max(int(servers), 1)
    a = arrival_rate * service_time_h
    rho = a / c
    if rho >= 0.995:
        return MAX_WAIT_HOURS, float(rho)
    pw = erlang_c(c, a)
    w = pw * service_time_h / max(c - a, 1e-6)
    return float(min(w, MAX_WAIT_HOURS)), float(rho)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------
@dataclass
class ChargingPortfolio:
    """Installed connectors by class and the resulting service performance."""
    connectors: dict[str, float]
    energy_share: dict[str, float]

    def total_connectors(self) -> float:
        return float(sum(self.connectors.values()))

    def installed_power_mw(self) -> float:
        return float(sum(n * CHARGER_LIBRARY[k].rated_power
                         for k, n in self.connectors.items()) / 1e6)


def design_portfolio(ev_stock: float, connectors_per_1000: float,
                     dc_fraction: float, ultrafast_fraction: float,
                     home_access: float) -> ChargingPortfolio:
    """Size the public charging portfolio for a given fleet.

    ``home_access`` is the share of vehicles with reliable private overnight
    charging; where it is low (dense cities, informal settlements, weak grids)
    the public network must carry a much larger share of the energy, which is
    the mechanism behind the queueing results reported in the study.
    """
    public = max(ev_stock, 0.0) * connectors_per_1000 / 1000.0
    dc_conn = public * float(np.clip(dc_fraction, 0.0, 1.0))
    ac_conn = public - dc_conn
    ultra = dc_conn * float(np.clip(ultrafast_fraction, 0.0, 1.0))
    rapid = (dc_conn - ultra) * 0.55
    dc50 = dc_conn - ultra - rapid
    connectors = {
        "ac_slow": ac_conn * 0.62,
        "ac_fast": ac_conn * 0.38,
        "dc_50": max(dc50, 0.0),
        "dc_150": max(rapid, 0.0),
        "dc_350": max(ultra, 0.0),
    }
    # Energy split: private charging first, remainder allocated by installed power
    public_energy = float(np.clip(1.0 - home_access, 0.05, 0.98))
    power = {k: connectors[k] * CHARGER_LIBRARY[k].rated_power for k in connectors}
    tot = sum(power.values())
    share = {k: (public_energy * power[k] / tot if tot > 1e-9 else 0.0) for k in power}
    share["private"] = 1.0 - public_energy
    return ChargingPortfolio(connectors, share)


#: Site-to-site dispersion of demand.  Arrivals at individual sites are
#: lognormal around the class mean with this log-standard deviation, which
#: represents the concentration of demand at busy locations; the quantiles
#: below discretise that distribution.
SITE_DISPERSION = 0.6
_SITE_Q = (np.arange(20) + 0.5) / 20.0


def _site_multipliers(sigma: float) -> np.ndarray:
    from scipy.stats import norm
    z = norm.ppf(_SITE_Q)
    m = np.exp(sigma * z)
    return m / m.mean()


def site_level_wait(n_connectors: float, connectors_per_site: int,
                    peak_arrivals: float, service_h: float,
                    dispersion: float = SITE_DISPERSION) -> tuple[float, float, float]:
    """Arrival-weighted waiting time [h], saturation and rationed share when
    demand is served by many small sites rather than one national pool.

    Each site is an M/M/c queue with c equal to its connector count; the site
    arrival rate is the class mean scaled by the lognormal multipliers.  Busy
    sites saturate while quiet ones idle, which is the local bottleneck a single
    pooled queue cannot represent.
    """
    sites = max(n_connectors / max(connectors_per_site, 1), 1.0)
    lam = peak_arrivals / sites * _site_multipliers(dispersion)
    waits, rhos = [], []
    for li in lam:
        w, r = waiting_time(connectors_per_site, float(li), service_h)
        waits.append(w)
        rhos.append(r)
    waits, rhos = np.array(waits), np.array(rhos)
    wgt = lam / max(lam.sum(), 1e-12)
    rationed = float(np.sum(wgt * np.clip(rhos - 1.0, 0.0, None)
                            / np.maximum(rhos, 1e-9)))
    return float(np.sum(wgt * waits)), float(np.sum(wgt * rhos)), rationed


def service_performance(portfolio: ChargingPortfolio, annual_energy_kwh: float,
                        path_efficiency: dict[str, float],
                        peak_concentration: float = 0.085,
                        mean_session_kwh: dict[str, float] | None = None,
                        queue_mode: str = "site") -> dict[str, float]:
    """Waiting time, utilisation and delivered energy by charger class.

    ``peak_concentration`` is the share of daily public-charging sessions that
    fall in the busiest hour; it is the parameter that smart charging and
    time-of-use tariffs act on.  ``queue_mode`` is ``"site"`` (one M/M/c queue
    per site, with dispersed demand) or ``"pooled"`` (one national M/M/c queue
    per class, the formulation of the first submission, kept for comparison).
    """
    if mean_session_kwh is None:
        mean_session_kwh = {"ac_slow": 7.5, "ac_fast": 14.0, "dc_50": 22.0,
                            "dc_150": 32.0, "dc_350": 46.0}
    out: dict[str, float] = {}
    weighted_wait = weighted_util = weighted_eff = share_sum = 0.0
    weighted_rho = rationed = 0.0
    sessions_dc = 0.0
    for key, cls in CHARGER_LIBRARY.items():
        n = portfolio.connectors.get(key, 0.0)
        share = portfolio.energy_share.get(key, 0.0)
        out[f"wait_{key}_min"] = 0.0
        out[f"util_{key}"] = 0.0
        if share <= 0.0:
            continue
        eff = path_efficiency.get("ac" if cls.coupling == "ac" else "dc", 0.95)
        e_class = annual_energy_kwh * share / max(eff, 1e-6)
        sessions_per_year = e_class / max(mean_session_kwh[key], 1e-6)
        if cls.coupling == "dc":
            sessions_dc += sessions_per_year
        peak_arrivals = sessions_per_year / 365.0 * peak_concentration     # per hour
        service_h = mean_session_kwh[key] / (cls.rated_power / 1e3) / max(eff, 1e-6)
        if queue_mode == "site":
            wait_h, rho, rat = site_level_wait(n, cls.connectors, peak_arrivals,
                                               service_h)
        else:
            wait_h, rho = waiting_time(int(max(round(n), 1)), peak_arrivals, service_h)
            rat = max(rho - 1.0, 0.0) / max(rho, 1e-9)
        util = e_class / max(n * cls.rated_power / 1e3 * 8760.0, 1e-9)
        out[f"wait_{key}_min"] = wait_h * 60.0
        out[f"util_{key}"] = float(np.clip(util, 0.0, 1.0))
        weighted_wait += share * wait_h * 60.0
        weighted_util += share * float(np.clip(util, 0.0, 1.0))
        weighted_eff += share * eff
        weighted_rho += share * rho
        rationed += share * rat
        share_sum += share
    n_dc = sum(portfolio.connectors.get(k, 0.0) for k, c in CHARGER_LIBRARY.items()
               if c.coupling == "dc")
    out["sessions_per_dc_connector"] = sessions_dc / max(n_dc, 1.0)
    out["wait_mean_min"] = weighted_wait / max(share_sum, 1e-9)
    out["utilisation_mean"] = weighted_util / max(share_sum, 1e-9)
    out["path_efficiency_mean"] = weighted_eff / max(share_sum, 1e-9)
    out["saturation_index"] = weighted_rho / max(share_sum, 1e-9)
    out["rationed_fraction"] = float(np.clip(rationed / max(share_sum, 1e-9), 0.0, 1.0))
    return out


def portfolio_capex(portfolio: ChargingPortfolio, cost_premium: float = 1.0,
                    import_duty: float = 0.0,
                    local_manufacturing: float = 0.0) -> dict[str, float]:
    """Capital and annual operating cost of the charging portfolio [USD]."""
    capex = opex = 0.0
    for key, cls in CHARGER_LIBRARY.items():
        n = portfolio.connectors.get(key, 0.0)
        sites = n / max(cls.connectors, 1)
        hardware = sites * cls.capex_per_site * cost_premium
        hardware *= 1.0 + import_duty * (1.0 - local_manufacturing)
        civil = sites * cls.site_civil_cost * cost_premium
        capex += hardware + civil
        opex += (hardware + civil) * cls.opex_fraction
    return {"capex_usd": capex, "opex_usd_per_year": opex}


def harmonic_injection(portfolio: ChargingPortfolio,
                       wbg_share: float = 0.0) -> float:
    """Aggregate current-distortion factor of the charging fleet [pu].

    Active front ends with wide-bandgap devices switch faster and can be
    controlled to a lower current distortion; diversity between sites reduces
    the aggregate further than the arithmetic mean of individual units
    (docs_reference: pe-anpc-pq, grid-harmonic-std, pe-emi-conducted).
    """
    num = den = 0.0
    for key, cls in CHARGER_LIBRARY.items():
        n = portfolio.connectors.get(key, 0.0)
        p = n * cls.rated_power
        num += p * cls.harmonic_current_pu
        den += p
    base = num / max(den, 1e-9)
    wbg_gain = 1.0 - 0.28 * float(np.clip(wbg_share, 0.0, 1.0))
    diversity = 0.78
    return float(base * wbg_gain * diversity)


def reliability_of_service(portfolio: ChargingPortfolio, grid_availability: float,
                           converter_failure_rate: float,
                           maintenance_quality: float = 0.6) -> float:
    """Probability that a randomly chosen connector is available and working.

    Combines grid supply availability, converter failure and the mean time to
    repair implied by the maintenance capability of the archetype.
    """
    mttr_days = 21.0 * (1.0 - 0.75 * float(np.clip(maintenance_quality, 0.0, 1.0))) + 2.0
    downtime = converter_failure_rate * mttr_days / 365.0
    return float(np.clip(grid_availability * (1.0 - downtime), 0.0, 1.0))
