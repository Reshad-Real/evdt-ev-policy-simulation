"""Stage -1: power-device parameters fitted to manufacturer datasheets.

The loss parameters of the switch positions are fitted to named automotive
power modules instead of representative device classes (third revision):

==================  ==========================  =================================
slot                part                        use
==================  ==========================  =================================
Si-IGBT             Infineon FS820R08A6P2B      750 V EDT2 IGBT + EmCon diode,
                                                links up to 625 V
Si-IGBT (HV)        Infineon FS380R12A6T4B      1200 V IGBT4, 800 V links
SiC-MOSFET          Infineon FS01MR08A8MA2C     750 V CoolSiC G2, 620 A; the
                                                current dependence of its
                                                switching energy is taken from
                                                FS02MR08A7MA2B (same chip
                                                generation), whose curves are
                                                published
SiC-MOSFET (HV)     Infineon FS03MR12A6MA1B     1200 V CoolSiC, 800 V links
GaN-HEMT            Transphorm TP65H035G4WS     650 V cascode GaN, 35 mOhm
==================  ==========================  =================================

Fits, each at the hot junction temperature of the datasheet curves:

* IGBT: V_CE = V_CE0 + r_CE I over 10-100 % of nominal current; the diode
  likewise (V_F0, r_F).
* MOSFET/HEMT: R_DS(on) at 25 C and the hot temperature, linear in T.
* Switching energy E_on + E_off + E_rec: the 25 C value at the datasheet test
  point, a linear temperature coefficient from the hot test value, and the
  current dependence E(I) = E_ref [(1-phi)(I/I_ref)^gamma + phi (I/I_ref)^0.5]
  fitted to the digitised hot curves; voltage scales linearly.
* Thermal resistance: junction-to-fluid per switch (the modules do not state
  junction-to-case), so the traction inverter adds no separate cooler term.

Silicon super-junction MOSFETs and the 100 V devices of two- and three-wheeler
drives keep representative parameters (no datasheet fit; flagged in the
library).  Outputs: ``configs/device_library.json`` (read by evdt.config) and
``results/device_fit.csv`` (datasheet value, model value and error at every
fitted point).

Usage:  py -3 fit_devices.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evdt import config as cfgmod  # noqa: E402

ROOT = HERE.parent
DATA = HERE / "data" / "devices"
RESULTS = ROOT / "results"
OUT = HERE / "configs" / "device_library.json"

SLOTS = {
    "Si-IGBT": {"part": "FS820R08A6P2B", "kind": "igbt", "t_hot": 150.0},
    "HV:Si-IGBT": {"part": "FS380R12A6T4B", "kind": "igbt", "t_hot": 150.0},
    "SiC-MOSFET": {"part": "FS01MR08A8MA2C", "kind": "mosfet", "t_hot": 175.0,
                   "shape_from": "FS02MR08A7MA2B", "vgs": 18.0},
    "HV:SiC-MOSFET": {"part": "FS03MR12A6MA1B", "kind": "mosfet", "t_hot": 150.0,
                      "vgs": 15.0},
    "GaN-HEMT": {"part": "TP65H035G4WS", "kind": "gan", "t_hot": 150.0},
}


def parse(cond: str) -> dict:
    """Temperature, current, voltage and gate voltage from a condition string."""
    out = {}
    m = re.search(r"T(?:vj|j|c)\s*=\s*(-?[\d.]+)\s*C", cond)
    if m:
        out["T"] = float(m.group(1))
    m = re.search(r"\b(?:IC|ID|IF,S|IF|ISD|IS|IL)\s*=\s*(-?[\d.]+)\s*A", cond)
    if m:
        out["I"] = abs(float(m.group(1)))
    m = re.search(r"\b(?:VCE|VDS|VR,DS|VR|Vr|VDD)\s*=\s*([\d.]+)\s*V", cond)
    if m:
        out["V"] = float(m.group(1))
    m = re.search(r"VGS\s*=\s*(?:-?[\d.]+\s*/\s*)?\+?([\d.]+)\s*V", cond)
    if m:
        out["VGS"] = float(m.group(1))
    return out


def table(pts: pd.DataFrame, part: str, param: str, **want) -> pd.DataFrame:
    d = pts[(pts.part_number == part) & (pts.parameter == param)].copy()
    meta = d.condition.map(parse)
    for k in ("T", "I", "V", "VGS"):
        d[k] = meta.map(lambda m, k=k: m.get(k, np.nan))
    for k, v in want.items():
        d = d[np.isclose(d[k], v)]
    return d


def value_at(pts, part, param, **want) -> float:
    d = table(pts, part, param, **want)
    if d.empty:
        raise KeyError(f"{part} {param} {want}")
    return float(d.value.iloc[0])


def unit_scale(unit: str) -> float:
    return {"mJ": 1e-3, "uJ": 1e-6, "J": 1.0, "mohm": 1e-3, "ohm": 1.0, "V": 1.0}[unit]


def fit_linear(i: np.ndarray, v: np.ndarray) -> tuple[float, float]:
    r, v0 = np.polyfit(i, v, 1)
    return float(v0), float(r)


def energy_curve(pts, part, t_hot) -> pd.DataFrame:
    """E_on + E_off + E_rec [J] on the common current grid of the hot curves."""
    parts = []
    for p in ("Eon_curve", "Eoff_curve", "Erec_curve"):
        d = table(pts, part, p, T=t_hot)
        if d.empty:
            continue
        d = d.assign(E=d.value * d.unit.map(unit_scale)).sort_values("I")
        parts.append(d[["I", "E"]].groupby("I").E.mean())
    grid = np.array(sorted(set(parts[0].index).intersection(*[set(x.index) for x in parts[1:]])
                           if len(parts) > 1 else parts[0].index))
    if grid.size < 4:          # curves on different grids: interpolate onto the first
        grid = parts[0].index.to_numpy()
    tot = sum(np.interp(grid, x.index.to_numpy(float), x.to_numpy(float)) for x in parts)
    return pd.DataFrame({"I": grid, "E": tot})


def fit_shape(curve: pd.DataFrame, i_ref: float) -> tuple[float, float, float]:
    """gamma, phi and the curve's own E at i_ref, by least squares in log space."""
    i = curve.I.to_numpy(float)
    e = curve.E.to_numpy(float)
    e_ref = float(np.interp(i_ref, i, e))

    def model(th, x):
        g, ph = th
        return e_ref * ((1 - ph) * (x / i_ref) ** g + ph * (x / i_ref) ** 0.5)

    r = least_squares(lambda th: np.log(model(th, i)) - np.log(e), [1.0, 0.2],
                      bounds=([0.6, 0.0], [2.5, 0.9]))
    return float(r.x[0]), float(r.x[1]), e_ref


#: Assumptions for the 2010 Prius traction machine (ORNL/TM-2010/253): rating,
#: design link voltage, speed at which the modulation index saturates per volt
#: of link (98 % contours turn vertical near 4000, 3000 and 2000 rpm at 650,
#: 500 and 225 V) and motor efficiency at the light-load map points.
PRIUS = {"kw": 60.0, "v_design": 650.0, "rpm_per_v": 6.5, "eta_motor": 0.88,
         "f_sw": 5000.0, "t_coolant": 65.0}


def prius_points() -> pd.DataFrame:
    d = pd.read_csv(DATA / "inverter_measurements.csv")
    p = d[d.measurement.str.contains("contour point")].copy()
    p["rpm"] = p.condition.map(lambda s: float(re.findall(r"~(\d+) rpm", s)[-1]))
    p["nm"] = p.condition.map(lambda s: float(re.findall(r"~([\d.]+) Nm", s)[-1]))
    p["measured"] = p.value.str.rstrip("%").astype(float) / 100.0
    return p


def prius_model(lib: dict, delta: float, pts: pd.DataFrame) -> np.ndarray:
    from evdt import powerelectronics as pe
    from evdt.config import Device
    lo, hi = Device(**lib["Si-IGBT"]), Device(**lib["HV:Si-IGBT"])
    out = []
    for _, r in pts.iterrows():
        vdc = float(r.dc_link_V)
        dev = hi if vdc * 1.2 > lo.v_rating else lo
        inv = replace(pe.traction_inverter(PRIUS["kw"], vdc, dev),
                      switching_frequency=PRIUS["f_sw"], ripple_pu_10k=delta,
                      ripple_v_design=PRIUS["v_design"])
        p_ac = r.nm * r.rpm * 2 * np.pi / 60.0 / PRIUS["eta_motor"]
        m = inv.modulation_index * min(1.0, r.rpm / (PRIUS["rpm_per_v"] * vdc))
        out.append(pe.solve_converter(inv, dev, p_ac, PRIUS["t_coolant"],
                                      modulation=max(m, 0.02)).efficiency)
    return np.array(out)


def fit_light_load(lib: dict) -> float:
    """Effective PWM ripple fitted to the measured light-load efficiency of
    the Prius inverter at 650 and 500 V; the 225 V map is held out."""
    from scipy.optimize import minimize_scalar
    pts = prius_points()
    train = pts[pts.dc_link_V > 300]
    res = minimize_scalar(lambda dl: float(np.sum((prius_model(lib, dl, train)
                                                   - train.measured.to_numpy()) ** 2)),
                          bounds=(0.0, 2.0), method="bounded")
    delta = float(res.x)
    pts = pts.assign(set=np.where(pts.dc_link_V > 300, "fit", "held out"),
                     model_without_ripple=prius_model(lib, 0.0, pts),
                     model=prius_model(lib, delta, pts))
    pts[["dc_link_V", "rpm", "nm", "measured", "model_without_ripple", "model", "set",
         "condition"]].to_csv(RESULTS / "light_load_fit.csv", index=False)
    for s, g in pts.groupby("set"):
        e0 = 100 * (g.model_without_ripple - g.measured)
        e1 = 100 * (g.model - g.measured)
        print(f"light load, {s}: MAE {e0.abs().mean():.2f} -> {e1.abs().mean():.2f} pp "
              f"(bias {e0.mean():+.2f} -> {e1.mean():+.2f})")
    print(f"traction ripple per unit at 10 kHz: {delta:.3f}")
    return delta


#: Discrete parts for the slots that the module fits above do not cover: the
#: silicon super-junction MOSFET (traction three-level leg and charger stages;
#: the automotive fast-body-diode CFD7A, as hard-switched bridge legs need),
#: the 100 V devices of two- and three-wheeler drives, and the SiC devices of
#: charger stages (650 V on the 400 V side, 1200 V on 800 V DC chargers).
TAB_SLOTS = {
    "Si-MOSFET": "IPDQ65R017CFD7A",
    "CHG:Si-MOSFET": "IPDQ65R017CFD7A",
    "LV:Si-LV": "IAUT300N10S5N015",
    "LV:GaN-LV": "EPC2302",
    "CHG:SiC-MOSFET": "IMZA65R027M1H",
    "CHG-HV:SiC-MOSFET": "IMZA120R022M2H",
}
#: The part whose datasheet tabulates switching energies as well as switching
#: times, output-charge energy and recovery charge; it calibrates the estimate
#: used for parts that tabulate no energies.
CALIBRATION_PART = "IMZA120R022M2H"
#: External gate resistance assumed where switching times must be derived from
#: gate charge (EPC states none; its evaluation boards use about 1 ohm).
R_G_EXT_ASSUMED = 1.0
_UNIT = {"mohm": 1e-3, "ohm": 1.0, "uJ": 1e-6, "nC": 1e-9, "ns": 1e-9, "V": 1.0, "A": 1.0,
         "C": 1.0, "K/W": 1.0}


def _tab(df: pd.DataFrame, part: str) -> dict[str, float]:
    d = df[df.part_number == part]
    return {r.parameter: float(r.value) * _UNIT[r.unit] for r in d.itertuples()}


def _times(t: dict) -> tuple[float, float]:
    """Turn-on and turn-off transition times [s]: tabulated rise and fall
    times, or else the charge-control estimate from gate charge."""
    if "t_r" in t:
        return t["t_r"], t["t_f"]
    r_g = t["r_g_int"] + R_G_EXT_ASSUMED
    q = (t["q_gs"] - t["q_gth"]) + t["q_gd"]
    return q * r_g / (t["v_drive"] - t["v_plateau"]), q * r_g / t["v_plateau"]


def _estimate(t: dict) -> tuple[float, float, float]:
    """Switching energies [J] at the test point before calibration: half the
    voltage-current product over each transition, the output-capacitance
    energy dissipated at turn-on, and the recovery charge at the test voltage."""
    v, i = t["v_test"], t["i_test"]
    t_on, t_off = _times(t)
    return (0.5 * v * i * t_on + t["e_oss"], 0.5 * v * i * t_off, t["q_rec"] * v)


def fit_tabulated(prior: dict, fitted: dict) -> tuple[dict, list[dict], float]:
    """Device parameters of the discrete parts from their datasheet tables."""
    df = pd.read_csv(DATA / "datasheet_tables.csv")
    cal = _tab(df, CALIBRATION_PART)
    k_cal = ((cal["e_on_25"] + cal["e_off_25"] + cal["e_rec_25"]) / sum(_estimate(cal)))
    tc_sic = ((cal["e_tot_hot"] / (cal["e_on_25"] + cal["e_off_25"] + cal["e_rec_25"]) - 1.0)
              / (175.0 - 25.0))
    out, rows = {}, []
    for slot, part in TAB_SLOTS.items():
        t = _tab(df, part)
        info = df[df.part_number == part].iloc[0]
        key = slot.split(":")[-1]
        base = prior[slot] if slot in prior else prior[key]
        r25, rh, th = t["rds_on_25"], t["rds_on_hot"], t["t_hot"]
        tc_r = (rh / r25 - 1.0) / (th - 25.0)
        if "e_on_25" in t:                      # energies tabulated
            e_on, e_off, e_rr = t["e_on_25"], t["e_off_25"], t["e_rec_25"]
            e_tc = (t["e_tot_hot"] / (e_on + e_off + e_rr) - 1.0) / (175.0 - 25.0)
            how = "switching energies tabulated"
        else:
            e1, e2, e3 = _estimate(t)
            e_on, e_off, e_rr = k_cal * e1, k_cal * e2, k_cal * e3
            e_tc = tc_sic if key.startswith("SiC") else base.e_tc
            how = (f"switching energies estimated from "
                   + ("switching times" if "t_r" in t else
                      f"gate charge with {R_G_EXT_ASSUMED:.0f} ohm external gate resistance")
                   + f", output-charge energy and recovery charge, x {k_cal:.2f} "
                     f"(calibrated on {CALIBRATION_PART})")
        e_sum = e_on + e_off + e_rr
        phi = (k_cal * t["e_oss"] + e_rr) / e_sum if "e_on_25" not in t else \
            (t["e_oss"] + e_rr) / e_sum
        figs = sorted(set(df[(df.part_number == part) & (df.how == "figure")].parameter))
        upd = {"name": f"{info.manufacturer} {part} ({t['v_rating']:.0f} V / "
                       f"{t['i_nominal']:.0f} A)",
               "v_rating": t["v_rating"], "i_rating": t["i_nominal"],
               "r_on_25": r25, "r_on_tc": tc_r, "v_ce0": 0.0, "r_ce": 0.0,
               "v_f0": 0.0, "r_f": 0.0, "v_sd": t["v_sd"],
               "e_on": e_on, "e_off": e_off, "e_rr": e_rr,
               "v_ref": t["v_test"], "i_ref": t["i_test"], "i_exponent": 1.0,
               "e_offset_fraction": float(min(phi, 0.9)), "e_tc": e_tc,
               "r_th_jc": t["rth_jc"], "rth_to_fluid": False,
               "source": f"{part} datasheet tables (conduction, reverse conduction, "
                         f"thermal); {how}"
                         + (f"; read from figures: {', '.join(figs)}" if figs else "")}
        out[slot] = asdict(replace(base, **upd))
        rows.append({"slot": slot, "part": part, "quantity": f"RDS(on) at {th:.0f} C",
                     "datasheet": rh, "model": r25 * (1 + tc_r * (th - 25.0))})
        if "e_on_25" in t:
            rows.append({"slot": slot, "part": part,
                         "quantity": f"Eon+Eoff+Efr at {t['i_test']:.0f} A, 175 C, mJ",
                         "datasheet": t["e_tot_hot"] * 1e3,
                         "model": e_sum * (1 + e_tc * 150.0) * 1e3})
    # parts already fitted above serve the charger slots of the same technology
    out["CHG:GaN-HEMT"] = dict(fitted["GaN-HEMT"])
    out["CHG-HV:Si-IGBT"] = dict(fitted["HV:Si-IGBT"])
    print(f"switching-energy estimate calibration factor: {k_cal:.2f}")
    return out, rows, k_cal


def main() -> None:
    pts = pd.read_csv(DATA / "datasheet_points.csv")
    lib, rows = {}, []
    prior = {**{k: cfgmod.DEVICE_LIBRARY[k] for k in cfgmod.DEVICE_LIBRARY},
             **{f"HV:{k}": v for k, v in cfgmod.HV_VARIANTS.items()}}
    for slot, spec in SLOTS.items():
        part, kind, th = spec["part"], spec["kind"], spec["t_hot"]
        base = prior.get(slot, prior[slot.replace("HV:", "")])
        info = pts[pts.part_number == part].iloc[0]
        v_rating, i_nom = float(info.v_rating_V), float(info.i_nominal_A)
        upd = {"name": f"{info.manufacturer} {part} ({v_rating:.0f} V / {i_nom:.0f} A)",
               "v_rating": v_rating, "i_rating": i_nom}
        e25 = {}
        if kind == "igbt":
            ce = table(pts, part, "VCE_point", T=th)
            ce = ce[(ce.I >= 0.1 * i_nom) & (ce.I <= i_nom)]
            v0, r = fit_linear(ce.I.to_numpy(float), ce.value.to_numpy(float))
            fd = table(pts, part, "VF_point", T=th)
            fd = fd[(fd.I >= 0.1 * i_nom) & (fd.I <= i_nom)]
            vf0, rf = fit_linear(fd.I.to_numpy(float), fd.value.to_numpy(float))
            upd.update(v_ce0=v0, r_ce=r, v_f0=vf0, r_f=rf, r_on_25=0.0, r_on_tc=0.0)
            for i, v in zip(ce.I, ce.value):
                rows.append({"slot": slot, "part": part, "quantity": f"VCE at {i:.0f} A, {th:.0f} C",
                             "datasheet": v, "model": v0 + r * i})
            for i, v in zip(fd.I, fd.value):
                rows.append({"slot": slot, "part": part, "quantity": f"VF at {i:.0f} A, {th:.0f} C",
                             "datasheet": v, "model": vf0 + rf * i})
            e_names = ("Eon", "Eoff", "Erec")
            rth = value_at(pts, part, "Rth_JF_IGBT_typ")
        else:
            vgs = spec.get("vgs")
            rds = table(pts, part, "RDS_on" if kind == "mosfet" else "RDS_on_eff")
            if vgs is not None and rds.VGS.notna().any():
                rds = rds[np.isclose(rds.VGS, vgs)]
            r25 = float(rds[np.isclose(rds["T"], 25.0)].value.iloc[0]) * unit_scale(rds.unit.iloc[0])
            rhot = float(rds[np.isclose(rds["T"], th)].value.iloc[0]) * unit_scale(rds.unit.iloc[0])
            tc = (rhot / r25 - 1.0) / (th - 25.0)
            vsd_name = "VSD_body_diode" if kind == "mosfet" else "VSD_reverse"
            vsd_tab = table(pts, part, vsd_name)
            hot = vsd_tab[np.isclose(vsd_tab["T"], th)]
            vsd = float((hot if not hot.empty else vsd_tab).value.iloc[0])
            upd.update(r_on_25=r25, r_on_tc=tc, v_ce0=0.0, r_ce=0.0, v_sd=vsd)
            rows.append({"slot": slot, "part": part, "quantity": f"RDS(on) at {th:.0f} C",
                         "datasheet": rhot, "model": r25 * (1 + tc * (th - 25.0))})
            vds = table(pts, part, "VDS_point", T=th)
            if vgs is not None and not vds.empty:
                vds = vds[np.isclose(vds.VGS, vgs)]
            for i, v in zip(vds.I, vds.value):
                if i <= i_nom:
                    rows.append({"slot": slot, "part": part,
                                 "quantity": f"VDS at {i:.0f} A, {th:.0f} C",
                                 "datasheet": v, "model": r25 * (1 + tc * (th - 25.0)) * i})
            e_names = ("Eon", "Eoff", "Erec") if kind == "mosfet" else ("Eon", "Eoff")
            rth = (value_at(pts, part, "Rth_JF_typ") if kind == "mosfet" and
                   not table(pts, part, "Rth_JF_typ").empty else
                   value_at(pts, part, "Rth_JF") if kind == "mosfet" else
                   value_at(pts, part, "Rth_JC"))
        # switching energies at the datasheet test point
        t_tab = th if kind != "gan" else 25.0
        e_hot_tab = 0.0
        for nm in e_names:
            d = table(pts, part, nm)
            d25 = d[np.isclose(d["T"], 25.0)]
            dh = d[np.isclose(d["T"], t_tab)]
            sc = unit_scale(d.unit.iloc[0])
            e25[nm] = float(d25.value.iloc[0]) * sc
            e_hot_tab += float(dh.value.iloc[0]) * sc
            i_ref, v_ref = float(d25.I.iloc[0]), float(d25.V.iloc[0])
        e_tc = ((e_hot_tab / sum(e25.values()) - 1.0) / (t_tab - 25.0)
                if kind != "gan" else base.e_tc)
        shape_part = spec.get("shape_from", part)
        t_curve = th if kind != "gan" else 25.0
        curve = energy_curve(pts, shape_part, t_curve)
        i_ref_shape = i_ref if shape_part == part else float(
            table(pts, shape_part, "Eon")[lambda d: np.isclose(d["T"], 25.0)].I.iloc[0])
        gamma, phi, _ = fit_shape(curve, i_ref_shape)
        for i, e in zip(curve.I, curve.E):
            e_model_shape = ((1 - phi) * (i / i_ref_shape) ** gamma
                             + phi * (i / i_ref_shape) ** 0.5)
            e_at_ref = float(np.interp(i_ref_shape, curve.I, curve.E))
            rows.append({"slot": slot, "part": shape_part,
                         "quantity": f"Eon+Eoff+Erec at {i:.0f} A, {t_curve:.0f} C (shape)",
                         "datasheet": e * 1e3, "model": e_at_ref * e_model_shape * 1e3})
        rows.append({"slot": slot, "part": part,
                     "quantity": f"Eon+Eoff+Erec at {i_ref:.0f} A, {t_tab:.0f} C, mJ",
                     "datasheet": e_hot_tab * 1e3,
                     "model": sum(e25.values()) * (1 + e_tc * (t_tab - 25.0)) * 1e3})
        upd.update(e_on=e25["Eon"], e_off=e25["Eoff"], e_rr=e25.get("Erec", 0.0),
                   v_ref=v_ref, i_ref=i_ref, i_exponent=gamma, e_offset_fraction=phi,
                   e_tc=e_tc, r_th_jc=rth, rth_to_fluid=(kind != "gan"),
                   source=f"{part} datasheet; switching-energy shape from {shape_part}"
                          + (f"; E_tc prior (25 C data only)" if kind == "gan" else ""))
        lib[slot] = asdict(replace(base, **upd))
    rep = cfgmod.REPRESENTATIVE
    tab_prior = {**{k: v for k, v in rep["traction"].items()},
                 **{f"LV:{k}": v for k, v in rep["lv"].items()},
                 **{f"CHG:{k}": v for k, v in rep["charger"].items()},
                 **{f"CHG-HV:{k}": v for k, v in rep["charger_hv"].items()},
                 "CHG-HV:SiC-MOSFET": rep["charger"]["SiC-MOSFET"]}
    tab_lib, tab_rows, k_cal = fit_tabulated(tab_prior, lib)
    lib.update(tab_lib)
    rows += tab_rows
    for r in rows:
        r["rel_error"] = (r["model"] - r["datasheet"]) / r["datasheet"]
    fit = pd.DataFrame(rows)
    RESULTS.mkdir(exist_ok=True)
    fit.to_csv(RESULTS / "device_fit.csv", index=False)
    lib["_switching_estimate_factor"] = k_cal
    lib["_traction_ripple_pu_10k"] = fit_light_load(lib)
    OUT.write_text(json.dumps(lib, indent=1), encoding="utf-8")
    for slot, d in lib.items():
        if slot.startswith("_"):
            continue
        print(f"{slot:15s} " + ", ".join(f"{k}={d[k]:.4g}" for k in (
            "v_ce0", "r_ce", "v_f0", "r_f", "r_on_25", "r_on_tc", "e_on", "e_off", "e_rr",
            "v_ref", "i_ref", "i_exponent", "e_offset_fraction", "e_tc", "r_th_jc", "v_sd")))
    print(fit.groupby(["slot"]).rel_error.agg(lambda s: np.max(np.abs(s))).to_string())


if __name__ == "__main__":
    main()
