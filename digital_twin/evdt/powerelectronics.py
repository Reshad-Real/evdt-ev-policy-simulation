"""Power-electronic conversion layer of the digital twin.

This module is the technological core of the framework.  It provides

* analytic conduction and switching loss models for Si IGBT, Si super-junction
  MOSFET, SiC MOSFET and GaN HEMT switch positions, including series stacking
  (blocking-voltage feasibility) and die paralleling (current feasibility);
* an electro-thermal fixed-point solver returning self-consistent junction
  temperature, losses and efficiency at a converter operating point;
* technology-appropriate switching frequencies, from which converter power
  density and magnetics mass follow;
* topology wrappers for the traction inverter, auxiliary DC/DC converter,
  bidirectional on-board charger, DC fast-charger front end and isolation
  stage, and the cascaded solid-state transformer;
* a LESIT-type power-cycling reliability model with rainflow counting and
  Miner damage accumulation, converting a mission profile into a converter
  failure rate.

Loss-model structure follows the datasheet-referred formulation used in the
reviewed literature (docs_reference: pe-sic-loss-datasheet, pe-sic-loss-dynamic,
pe-loss-rt, pe-sic-switching); topology choices follow the review literature
(pe-traction-inv-review, pe-bidir-dcdc-review, pe-obc-totem, pe-dab-compare,
pe-sst-review, pe-hv-station); the reliability formulation follows the
power-cycling literature (pe-sic-powercycling, pe-bondwire, pe-module-lifetime).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.special import gamma as _gamma

from .config import (BOLTZMANN_EV, CHARGER_DEVICE_LIBRARY, Converter, Device,
                     DEVICE_LIBRARY, DEVICE_VALIDITY, LV_DEVICE_LIBRARY,
                     charger_device_for, device_for)


#: Multiplier on all switching and conduction losses of silicon devices, used
#: only by the sensitivity in which the model is made to reproduce the published
#: drive-cycle gain of SiC (run_revision_analyses.silicon_loss_sensitivity).
#: Caches must be cleared when it is changed (clear_caches()).
SILICON_LOSS_MULT = 1.0
SILICON_TECH = ("Si-IGBT", "Si-MOSFET", "Si-LV")


def perturbed(device: Device, esw_mult: float = 1.0, ron_mult: float = 1.0,
              rth_mult: float = 1.0) -> Device:
    """Device with its loss and thermal parameters scaled (uncertainty study)."""
    k = SILICON_LOSS_MULT if device.technology in SILICON_TECH else 1.0
    if esw_mult == 1.0 and ron_mult == 1.0 and rth_mult == 1.0 and k == 1.0:
        return device
    return replace(device, e_on=device.e_on * esw_mult * k,
                   e_off=device.e_off * esw_mult * k, e_rr=device.e_rr * esw_mult * k,
                   r_on_25=device.r_on_25 * ron_mult * k, r_ce=device.r_ce * ron_mult * k,
                   v_ce0=device.v_ce0 * k, v_f0=device.v_f0 * k,
                   r_f=device.r_f * ron_mult * k, r_th_jc=device.r_th_jc * rth_mult)


def clear_caches() -> None:
    """Forget cached converter results (after changing SILICON_LOSS_MULT)."""
    for fn in (_powertrain_efficiency_cached, _charging_path_cached, _session_swing,
               _cycle_power):
        fn.cache_clear()

# Design rules ---------------------------------------------------------------
DIE_UTILISATION = 0.55        # fraction of rated die current used at converter rating
VOLTAGE_MARGIN = 1.20         # device blocking voltage must exceed 1.2 x DC link
# Global calibration factor on power-cycling capability.  It is set so that a
# silicon IGBT traction inverter operating on the reference urban mission
# profile of this study attains a B10 lifetime of the order of 15-20 years,
# which is the automotive qualification target; the relative ranking of the
# semiconductor technologies is unaffected by its value.
PC_SCALE = 0.15

# Technology-appropriate switching frequency [Hz] by (role, technology).
# Hard-switched stages are limited by loss; soft-switched (resonant / ZVS)
# stages are limited by gate-drive and magnetics design.  The systematic
# frequency advantage of wide-bandgap devices is the mechanism by which they
# raise converter power density.
FREQUENCY_MAP: dict[tuple[str, str], float] = {
    ("traction-inverter", "Si-IGBT"): 8.0e3,
    ("traction-inverter", "Si-MOSFET"): 10.0e3,
    ("traction-inverter", "SiC-MOSFET"): 16.0e3,
    ("traction-inverter", "GaN-HEMT"): 20.0e3,
    ("dcfc-afe", "Si-IGBT"): 8.0e3,
    ("dcfc-afe", "Si-MOSFET"): 10.0e3,
    ("dcfc-afe", "SiC-MOSFET"): 24.0e3,
    ("dcfc-afe", "GaN-HEMT"): 30.0e3,
    ("obc-pfc", "Si-IGBT"): 20.0e3,
    ("obc-pfc", "Si-MOSFET"): 45.0e3,
    ("obc-pfc", "SiC-MOSFET"): 100.0e3,
    ("obc-pfc", "GaN-HEMT"): 160.0e3,
    ("dcdc", "Si-IGBT"): 20.0e3,
    ("dcdc", "Si-MOSFET"): 70.0e3,
    ("dcdc", "SiC-MOSFET"): 150.0e3,
    ("dcdc", "GaN-HEMT"): 250.0e3,
    ("dcfc-dcdc", "Si-IGBT"): 16.0e3,
    ("dcfc-dcdc", "Si-MOSFET"): 40.0e3,
    ("dcfc-dcdc", "SiC-MOSFET"): 80.0e3,
    ("dcfc-dcdc", "GaN-HEMT"): 120.0e3,
    ("sst", "Si-IGBT"): 10.0e3,
    ("sst", "Si-MOSFET"): 25.0e3,
    ("sst", "SiC-MOSFET"): 50.0e3,
    ("sst", "GaN-HEMT"): 75.0e3,
    # 48-72 V two- and three-wheeler drives
    ("lv-traction-inverter", "Si-LV"): 16.0e3,
    ("lv-traction-inverter", "GaN-LV"): 32.0e3,
}

#: Technologies that cannot be built at 1200 V in volume.  On an 800 V link they
#: are used in a three-level (ANPC / flying-capacitor) leg in which each device
#: blocks half the link, rather than as a two-die series stack.
MULTILEVEL_TECH = ("Si-MOSFET", "GaN-HEMT")

# Reference frequency for the magnetics scaling law.
F_REF_MAGNETICS = 20.0e3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sine_energy_factor(k: float) -> float:
    r"""Mean commutation-energy factor for a sinusoidal current.

    Returns :math:`B_k/(2\pi)` with :math:`B_k=\int_0^\pi\sin^k\theta\,d\theta`,
    which for ``k = 1`` reduces to the classical :math:`1/\pi`.
    """
    b_k = math.sqrt(math.pi) * _gamma((k + 1.0) / 2.0) / _gamma(k / 2.0 + 1.0)
    return b_k / (2.0 * math.pi)


def r_on(device: Device, t_j: np.ndarray | float) -> np.ndarray | float:
    """Temperature-dependent on-state resistance of a unipolar device."""
    return device.r_on_25 * (1.0 + device.r_on_tc * (np.asarray(t_j) - 25.0))


ZVS_RESIDUAL = 0.35   # residual turn-off energy retained under zero-voltage switching
#: midpoints of the conducting half-wave, for averaging commutation energies
_SIN_THETA = np.sin((np.arange(32) + 0.5) * math.pi / 32)


def switching_energy(device: Device, v_die: float, i_die: np.ndarray | float,
                     t_j: np.ndarray | float, commutation: str = "hard",
                     e_rr_scale: float = 1.0) -> np.ndarray:
    """Datasheet-referred switching energy of one die per commutation [J].

    Under zero-voltage switching the turn-on transition and the reverse-recovery
    of the complementary device are suppressed; only a fraction of the turn-off
    energy remains.
    """
    i_die = np.maximum(np.asarray(i_die, dtype=float), 0.0)
    if commutation == "zvs":
        e_base = ZVS_RESIDUAL * device.e_off
    else:
        e_base = device.e_on + device.e_off + e_rr_scale * device.e_rr
    scale_v = v_die / device.v_ref
    scale_i = np.power(np.maximum(i_die, 1e-9) / device.i_ref, device.i_exponent)
    scale_t = 1.0 + device.e_tc * (np.asarray(t_j) - 25.0)
    return e_base * scale_v * scale_i * np.maximum(scale_t, 0.2)


def switching_frequency_for(role: str, device: Device,
                            default: float = 10.0e3) -> float:
    """Practical switching frequency for a (role, technology) pair."""
    f = FREQUENCY_MAP.get((role, device.technology), default)
    return float(min(f, device.f_sw_max))


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------
@dataclass
class Sizing:
    """Current/voltage stresses and die count of one switch position."""
    i_rms: float               # A, rms current of the switch position
    i_avg: float               # A, average current of the switch position
    i_switched: float          # A, current at the commutation instant
    commutation_factor: float  # - , averaging factor of the commutation energy
    n_parallel: int            # dies in parallel
    n_series: int              # dies in series (blocking-voltage stacking)
    # Freewheeling interval of a bridge leg: the current that flows in the
    # reverse direction through the position (the antiparallel diode of an
    # IGBT, the channel of a synchronously rectified MOSFET or HEMT).
    i_rms_rev: float = 0.0
    i_avg_rev: float = 0.0
    ripple_pp: float = 0.0     # A, peak-to-peak PWM ripple of the phase current

    @property
    def n_dies(self) -> int:
        return self.n_parallel * self.n_series


TRACTION_ROLES = ("traction-inverter", "lv-traction-inverter")
#: Three-phase two-level bridges, whose switch positions also carry the
#: freewheeling current.
BRIDGE_ROLES = ("traction-inverter", "lv-traction-inverter", "dcfc-afe")
#: Dead time per commutation [s] by technology; during it the reverse current
#: flows through the body diode (or the HEMT's reverse channel) at ``v_sd``.
DEAD_TIME_S = {"Si-IGBT": 1.0e-6, "Si-MOSFET": 300e-9, "SiC-MOSFET": 150e-9,
               "GaN-HEMT": 50e-9, "Si-LV": 200e-9, "GaN-LV": 30e-9}


def size_switch_position(conv: Converter, device: Device,
                         power: float | None = None,
                         modulation: float | None = None) -> Sizing:
    """Stresses per switch position plus the die array needed to sustain them.

    Die count is fixed by the converter *rating* at the nominal modulation
    index (it is hardware), while the stresses are evaluated at the requested
    operating ``power`` and, for a traction inverter, at the operating
    ``modulation`` index: below base speed the machine voltage, and with it
    the modulation index, falls with speed, so the same power needs more
    current.
    """
    p_rated = conv.rated_power
    p = p_rated if power is None else power

    def stresses(pp: float, m_op: float) -> tuple[float, ...]:
        if conv.role in ("traction-inverter", "lv-traction-inverter", "dcfc-afe",
                         "obc-pfc"):
            phases = 1 if conv.role == "obc-pfc" else 3
            v_ll = conv.dc_link_voltage * m_op / math.sqrt(2.0)
            i_rms_line = pp / max(math.sqrt(phases) * v_ll * conv.power_factor, 1e-6)
            i_peak = i_rms_line * math.sqrt(2.0)
            m, cphi = m_op, conv.power_factor
            i_r = i_peak * math.sqrt(max(0.125 + m * cphi / (3.0 * math.pi), 1e-9))
            i_a = i_peak * (1.0 / (2.0 * math.pi) + m * cphi / 8.0)
            # Sinusoidal-PWM bridge leg (e.g. Bierhoff and Fuchs, PESC 2004):
            # the freewheeling share carries the same expressions with the
            # sign of m*cos(phi) reversed.  Only three-phase bridges have it.
            if conv.role in BRIDGE_ROLES:
                i_rr = i_peak * math.sqrt(max(0.125 - m * cphi / (3.0 * math.pi), 0.0))
                i_ar = i_peak * max(1.0 / (2.0 * math.pi) - m * cphi / 8.0, 0.0)
            else:
                i_rr = i_ar = 0.0
            return i_r, i_a, i_peak, _sine_energy_factor(device.i_exponent), i_rr, i_ar
        i_dc = pp / max(conv.dc_link_voltage, 1e-6)
        ripple = 0.30
        i_r = i_dc * math.sqrt(max(0.5 * (1.0 + ripple ** 2 / 12.0), 1e-9))
        return i_r, 0.5 * i_dc, i_dc * (1.0 + ripple / 2.0), 1.0, 0.0, 0.0

    rated = stresses(p_rated, conv.modulation_index)
    i_rms_rated = rated[0]
    n_par = max(1, math.ceil(i_rms_rated / max(device.i_rating * DIE_UTILISATION, 1e-9)))
    n_ser = max(1, math.ceil(conv.dc_link_voltage * VOLTAGE_MARGIN / device.v_rating))

    m_op = conv.modulation_index
    if modulation is not None and conv.role in TRACTION_ROLES:
        m_op = float(np.clip(modulation, 0.02, conv.modulation_index))
    i_r, i_a, i_sw, cf, i_rr, i_ar = stresses(p, m_op)
    ripple = 0.0
    if conv.role in BRIDGE_ROLES and conv.ripple_pu_10k > 0.0:
        v_fac = (conv.dc_link_voltage / conv.ripple_v_design
                 if conv.ripple_v_design > 0.0 else 1.0)
        ripple = (conv.ripple_pu_10k * rated[2] * 1.0e4
                  / max(conv.switching_frequency, 1.0) * v_fac)
        # a triangular ripple adds ripple_pp^2/12 to the mean square of the
        # phase current, shared by the forward and freewheeling intervals
        i_r = math.sqrt(i_r ** 2 + ripple ** 2 / 24.0)
        i_rr = math.sqrt(i_rr ** 2 + ripple ** 2 / 24.0)
    return Sizing(i_r, i_a, i_sw, cf, n_par, n_ser, i_rr, i_ar, ripple)


# ---------------------------------------------------------------------------
# Operating point
# ---------------------------------------------------------------------------
@dataclass
class OperatingPoint:
    power_out: float
    p_conduction: float
    p_switching: float
    p_passive: float
    p_total: float
    efficiency: float
    t_junction: float
    t_case: float
    device_current_rms: float
    n_parallel: int = 1
    n_series: int = 1

    def as_dict(self) -> dict[str, float]:
        return {"power_out_w": self.power_out, "p_conduction_w": self.p_conduction,
                "p_switching_w": self.p_switching, "p_passive_w": self.p_passive,
                "p_total_w": self.p_total, "efficiency": self.efficiency,
                "t_junction_c": self.t_junction, "t_case_c": self.t_case,
                "i_rms_a": self.device_current_rms,
                "n_parallel": self.n_parallel, "n_series": self.n_series}


def solve_converter(conv: Converter, device: Device, power_out: float,
                    t_ambient: float = 40.0, soft_switching: float | None = None,
                    iterations: int = 12,
                    modulation: float | None = None) -> OperatingPoint:
    """Self-consistent electro-thermal solution of one converter operating point.

    ``modulation`` (traction inverters only): operating modulation index; the
    default is the nominal value at and above base speed.
    """
    p_out = float(np.clip(power_out, 0.0, 1.5 * conv.rated_power))
    sz_rated = size_switch_position(conv, device)
    n_par, n_ser = sz_rated.n_parallel, sz_rated.n_series
    n_dies = n_par * n_ser
    # Three-level leg: two devices conduct in series, but each commutation is
    # performed by one device at half the link voltage, so the switching loss
    # is that of one die array at V/2 rather than of n_ser arrays.
    multilevel = n_ser == 2 and device.technology in MULTILEVEL_TECH
    sw_arrays = 1 if multilevel else n_ser
    ss = 1.0 if soft_switching is None else soft_switching

    if p_out <= 0.0:
        p_pass = conv.passive_loss_fixed * conv.rated_power
        return OperatingPoint(0.0, 0.0, 0.0, p_pass, p_pass, 0.0, t_ambient,
                              t_ambient, 0.0, n_par, n_ser)

    sz = size_switch_position(conv, device, p_out, modulation)
    load = p_out / conv.rated_power
    # copper and capacitor losses follow the current, which rises as the
    # modulation index falls below its nominal value
    load_i = load
    if modulation is not None and conv.role in TRACTION_ROLES:
        load_i = load * conv.modulation_index / float(np.clip(modulation, 0.02,
                                                               conv.modulation_index))
    v_die = conv.dc_link_voltage / n_ser
    i_die = sz.i_switched / n_par

    # ---- electro-thermal fixed point --------------------------------------
    # n_par dies share the current; n_ser dies share the blocking voltage.
    r_th_pos = device.r_th_jc / n_dies + (0.0 if device.rth_to_fluid
                                          else conv.cooling_r_th)
    t_j = t_ambient + 25.0
    p_pos = 0.0
    t_dead = DEAD_TIME_S.get(device.technology, 0.0) if conv.role in BRIDGE_ROLES else 0.0
    for _ in range(iterations):
        if device.technology == "Si-IGBT":
            p_cond = n_ser * (device.v_ce0 * sz.i_avg
                              + device.r_ce * sz.i_rms ** 2 / n_par
                              # antiparallel PiN diode in the freewheeling interval
                              + device.v_f0 * sz.i_avg_rev
                              + device.r_f * sz.i_rms_rev ** 2 / n_par)
        else:
            # synchronous rectification: the channel carries the reverse
            # current too, except during the dead times, when the body diode
            # (reverse-conducting HEMT) does at v_sd; per position this is
            # v_sd * (I_peak/pi) * 2 t_dead f_sw for a sinusoidal current
            p_cond = n_ser * (r_on(device, t_j) * (sz.i_rms ** 2 + sz.i_rms_rev ** 2)
                              / n_par
                              + device.v_sd * sz.i_switched / math.pi
                              * 2.0 * t_dead * conv.switching_frequency)
        # Datasheet E(I) curves are concave: diode recovery and tail energy grow
        # roughly with the square root of current, so a share ``phi`` of the
        # reference energy follows I^0.5 and the rest I^gamma.  Each part is
        # averaged over the sinusoid with its own factor (hard switching only).
        phi = device.e_offset_fraction if conv.commutation == "hard" else 0.0
        e_die = switching_energy(device, v_die, i_die, t_j,
                                 conv.commutation, conv.e_rr_scale)
        e_ref = switching_energy(device, v_die, device.i_ref, t_j,
                                 conv.commutation, conv.e_rr_scale)
        sine = sz.commutation_factor < 0.99
        if sine and sz.ripple_pp > 0.0 and conv.commutation == "hard":
            # With ripple the device turns off at i + di/2 and turns on at
            # i - di/2; where the ripple reverses the current the turn-on is
            # soft.  The energy is averaged over the conducting half-wave.
            i_t = i_die * _SIN_THETA
            half = 0.5 * sz.ripple_pp / n_par
            x_on = np.maximum(i_t - half, 0.0) / device.i_ref
            x_off = (i_t + half) / device.i_ref
            gam = device.i_exponent

            def shape(x):
                return (1.0 - phi) * x ** gam + phi * np.sqrt(x)

            e_sum = device.e_on + device.e_off + conv.e_rr_scale * device.e_rr
            w_on = (device.e_on + conv.e_rr_scale * device.e_rr) / max(e_sum, 1e-15)
            e_cyc = float(e_ref) * np.mean(w_on * shape(x_on) + (1.0 - w_on) * shape(x_off))
            p_sw = conv.switching_frequency * n_par * sw_arrays * ss * 0.5 * e_cyc
        else:
            cf_half = _sine_energy_factor(0.5) if sine else 1.0
            e_sqrt = float(e_ref) * math.sqrt(max(i_die, 0.0) / device.i_ref)
            p_sw = (conv.switching_frequency * n_par * sw_arrays * ss
                    * ((1.0 - phi) * float(e_die) * sz.commutation_factor
                       + phi * e_sqrt * cf_half))
        p_pos = p_cond + p_sw
        t_new = t_ambient + p_pos * r_th_pos
        if abs(t_new - t_j) < 1e-3:
            t_j = t_new
            break
        t_j = 0.5 * t_j + 0.5 * t_new

    p_conduction = float(p_cond) * conv.n_switches
    p_switching = float(p_sw) * conv.n_switches
    # The line-frequency ("slow") leg of a totem-pole PFC is populated with
    # dedicated low-Rds silicon devices and dissipates conduction loss only.
    p_conduction += conv.n_switches_slow * conv.slow_leg_r_on * sz.i_rms ** 2
    # A series rectifier bridge carries the full rectified line current
    # (average 2*i_peak/pi) through two forward drops.
    if conv.series_diode_drop > 0.0:
        p_conduction += 2.0 * conv.series_diode_drop * (2.0 / math.pi) * sz.i_switched

    # ---- passives: copper scales with load^2, core/aux with frequency ------
    f_scale = (conv.switching_frequency / F_REF_MAGNETICS) ** 0.25
    p_passive = conv.rated_power * (conv.passive_loss_fixed * f_scale
                                    + conv.passive_loss_coeff * load_i ** 2)

    p_total = p_conduction + p_switching + p_passive
    eff = p_out / (p_out + p_total)
    t_case = t_ambient + float(p_pos) * conv.cooling_r_th
    return OperatingPoint(p_out, p_conduction, p_switching, p_passive, p_total,
                          eff, float(t_j), t_case, float(sz.i_rms), n_par, n_ser)


def efficiency_curve(conv: Converter, device: Device, t_ambient: float = 40.0,
                     n: int = 60, p_min_frac: float = 0.02
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Efficiency versus per-unit load."""
    loads = np.linspace(p_min_frac, 1.0, n)
    eff = np.array([solve_converter(conv, device, ll * conv.rated_power,
                                    t_ambient).efficiency for ll in loads])
    return loads, eff


def weighted_efficiency(conv: Converter, device: Device,
                        load_weights: dict[float, float],
                        t_ambient: float = 40.0) -> float:
    """Load-weighted (European-style) efficiency for a duty distribution."""
    num = den = 0.0
    for load, w in load_weights.items():
        num += w * solve_converter(conv, device, load * conv.rated_power,
                                   t_ambient).efficiency
        den += w
    return num / max(den, 1e-12)


TRACTION_DUTY = {0.05: 0.10, 0.10: 0.18, 0.20: 0.26, 0.35: 0.22, 0.50: 0.14,
                 0.75: 0.07, 1.00: 0.03}
CHARGING_DUTY = {0.10: 0.06, 0.25: 0.14, 0.50: 0.26, 0.70: 0.28, 0.85: 0.16,
                 1.00: 0.10}


# ---------------------------------------------------------------------------
# Topology constructors (frequency chosen from the technology)
# ---------------------------------------------------------------------------
#: Effective PWM ripple of traction drives (peak-to-peak, per unit of rated
#: peak current at 10 kHz), fitted by fit_devices.fit_light_load to the ORNL
#: inverter-efficiency maps of the 2010 Prius at 650 and 500 V and tested on
#: the 225 V map.  It carries the light-load losses the datasheet curves do
#: not (ripple-current switching, harmonics, dead time); the implied
#: inductance, about 0.2 mH for that machine, is below its physical value.
from .config import TRACTION_RIPPLE_PU_10K  # noqa: E402


def traction_inverter(rated_kw: float, dc_link: float, device: Device) -> Converter:
    return Converter(
        ripple_pu_10k=TRACTION_RIPPLE_PU_10K,
        name=f"{rated_kw:.0f} kW three-phase two-level traction inverter",
        role="traction-inverter", rated_power=rated_kw * 1e3,
        dc_link_voltage=dc_link, n_switches=6,
        switching_frequency=switching_frequency_for("traction-inverter", device),
        modulation_index=0.90, power_factor=0.92,
        # copper/busbar/capacitor loss at rating, and a standby loss of gate
        # drives, control and capacitor leakage of about 40 W
        passive_loss_coeff=0.0030, passive_loss_fixed=0.00027,
        ac_resistance_pu=0.008, cooling_r_th=0.045, specific_cost=9.5,
        bidirectional=True)


def lv_traction_inverter(rated_kw: float, dc_link: float, device: Device) -> Converter:
    """Three-phase inverter of a 48-72 V two- or three-wheeler drive.

    At these voltages the phase currents are high relative to the power, so
    board, busbar, shunt and connector resistance is a much larger share of the
    loss than in a high-voltage inverter; the passive coefficients carry it.
    """
    return Converter(
        ripple_pu_10k=TRACTION_RIPPLE_PU_10K,
        name=f"{rated_kw:.1f} kW {dc_link:.0f} V two-level drive inverter",
        role="lv-traction-inverter", rated_power=rated_kw * 1e3,
        dc_link_voltage=dc_link, n_switches=6,
        switching_frequency=switching_frequency_for("lv-traction-inverter", device),
        modulation_index=0.90, power_factor=0.90,
        passive_loss_coeff=0.012, passive_loss_fixed=0.004,
        ac_resistance_pu=0.020, cooling_r_th=0.60, specific_cost=6.0,
        bidirectional=True)


def auxiliary_dcdc(rated_kw: float, dc_link: float, device: Device) -> Converter:
    return Converter(
        name=f"{rated_kw:.1f} kW isolated auxiliary DC/DC (LLC, ZVS)", role="dcdc",
        rated_power=rated_kw * 1e3, dc_link_voltage=dc_link, n_switches=8,
        switching_frequency=switching_frequency_for("dcdc", device),
        modulation_index=1.0, power_factor=1.0,
        passive_loss_coeff=0.0090, passive_loss_fixed=0.0025,
        ac_resistance_pu=0.011, cooling_r_th=0.32, specific_cost=42.0,
        commutation="zvs")


def obc_pfc_stage(rated_kw: float, device: Device) -> Converter:
    """Power-factor-correction front end of an on-board charger.

    The bridgeless totem-pole topology is only viable in continuous conduction
    mode with a switch whose reverse-conduction path has negligible stored
    charge, i.e. with SiC or GaN.  Silicon super-junction MOSFETs and IGBTs are
    therefore modelled in the conventional diode-bridge + boost arrangement,
    which carries a rectifier forward drop but commutates against a SiC
    Schottky boost diode (docs_reference: pe-obc-totem, pe-gan-ev).
    """
    wbg = device.technology in ("SiC-MOSFET", "GaN-HEMT")
    if wbg:
        return Converter(
            name=f"{rated_kw:.1f} kW bridgeless totem-pole PFC", role="obc-pfc",
            rated_power=rated_kw * 1e3, dc_link_voltage=400.0,
            n_switches=2, n_switches_slow=2,
            switching_frequency=switching_frequency_for("obc-pfc", device),
            modulation_index=0.95, power_factor=0.99,
            passive_loss_coeff=0.0060, passive_loss_fixed=0.0018,
            ac_resistance_pu=0.012, cooling_r_th=0.30, specific_cost=26.0,
            bidirectional=True, commutation="hard", e_rr_scale=1.0)
    return Converter(
        name=f"{rated_kw:.1f} kW diode-bridge boost PFC", role="obc-pfc",
        rated_power=rated_kw * 1e3, dc_link_voltage=400.0,
        n_switches=1, n_switches_slow=0,
        switching_frequency=switching_frequency_for("obc-pfc", device),
        modulation_index=0.95, power_factor=0.99,
        passive_loss_coeff=0.0072, passive_loss_fixed=0.0022,
        ac_resistance_pu=0.013, cooling_r_th=0.30, specific_cost=22.0,
        bidirectional=False, commutation="hard", e_rr_scale=0.06,
        series_diode_drop=0.95)


def obc_dab_stage(rated_kw: float, dc_link: float, device: Device) -> Converter:
    return Converter(
        name=f"{rated_kw:.1f} kW isolated dual-active-bridge stage", role="dcdc",
        rated_power=rated_kw * 1e3, dc_link_voltage=dc_link, n_switches=8,
        switching_frequency=switching_frequency_for("dcdc", device),
        modulation_index=1.0, power_factor=1.0,
        passive_loss_coeff=0.0085, passive_loss_fixed=0.0022,
        ac_resistance_pu=0.012, cooling_r_th=0.26, specific_cost=32.0,
        bidirectional=True, commutation="zvs")


def dcfc_front_end(rated_kw: float, dc_link: float, device: Device) -> Converter:
    return Converter(
        name=f"{rated_kw:.0f} kW active front end of a DC fast charger",
        role="dcfc-afe", rated_power=rated_kw * 1e3, dc_link_voltage=dc_link,
        n_switches=6, switching_frequency=switching_frequency_for("dcfc-afe", device),
        modulation_index=0.92, power_factor=0.99,
        passive_loss_coeff=0.0060, passive_loss_fixed=0.0020,
        ac_resistance_pu=0.009, cooling_r_th=0.030, specific_cost=27.0,
        bidirectional=True)


def dcfc_isolation(rated_kw: float, dc_link: float, device: Device) -> Converter:
    return Converter(
        name=f"{rated_kw:.0f} kW isolated DC/DC stage of a DC fast charger",
        role="dcfc-dcdc", rated_power=rated_kw * 1e3, dc_link_voltage=dc_link,
        n_switches=8, switching_frequency=switching_frequency_for("dcfc-dcdc", device),
        modulation_index=1.0, power_factor=1.0,
        passive_loss_coeff=0.0085, passive_loss_fixed=0.0026,
        ac_resistance_pu=0.012, cooling_r_th=0.028, specific_cost=34.0,
        bidirectional=True, commutation="zvs")


def solid_state_transformer(rated_kw: float, device: Device, cells: int = 6,
                            cell_voltage: float = 1500.0) -> Converter:
    return Converter(
        name=f"{rated_kw:.0f} kW cascaded solid-state transformer ({cells} cells/phase)",
        role="sst", rated_power=rated_kw * 1e3, dc_link_voltage=cell_voltage,
        n_switches=12 * cells, switching_frequency=switching_frequency_for("sst", device),
        modulation_index=0.95, power_factor=0.99,
        passive_loss_coeff=0.0070, passive_loss_fixed=0.0031,
        ac_resistance_pu=0.010, cooling_r_th=0.055, specific_cost=118.0,
        bidirectional=True)


# ---------------------------------------------------------------------------
# Conversion chains
# ---------------------------------------------------------------------------
def _q(rated_kw: float, dc_link: float, t_ambient: float) -> tuple[float, float, float]:
    """Cache quantisation: 0.1 kW, 50 V and 2 K.

    Drive-cycle efficiency changes by less than 0.02 percentage points over one
    step of either (Supplementary Section S2), which is far below the precision
    with which either quantity is known, while the coarse grid keeps the
    Monte-Carlo and lever-space campaigns tractable.
    """
    return (round(rated_kw, 1), round(dc_link / 50.0) * 50.0,
            round(t_ambient / 2.0) * 2.0)


def _qm(mult: float) -> float:
    """Device-parameter multipliers are quantised to 5 %."""
    return round(round(mult / 0.05) * 0.05, 3)


@lru_cache(maxsize=16384)
def _powertrain_efficiency_cached(device_key: str, rated_kw: float, dc_link: float,
                                  t_ambient: float, esw: float, ron: float,
                                  mission: Mission | None
                                  ) -> tuple[float, float, float, float]:
    d = powertrain_efficiency(device_key, rated_kw, dc_link, t_ambient, esw, ron,
                              mission)
    return (d["inverter"], d["auxiliary_dcdc"], d["traction_chain"],
            d["f_sw_inverter"])


def powertrain_efficiency_fast(device_key: str, rated_kw: float = 150.0,
                               dc_link: float = 400.0, t_ambient: float = 40.0,
                               esw_mult: float = 1.0, ron_mult: float = 1.0,
                               mission: Mission | None = None) -> dict[str, float]:
    """Memoised wrapper on :func:`powertrain_efficiency`."""
    inv, aux, chain, f = _powertrain_efficiency_cached(
        device_key, *_q(rated_kw, dc_link, t_ambient),
        _qm(esw_mult), _qm(ron_mult), mission)
    return {"inverter": inv, "auxiliary_dcdc": aux, "traction_chain": chain,
            "f_sw_inverter": f}


@lru_cache(maxsize=16384)
def _charging_path_cached(device_key: str, coupling: str, rated_kw: float,
                          dc_link: float, t_ambient: float, esw: float, ron: float
                          ) -> tuple[float, float, float, float]:
    d = charging_path_efficiency(device_key, coupling, rated_kw, dc_link, t_ambient,
                                 esw, ron)
    return d["stage_1"], d["stage_2"], d["path"], d["f_sw"]


def charging_path_efficiency_fast(device_key: str, coupling: str, rated_kw: float,
                                  dc_link: float = 800.0, t_ambient: float = 40.0,
                                  esw_mult: float = 1.0,
                                  ron_mult: float = 1.0) -> dict[str, float]:
    """Memoised wrapper on :func:`charging_path_efficiency`."""
    s1, s2, path, f = _charging_path_cached(
        device_key, coupling, *_q(rated_kw, dc_link, t_ambient),
        _qm(esw_mult), _qm(ron_mult))
    return {"stage_1": s1, "stage_2": s2, "path": path, "f_sw": f}


def powertrain_efficiency(device_key: str, rated_kw: float = 150.0,
                          dc_link: float = 400.0, t_ambient: float = 40.0,
                          esw_mult: float = 1.0, ron_mult: float = 1.0,
                          mission: Mission | None = None) -> dict[str, float]:
    """Efficiency of the traction path (inverter + auxiliary DC/DC).

    ``device_key`` may name a high-voltage technology (the device actually used
    at ``dc_link`` is selected by :func:`evdt.config.device_for`) or a 100 V
    technology, in which case the 48-72 V drive inverter is used and there is
    no separate auxiliary converter.  With a ``mission`` the inverter
    efficiency is the drive-cycle energy efficiency of :func:`cycle_efficiency`;
    without one it is the load-weighted value over ``TRACTION_DUTY``, kept for
    comparison with datasheet-style figures.
    """
    dev = perturbed(device_for(device_key, dc_link), esw_mult, ron_mult)

    def eta_of(inv):
        if mission is not None:
            return cycle_efficiency(device_key, rated_kw, dc_link, mission, t_ambient,
                                    esw_mult, ron_mult)
        return weighted_efficiency(inv, dev, TRACTION_DUTY, t_ambient)

    if device_key in LV_DEVICE_LIBRARY:
        inv = lv_traction_inverter(rated_kw, dc_link, dev)
        eta_inv = eta_of(inv)
        return {"inverter": eta_inv, "auxiliary_dcdc": 1.0,
                "traction_chain": eta_inv, "f_sw_inverter": inv.switching_frequency}
    inv = traction_inverter(rated_kw, dc_link, dev)
    dev_aux = perturbed(charger_device_for(device_key, dc_link), esw_mult, ron_mult)
    aux = auxiliary_dcdc(2.5, dc_link, dev_aux)
    eta_inv = eta_of(inv)
    eta_aux = weighted_efficiency(aux, dev_aux, CHARGING_DUTY, t_ambient)
    return {"inverter": eta_inv, "auxiliary_dcdc": eta_aux,
            "traction_chain": eta_inv * (0.97 + 0.03 * eta_aux),
            "f_sw_inverter": inv.switching_frequency}


def charging_path_efficiency(device_key: str, coupling: str, rated_kw: float,
                             dc_link: float = 800.0, t_ambient: float = 40.0,
                             esw_mult: float = 1.0,
                             ron_mult: float = 1.0) -> dict[str, float]:
    """Wall-plug-to-battery efficiency of an AC (on-board) or DC charging path."""
    if coupling == "ac":
        # The front end sits on the 230 V mains and the isolation stage on a
        # 400 V intermediate link, whatever the battery voltage.
        dev = perturbed(CHARGER_DEVICE_LIBRARY[device_key], esw_mult, ron_mult)
        pfc = obc_pfc_stage(rated_kw, dev)
        dab = obc_dab_stage(rated_kw, 400.0, dev)
        e1 = weighted_efficiency(pfc, dev, CHARGING_DUTY, t_ambient)
        e2 = weighted_efficiency(dab, dev, CHARGING_DUTY, t_ambient)
        return {"stage_1": e1, "stage_2": e2, "path": e1 * e2,
                "f_sw": pfc.switching_frequency}
    dev = perturbed(charger_device_for(device_key, dc_link), esw_mult, ron_mult)
    afe = dcfc_front_end(rated_kw, dc_link, dev)
    iso = dcfc_isolation(rated_kw, dc_link, dev)
    e1 = weighted_efficiency(afe, dev, CHARGING_DUTY, t_ambient)
    e2 = weighted_efficiency(iso, dev, CHARGING_DUTY, t_ambient)
    return {"stage_1": e1, "stage_2": e2, "path": e1 * e2,
            "f_sw": afe.switching_frequency}


def blended_efficiency(eta_by_device: dict[str, float],
                       shares: dict[str, float]) -> float:
    """Fleet-level efficiency for a mix of semiconductor technologies."""
    total = sum(shares.values())
    if total <= 0:
        return float(np.mean(list(eta_by_device.values())))
    return sum(eta_by_device[k] * s for k, s in shares.items() if k in eta_by_device) / total


# ---------------------------------------------------------------------------
# Power density
# ---------------------------------------------------------------------------
def power_density(conv: Converter, device: Device,
                  t_ambient: float = 40.0) -> dict[str, float]:
    """Volumetric power density [kW/L] from magnetics, cooling and die volume.

    Magnetic and capacitive volume scale approximately as ``f^-0.6``; the heat
    sink scales with dissipated loss; the die/package volume scales with the
    number of dies.  Coefficients are normalised so that a Si-IGBT traction
    inverter lands near 12 kW/L.
    """
    op = solve_converter(conv, device, conv.rated_power, t_ambient)
    kw = conv.rated_power / 1e3
    v_mag = 0.062 * kw * (conv.switching_frequency / F_REF_MAGNETICS) ** -0.60
    v_cool = 0.145 * (op.p_total / 1e3) ** 0.85
    v_die = 0.0016 * conv.n_switches * op.n_parallel * op.n_series
    v_total = max(v_mag + v_cool + v_die, 1e-6)
    return {"kw_per_litre": kw / v_total, "volume_litre": v_total,
            "v_magnetics": v_mag, "v_cooling": v_cool, "v_semiconductor": v_die}


# ---------------------------------------------------------------------------
# Reliability: power cycling
# ---------------------------------------------------------------------------
def cycles_to_failure(device: Device, delta_tj: np.ndarray | float,
                      tj_mean_c: np.ndarray | float) -> np.ndarray:
    """LESIT-type power-cycling capability [cycles].

    ``N_f = A * dTj^{-n} * exp(Ea / (k_B * T_jm))`` with ``T_jm`` in kelvin.
    """
    dt = np.maximum(np.asarray(delta_tj, dtype=float), 1.0)
    tjm_k = np.asarray(tj_mean_c, dtype=float) + 273.15
    return (PC_SCALE * device.pc_coefficient * np.power(dt, -device.pc_exponent)
            * np.exp(device.activation_energy / (BOLTZMANN_EV * tjm_k)))


def rainflow_swings(temperature: np.ndarray
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Three-point rainflow extraction of thermal swings from a profile.

    Returns ``(delta_tj, tj_mean, count)``.
    """
    x = np.asarray(temperature, dtype=float)
    if x.size < 3:
        return np.array([]), np.array([]), np.array([])
    d = np.diff(x)
    nz = np.flatnonzero(d)
    if nz.size < 2:
        return np.array([]), np.array([]), np.array([])
    idx = np.flatnonzero(np.sign(d[nz][:-1]) != np.sign(d[nz][1:]))
    turn = nz[idx] + 1
    tp = np.concatenate(([x[0]], x[turn], [x[-1]]))

    stack: list[float] = []
    rng, mean, cnt = [], [], []
    for point in tp:
        stack.append(float(point))
        while len(stack) >= 3:
            a, b, c = stack[-3], stack[-2], stack[-1]
            if abs(b - a) <= abs(c - b):
                rng.append(abs(b - a))
                mean.append(0.5 * (a + b))
                cnt.append(1.0)
                del stack[-3:-1]
            else:
                break
    for i in range(len(stack) - 1):
        rng.append(abs(stack[i + 1] - stack[i]))
        mean.append(0.5 * (stack[i] + stack[i + 1]))
        cnt.append(0.5)
    return np.array(rng), np.array(mean), np.array(cnt)


def mission_profile_damage(device: Device, tj_profile: np.ndarray,
                           years: float = 1.0) -> dict[str, float]:
    """Miner damage accumulated by a mission profile of length ``years``."""
    dt, tm, cnt = rainflow_swings(tj_profile)
    if dt.size == 0:
        return {"damage_per_year": 0.0, "b10_years": float("inf"), "n_cycles": 0.0,
                "delta_tj_p95": 0.0, "tj_max": float(np.max(tj_profile))}
    nf = cycles_to_failure(device, dt, tm)
    damage = float(np.sum(cnt / np.maximum(nf, 1.0))) / max(years, 1e-9)
    eta_life = 1.0 / max(damage, 1e-12)                     # characteristic life
    b10 = eta_life * (math.log(1.0 / 0.9) ** (1.0 / 3.0))   # Weibull shape 3
    return {"damage_per_year": damage, "b10_years": float(b10),
            "n_cycles": float(np.sum(cnt)),
            "delta_tj_p95": float(np.percentile(dt, 95)),
            "tj_max": float(np.max(tj_profile))}


def converter_failure_rate(device: Device, tj_profile: np.ndarray, n_switches: int,
                           years: float = 1.0) -> float:
    """Annual failure probability of a converter with ``n_switches`` positions."""
    d = mission_profile_damage(device, tj_profile, years)["damage_per_year"]
    return float(1.0 - (1.0 - min(d, 1.0)) ** n_switches)


# ---------------------------------------------------------------------------
# Sub-hourly mission profiles
# ---------------------------------------------------------------------------
# An hourly simulation cannot resolve the thermal cycles that drive bond-wire
# fatigue: an urban drive produces a swing at every acceleration, lasting
# seconds.  Traction reliability is therefore evaluated on a synthetic 0.1 s
# drive cycle passed through a Foster thermal network, and the result is scaled
# to the annual driving time.  Charger reliability is evaluated per charging
# session, the natural thermal cycle of a charger front end.
FOSTER_TAU_S = (0.02, 0.30, 4.0)        # die, die-attach/substrate, cooler
FOSTER_SPLIT_JC = (0.35, 0.65)          # share of R_th,jc in the first two cells
B10_CENSOR_YEARS = 50.0


def urban_drive_cycle(mean_speed_kmh: float, v_max_kmh: float, seed: int = 0,
                      duration_s: float = 1800.0, dt: float = 0.1,
                      acc_range: tuple[float, float] = (0.7, 1.5),
                      dec_range: tuple[float, float] = (0.7, 1.3)) -> np.ndarray:
    """Synthetic micro-trip speed trace [m/s] with a prescribed mean speed.

    Micro-trips of idle, acceleration, cruise and deceleration are drawn from
    uniform ranges typical of congested urban driving, and the idle periods are
    then stretched or compressed so that the cycle mean equals
    ``mean_speed_kmh``.  The same generator is used for every device, so the
    comparison between technologies is on an identical mission.
    """
    rng = np.random.default_rng(seed)
    vmax = v_max_kmh / 3.6
    segs: list[tuple[str, float, float, float]] = []   # kind, duration, v0, v1
    t = 0.0
    while t < duration_s:
        idle = rng.uniform(4.0, 25.0)
        vp = rng.uniform(0.35, 1.0) * vmax
        acc = rng.uniform(*acc_range)
        dec = rng.uniform(*dec_range)
        cruise = rng.uniform(3.0, 45.0)
        segs += [("idle", idle, 0.0, 0.0), ("acc", vp / acc, 0.0, vp),
                 ("cruise", cruise, vp, vp), ("dec", vp / dec, vp, 0.0)]
        t += idle + vp / acc + cruise + vp / dec
    moving = sum(d * (0.5 * (a + b)) for k, d, a, b in segs if k != "idle")
    t_moving = sum(d for k, d, a, b in segs if k != "idle")
    t_idle = sum(d for k, d, a, b in segs if k == "idle")
    target = mean_speed_kmh / 3.6
    idle_needed = max(moving / max(target, 1e-6) - t_moving, 0.05 * t_idle)
    stretch = idle_needed / max(t_idle, 1e-9)
    v = []
    for kind, d, a, b in segs:
        d_eff = d * stretch if kind == "idle" else d
        n = max(int(round(d_eff / dt)), 1)
        v.append(np.linspace(a, b, n, endpoint=False))
    return np.concatenate(v)


#: Split of a junction-to-coolant resistance over die, substrate and cooler
#: cells when the module datasheet states only that value.
FOSTER_SPLIT_JF = (0.25, 0.45, 0.30)


def foster_cells(inv: Converter, dev: Device) -> tuple[float, float, float]:
    """Foster resistances of one switch position: die, substrate, cooler."""
    rjx = dev.r_th_jc / max(size_switch_position(inv, dev).n_dies, 1)
    if dev.rth_to_fluid:
        return tuple(f * rjx for f in FOSTER_SPLIT_JF)
    return (FOSTER_SPLIT_JC[0] * rjx, FOSTER_SPLIT_JC[1] * rjx, inv.cooling_r_th)


def foster_junction(loss_w: np.ndarray, r_cells: tuple[float, ...],
                    tau_s: tuple[float, ...], t_coolant: float,
                    dt: float = 0.1) -> np.ndarray:
    """Junction temperature of one switch position from a Foster network.

    Exact for piecewise-constant loss within each step.
    """
    t_cells = np.array([r * float(loss_w[0]) for r in r_cells])
    decay = np.exp(-dt / np.asarray(tau_s))
    out = np.empty(loss_w.size)
    for k, p in enumerate(loss_w):
        t_cells = t_cells * decay + np.asarray(r_cells) * p * (1.0 - decay)
        out[k] = t_coolant + t_cells.sum()
    return out


def _cycle_damage(device: Device, dt_k: np.ndarray, tm_c: np.ndarray,
                  cnt: np.ndarray) -> tuple[float, float]:
    """Miner damage of a set of cycles, total and within the calibrated range."""
    if dt_k.size == 0:
        return 0.0, 0.0
    nf = cycles_to_failure(device, dt_k, tm_c)
    d = cnt / np.maximum(nf, 1.0)
    lo, hi = DEVICE_VALIDITY["power_cycling_delta_tj_k"]
    inside = (dt_k >= lo) & (dt_k <= hi)
    return float(d.sum()), float(d[inside].sum())


def traction_reliability(device_key: str, rated_kw: float, dc_link: float,
                         vehicle_mass: float, frontal_area: float, cd: float,
                         crr: float, drivetrain_eff: float, annual_km: float,
                         mean_speed_kmh: float, trips_per_day: float,
                         t_ambient: float = 30.0, seed: int = 0) -> dict[str, float]:
    """Power-cycling life of a traction inverter on a sub-hourly mission.

    Fast cycles come from a 0.1 s drive cycle; one slow cycle per trip comes
    from the warm-up of the cooling loop.  B10 is censored at
    :data:`B10_CENSOR_YEARS` and is reported only with the share of damage that
    lies inside the swing range on which the lifetime law was fitted.
    """
    dev = device_for(device_key, dc_link)
    lv = device_key in LV_DEVICE_LIBRARY
    inv = (lv_traction_inverter if lv else traction_inverter)(rated_kw, dc_link, dev)
    heavy = vehicle_mass > 5000.0
    v_max = 50.0 if (lv or heavy) else 70.0
    acc = (0.4, 0.9) if heavy else (0.7, 1.5)
    dec = (0.5, 1.0) if heavy else (0.7, 1.3)
    dt = 0.1
    v = urban_drive_cycle(mean_speed_kmh, v_max, seed=seed, dt=dt,
                          acc_range=acc, dec_range=dec)
    a = np.gradient(v, dt)
    f = (crr * vehicle_mass * 9.81 + 0.5 * 1.2 * cd * frontal_area * v ** 2
         + vehicle_mass * a)
    p_wheel = f * v
    p_inv = np.where(p_wheel >= 0.0, p_wheel / drivetrain_eff,
                     np.maximum(p_wheel * drivetrain_eff * 0.62, -inv.rated_power))
    # the drive cannot deliver more than its rating; acceleration is
    # power-limited above it
    load = np.clip(np.abs(p_inv) / inv.rated_power, 0.0, 1.0)

    t_cool = t_ambient + 20.0
    loss = cycle_losses(inv, dev, load * inv.rated_power, v, base_speed_ms(lv, heavy),
                        t_cool, per_position=True)
    tj = foster_junction(loss, foster_cells(inv, dev), FOSTER_TAU_S, t_cool, dt)

    dtk, tmc, cnt = rainflow_swings(tj)
    cycle_hours = v.size * dt / 3600.0
    drive_hours = annual_km / max(mean_speed_kmh, 1.0)
    scale = drive_hours / max(cycle_hours, 1e-9)
    lo, hi = DEVICE_VALIDITY["power_cycling_delta_tj_k"]
    inside = (dtk >= lo) & (dtk <= hi)
    # Lifetimes are deliberately not reported: published power-cycling laws
    # are fitted on swings of roughly 30-130 K in silicon IGBT modules, and
    # most of the swings below lie outside that range or concern packages
    # (SiC, GaN) the laws were not fitted on.  The swing statistics are the
    # physical result; the share inside the calibrated range says where a
    # lifetime law could legitimately be applied.
    return {"device": device_key, "device_fitted": dev.name,
            "fast_cycles_per_year": float(cnt.sum() * scale),
            "cycles_in_calibrated_range_per_year": float(cnt[inside].sum() * scale),
            "share_cycles_in_calibrated_range": float(cnt[inside].sum()
                                                      / max(cnt.sum(), 1e-12)),
            "delta_tj_fast_median_k": float(np.median(dtk)) if dtk.size else 0.0,
            "delta_tj_fast_p95_k": float(np.percentile(dtk, 95)) if dtk.size else 0.0,
            "delta_tj_fast_max_k": float(dtk.max()) if dtk.size else 0.0,
            "delta_tj_trip_k": float(np.mean(tj)) - t_ambient,
            "trips_per_year": trips_per_day * 365.0,
            "tj_max_c": float(tj.max()),
            "tj_mean_c": float(np.mean(tj))}


#: Mission of a vehicle segment for drive-cycle-weighted efficiency:
#: (mass kg, frontal area m2, Cd, Crr, drivetrain efficiency, cycle), where
#: cycle is a standard-cycle key (see :func:`standard_cycle`) or a mean speed
#: in km/h for the synthetic urban cycle.
Mission = tuple[float, float, float, float, float, float | str]


def mission_of(seg, cycle: float | str) -> Mission:
    """The efficiency entry is drivetrain times motor, wheel to inverter AC side."""
    return (float(seg.mass), float(seg.frontal_area), float(seg.drag_coefficient),
            float(seg.rolling_resistance),
            float(seg.drivetrain_efficiency * getattr(seg, "motor_efficiency", 1.0)),
            cycle if isinstance(cycle, str) else round(float(cycle), 1))


CYCLE_DATA = Path(__file__).resolve().parents[1] / "data" / "cycles"
#: WLTC class 3 phase boundaries [s] (UN GTR No. 15)
WLTC_PHASES = {"low": (0, 589), "medium": (589, 1022), "high": (1022, 1477),
               "extra_high": (1477, 1800)}


@lru_cache(maxsize=32)
def standard_cycle(key: str, dt: float = 0.1) -> np.ndarray:
    """Speed trace [m/s] of a standard cycle resampled to ``dt``.

    ``key`` names ``data/cycles/<stem>.csv`` (t_s, speed_kmh at 1 Hz),
    optionally followed by ``:`` and contiguous WLTC phases joined by ``+``
    (e.g. ``"wltc3b:low+medium"`` for congested urban driving).
    """
    stem, _, phases = key.partition(":")
    data = np.loadtxt(CYCLE_DATA / f"{stem}.csv", delimiter=",", skiprows=1,
                      comments="#")
    t, v = data[:, 0], data[:, 1] / 3.6
    if phases:
        names = phases.split("+")
        a, b = WLTC_PHASES[names[0]][0], WLTC_PHASES[names[-1]][1]
        keep = (t >= a) & (t <= b)
        t, v = t[keep] - a, v[keep]
    tt = np.arange(0.0, t[-1], dt)
    return np.interp(tt, t, v)


#: Vehicle speed at which the machine reaches base speed [km/h].  Below it the
#: machine voltage, and with it the inverter modulation index, rises in
#: proportion to speed while the current follows torque; above it the voltage
#: is at its limit (field weakening).  Assumed: a 150 kW, 310 N m car machine
#: with a 9:1 reduction reaches base speed near 55 km/h; hub motors of two- and
#: three-wheelers near 25 km/h; city buses near 30 km/h.
BASE_SPEED_KMH = {"car": 55.0, "lv": 25.0, "heavy": 30.0}
#: Modulation grid (fractions of the nominal index) for the loss tables.
M_GRID_FRAC = np.array([0.04, 0.12, 0.30, 0.60, 1.0])


def base_speed_ms(lv: bool, heavy: bool) -> float:
    return BASE_SPEED_KMH["lv" if lv else "heavy" if heavy else "car"] / 3.6


def cycle_losses(inv: Converter, dev: Device, p: np.ndarray, v: np.ndarray,
                 v_base: float, t_cool: float, per_position: bool = False) -> np.ndarray:
    """Converter loss at every drive-cycle step, from a table over power and
    modulation index (operating point set by torque and speed, not by power
    alone).  ``per_position``: semiconductor loss of one switch position, for
    the thermal network; otherwise the total converter loss."""
    m_nom = inv.modulation_index
    m_step = m_nom * np.clip(np.abs(v) / max(v_base, 1e-6), M_GRID_FRAC[0], 1.0)
    grid = np.concatenate(([0.0], np.geomspace(0.002, 1.0, 29))) * inv.rated_power
    m_grid = m_nom * M_GRID_FRAC

    def val(o: OperatingPoint) -> float:
        return ((o.p_conduction + o.p_switching) / inv.n_switches if per_position
                else o.p_total)

    table = np.array([[val(solve_converter(inv, dev, g, t_cool, modulation=m))
                       for g in grid] for m in m_grid])
    p = np.minimum(np.abs(p), inv.rated_power)
    per_m = np.array([np.interp(p, grid, row) for row in table])
    idx = np.clip(np.searchsorted(m_grid, m_step), 1, m_grid.size - 1)
    w = (m_step - m_grid[idx - 1]) / (m_grid[idx] - m_grid[idx - 1])
    cols = np.arange(p.size)
    return per_m[idx - 1, cols] * (1.0 - w) + per_m[idx, cols] * w


@lru_cache(maxsize=4096)
def _cycle_power(mission: Mission, lv: bool, seed: int = 0
                 ) -> tuple[np.ndarray, np.ndarray, float]:
    mass, area, cd, crr, eta_dt, cycle = mission
    heavy = mass > 5000.0
    dt = 0.1
    if isinstance(cycle, str):
        v = standard_cycle(cycle, dt)
    else:
        v = urban_drive_cycle(cycle, 50.0 if (lv or heavy) else 70.0, seed=seed, dt=dt,
                              acc_range=(0.4, 0.9) if heavy else (0.7, 1.5),
                              dec_range=(0.5, 1.0) if heavy else (0.7, 1.3))
    a = np.gradient(v, dt)
    p_wheel = (crr * mass * 9.81 + 0.5 * 1.2 * cd * area * v ** 2 + mass * a) * v
    # inverter output (motoring) or input (regenerating) power at the AC side
    p_ac = np.where(p_wheel >= 0.0, p_wheel / eta_dt, p_wheel * eta_dt * 0.62)
    return p_ac, v, dt


@lru_cache(maxsize=256)
def cycle_wheel_energy(mission: Mission, lv: bool, regen_recovery: float) -> float:
    """Net tractive energy at the wheels [Wh/km] over the segment's drive cycle.

    The same speed trace as the converter efficiency (:func:`_cycle_power`) is
    used, so energy use and converter losses refer to one operating profile.
    Braking energy is recovered in the fraction ``regen_recovery``.  The earlier
    estimate from the mean speed and a stop density understated urban use,
    because aerodynamic and acceleration energy grow with the square of the
    instantaneous speed: an electric two-wheeler came out at 17 Wh/km, below
    the 20-60 Wh/km reported.
    """
    mass, area, cd, crr, _eta, _cycle = mission
    _p, v, dt = _cycle_power(mission, lv)
    a = np.gradient(v, dt)
    p = (crr * mass * 9.81 + 0.5 * 1.2 * cd * area * v ** 2 + mass * a) * v
    km = float(v.sum()) * dt / 1000.0
    e_traction = float(p[p > 0.0].sum()) * dt
    e_braking = -float(p[p < 0.0].sum()) * dt
    return (e_traction - regen_recovery * e_braking) / 3600.0 / max(km, 1e-9)


def cycle_efficiency(device_key: str, rated_kw: float, dc_link: float,
                     mission: Mission, t_coolant: float = 40.0,
                     esw_mult: float = 1.0, ron_mult: float = 1.0) -> float:
    """Energy efficiency of a traction inverter over the segment's drive cycle.

    Losses are evaluated at every 0.1 s step from the electro-thermal solution
    at that step's load, including the standby loss while the vehicle idles,
    and the efficiency is the ratio of energy delivered to energy drawn over
    the whole cycle.  This replaces a fixed load-weighting, which put the
    average operating point near 28 % of rating, whereas urban driving keeps a
    car inverter below 10 % most of the time, where silicon is least efficient.
    """
    dev = perturbed(device_for(device_key, dc_link), esw_mult, ron_mult)
    lv = device_key in LV_DEVICE_LIBRARY
    inv = (lv_traction_inverter if lv else traction_inverter)(rated_kw, dc_link, dev)
    p_ac, v, dt = _cycle_power(mission, lv)
    p = np.minimum(np.abs(p_ac), inv.rated_power)
    p_loss = cycle_losses(inv, dev, p, v, base_speed_ms(lv, mission[0] > 5000.0),
                          t_coolant)
    return float(p.sum() / (p.sum() + p_loss.sum()))


def drive_cycle_trace(device_key: str, rated_kw: float, dc_link: float, seg,
                      mean_speed_kmh: float, t_ambient: float = 30.0,
                      seconds: float = 300.0, seed: int = 0) -> dict[str, np.ndarray]:
    """Speed, inverter load and junction temperature over a cycle excerpt,
    for plotting the sub-hourly mission (same construction as above)."""
    dev = device_for(device_key, dc_link)
    lv = device_key in LV_DEVICE_LIBRARY
    inv = (lv_traction_inverter if lv else traction_inverter)(rated_kw, dc_link, dev)
    heavy = seg.mass > 5000.0
    dt = 0.1
    v = urban_drive_cycle(mean_speed_kmh, 50.0 if (lv or heavy) else 70.0, seed=seed,
                          dt=dt, acc_range=(0.4, 0.9) if heavy else (0.7, 1.5),
                          dec_range=(0.5, 1.0) if heavy else (0.7, 1.3))
    a = np.gradient(v, dt)
    f = (seg.rolling_resistance * seg.mass * 9.81
         + 0.5 * 1.2 * seg.drag_coefficient * seg.frontal_area * v ** 2 + seg.mass * a)
    p_wheel = f * v
    eta_m = seg.drivetrain_efficiency * getattr(seg, "motor_efficiency", 1.0)
    p_inv = np.where(p_wheel >= 0.0, p_wheel / eta_m,
                     np.maximum(p_wheel * eta_m * 0.62, -inv.rated_power))
    load = np.clip(np.abs(p_inv) / inv.rated_power, 0.0, 1.0)
    t_cool = t_ambient + 20.0
    per_step = cycle_losses(inv, dev, load * inv.rated_power, v,
                            base_speed_ms(lv, heavy), t_cool, per_position=True)
    sz = size_switch_position(inv, dev)
    tj = foster_junction(per_step, foster_cells(inv, dev), FOSTER_TAU_S, t_cool, dt)
    n = int(seconds / dt)
    t = np.arange(v.size) * dt
    return {"t_s": t[:n], "speed_kmh": v[:n] * 3.6, "load": load[:n], "tj_c": tj[:n]}


@lru_cache(maxsize=4096)
def _session_swing(device_key: str, rated_kw: float, dc_link: float,
                   t_ambient: float, esw: float, ron: float) -> tuple[float, float]:
    dev = perturbed(charger_device_for(device_key, dc_link), esw, ron)
    afe = dcfc_front_end(rated_kw, dc_link, dev)
    op = solve_converter(afe, dev, 0.8 * afe.rated_power, t_ambient)
    return op.t_junction - t_ambient, 0.5 * (op.t_junction + t_ambient)


def charger_session_failure_rate(device_key: str, sessions_per_year: float,
                                 t_ambient: float, rated_kw: float = 150.0,
                                 dc_link: float = 800.0, esw_mult: float = 1.0,
                                 ron_mult: float = 1.0) -> float:
    """Annual wear-out failure probability of a DC fast-charger front end.

    Each charging session is one thermal cycle from idle to the session load
    (taken as 80 % of rating), which is the cycle a charger front end actually
    experiences; it is resolved per session rather than per simulation hour.
    """
    dt_k, tm = _session_swing(device_key, *_q(rated_kw, dc_link, t_ambient),
                              _qm(esw_mult), _qm(ron_mult))
    dev = charger_device_for(device_key, dc_link)
    nf = float(cycles_to_failure(dev, dt_k, tm))
    d = sessions_per_year / max(nf, 1.0)
    return float(1.0 - (1.0 - min(d, 1.0)) ** 6)


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------
def converter_cost(conv: Converter, device: Device, learning_factor: float = 1.0,
                   local_manufacturing: float = 0.0,
                   import_duty: float = 0.0) -> float:
    """Installed cost of a converter [USD]."""
    sz = size_switch_position(conv, device)
    # a three-level leg carries two clamping positions per phase in addition to
    # the four series-connected switches
    ml = 1.5 if (sz.n_series == 2 and device.technology in MULTILEVEL_TECH) else 1.0
    die_cost = conv.n_switches * sz.n_dies * ml * device.i_rating * device.cost_per_a
    balance = conv.specific_cost * conv.rated_power / 1e3
    base = (die_cost + balance) * learning_factor
    return float(base + base * (1.0 - local_manufacturing) * import_duty)


def thermal_derating(conv: Converter, device: Device,
                     t_ambient: np.ndarray | float,
                     t_j_max: float = 175.0, tol: float = 1e-3) -> np.ndarray:
    """Deliverable output-power fraction as the coolant temperature rises.

    The limit is found by bisecting the load fraction until the self-consistent
    junction temperature returned by :func:`solve_converter` reaches ``t_j_max``.
    Because the electro-thermal solution depends on the device's on-state
    resistance, switching energy, die count and junction-to-case resistance, the
    resulting curve is genuinely device-specific: a low-loss device retains full
    output to a much higher coolant temperature than a lossy one.
    """
    t_a = np.atleast_1d(np.asarray(t_ambient, dtype=float))
    out = np.empty_like(t_a)
    for i, ta in enumerate(t_a):
        if solve_converter(conv, device, conv.rated_power, float(ta)).t_junction <= t_j_max:
            out[i] = 1.0
            continue
        lo, hi = 0.0, 1.0
        while hi - lo > tol:
            mid = 0.5 * (lo + hi)
            tj = solve_converter(conv, device, mid * conv.rated_power,
                                 float(ta)).t_junction
            if tj > t_j_max:
                hi = mid
            else:
                lo = mid
        out[i] = lo
    return out if out.size > 1 else float(out[0])
