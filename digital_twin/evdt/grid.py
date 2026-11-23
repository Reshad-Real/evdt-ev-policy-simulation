"""Distribution-network layer of the digital twin.

A 33-node radial medium-voltage feeder is solved with a backward/forward sweep
power flow that is vectorised over the whole 8760-hour year, so a full annual
network study costs a few tens of milliseconds and can therefore be embedded
inside Monte-Carlo and multi-year policy loops.

The layer returns the quantities that distribution policy actually turns on:
technical losses, voltage deviation and statutory-limit violations, line and
transformer loading, transformer insulation ageing under the IEEE C57.91
thermal model, voltage distortion at the point of common coupling, and the
energy not served that follows from overload and supply unavailability
(docs_reference: grid-tx-loading, grid-infra-impact, grid-harmonic-std,
grid-der-standards, ldc-minigrid-rel).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import FeederConfig


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------
@dataclass
class Feeder:
    """Radial feeder with a fixed parent array and per-branch impedance."""
    parent: np.ndarray          # parent[i] is upstream node of i; parent[0] = -1
    r: np.ndarray               # Ohm per branch feeding node i
    x: np.ndarray               # Ohm per branch feeding node i
    load_share: np.ndarray      # allocation of feeder demand to each node
    order: np.ndarray           # nodes sorted so parents precede children
    cfg: FeederConfig
    i_rated_pu: np.ndarray | None = None   # thermal rating of each branch [pu]
    path: np.ndarray | None = None         # path[i, k] = 1 if branch k feeds node i

    @property
    def n(self) -> int:
        return int(self.parent.size)


def build_feeder(cfg: FeederConfig | None = None, seed: int = 7) -> Feeder:
    """Construct the 33-node radial test feeder used throughout the study.

    A trunk of 18 nodes carries three laterals, which reproduces the voltage
    profile and loss behaviour of a real medium-voltage distribution feeder far
    better than a single radial string.
    """
    cfg = cfg or FeederConfig()
    n = cfg.n_nodes
    rng = np.random.default_rng(seed)
    parent = np.full(n, -1, dtype=int)
    trunk = min(18, n - 1)
    for i in range(1, trunk + 1):
        parent[i] = i - 1
    laterals = [(6, trunk + 1), (11, trunk + 6), (15, trunk + 10)]
    node = trunk + 1
    for root, _ in laterals:
        prev = root
        for _ in range(5):
            if node >= n:
                break
            parent[node] = prev
            prev = node
            node += 1
    for i in range(1, n):                       # attach any stragglers
        if parent[i] < 0:
            parent[i] = max(i - 1, 0)

    length = cfg.mean_branch_km * rng.uniform(0.55, 1.55, n)
    length[0] = 0.0
    depth = np.zeros(n, dtype=int)
    for i in range(1, n):
        depth[i] = depth[parent[i]] + 1
    # conductor cross-section is reduced away from the substation, so the
    # per-kilometre impedance rises with electrical depth
    taper = 1.0 + 0.05 * depth
    r = cfg.r_per_km * length * taper
    x = cfg.x_per_km * length * taper

    share = rng.uniform(0.5, 1.5, n)
    share[0] = 0.0
    share /= share.sum()

    order = np.argsort(depth, kind="stable")

    # Branch thermal ratings follow the downstream load they are built to carry,
    # sized against the substation transformer rating with planning headroom.
    downstream = share.copy()
    for node in order[::-1]:
        p = parent[node]
        if p >= 0:
            downstream[p] += downstream[node]
    i_design_pu = cfg.transformer_mva * 1e6 / cfg.base_power
    i_rated = np.maximum(i_design_pu * downstream * 1.25, 0.02)
    i_rated[0] = max(i_design_pu * 1.25, 0.02)

    # Path-incidence matrix: path[i, k] = 1 when branch k lies on the route from
    # the substation to node i.  With it, the backward and forward sweeps each
    # reduce to a single matrix product over the whole time axis.
    path = np.zeros((n, n))
    for node in order:
        pnode = parent[node]
        if pnode >= 0:
            path[node] = path[pnode]
            path[node, node] = 1.0
    return Feeder(parent, r, x, share, order, cfg, i_rated, path)


# ---------------------------------------------------------------------------
# Power flow
# ---------------------------------------------------------------------------
def power_flow(feeder: Feeder, p_node_mw: np.ndarray, q_node_mvar: np.ndarray,
               v_slack_pu: float = 1.02, tol: float = 1e-6,
               max_iter: int = 30) -> dict[str, np.ndarray]:
    """Backward/forward sweep load flow, vectorised over the time axis.

    Parameters
    ----------
    p_node_mw, q_node_mvar : array (n_nodes, n_hours)
        Nodal active and reactive demand.

    Returns
    -------
    dict with per-hour arrays: ``v_min_pu``, ``v_mean_pu``, ``losses_mw``,
    ``branch_loading_pu``, ``head_flow_mva`` and the full ``v_pu`` matrix.
    """
    cfg = feeder.cfg
    n, h = p_node_mw.shape
    z_base = cfg.base_voltage ** 2 / cfg.base_power          # Ohm
    r_pu = feeder.r / z_base
    x_pu = feeder.x / z_base
    s_pu = (p_node_mw * 1e6 + 1j * q_node_mvar * 1e6) / cfg.base_power

    path = (feeder.path if feeder.path is not None
            else np.eye(n))
    z_pu = (r_pu + 1j * x_pu)
    v = np.full((n, h), v_slack_pu, dtype=complex)
    i_br = np.zeros((n, h), dtype=complex)

    for _ in range(max_iter):
        v_prev = v
        # backward sweep: branch current = sum of injections it supplies
        i_node = np.conj(s_pu / np.where(np.abs(v) < 1e-6, 1e-6, v))
        i_br = path.T @ i_node
        # forward sweep: voltage drop is the sum of drops along the path
        v = v_slack_pu - path @ (z_pu[:, None] * i_br)
        v[0, :] = v_slack_pu
        if np.max(np.abs(v - v_prev)) < tol:
            break

    v_mag = np.abs(v)
    losses_pu = np.sum(r_pu[:, None] * np.abs(i_br) ** 2, axis=0)
    losses_mw = losses_pu * cfg.base_power / 1e6

    i_rated = (feeder.i_rated_pu if feeder.i_rated_pu is not None
               else np.full(n, 1.0))
    loading = np.abs(i_br) / np.maximum(i_rated, 1e-9)[:, None]

    head_mva = np.abs(v[0] * np.conj(i_br[0])) * cfg.base_power / 1e6
    return {
        "v_pu": v_mag,
        "v_min_pu": v_mag[1:].min(axis=0),
        "v_max_pu": v_mag[1:].max(axis=0),
        "v_mean_pu": v_mag[1:].mean(axis=0),
        "losses_mw": losses_mw,
        "branch_loading_pu": loading,
        "line_loading_max": loading[1:].max(axis=0),
        "head_flow_mva": head_mva,
    }


def feeder_from_data(from_bus: np.ndarray, to_bus: np.ndarray, r_ohm: np.ndarray,
                     x_ohm: np.ndarray, load_kw: np.ndarray,
                     cfg: FeederConfig, impedance_multiplier: float = 1.0,
                     i_rated_a: np.ndarray | None = None) -> Feeder:
    """Radial feeder from bus-branch data (buses numbered 1..N, bus 1 the
    substation).  ``load_kw[b-1]`` is the published load of bus b and fixes
    the allocation of the feeder total; branch ratings are taken from
    ``i_rated_a`` (per branch, A) when given, otherwise from the same design
    rule as :func:`build_feeder`."""
    n = int(max(np.max(from_bus), np.max(to_bus)))
    parent = np.full(n, -1, dtype=int)
    r = np.zeros(n)
    x = np.zeros(n)
    rated_a = np.full(n, np.nan)
    for k, (f, t) in enumerate(zip(from_bus.astype(int), to_bus.astype(int))):
        if parent[t - 1] >= 0:
            raise ValueError(f"bus {t} has two parents: feeder is not radial")
        parent[t - 1] = f - 1
        r[t - 1] = r_ohm[k] * impedance_multiplier
        x[t - 1] = x_ohm[k] * impedance_multiplier
        if i_rated_a is not None:
            rated_a[t - 1] = i_rated_a[k]
    if np.sum(parent < 0) != 1 or parent[0] != -1:
        raise ValueError("bus 1 must be the only root")
    depth = np.zeros(n, dtype=int)
    for _ in range(n):                      # parents may be listed after children
        changed = False
        for i in range(1, n):
            d = depth[parent[i]] + 1
            if depth[i] != d:
                depth[i], changed = d, True
        if not changed:
            break
    order = np.argsort(depth, kind="stable")
    share = np.clip(np.asarray(load_kw, dtype=float), 0.0, None)
    share[0] = 0.0
    share = share / max(share.sum(), 1e-12)
    downstream = share.copy()
    for node in order[::-1]:
        if parent[node] >= 0:
            downstream[parent[node]] += downstream[node]
    i_design_pu = cfg.transformer_mva * 1e6 / cfg.base_power
    i_rated = np.maximum(i_design_pu * downstream * 1.25, 0.02)
    i_rated[0] = max(i_design_pu * 1.25, 0.02)
    if i_rated_a is not None:
        i_base_a = cfg.base_power / (np.sqrt(3.0) * cfg.base_voltage)
        have = np.isfinite(rated_a)
        i_rated[have] = rated_a[have] / i_base_a
    path = np.zeros((n, n))
    for node in order:
        pn = parent[node]
        if pn >= 0:
            path[node] = path[pn]
            path[node, node] = 1.0
    return Feeder(parent, r, x, share, order, cfg, i_rated, path)


FEEDER_DATA = Path(__file__).resolve().parents[1] / "data" / "feeders"


@lru_cache(maxsize=32)
def load_benchmark(key: str) -> dict:
    """Bus-branch data of a benchmark feeder from ``data/feeders``:
    ``<key>_branches.csv`` (from_bus, to_bus, r_ohm, x_ohm[, i_max_a]),
    ``<key>_loads.csv`` (bus, p_kw, q_kvar) and ``<key>_meta.json``
    (base_kv, source, ...)."""
    import json
    import pandas as pd
    br = pd.read_csv(FEEDER_DATA / f"{key}_branches.csv", comment="#")
    ld = pd.read_csv(FEEDER_DATA / f"{key}_loads.csv", comment="#")
    meta = json.loads((FEEDER_DATA / f"{key}_meta.json").read_text(encoding="utf-8"))
    n = int(max(br.from_bus.max(), br.to_bus.max()))
    load = np.zeros(n)
    for b, pk in zip(ld.bus.astype(int), ld.p_kw.astype(float)):
        load[b - 1] += pk
    return {"from": br.from_bus.to_numpy(int), "to": br.to_bus.to_numpy(int),
            "r": br.r_ohm.to_numpy(float), "x": br.x_ohm.to_numpy(float),
            "i_max_a": (br.i_max_a.to_numpy(float) if "i_max_a" in br else None),
            "load_kw": load, "peak_mw": float(load.sum()) / 1e3, "meta": meta}


def power_flow_lookup(feeder: Feeder, total_mw: np.ndarray, power_factor: float = 0.95,
                      v_slack_pu: float = 1.02, n_levels: int = 48) -> dict[str, np.ndarray]:
    """Annual power flow by interpolation in the feeder total.

    Every nodal load is a fixed share of the feeder total at a fixed power
    factor, so the solution is a smooth function of one scalar.  It is solved
    at ``n_levels`` totals spanning the year's range and interpolated to every
    hour; against the direct solution the error is below 1e-5 pu in voltage
    and 0.1 % in losses (checked in run_validation.py).  This keeps feeders of
    a hundred or more nodes affordable inside the Monte-Carlo and lever-space
    campaigns.
    """
    total_mw = np.asarray(total_mw, dtype=float)
    lo, hi = float(total_mw.min()), float(total_mw.max())
    if hi - lo < 1e-9:
        hi = lo + 1e-6
    levels = np.linspace(lo, hi, n_levels)
    p, q = allocate_demand(feeder, levels, power_factor)
    pf = power_flow(feeder, p, q, v_slack_pu=v_slack_pu)
    out = {}
    for key in ("v_min_pu", "v_max_pu", "v_mean_pu", "losses_mw", "line_loading_max",
                "head_flow_mva"):
        out[key] = np.interp(total_mw, levels, pf[key])
    return out


def allocate_demand(feeder: Feeder, total_mw: np.ndarray,
                    power_factor: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    """Spread an aggregate feeder demand over the nodes."""
    p = feeder.load_share[:, None] * total_mw[None, :]
    q = p * np.tan(np.arccos(power_factor))
    return p, q


# ---------------------------------------------------------------------------
# Transformer thermal ageing (IEEE C57.91 style)
# ---------------------------------------------------------------------------
def transformer_thermal(cfg: FeederConfig, load_mva: np.ndarray,
                        ambient_c: np.ndarray, n_exp: float = 0.8,
                        m_exp: float = 0.8) -> dict[str, np.ndarray]:
    """Top-oil and hot-spot temperature and insulation loss of life.

    ``F_AA = exp(15000/383 - 15000/(theta_H + 273))`` is the ageing
    acceleration factor for thermally upgraded insulation.
    """
    k = np.clip(load_mva / max(cfg.transformer_mva, 1e-9), 0.0, 4.0)
    ratio = cfg.transformer_load_loss / max(cfg.transformer_no_load_loss, 1e-9)
    d_top_rated = 45.0
    d_top = d_top_rated * ((k ** 2 * ratio + 1.0) / (ratio + 1.0)) ** n_exp
    d_hs = (cfg.hot_spot_rise_rated - d_top_rated) * k ** (2.0 * m_exp)
    theta_h = ambient_c + d_top + d_hs
    f_aa = np.exp(15000.0 / 383.0 - 15000.0 / (theta_h + 273.0))
    return {"hot_spot_c": theta_h, "top_oil_c": ambient_c + d_top,
            "loading_pu": k, "ageing_factor": f_aa,
            "loss_of_life_pu": float(np.mean(f_aa))}


def transformer_losses(cfg: FeederConfig, load_mva: np.ndarray) -> np.ndarray:
    """Transformer no-load plus load losses [MW]."""
    k = load_mva / max(cfg.transformer_mva, 1e-9)
    return (cfg.transformer_no_load_loss + cfg.transformer_load_loss * k ** 2) / 1e6


# ---------------------------------------------------------------------------
# Power quality
# ---------------------------------------------------------------------------
def voltage_distortion(cfg: FeederConfig, nonlinear_mva: np.ndarray,
                       current_distortion: float,
                       harmonic_weight: float = 4.6) -> np.ndarray:
    """Voltage total harmonic distortion at the point of common coupling [pu].

    Estimated from the harmonic current injected by the charging fleet acting
    on the short-circuit impedance seen at the coupling point; the weighting
    factor aggregates the dominant low-order harmonics of a six-pulse-equivalent
    spectrum.
    """
    s_sc = cfg.transformer_mva / max(cfg.transformer_impedance, 1e-6)
    return np.clip(harmonic_weight * current_distortion
                   * np.asarray(nonlinear_mva) / max(s_sc, 1e-9), 0.0, 0.35)


# ---------------------------------------------------------------------------
# Aggregate network indicators
# ---------------------------------------------------------------------------
def network_indicators(feeder: Feeder, pf: dict[str, np.ndarray],
                       load_mva: np.ndarray, ambient_c: np.ndarray,
                       ev_mva: np.ndarray, current_distortion: float,
                       availability: np.ndarray,
                       total_demand_mwh: float) -> dict[str, float]:
    """Condense an annual network solution into policy-relevant indicators."""
    cfg = feeder.cfg
    v_min, v_max = pf["v_min_pu"], pf["v_max_pu"]
    dev = np.maximum(np.abs(pf["v_mean_pu"] - 1.0),
                     np.maximum(1.0 - v_min, v_max - 1.0))
    under = float(np.mean(v_min < cfg.voltage_limit_low))
    over = float(np.mean(v_max > cfg.voltage_limit_high))

    tx = transformer_thermal(cfg, load_mva, ambient_c)
    tx_loss = transformer_losses(cfg, load_mva)
    total_losses = pf["losses_mw"] + tx_loss

    thd = voltage_distortion(cfg, ev_mva, current_distortion)

    overload = np.clip(load_mva / cfg.transformer_mva - 1.0, 0.0, None)
    ens_overload = float(np.sum(overload * cfg.transformer_mva * 0.95))     # MWh
    ens_outage = float(np.sum((1.0 - availability) * load_mva * 0.95))      # MWh
    ens = ens_overload + ens_outage

    # Resilience: ability to keep serving critical load through the worst week
    weekly = load_mva.reshape(-1, 168).mean(axis=1) if load_mva.size % 168 == 0 \
        else load_mva[:load_mva.size // 168 * 168].reshape(-1, 168).mean(axis=1)
    worst = float(np.max(weekly)) if weekly.size else float(np.max(load_mva))
    resilience = float(np.clip(cfg.transformer_mva / max(worst, 1e-9) / 1.6, 0.0, 1.0))

    return {
        "losses_mwh": float(np.sum(total_losses)),
        "loss_fraction": float(np.sum(total_losses) / max(total_demand_mwh, 1e-9)),
        "voltage_deviation_mean_pu": float(np.mean(dev)),
        "voltage_deviation_p95_pu": float(np.percentile(dev, 95)),
        "v_min_pu": float(np.min(v_min)),
        "undervoltage_hours_frac": under,
        "overvoltage_hours_frac": over,
        "transformer_loading_peak_pu": float(np.max(tx["loading_pu"])),
        "transformer_loading_mean_pu": float(np.mean(tx["loading_pu"])),
        "transformer_hotspot_max_c": float(np.max(tx["hot_spot_c"])),
        "transformer_ageing_pu": float(np.mean(tx["ageing_factor"])),
        "line_loading_p95_pu": float(np.percentile(pf["line_loading_max"], 95)),
        "line_loading_max_pu": float(np.max(pf["line_loading_max"])),
        "thd_v_mean": float(np.mean(thd)),
        "thd_v_p95": float(np.percentile(thd, 95)),
        "thd_violation_frac": float(np.mean(thd > cfg.thd_limit)),
        "energy_not_served_mwh": ens,
        "reliability_index": float(np.clip(1.0 - ens / max(total_demand_mwh, 1e-9),
                                           0.0, 1.0)),
        "resilience_index": resilience,
        "peak_demand_mva": float(np.max(load_mva)),
        "load_factor": float(np.mean(load_mva) / max(np.max(load_mva), 1e-9)),
    }


def hosting_capacity(feeder: Feeder, base_mw: np.ndarray, ambient_c: np.ndarray,
                     step_mw: float = 0.25, max_steps: int = 60) -> float:
    """Additional EV load the feeder can host before a limit is violated [MW]."""
    cfg = feeder.cfg
    for i in range(1, max_steps + 1):
        extra = i * step_mw
        total = base_mw + extra
        p, q = allocate_demand(feeder, total)
        pf = power_flow(feeder, p, q)
        if (np.min(pf["v_min_pu"]) < cfg.voltage_limit_low
                or np.max(total) > cfg.transformer_mva
                or np.max(pf["line_loading_max"]) > 1.0):
            return float((i - 1) * step_mw)
    return float(max_steps * step_mw)
