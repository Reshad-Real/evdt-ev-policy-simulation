"""Indicator definitions, normalisation and composite scoring.

The twin reports twenty-four primary indicators spanning energy, power quality,
service, technology, environment and economics.  Because these are measured in
incompatible units and have opposite preference directions, policy ranking uses
the Technique for Order of Preference by Similarity to Ideal Solution (TOPSIS),
which is the multi-criteria method most widely applied to energy-policy
comparison (docs_reference: econ-topsis-power, econ-moo-mcdm).

Three composite scores are derived: an overall policy score, a sustainability
score restricted to environmental and resource criteria, and a technology
readiness score obtained from the readiness levels of the technologies each
policy actually deploys (docs_reference: wf-trl-ccs, wf-trl-system).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import DEVICE_LIBRARY


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    unit: str
    group: str
    benefit: bool          # True if larger is better
    weight: float


#: Indicators are expressed as *intensities* wherever the underlying quantity
#: scales with fleet size.  Ranking on absolute energy, losses or peak demand
#: would reward doing nothing, because a policy that succeeds in electrifying
#: transport necessarily increases all three; what policy can legitimately be
#: judged on is how much energy, loss and peak it incurs per unit of mobility
#: delivered.
#: Every indicator is an outcome: the wide-bandgap share, which is an input that
#: the technology packages set directly, charger utilisation, whose preference
#: direction is ambiguous, and the converter failure rate, which rested on an
#: extrapolated power-cycling law, were removed in the revision.  Horizon
#: means are used for efficiencies and losses, 2040 values for the network and
#: service state a package leaves behind, and the abatement indicator is the
#: cumulative reduction additional to the reference package of the archetype.
INDICATORS: tuple[Indicator, ...] = (
    # --- energy -----------------------------------------------------------
    Indicator("fleet_energy_per_km_wh", "Fleet specific energy use", "Wh/km", "energy", False, 0.045),
    Indicator("mean_conversion_loss_ratio", "Power-conversion loss ratio", "-", "energy", False, 0.055),
    Indicator("mean_loss_fraction", "Network loss fraction", "-", "energy", False, 0.050),
    Indicator("load_factor", "System load factor", "-", "energy", True, 0.045),
    # --- power electronics -------------------------------------------------
    Indicator("mean_eta_traction", "Traction-chain efficiency", "-", "power_electronics", True, 0.060),
    Indicator("mean_eta_charging", "Charging-path efficiency", "-", "power_electronics", True, 0.060),
    # --- service -----------------------------------------------------------
    Indicator("final_wait_min", "Mean charging waiting time", "min", "service", False, 0.055),
    Indicator("final_charger_availability", "Charging service availability", "-", "service", True, 0.040),
    # --- network quality ---------------------------------------------------
    Indicator("voltage_deviation_pu", "Mean voltage deviation", "pu", "network", False, 0.040),
    Indicator("final_transformer_loading", "Peak transformer loading", "pu", "network", False, 0.045),
    Indicator("line_loading_pu", "95th-percentile line loading", "pu", "network", False, 0.030),
    Indicator("thd_v", "Voltage total harmonic distortion", "-", "network", False, 0.035),
    Indicator("final_reliability", "Supply reliability", "-", "network", True, 0.050),
    Indicator("resilience_index", "Network resilience", "-", "network", True, 0.030),
    # --- sustainability ----------------------------------------------------
    Indicator("delta_emissions_mt", "Additional CO2 avoided vs. reference", "Mt", "environment", True, 0.070),
    Indicator("emissions_intensity_g_km", "Charging emission intensity", "g/km", "environment", False, 0.045),
    Indicator("mean_renewable_utilisation", "Renewable share of charging", "-", "environment", True, 0.045),
    Indicator("battery_fade_pct", "Battery capacity fade", "%", "environment", False, 0.030),
    # --- economics ---------------------------------------------------------
    Indicator("incremental_bcr", "Incremental benefit-cost ratio", "-", "economic", True, 0.065),
    Indicator("payback_years", "Discounted payback period", "yr", "economic", False, 0.050),
    Indicator("abatement_cost_usd_t", "Marginal abatement cost", "USD/t", "economic", False, 0.045),
)

#: A marginal abatement cost is reported only when the additional abatement is
#: large enough for the ratio to be well conditioned.
MAC_MIN_MT = 0.5
MAC_MIN_REL = 0.02

INDICATOR_KEYS = tuple(i.key for i in INDICATORS)

SUSTAINABILITY_KEYS = ("cumulative_emissions_saved_mt", "renewable_utilisation",
                       "battery_fade_pct", "conversion_loss_ratio", "loss_fraction",
                       "recycled_content", "eta_traction")


# ---------------------------------------------------------------------------
# Normalisation and TOPSIS
# ---------------------------------------------------------------------------
def normalise(matrix: np.ndarray, benefit: np.ndarray) -> np.ndarray:
    """Min-max normalisation with the preference direction applied.

    An indicator that does not vary across the alternatives carries no
    discriminating information, so it is mapped to the neutral value 0.5 rather
    than collapsing to one end of the scale, which would misrepresent every
    alternative as either best or worst on that criterion.
    """
    x = np.asarray(matrix, dtype=float).copy()
    x[~np.isfinite(x)] = np.nanmax(x[np.isfinite(x)]) if np.any(np.isfinite(x)) else 0.0
    lo = x.min(axis=0)
    hi = x.max(axis=0)
    degenerate = (hi - lo) < 1e-12
    span = np.where(degenerate, 1.0, hi - lo)
    z = (x - lo) / span
    z = np.where(benefit[None, :], z, 1.0 - z)
    return np.where(degenerate[None, :], 0.5, z)


def topsis(matrix: np.ndarray, weights: np.ndarray,
           benefit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """TOPSIS closeness coefficient and rank for each alternative.

    Columns are vector-normalised (each divided by its Euclidean norm), then
    weighted.  An undefined entry (a marginal abatement cost withheld because
    the abatement is too small) is given the worst finite value of its column.
    """
    x = np.asarray(matrix, dtype=float).copy()
    finite = np.isfinite(x)
    if not finite.all():
        fx = np.where(finite, x, np.nan)
        worst = np.where(benefit, np.nanmin(fx, axis=0), np.nanmax(fx, axis=0))
        worst = np.where(np.isfinite(worst), worst, 0.0)
        x = np.where(finite, x, worst[None, :])
    norm = np.sqrt(np.sum(x ** 2, axis=0))
    norm = np.where(norm < 1e-12, 1.0, norm)
    v = x / norm * weights[None, :]
    ideal = np.where(benefit, v.max(axis=0), v.min(axis=0))
    anti = np.where(benefit, v.min(axis=0), v.max(axis=0))
    d_plus = np.sqrt(np.sum((v - ideal[None, :]) ** 2, axis=1))
    d_minus = np.sqrt(np.sum((v - anti[None, :]) ** 2, axis=1))
    cc = d_minus / np.maximum(d_plus + d_minus, 1e-12)
    order = np.argsort(-cc)
    rank = np.empty_like(order)
    rank[order] = np.arange(1, cc.size + 1)
    return cc, rank


def build_matrix(rows: list[dict], keys: tuple[str, ...] = INDICATOR_KEYS
                 ) -> np.ndarray:
    """Assemble the decision matrix from a list of scenario result dictionaries."""
    return np.array([[float(r.get(k, np.nan)) for k in keys] for r in rows], dtype=float)


def base_weights() -> np.ndarray:
    w = np.array([i.weight for i in INDICATORS], dtype=float)
    return w / w.sum()


def policy_score(rows: list[dict], weights: np.ndarray | None = None
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Overall policy score (0-1) and rank across a set of scenarios.

    Scores are relative to the alternatives compared: they rank packages within
    one archetype and are not comparable between archetypes.
    """
    m = build_matrix(rows)
    w = base_weights() if weights is None else np.asarray(weights, float) / np.sum(weights)
    b = np.array([i.benefit for i in INDICATORS], dtype=bool)
    return topsis(m, w, b)


def weight_sensitivity(rows: list[dict], n: int = 5000, seed: int = 31
                       ) -> dict[str, object]:
    """Rank stability of the TOPSIS ordering under alternative weightings.

    Three families are evaluated: equal weights; equal weight per indicator
    group; and ``n`` random weight vectors drawn uniformly from the simplex
    (Dirichlet with unit concentration), which explores every weighting a
    decision maker might hold.  Returns, for each alternative, the share of
    random weightings in which it ranks first, and the mean Kendall rank
    correlation with the base ranking.
    """
    from scipy.stats import kendalltau
    m = build_matrix(rows)
    b = np.array([i.benefit for i in INDICATORS], dtype=bool)
    keys = [r["policy"] for r in rows]
    _, base_rank = topsis(m, base_weights(), b)
    out: dict[str, object] = {"keys": keys, "base_rank": base_rank.tolist()}
    k = len(INDICATORS)
    _, r_eq = topsis(m, np.full(k, 1.0 / k), b)
    groups = [i.group for i in INDICATORS]
    ng = len(set(groups))
    w_g = np.array([1.0 / ng / groups.count(g) for g in groups])
    _, r_gr = topsis(m, w_g, b)
    out["equal_rank"] = r_eq.tolist()
    out["group_rank"] = r_gr.tolist()
    rng = np.random.default_rng(seed)
    first = np.zeros(len(rows))
    taus = []
    ranks = np.zeros((n, len(rows)), dtype=int)
    for j in range(n):
        w = rng.dirichlet(np.ones(k))
        _, r = topsis(m, w, b)
        ranks[j] = r
        first[np.argmin(r)] += 1
        taus.append(kendalltau(base_rank, r).statistic)
    out["p_first"] = (first / n).tolist()
    out["mean_rank"] = ranks.mean(axis=0).tolist()
    out["kendall_tau_mean"] = float(np.nanmean(taus))
    out["kendall_tau_p05"] = float(np.nanpercentile(taus, 5))
    return out


def sustainability_score(rows: list[dict]) -> np.ndarray:
    """Composite sustainability score (0-1) on environmental criteria only."""
    keys = SUSTAINABILITY_KEYS
    benefit = np.array([k in ("cumulative_emissions_saved_mt", "renewable_utilisation",
                              "recycled_content", "eta_traction") for k in keys])
    m = build_matrix(rows, keys)
    z = normalise(m, benefit)
    w = np.array([0.30, 0.20, 0.12, 0.12, 0.10, 0.10, 0.06])
    return z @ (w / w.sum())


def technology_readiness(row: dict) -> float:
    """Fleet-weighted technology readiness level of the deployed technology mix.

    Semiconductor readiness is taken from the device library; the readiness of
    the system-level technologies each policy deploys (smart charging,
    vehicle-to-grid, digital twin, solid-state transformation at ultra-fast
    sites) is combined with it in proportion to their deployment intensity.
    """
    sic = row.get("sic_share", 0.0)
    gan = row.get("gan_share", 0.0)
    si = max(1.0 - sic - gan, 0.0)
    device_trl = (sic * DEVICE_LIBRARY["SiC-MOSFET"].trl
                  + gan * DEVICE_LIBRARY["GaN-HEMT"].trl
                  + si * DEVICE_LIBRARY["Si-IGBT"].trl)
    system_terms = [
        (row.get("digital_maturity", 0.0), 7.0),      # national digital twin
        (row.get("v2g_energy_gwh", 0.0) > 0.0, 7.0),  # bidirectional charging
        (row.get("renewable_utilisation", 0.0), 9.0),
        (row.get("recycled_content", 0.0), 6.0),
    ]
    num = device_trl * 2.0
    den = 2.0
    for intensity, trl in system_terms:
        w = float(intensity)
        num += w * trl
        den += w
    return float(np.clip(num / max(den, 1e-9), 1.0, 9.0))


def incremental_assessment(rows: list[dict], baseline: dict) -> list[dict]:
    """Express each scenario relative to the no-policy counterfactual.

    Absolute benefit-cost ratios are ill-posed when the counterfactual itself
    carries large benefits; the policy-relevant quantity is the incremental
    ratio of additional benefit to additional cost.
    """
    out = []
    s0_net = max(abs(baseline["cumulative_emissions_saved_mt"]), 1e-9)
    for r in rows:
        d_cost = r["discounted_cost_musd"] - baseline["discounted_cost_musd"]
        d_ben = r["discounted_benefit_musd"] - baseline["discounted_benefit_musd"]
        rec = dict(r)
        rec["delta_cost_musd"] = d_cost
        rec["delta_benefit_musd"] = d_ben
        rec["incremental_bcr"] = (d_ben / d_cost) if d_cost > 1e-6 else float("nan")
        rec["delta_npv_musd"] = r["npv_musd"] - baseline["npv_musd"]
        rec["delta_emissions_mt"] = (r["cumulative_emissions_saved_mt"]
                                     - baseline["cumulative_emissions_saved_mt"])
        well_posed = (rec["delta_emissions_mt"] >= MAC_MIN_MT
                      and rec["delta_emissions_mt"] >= MAC_MIN_REL * s0_net)
        rec["mac_well_posed"] = bool(well_posed)
        # Net cost per additional tonne: the discounted cost not recovered by the
        # non-carbon benefits, divided by the additional abatement.  Using the
        # gross cost would ignore that fuel and health savings pay for part of it.
        carbon_inc = (r.get("pv_b_carbon_musd", 0.0)
                      - baseline.get("pv_b_carbon_musd", 0.0))
        net_cost = d_cost - (d_ben - carbon_inc)
        rec["abatement_cost_usd_t"] = (net_cost / rec["delta_emissions_mt"]
                                       if well_posed else float("nan"))
        rec["gross_abatement_cost_usd_t"] = (d_cost / rec["delta_emissions_mt"]
                                             if well_posed else float("nan"))
        out.append(rec)
    return out


def summarise_groups(row: dict) -> dict[str, float]:
    """Group-level normalised performance, used for radar charts."""
    groups: dict[str, list[float]] = {}
    for ind in INDICATORS:
        v = float(row.get(ind.key, np.nan))
        if not np.isfinite(v):
            continue
        groups.setdefault(ind.group, []).append(v)
    return {g: float(np.mean(v)) for g, v in groups.items()}
