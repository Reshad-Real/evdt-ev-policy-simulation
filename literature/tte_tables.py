"""Tables of the revised TTE manuscript and of its supplementary material.

Every value is read from ``results/`` or ``digital_twin/data``; nothing is typed
by hand, so the tables cannot disagree with the text, which takes its numbers
from the same files through tte_numbers.py.

Usage:  py -3 literature/tte_tables.py
Output: "Manuscript TTE/build/tables/*.csv" and supplementary/*.csv
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "results"
DATA = ROOT / "digital_twin" / "data"
# In the public reproduction package there is no manuscript folder: write to tables/.
OUT = (ROOT / "Manuscript TTE" / "build" / "tables"
       if (ROOT / "Manuscript TTE").exists() else ROOT / "tables")
SUP = OUT / "supplementary"
ARCH = {"underdeveloped": "LDC", "developing": "BD", "developed": "DE"}
ARCH_LONG = {"underdeveloped": "Least-developed", "developing": "Developing (BD)",
             "developed": "Developed (DE)"}

CAPTIONS = {
    "T01_instruments": (
        "Policy instruments and the model parameter each changes. A package is a vector "
        "of lever settings with a phase-in window (settings in Supplementary Table S3; "
        "equations each parameter enters in Table S0)."),
    "T02_validation": (
        "Validation (V) against independent data and verification (Ver.) of the code. "
        "Adoption errors are on years excluded from the fit; range gains are against a "
        "400 V Si IGBT inverter. DE, Germany; BD, Bangladesh; IN, India; ID, Indonesia; "
        "KE, Kenya; VN, Vietnam."),
    "T03_outcomes": (
        "Outcomes of the twenty-one runs, 2025-2040. EV, electric share of the stock in "
        "2040 (%); ΔCO2, abatement additional to S0 of the same archetype (Mt); ΔNPV, "
        "change in NPV against S0 (billion USD); BCR and MAC (USD/t) follow (9) and (10), "
        "MAC withheld (n/m) below 0.5 Mt or 2 % of the reference abatement; R, TOPSIS "
        "rank within the archetype. Gross CO2, transformer loading and weight robustness "
        "are in Supplementary Table S14."),
}


DOMAIN_SHORT = {"Fiscal": "Fisc.", "Infrastructure": "Infra.", "Power electronics": "PE",
                "Grid": "Grid", "Institutional": "Inst.", "Digital": "Dig."}


def instruments() -> pd.DataFrame:
    """Two blocks side by side across the page (fiscal, infrastructure and power
    electronics | grid, institutional and digital), so no row wraps and the
    table cannot break between columns; the full mapping is Supplementary
    Table S0. The second block's headers carry a zero-width space so that the
    column names stay distinct."""
    df = pd.read_csv(DATA / "instrument_mapping.csv")
    t = pd.DataFrame({"Dom.": df.domain.map(DOMAIN_SHORT),
                      "Instrument": df.instrument,
                      "Parameter changed": df.model_parameter})
    first = df.domain.isin(["Fiscal", "Infrastructure", "Power electronics"])
    left = t[first].reset_index(drop=True)
    right = t[~first].reset_index(drop=True)
    right.columns = [c + "​" for c in right.columns]
    n = max(len(left), len(right))
    left = left.reindex(range(n)).fillna("")
    right = right.reindex(range(n)).fillna("")
    return pd.concat([left, right], axis=1)


def validation() -> pd.DataFrame:
    """One row per check, compact enough for one column."""
    rows = []
    cal = pd.read_csv(RES / "calibration_summary.csv").set_index("archetype")
    de_cal = cal.loc["developed"]
    rows.append(["V", "Adoption, BEV cars, DE",
                 f"test {de_cal.validation_years.replace('-20', '-')}",
                 f"MAPE {100 * de_cal.mape_validation:.0f} %"])
    rows.append(["V", "Adoption, e-2W, IN (panel)", "test 2023-25",
                 f"MAPE {100 * cal.loc['developing', 'mape_validation']:.0f} %"])
    tr = pd.read_csv(RES / "calibration_transfer.csv")
    loco = tr[~tr.country.str.contains("check")]
    vn = tr[tr.country.str.contains("Vietnam")].iloc[0]
    rows.append(["V", "Transfer, IN/ID/KE left out", "e-2W sales",
                 f"MAPE {100 * loco.mape.min():.0f}-{100 * loco.mape.max():.0f} %"])
    rows.append(["V", "Transfer to VN (no incentive)", "e-2W 2020-24",
                 f"MAPE {100 * vn.mape:.0f} %"])
    rows.append(["V", "Sales per 1000 EUR, DE", "+5-7 % [munzel-2019]",
                 f"+{100 * de_cal.own_effect_per_1000eur:.1f} %"])
    rec = pd.read_csv(RES / "emission_reconciliation.csv")
    de = rec[rec.comparison == "match"].iloc[0]
    rows.append(["V", "Road CO2 2024, DE (CRF)", f"{de.inventory_mt:.1f} Mt",
                 f"{de.model_ttw_mt:.1f} Mt"])
    bd = rec[rec.country == "Bangladesh"].iloc[0]
    rows.append(["V", "Transport CO2 2023, BD (bound)", f"{bd.inventory_mt:.1f} Mt",
                 f"{bd.model_ttw_mt:.1f} Mt"])
    dfit = pd.read_csv(RES / "device_fit.csv")
    rows.append(["V", f"Datasheets, {dfit.part.nunique()} parts",
                 f"{len(dfit)} points [infineon-hpd; transphorm-gan]",
                 f"max error {100 * dfit.rel_error.abs().max():.0f} %"])
    ll = pd.read_csv(RES / "light_load_fit.csv")
    ho = ll[ll.set == "held out"]
    rows.append(["V", "Light load, 225 V (held out)",
                 f"{len(ho)} points [ornl-prius-2011]",
                 f"MAE {100 * (ho.model - ho.measured).abs().mean():.1f} pp"])
    lit = pd.read_csv(RES / "validation_converter_literature.csv")
    ig = lit[lit.quantity.str.contains("Si IGBT traction inverter, peak")]
    rows.append(["V", "Si IGBT inverter peak", ">99 % [ornl-prius-2011; doe-amr-ornl]",
                 f"{100 * ig.model.min():.1f}-{100 * ig.model.max():.1f} %"])
    r_s = lit[lit.quantity.str.contains("SiC-MOSFET at 800 V")].iloc[0]
    r_i = lit[lit.quantity.str.contains("Si-IGBT at 800 V")].iloc[0]
    pub = lambda s: str(s).replace("%", "").strip()  # noqa: E731
    rows.append(["V", "Range gain, 800 V SiC / IGBT",
                 f"{pub(r_s.published)} / {pub(r_i.published)} % [allca-2024]",
                 f"{100 * r_s.model:+.1f} / {100 * r_i.model:+.1f} %"])
    pfc = lit[lit.quantity.str.contains("PFC")].iloc[0]
    obc = lit[lit.quantity.str.contains("on-board")].iloc[0]
    dc = lit[lit.quantity.str.contains("fast-charger")]
    rows.append(["V", "SiC PFC / WBG OBC peak", f"98.5 / >96 %",
                 f"{100 * pfc.model:.1f} / {100 * obc.model:.1f} %"])
    rows.append(["V", "DC stage peak, SiC / Si", ">97 / >94 %",
                 f"{100 * dc.model.iloc[0]:.1f} / {100 * dc.model.iloc[1]:.1f} %"])
    bench = pd.read_csv(RES / "validation_benchmark_feeders.csv").dropna(
        subset=["published_losses_kw"])
    rows.append(["V", "Feeders, loss / V_min",
                 "IEEE 33/69, IN 28 [baran-wu-1989; baran-wu-1989b; das-1994]",
                 f"{100 * (abs(bench.losses_kw - bench.published_losses_kw) / bench.published_losses_kw).max():.2f} % / "
                 f"{abs(bench.v_min_pu - bench.published_v_min_pu).max():.4f} pu"])
    pfv = RES / "validation_power_flow.csv"
    if pfv.exists():
        pfv = pd.read_csv(pfv)
        if "lookup_max_voltage_error_pu" in pfv:
            rows.append(["Ver.", "Power flow, interpolated", "direct",
                         f"{pfv.lookup_max_voltage_error_pu.max():.0e} pu".replace("e-0", "e-")])
    q = pd.read_csv(RES / "validation_queue.csv")
    rows.append(["Ver.", "Queue (6) vs simulation", f"{len(q)} cases",
                 f"{100 * q.relative_error.max():.1f} %"])
    eb = pd.read_csv(RES / "validation_energy_balance.csv")
    rows.append(["Ver.", "Energy balance", "9 years",
                 f"{eb.relative_residual.max():.0e}"])
    return pd.DataFrame(rows, columns=["Type", "Check", "Data", "Model"])


def s_instruments() -> pd.DataFrame:
    df = pd.read_csv(DATA / "instrument_mapping.csv")
    return df.rename(columns={"domain": "Domain", "instrument": "Instrument",
                              "lever": "Lever", "model_parameter": "Parameter changed",
                              "acts_through": "Acts through"})


def outcomes() -> pd.DataFrame:
    """Packages as rows, the three archetypes side by side ("LDC::EV" headers
    become a spanning group row in make_tte_docx.py); the full record with gross
    CO2, transformer loading and P1 is Supplementary Table S14."""
    full = outcomes_full()
    keep = {"EV 2040 (%)": "EV", "Add. CO2 (Mt)": "ΔCO₂", "dNPV (bn USD)": "ΔNPV",
            "BCR": "BCR", "MAC (USD/t)": "MAC", "Rank": "R"}
    out = pd.DataFrame({"Pkg": [f"S{i}" for i in range(7)]})
    for a in ARCH:
        sub = full[full["Arch."] == ARCH[a]].set_index("Pkg")
        for col, lab in keep.items():
            vals = sub[col].reindex(out.Pkg).tolist()
            out[f"{ARCH[a]}{'::'}{lab}"] = ["" if v == "-" else v for v in vals]
    return out


def outcomes_full() -> pd.DataFrame:
    rank = pd.read_csv(RES / "policy_ranking.csv")
    ws = json.loads((RES / "topsis_weight_sensitivity.json").read_text(encoding="utf-8"))
    rows = []
    for a in ARCH:
        p1 = dict(zip(ws[a]["keys"], ws[a]["p_first"]))
        for pol in [f"S{i}" for i in range(7)]:
            r = rank[(rank.archetype == a) & (rank.policy == pol)].iloc[0]
            ref = pol == "S0"
            mac = r.abatement_cost_usd_t
            rows.append({
                "Arch.": ARCH[a], "Pkg": pol,
                "EV 2040 (%)": f"{100 * r.final_ev_share:.1f}",
                "Add. CO2 (Mt)": "ref" if ref else f"{r.delta_emissions_mt:.1f}",
                "Gross CO2 (Mt)": f"{r.cumulative_gross_avoided_mt:.0f}",
                "dNPV (bn USD)": "ref" if ref else f"{r.delta_npv_musd / 1e3:.2f}",
                "BCR": "-" if ref else (f"{r.incremental_bcr:.2f}"
                                        if np.isfinite(r.incremental_bcr) else "n/a"),
                "MAC (USD/t)": "-" if ref else ("n/m" if not np.isfinite(mac)
                                                else f"{mac:,.0f}"),
                "Tx 2040 (pu)": f"{r.final_transformer_loading:.2f}",
                "Rank": "-" if ref else str(int(r.policy_rank)),
                "P1": "-" if ref else f"{p1[pol]:.2f}",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# supplementary tables
# ---------------------------------------------------------------------------
def s_devices() -> pd.DataFrame:
    d = pd.read_csv(RES / "converter_device_parameters.csv")
    keep = ["key", "class", "name", "v_rating", "i_rating", "r_on_25", "r_on_tc", "v_ce0",
            "r_ce", "v_f0", "r_f", "v_sd", "e_on", "e_off", "e_rr", "v_ref", "i_ref",
            "i_exponent", "e_offset_fraction", "e_tc", "r_th_jc", "cost_per_a"]
    d = d[[c for c in keep if c in d]].copy()
    for c in ("r_on_25", "r_ce", "r_f"):
        if c in d:
            d[c] = (d[c] * 1e3).round(2)
    for c in ("e_on", "e_off", "e_rr"):
        d[c] = (d[c] * 1e3).round(3)
    return d.rename(columns={"r_on_25": "R_on25 (mOhm)", "r_ce": "r_ce (mOhm)",
                             "r_f": "r_F (mOhm)", "v_f0": "V_F0 (V)", "v_sd": "V_SD (V)",
                             "e_on": "E_on (mJ)", "e_off": "E_off (mJ)", "e_rr": "E_rr (mJ)",
                             "r_th_jc": "R_th (K/W)", "v_ce0": "V_ce0 (V)"})


def s_device_fit() -> pd.DataFrame:
    """Datasheet points of the fitted parts against the model (third revision)."""
    f = pd.read_csv(RES / "device_fit.csv")
    f["abs"] = f.rel_error.abs() * 100
    f["kind"] = f.quantity.str.extract(r"^(VCE|VF|VDS|RDS\(on\)|Eon\+Eoff\+Erec)")[0]
    out = (f.groupby(["slot", "part", "kind"])["abs"]
           .agg(points="size", mean_abs_error_pct="mean", max_abs_error_pct="max")
           .reset_index())
    return out.round(2)


def s_adoption_panel() -> pd.DataFrame:
    p = pd.read_csv(ROOT / "digital_twin" / "data" / "adoption_panel.csv", comment="#")
    return p[["country", "year", "ev_sales_share", "incentive_fraction", "set", "source"]]


def s_transfer() -> pd.DataFrame:
    return pd.read_csv(RES / "calibration_transfer.csv").round(4)


def s_feeders() -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "digital_twin"))
    from evdt import grid as gridmod
    from evdt import scenarios as sc
    rows = []
    for a, types in (("underdeveloped", sc.FEEDERS_LDC), ("developing", sc.FEEDERS_BD),
                     ("developed", sc.FEEDERS_DE)):
        for t in types:
            b = gridmod.load_benchmark(t.key)
            rows.append({"archetype": ARCH[a], "type": t.label, "feeder": t.key,
                         "buses": int(b["load_kw"].size),
                         "kV": t.base_kv or b["meta"]["base_kv"],
                         "impedance x": round(t.z_scale, 3),
                         "peak (MW)": round(t.peak_mw or b["peak_mw"], 2),
                         "demand share": t.demand_share, "source": t.source})
    return pd.DataFrame(rows)


def s_feeder_check() -> pd.DataFrame:
    return pd.read_csv(RES / "validation_benchmark_feeders.csv").round(4)


def s_converters() -> pd.DataFrame:
    s = pd.read_csv(RES / "converter_converter_summary.csv")
    cols = ["topology", "device", "device_fitted", "leg", "rated_kw", "dc_link_v",
            "f_sw_khz", "weighted_efficiency", "efficiency_at_rated", "p_cond_w", "p_sw_w",
            "p_passive_w", "t_junction_c", "n_parallel", "n_series", "kw_per_litre",
            "cost_usd"]
    return s[cols].round(4)


def s_packages() -> pd.DataFrame:
    lv = pd.read_csv(RES / "policy_levers.csv")
    t = lv.pivot_table(index=["archetype", "lever"], columns="policy", values="value_2035")
    t = t.reset_index()
    t["archetype"] = t["archetype"].map(ARCH)
    return t.round(3)


def s_indicators() -> pd.DataFrame:
    ws = json.loads((RES / "topsis_weight_sensitivity.json").read_text(encoding="utf-8"))
    return pd.DataFrame([{"indicator": k, "label": v["label"], "group": v["group"],
                          "direction": "maximise" if v["benefit"] else "minimise",
                          "weight": round(v["weight"], 4)}
                         for k, v in ws["weights"].items()])


def s_uncertainty() -> pd.DataFrame:
    meta = json.loads((RES / "uncertainty_meta.json").read_text(encoding="utf-8"))
    return pd.DataFrame(meta["parameters"])


def s_cba() -> pd.DataFrame:
    """Discounted benefit and cost components of every package, 2025-2040."""
    h = pd.read_csv(RES / "horizon_summary.csv")
    comps = [c for c in h.columns if c.startswith("pv_")]
    out = h[["archetype", "policy"] + comps + ["discounted_benefit_musd",
                                                "discounted_cost_musd", "npv_musd",
                                                "discounted_fiscal_transfer_musd"]].copy()
    out["archetype"] = out["archetype"].map(ARCH)
    # strip only the present-value prefix: "npv_musd" and "c_pv_capex" keep their pv
    out.columns = [(c[3:] if c.startswith("pv_") else c).replace("_musd", " (MUSD)")
                   for c in out.columns]
    return out.round(1)


def s_plausibility() -> pd.DataFrame:
    return pd.read_csv(RES / "validation_plausibility.csv").round(4)


def s_calibration() -> pd.DataFrame:
    return pd.read_csv(RES / "calibration_adoption.csv").round(5)


def s_reliability() -> pd.DataFrame:
    r = pd.read_csv(RES / "converter_reliability.csv")
    cols = ["mission", "converter", "device", "device_fitted", "fast_cycles_per_year",
            "delta_tj_fast_median_k", "delta_tj_fast_p95_k", "delta_tj_fast_max_k",
            "share_cycles_in_calibrated_range", "delta_tj_trip_k", "tj_max_c"]
    return r[[c for c in cols if c in r.columns]].round(3)


def s_archetypes() -> pd.DataFrame:
    cfg = json.loads((RES / "model_configuration.json").read_text(encoding="utf-8"))
    keys = ["population_million", "vehicle_stock_million", "vehicle_stock_growth",
            "base_ev_share", "segment_shares", "segment_overrides", "grid_emission_factor",
            "grid_emission_trend", "renewable_share", "grid_availability", "network_losses",
            "electricity_price", "industrial_price", "fuel_price", "fuel_price_ratio",
            "health_cost_per_litre", "discount_rate", "wacc", "social_carbon_price",
            "value_of_lost_load", "value_of_time", "import_duty", "charger_cost_mult",
            "charger_density_base", "wbg_share_base", "bass_p", "bass_q", "market_potential",
            "fleet_lifetime_y", "base_sales_share", "price_elasticity", "parity_ref",
            "adequacy_ref", "drive_cycles"]
    rows = []
    for k in keys:
        rows.append({"parameter": k, **{ARCH_LONG[a]: str(cfg["archetypes"][a].get(k))
                                        for a in ARCH}})
    return pd.DataFrame(rows)


TABLES = {"T01_instruments": instruments, "T02_validation": validation,
          "T03_outcomes": outcomes}
SUPPLEMENT = {"S00_instruments": s_instruments, "S01_devices": s_devices, "S02_converters": s_converters,
              "S03_packages": s_packages, "S04_indicators": s_indicators,
              "S05_uncertainty": s_uncertainty, "S06_cba": s_cba,
              "S07_plausibility": s_plausibility, "S08_calibration": s_calibration,
              "S09_reliability": s_reliability, "S10_archetypes": s_archetypes,
              "S01b_device_fit": s_device_fit, "S08b_adoption_panel": s_adoption_panel,
              "S08c_transfer": s_transfer, "S13_feeders": s_feeders,
              "S13b_feeder_check": s_feeder_check, "S14_outcomes": outcomes_full}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SUP.mkdir(parents=True, exist_ok=True)
    for key, fn in TABLES.items():
        df = fn()
        df.to_csv(OUT / f"{key}.csv", index=False)
        print(f"{key:18s} {df.shape[0]:3d} x {df.shape[1]}")
    for key, fn in SUPPLEMENT.items():
        try:
            df = fn()
        except FileNotFoundError as e:
            print(f"{key:18s} skipped ({e.filename} not yet produced)")
            continue
        df.to_csv(SUP / f"{key}.csv", index=False)
        print(f"{key:18s} {df.shape[0]:3d} x {df.shape[1]}  (supplement)")
    (OUT / "captions.md").write_text(
        "\n\n".join(f"**{k}** {v}" for k, v in CAPTIONS.items()) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
