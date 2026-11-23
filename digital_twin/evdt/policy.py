"""Policy engine.

A policy is expressed as a vector of *levers*.  Each lever has a normalised
intensity in [0, 1] (or a directly interpretable physical value), a phase-in
window, and a public-budget cost coefficient.  ``apply`` maps a resolved lever
vector onto the parameters of the physical models, so that every policy claim
made in the manuscript is traceable to a specific parameter change inside the
digital twin rather than to a narrative assertion.

The lever set spans the six policy domains used throughout the study: fiscal,
infrastructure, technology and standards, grid and system, institutional and
industrial, and digital.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import Archetype

# ---------------------------------------------------------------------------
# Lever catalogue
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Lever:
    key: str
    label: str
    domain: str
    unit: str
    lo: float
    hi: float
    unit_cost: float          # public cost, USD per year per unit of intensity
                              # per million vehicles in the national stock
    description: str
    # A transfer moves money between the state and households (a subsidy or
    # forgone duty) without consuming resources.  It is reported as a fiscal
    # cost but excluded from the social cost-benefit account, where counting it
    # alongside the private saving it finances would count it twice.
    transfer: bool = False


LEVERS: dict[str, Lever] = {
    # -- fiscal ------------------------------------------------------------
    "purchase_incentive": Lever(
        "purchase_incentive", "Purchase incentive", "fiscal", "fraction of price",
        0.0, 0.35, 9.8e7,
        "Direct subsidy or tax credit expressed as a share of the delivered price.",
        transfer=True),
    "duty_relief": Lever(
        "duty_relief", "Import-duty relief on EVs and converters", "fiscal",
        "fraction of duty removed", 0.0, 1.0, 2.6e7,
        "Reduction of tariffs on complete vehicles, packs and power-conversion "
        "assemblies; forgone revenue is charged to the public budget.",
        transfer=True),
    "tou_tariff": Lever(
        "tou_tariff", "Time-of-use retail tariff", "fiscal", "adoption share",
        0.0, 1.0, 5.5e6,
        "Time-differentiated retail pricing with metering roll-out."),
    # -- infrastructure ----------------------------------------------------
    # Note: the hardware cost of the three levers below is accounted physically
    # in the charging-portfolio capital cost, so their budget coefficient covers
    # programme administration, siting and permitting only.
    "charger_rollout": Lever(
        "charger_rollout", "Public charging roll-out", "infrastructure",
        "connectors per 1000 EVs", 2.0, 90.0, 2.0e5,
        "Publicly co-funded connector deployment target."),
    "dc_share": Lever(
        "dc_share", "DC share of public connectors", "infrastructure", "fraction",
        0.02, 0.60, 1.0e5,
        "Share of public connectors that are direct-current fast chargers."),
    "ultrafast_share": Lever(
        "ultrafast_share", "Ultra-fast share of DC connectors", "infrastructure",
        "fraction", 0.0, 0.55, 1.0e5,
        "Share of DC connectors rated at 350 kW on an 800 V architecture."),
    "bus_electrification": Lever(
        "bus_electrification", "Public-transport electrification", "infrastructure",
        "fraction of bus fleet", 0.0, 0.90, 4.4e7,
        "Programme electrifying urban bus and paratransit fleets."),
    # -- technology and standards -----------------------------------------
    "wbg_mandate": Lever(
        "wbg_mandate", "Wide-bandgap converter requirement", "technology",
        "minimum WBG share", 0.0, 0.95, 6.0e6,
        "Minimum share of new traction and charging converters using SiC or GaN, "
        "enforced through type approval."),
    "efficiency_standard": Lever(
        "efficiency_standard", "Minimum converter efficiency standard", "technology",
        "intensity", 0.0, 1.0, 4.2e6,
        "Weighted-efficiency floor for on-board chargers, DC chargers and "
        "traction inverters, with conformity assessment."),
    "hv_architecture": Lever(
        "hv_architecture", "800 V architecture promotion", "technology", "intensity",
        0.0, 1.0, 3.0e6,
        "Incentives and standards favouring 800 V vehicle and charger platforms."),
    "grid_code": Lever(
        "grid_code", "Grid-code and power-quality enforcement", "technology",
        "intensity", 0.0, 1.0, 7.5e6,
        "Harmonic, power-factor and ride-through requirements on charging "
        "equipment, with market surveillance."),
    # -- grid and system ---------------------------------------------------
    # Reinforcement and generation assets are capitalised explicitly in the
    # engine; the coefficients here cover planning, procurement and regulation.
    "grid_investment": Lever(
        "grid_investment", "Distribution reinforcement", "grid", "intensity",
        0.0, 1.0, 1.5e6,
        "Substation and feeder reinforcement, reconductoring and automation."),
    "renewable_target": Lever(
        "renewable_target", "Renewable capacity aligned to charging", "grid",
        "intensity", 0.0, 1.0, 1.0e6,
        "Solar and storage capacity procured explicitly to serve charging load."),
    "smart_charging": Lever(
        "smart_charging", "Smart-charging requirement", "grid",
        "controllable share", 0.0, 0.95, 1.1e7,
        "Share of charging energy that is dispatchable by the system operator "
        "or an aggregator."),
    "v2g_enablement": Lever(
        "v2g_enablement", "Vehicle-to-grid enablement", "grid",
        "participation share", 0.0, 0.60, 2.4e7,
        "Bidirectional-capable fleet share with market access and metering."),
    # -- institutional and industrial --------------------------------------
    "local_manufacturing": Lever(
        "local_manufacturing", "Domestic converter and pack manufacturing",
        "institutional", "intensity", 0.0, 1.0, 1.35e8,
        "Localisation of power-electronic assembly, magnetics and pack lines.",
        # capital grants to manufacturers; the resource effect (lower converter
        # and charger cost, lower duty pass-through) is modelled physically
        transfer=True),
    "workforce": Lever(
        "workforce", "Power-electronics workforce programme", "institutional",
        "intensity", 0.0, 1.0, 3.2e7,
        "Technician certification, university-industry laboratories and "
        "curriculum reform."),
    "recycling": Lever(
        "recycling", "Battery recycling and second-life mandate", "institutional",
        "intensity", 0.0, 1.0, 2.8e7,
        "Extended producer responsibility with collection and recovery targets."),
    # -- digital -----------------------------------------------------------
    # The key is kept for compatibility with archived settings; the instrument
    # is a monitoring and telemetry programme, not a digital twin.
    "digital_twin": Lever(
        "digital_twin", "Charging monitoring and telemetry platform", "digital",
        "intensity", 0.0, 1.0, 1.8e7,
        "Metering, telemetry and a national planning platform for charging "
        "operations and asset health."),
    "cybersecurity": Lever(
        "cybersecurity", "Charging cybersecurity programme", "digital", "intensity",
        0.0, 1.0, 1.2e7,
        "Certification of charge-point protocols, monitoring and incident "
        "response for charging infrastructure."),
}

DOMAINS = ["fiscal", "infrastructure", "technology", "grid", "institutional", "digital"]


# ---------------------------------------------------------------------------
# Policy package
# ---------------------------------------------------------------------------
@dataclass
class PolicyPackage:
    """A named bundle of lever settings with phase-in windows."""
    key: str
    label: str
    archetype: str
    description: str
    targets: dict[str, float]
    start_year: int = 2026
    full_year: int = 2032
    phase_in: dict[str, tuple[int, int]] = field(default_factory=dict)

    def resolve(self, year: int) -> dict[str, float]:
        """Lever values effective in ``year`` after linear phase-in."""
        out: dict[str, float] = {}
        for key, target in self.targets.items():
            lo, hi = self.phase_in.get(key, (self.start_year, self.full_year))
            if year <= lo:
                frac = 0.0
            elif year >= hi:
                frac = 1.0
            else:
                frac = (year - lo) / max(hi - lo, 1)
            base = LEVERS[key].lo if key in LEVERS else 0.0
            out[key] = base + (target - base) * frac
        for key in LEVERS:
            out.setdefault(key, LEVERS[key].lo)
        return out

    def annual_public_cost(self, year: int, stock_million: float,
                           transfers: bool | None = None) -> float:
        """Public budgetary cost of the package in ``year`` [USD].

        ``transfers=None`` returns the whole budget, ``False`` only the
        resource-consuming programme cost and ``True`` only the transfers.
        """
        levels = self.resolve(year)
        total = 0.0
        for key, lever in LEVERS.items():
            if transfers is not None and lever.transfer != transfers:
                continue
            span = max(lever.hi - lever.lo, 1e-9)
            intensity = float(np.clip((levels[key] - lever.lo) / span, 0.0, 1.0))
            total += intensity * lever.unit_cost * max(stock_million, 0.0)
        return float(total)

    def domain_intensity(self, year: int) -> dict[str, float]:
        """Mean normalised intensity by policy domain, for radar plots."""
        levels = self.resolve(year)
        out = {}
        for d in DOMAINS:
            keys = [k for k, v in LEVERS.items() if v.domain == d]
            vals = [float(np.clip((levels[k] - LEVERS[k].lo)
                                  / max(LEVERS[k].hi - LEVERS[k].lo, 1e-9), 0, 1))
                    for k in keys]
            out[d] = float(np.mean(vals)) if vals else 0.0
        return out


# ---------------------------------------------------------------------------
# Mapping levers onto physical model parameters
# ---------------------------------------------------------------------------
def device_mix(arch: Archetype, levels: dict[str, float], year: int) -> dict[str, float]:
    """Semiconductor technology shares in newly deployed converters.

    Baseline diffusion of wide-bandgap devices is archetype-specific; the
    mandate lever raises the floor, and the efficiency standard shifts the
    residual silicon share from IGBTs to super-junction MOSFETs.
    """
    rate = 0.008 + 0.030 * arch.digital_maturity
    autonomous = float(np.clip(arch.wbg_share_base + rate * (year - 2025), 0.0, 0.92))
    wbg = float(np.clip(max(autonomous, levels["wbg_mandate"]), 0.0, 0.97))
    # GaN is confined to lower-power on-board and auxiliary conversion
    gan_share = wbg * float(np.clip(0.16 + 0.30 * levels["hv_architecture"], 0.0, 0.45))
    sic_share = wbg - gan_share
    si = 1.0 - wbg
    sj_share = si * float(np.clip(0.25 + 0.55 * levels["efficiency_standard"], 0.0, 0.9))
    return {"SiC-MOSFET": sic_share, "GaN-HEMT": gan_share,
            "Si-MOSFET": sj_share, "Si-IGBT": si - sj_share}


def apply(arch: Archetype, levels: dict[str, float], year: int) -> dict[str, float]:
    """Translate resolved lever values into physical model parameters."""
    yr = max(year - 2025, 0)

    # --- infrastructure ---------------------------------------------------
    # The counterfactual is the charging density the archetype already has, not
    # an empty network: a "no policy" case still inherits existing provision.
    connectors = float(np.clip(max(levels["charger_rollout"], arch.charger_density_base),
                               1.0, 90.0))
    dc_fraction = float(np.clip(max(levels["dc_share"], arch.dc_share_base), 0.02, 0.60))
    ultrafast = float(np.clip(levels["ultrafast_share"], 0.0, 0.55))

    # --- technology -------------------------------------------------------
    mix = device_mix(arch, levels, year)
    dc_link = 400.0 + 400.0 * float(np.clip(levels["hv_architecture"], 0.0, 1.0))

    # --- grid -------------------------------------------------------------
    # Reinforcement raises substation capacity and lowers effective impedance.
    tx_multiplier = 1.0 + 0.55 * levels["grid_investment"]
    z_multiplier = 1.0 - 0.30 * levels["grid_investment"]
    availability_gain = (1.0 - arch.grid_availability) * (
        0.55 * levels["grid_investment"] + 0.15 * levels["digital_twin"])
    availability = float(np.clip(arch.grid_availability + availability_gain, 0.0, 0.9995))

    renewable_share = float(np.clip(
        arch.renewable_share + (0.42 - arch.renewable_share) * levels["renewable_target"]
        + 0.008 * yr, 0.0, 0.85))

    flexibility = float(np.clip(levels["smart_charging"]
                                * (0.55 + 0.45 * arch.digital_maturity
                                   + 0.35 * levels["digital_twin"]), 0.0, 0.95))
    v2g = float(np.clip(levels["v2g_enablement"]
                        * (0.5 + 0.5 * levels["digital_twin"]), 0.0, 0.60))

    # --- institutional ----------------------------------------------------
    local_mfg = float(np.clip(arch.manufacturing_index
                              + (1.0 - arch.manufacturing_index)
                              * levels["local_manufacturing"] * min(yr / 8.0, 1.0),
                              0.0, 0.95))
    workforce = float(np.clip(arch.workforce_index
                              + (1.0 - arch.workforce_index) * levels["workforce"],
                              0.0, 0.98))
    recycled = float(np.clip(0.05 + 0.60 * levels["recycling"], 0.0, 0.70))

    # --- digital ----------------------------------------------------------
    digital = float(np.clip(arch.digital_maturity
                            + (1.0 - arch.digital_maturity) * levels["digital_twin"],
                            0.0, 0.98))
    # A digital twin reduces unplanned downtime and raises asset utilisation
    maintenance_quality = float(np.clip(0.35 * workforce + 0.45 * digital
                                        + 0.20 * levels["cybersecurity"], 0.0, 0.98))
    cyber_risk = float(np.clip(0.045 * (1.0 - levels["cybersecurity"])
                               * (0.4 + 0.6 * digital), 0.0, 0.06))

    # --- fiscal -----------------------------------------------------------
    incentive = float(np.clip(levels["purchase_incentive"], 0.0, 0.35))
    duty = float(np.clip(arch.import_duty * (1.0 - levels["duty_relief"]), 0.0, 1.0))

    # Private overnight-charging access improves with reinforcement and metering
    home_access_base = 0.22 + 0.55 * arch.digital_maturity
    home_access = float(np.clip(home_access_base
                                + 0.18 * levels["grid_investment"]
                                + 0.10 * levels["tou_tariff"], 0.05, 0.92))

    # Grid-code enforcement lowers the harmonic current injected by chargers
    harmonic_factor = float(np.clip(1.0 - 0.42 * levels["grid_code"], 0.45, 1.0))

    return {
        "connectors_per_1000": connectors,
        "dc_fraction": dc_fraction,
        "ultrafast_fraction": ultrafast,
        "device_mix": mix,
        "dc_link_voltage": dc_link,
        "transformer_multiplier": tx_multiplier,
        "impedance_multiplier": z_multiplier,
        "availability": availability,
        "renewable_share": renewable_share,
        "flexibility": flexibility,
        "v2g_participation": v2g,
        "tou_enabled": levels["tou_tariff"] > 0.35,
        "local_manufacturing": local_mfg,
        "workforce_index": workforce,
        "recycled_content": recycled,
        "digital_maturity": digital,
        "maintenance_quality": maintenance_quality,
        "cyber_risk": cyber_risk,
        "purchase_incentive": incentive,
        "import_duty": duty,
        "home_access": home_access,
        "harmonic_factor": harmonic_factor,
        "bus_electrification": float(np.clip(levels["bus_electrification"], 0.0, 0.9)),
        "efficiency_standard": float(np.clip(levels["efficiency_standard"], 0.0, 1.0)),
        "awareness": float(np.clip(0.25 + 0.40 * levels["purchase_incentive"] / 0.35
                                   + 0.35 * levels["bus_electrification"], 0.0, 1.0)),
        "supply_constraint": supply_constraint(local_mfg, duty),
    }


def supply_constraint(local_mfg: float, effective_duty: float) -> float:
    """Share of would-be buyers who can obtain an electric vehicle.

    Supply binds where vehicles are imported against high duties (and, with
    them, scarce foreign exchange and thin dealer networks) and domestic
    assembly is weak.  The first revision used 0.55 + 0.30 m + 0.25 d for all
    archetypes, which capped German sales at about 72 % indefinitely although
    neither condition holds there.  Here the barrier grows with the square root
    of the effective import duty (0.45 at a 30 % duty) and is removed by local
    manufacturing: about 0.94 for Germany, 0.59 for Bangladesh and 0.49 for the
    least-developed archetype in the base year (assumed form).
    """
    barrier = float(np.clip(0.45 * np.sqrt(max(effective_duty, 0.0) / 0.30), 0.0, 0.60))
    return float(np.clip(1.0 - (1.0 - local_mfg) * barrier, 0.35, 1.0))


def lever_vector(package: PolicyPackage, year: int) -> np.ndarray:
    """Normalised lever vector, used by the sensitivity and optimisation layers."""
    levels = package.resolve(year)
    return np.array([
        float(np.clip((levels[k] - LEVERS[k].lo)
                      / max(LEVERS[k].hi - LEVERS[k].lo, 1e-9), 0.0, 1.0))
        for k in LEVERS])


def package_from_vector(key: str, label: str, archetype: str, vector: np.ndarray,
                        description: str = "") -> PolicyPackage:
    """Build a package from a normalised lever vector (used by the optimiser)."""
    targets = {}
    for v, (k, lev) in zip(vector, LEVERS.items()):
        targets[k] = float(lev.lo + np.clip(v, 0.0, 1.0) * (lev.hi - lev.lo))
    return PolicyPackage(key, label, archetype, description, targets)
