"""Every number quoted in the text of the revised TTE manuscript and its
response letter.

The sections in manuscript/tte_sections and manuscript/tte_response carry
placeholders such as ``{{bd_s5_dco2}}``; build_tte.py and build_response.py
substitute them from the JSON written here.  Each value is computed from the
result files and formatted once, so the prose cannot drift from the tables and
figures (Reviewer 4, comment 8).  Where a sentence's wording depends on the
outcome (for example whether any ranking changes), the sentence itself is
generated here rather than assumed in the text.

Usage:  py -3 literature/tte_numbers.py
Output: "Manuscript TTE/build/numbers.json"
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "results"
# In the public reproduction package there is no manuscript folder: write to results/.
OUT = (ROOT / "Manuscript TTE" / "build" / "numbers.json"
       if (ROOT / "Manuscript TTE").exists() else ROOT / "results" / "numbers.json")
sys.path.insert(0, str(ROOT / "digital_twin"))
sys.path.insert(0, str(ROOT / "literature"))
A3 = {"ldc": "underdeveloped", "bd": "developing", "de": "developed"}
ANAME = {"underdeveloped": "the least-developed archetype", "developing": "Bangladesh",
         "developed": "Germany"}


def f(x: float, nd: int = 1) -> str:
    """Fixed decimals; a comma separates thousands from 10 000 upwards."""
    s = f"{x:,.{nd}f}"
    return s if abs(x) >= 10000 else s.replace(",", "")


def pct(x: float, nd: int = 1) -> str:
    return f(100.0 * x, nd)


def rng(a: float, b: float, nd: int = 2) -> str:
    lo, hi = min(a, b), max(a, b)
    return f(lo, nd) if f(lo, nd) == f(hi, nd) else f"{f(lo, nd)}-{f(hi, nd)}"


def _lc(label: str) -> str:
    """Lower-case the first letter of a label unless it starts an acronym (DC, PV)."""
    if len(label) > 1 and label[:2].isupper():
        return label
    return label[0].lower() + label[1:]


def read(name: str) -> pd.DataFrame | None:
    p = RES / name
    return pd.read_csv(p) if p.exists() else None


def main() -> None:
    try:                                     # front matter is not in the public package
        from tte_front import TITLE
    except ImportError:
        TITLE = ("Device-Level Power-Electronics Modeling in Electric-Vehicle Policy "
                 "Assessment: A Calibrated Simulation Across Development Contexts")
    from evdt import powerelectronics as pe, engine, economics as eco
    from evdt import scenarios as sc
    from evdt.config import VEHICLE_LIBRARY

    n: dict[str, str] = {"title": TITLE}
    cfg = json.loads((RES / "model_configuration.json").read_text(encoding="utf-8"))
    arch = cfg["archetypes"]
    n["bd_stock_m"] = f(arch["developing"]["vehicle_stock_million"], 1)
    n["bd_2w_share"] = pct(arch["developing"]["segment_shares"]["two_wheeler"], 1)
    n["de_stock_m"] = f(arch["developed"]["vehicle_stock_million"], 1)
    n["de_base_share"] = pct(arch["developed"]["base_ev_share"], 1)

    # ---- packages ---------------------------------------------------------
    rank = pd.read_csv(RES / "policy_ranking.csv")
    rec = pd.read_csv(RES / "scenario_records.csv")

    def r(a: str, p: str, col: str) -> float:
        return float(rank[(rank.archetype == A3[a]) & (rank.policy == p)][col].iloc[0])

    for a in A3:
        for p in [f"S{i}" for i in range(7)]:
            k = f"{a}_{p.lower()}"
            ev = r(a, p, "final_ev_share")
            n[f"{k}_ev"] = pct(ev, 0 if ev >= 0.095 else 1)
            n[f"{k}_gross"] = f(r(a, p, "cumulative_gross_avoided_mt"), 0)
            n[f"{k}_tx"] = f(r(a, p, "final_transformer_loading"), 2)
            n[f"{k}_wait"] = f(r(a, p, "final_wait_min"), 0)
            if p == "S0":
                continue
            d = r(a, p, "delta_emissions_mt")
            n[f"{k}_dco2"] = f(d, 1 if d < 100 else 0)
            n[f"{k}_dnpv"] = f(r(a, p, "delta_npv_musd") / 1e3, 1)
            b = r(a, p, "incremental_bcr")
            n[f"{k}_bcr"] = f(b, 2) if np.isfinite(b) else "n/a"
            m = r(a, p, "abatement_cost_usd_t")
            n[f"{k}_mac"] = f(m, 0) if np.isfinite(m) else "n/m"
            n[f"{k}_rank"] = str(int(r(a, p, "policy_rank")))
    n["de_max_gain"] = f(100 * max(r("de", p, "final_ev_share") - r("de", "S0",
                                   "final_ev_share") for p in [f"S{i}" for i in range(1, 7)]), 1)
    ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "last"}

    def ranks_text(pkg: str) -> str:
        ks = [int(r(a, pkg, "policy_rank")) for a in A3]
        if len(set(ks)) == 1:
            return f"{ordinal[ks[0]]} in every archetype"
        parts = [f"{ordinal[k]} in {ANAME[A3[a]]}" for a, k in zip(A3, ks)]
        return ", ".join(parts[:-1]) + " and " + parts[-1]
    from evdt.scenarios import DEVELOPED
    cp_de = float(DEVELOPED.social_carbon_price)
    n["de_carbon_price"] = f(cp_de, 0)
    above = [p for p in ("S4", "S5", "S6")
             if np.isfinite(r("de", p, "abatement_cost_usd_t"))
             and r("de", p, "abatement_cost_usd_t") > cp_de]
    below = [p for p in ("S4", "S5", "S6") if p not in above]
    if not below:
        n["de_mac_text"] = (f"All exceed the USD {cp_de:.0f} carbon value, so carbon value "
                            "does not justify any of them there")
    elif not above:
        n["de_mac_text"] = f"All lie below the USD {cp_de:.0f} carbon value"
    else:
        n["de_mac_text"] = (f"{' and '.join(above)} "
                            f"{'exceeds' if len(above) == 1 else 'exceed'} the USD {cp_de:.0f} "
                            f"carbon value, so carbon value does not justify "
                            f"{'it' if len(above) == 1 else 'them'} there; "
                            f"{' and '.join(below)} "
                            f"{'lies' if len(below) == 1 else 'lie'} below it")
    # which integrated packages (S4-S6) pay for themselves where
    integ = ("S4", "S5", "S6")
    phr = []
    for a in ("ldc", "bd", "de"):
        pays = [p for p in integ if r(a, p, "incremental_bcr") >= 1.0]
        ratios = ", ".join(f(r(a, p, "incremental_bcr"), 2) for p in pays)
        where = ANAME[A3[a]]
        if len(pays) == 3:
            phr.append(f"all three pay for themselves in {where} (ratios {ratios})")
        elif not pays:
            phr.append(f"none does in {where}")
        else:
            phr.append(f"{' and '.join(pays)} {'does' if len(pays) == 1 else 'do'} in "
                       f"{where} ({'ratio' if len(pays) == 1 else 'ratios'} {ratios})")
    n["integrated_text"] = ("The integrated packages S4-S6 add abatement at a lower return: "
                            + "; ".join(phr) + " (Fig. 5(d)).")
    m5, m6 = r("de", "S5", "abatement_cost_usd_t"), r("de", "S6", "abatement_cost_usd_t")
    rel = ("above" if min(m5, m6) > cp_de else "below" if max(m5, m6) < cp_de
           else "around")
    n["de_s56_mac_text"] = (f"In Germany the charging, network and program costs of S5 and "
                            f"S6 give net abatement costs of {f(m5, 0)} and {f(m6, 0)} USD "
                            f"per tonne, {rel} the {cp_de:.0f} USD carbon value.")
    n["s2_ranks"] = ranks_text("S2")
    n["s3_ranks"] = ranks_text("S3")
    leaders = {a: rank[(rank.archetype == A3[a]) & (rank.policy_rank == 1)].policy.iloc[0]
               for a in A3}
    n["leaders_text"] = (f"{leaders['ldc']} in the least-developed archetype, "
                         f"{leaders['bd']} in Bangladesh and {leaders['de']} in Germany")
    for a in A3:
        n[f"leader_{a}"] = leaders[a]
        n[f"best_npv_{a}"] = rank[(rank.archetype == A3[a]) & (rank.policy != "S0")] \
            .sort_values("delta_npv_musd", ascending=False).policy.iloc[0]
    # first year in which a package's electric share of new sales reaches 99 %
    for a in A3:
        for p in ("S0", "S1", "S5"):
            ss = rec[(rec.archetype == A3[a]) & (rec.policy == p)].set_index("year") \
                .ev_sales_share
            hit = ss[ss >= 0.99]
            n[f"{a}_{p.lower()}_full_sales_year"] = str(int(hit.index[0])) if len(hit) else "none"
            n[f"{a}_{p.lower()}_sales_2030"] = pct(float(ss.loc[2030]), 0)
            n[f"{a}_{p.lower()}_sales_2040"] = pct(float(ss.loc[2040]), 0)
    bd30 = rec[(rec.archetype == "developing") & (rec.year == 2030)]
    i = bd30.ev_share.idxmax()
    n["bd_max_2030"] = pct(bd30.ev_share.max(), 0)
    n["bd_max_2030_pkg"] = str(bd30.loc[i, "policy"])
    de0s = (rec[(rec.archetype == "developed") & (rec.policy == "S0")]
            .set_index("year").ev_sales_share)
    n["de_s0_sales_2030"] = pct(de0s[2030], 0)
    n["de_s0_sales_2035"] = pct(de0s[2035], 0)
    bd5 = rec[(rec.archetype == "developing") & (rec.policy == "S5") & (rec.year == 2040)]
    n["bd_s5_gross_2040"] = f(float(bd5.emissions_avoided_kt.iloc[0]) / 1e3, 1)
    a_bd = sc.ARCHETYPES["developing"]
    stock40 = a_bd.vehicle_stock_million * 1e6 * (1 + a_bd.vehicle_stock_growth) ** 15
    wtw = 0.0
    for s, share in a_bd.segment_shares.items():
        seg = engine.segment(a_bd, s)
        wtw += (stock40 * share * seg.annual_km * seg.ice_l_per_100km / 100.0
                * eco.fuel_co2_wtw(seg.fuel))
    n["bd_road_2040"] = f(wtw / 1e9, 0)

    ws = json.loads((RES / "topsis_weight_sensitivity.json").read_text(encoding="utf-8"))
    for a in A3:
        w = ws[A3[a]]
        first = w["keys"][int(np.argmin(w["base_rank"]))]
        n[f"p1_{a}_first"] = pct(dict(zip(w["keys"], w["p_first"]))[first], 0)
        n[f"p1_{a}_s6"] = pct(dict(zip(w["keys"], w["p_first"]))["S6"], 0)
    for a in A3:
        n[f"tau_{a}"] = f(ws[A3[a]]["kendall_tau_mean"], 2)
    # where another package leads more often than the base-weight leader
    notes = []
    for a in A3:
        w = ws[A3[a]]
        pf = dict(zip(w["keys"], w["p_first"]))
        first = w["keys"][int(np.argmin(w["base_rank"]))]
        top = max(pf, key=pf.get)
        if top != first:
            notes.append(f"In {ANAME[A3[a]]} {top} leads more often ({pct(pf[top], 0)} %) "
                         f"than {first}, so the leader there depends on the weights")
    n["p1_text"] = ("; ".join(notes) + ".") if notes else ""

    # ---- calibration and validation ----------------------------------------
    cal = pd.read_csv(RES / "calibration_summary.csv").set_index("archetype")
    n["mape_de"] = pct(cal.loc["developed", "mape_validation"], 0)
    n["mape_in"] = pct(cal.loc["developing", "mape_validation"], 0)
    cde = cal.loc["developed"]
    n["beta"] = f(cde.beta, 1)
    n["beta_lo"] = f(cde.beta_literature_low, 1)
    n["beta_hi"] = f(cde.beta_literature_high, 1)
    n["beta_own"] = f(cde.beta_own_estimate, 1)
    n["beta_own_se"] = f(cde.beta_own_se, 1)
    n["beta_own_effect"] = pct(cde.own_effect_per_1000eur, 1)
    n["de_stock_model"] = pct(cde.stock_2025_model, 1)
    n["de_stock_obs"] = pct(cde.stock_2025_observed, 1)
    ca = pd.read_csv(RES / "calibration_adoption.csv")
    ca = ca[ca.series == "sales"]

    def ca_(a, y, col):
        return float(ca[(ca.archetype == a) & (ca.year == y)][col].iloc[0])
    p24, o24 = ca_("developed", 2024, "fitted"), ca_("developed", 2024, "observed")
    p23, o23 = ca_("developed", 2023, "fitted"), ca_("developed", 2023, "observed")
    p25, o25 = ca_("developed", 2025, "fitted"), ca_("developed", 2025, "observed")
    if p24 < p23:
        n["de_holdout_text"] = (
            f"It reproduces the fall in 2024 (predicted {pct(p23, 1)} % to {pct(p24, 1)} %, "
            f"observed {pct(o23, 1)} % to {pct(o24, 1)} %) and gives {pct(p25, 1)} % for "
            f"2025 against {pct(o25, 1)} %.")
    else:
        n["de_holdout_text"] = (
            f"It gives {pct(p25, 1)} % for 2025 against {pct(o25, 1)} % but not the fall in "
            f"2024 ({pct(p24, 1)} % against {pct(o24, 1)} %): the end of the premium slows "
            f"growth in the model rather than reversing it.")
        if o23 > p23 and o24 < p24:
            # observed 2023 above the path, 2024 below it: purchases brought forward
            n["de_holdout_text"] += (
                f" The observed {pct(o23, 1)} % of 2023 (model {pct(p23, 1)} %) includes "
                f"purchases brought forward before companies lost the premium in September "
                f"2023 [bmwk-umweltbonus-2022]; the model has no such anticipation.")
    n["in_2025_pred"] = pct(ca_("developing", 2025, "fitted"), 0)
    n["in_2025_obs"] = pct(ca_("developing", 2025, "observed"), 0)
    # two-wheeler panel (third revision)
    panel = RES / "calibration_panel.json"
    if panel.exists():
        pm = json.loads(panel.read_text(encoding="utf-8"))
        n["beta_2w"] = f(pm["beta"], 1)
        n["beta_2w_se"] = f(pm["beta_se"], 1)
    tr = read("calibration_transfer.csv")
    if tr is not None:
        loco = tr[~tr.country.str.contains("check")]
        n["transfer_range"] = rng(100 * loco.mape.min(), 100 * loco.mape.max(), 0)
        n["vn_mape"] = pct(float(tr[tr.country.str.contains("Vietnam")].mape.iloc[0]), 0)
    # converter model fitted to datasheets and to the Prius light-load map
    dfit = read("device_fit.csv")
    if dfit is not None:
        n["dev_fit_max"] = f(100 * dfit.rel_error.abs().max(), 0)
    ll = read("light_load_fit.csv")
    if ll is not None:
        for s, tag in (("fit", "fit"), ("held out", "test")):
            g_ = ll[ll.set == s]
            n[f"ll_mae_{tag}"] = f(100 * (g_.model - g_.measured).abs().mean(), 1)
            n[f"ll_mae0_{tag}"] = f(100 * (g_.model_without_ripple - g_.measured).abs().mean(), 1)
    bench = read("validation_benchmark_feeders.csv")
    if bench is not None:
        b_ = bench.dropna(subset=["published_losses_kw"])
        n["bench_loss_err"] = f(100 * float((abs(b_.losses_kw - b_.published_losses_kw)
                                             / b_.published_losses_kw).max()), 2)
        n["bench_v_err"] = f(float(abs(b_.v_min_pu - b_.published_v_min_pu).max()), 4)
    sis = RES / "silicon_sensitivity.csv"
    if sis.exists():
        si = pd.read_csv(sis)
        n["si_mult"] = f(float(si.silicon_loss_mult.iloc[0]), 1)
        n["si_peak"] = pct(float(si.igbt_peak_375v.iloc[0]), 1)
        n["si_rank_changes"] = str(int(si.rank_changes_vs_base.iloc[0]))
        n["si_rank_changes_word"] = ("no" if int(si.rank_changes_vs_base.iloc[0]) == 0
                                     else str(int(si.rank_changes_vs_base.iloc[0])))
        sde = si[(si.archetype == "developed") & (si.pe_mode == "device")
                 & (si.lever == "all_pe")].iloc[0]
        n["si_de_npv"] = f(sde.d_npv_musd / 1e3, 1)
        n["si_de_co2"] = f(sde.d_co2_mt, 1)
    sil = RES / "silicon_sensitivity_low.csv"
    if sil.exists():
        sl = pd.read_csv(sil)
        n["si_low_mult"] = f(float(sl.silicon_loss_mult.iloc[0]), 2)
        n["si_low_gain"] = pct(float(sl.range_gain_sic800.iloc[0]), 1)
        k_ = int(sl.rank_changes_vs_base.iloc[0])
        n["si_low_rank_changes_word"] = "no" if k_ == 0 else str(k_)
        sle = sl[(sl.archetype == "developed") & (sl.pe_mode == "device")
                 & (sl.lever == "all_pe")].iloc[0]
        n["si_low_de_npv"] = f(sle.d_npv_musd / 1e3, 1)
        n["si_low_de_co2"] = f(sle.d_co2_mt, 1)
        if sis.exists():
            k_hi = int(pd.read_csv(sis).rank_changes_vs_base.iloc[0])
            n["si_both_rank_text"] = (
                "Neither bracket changes any package rank." if k_hi == 0 and k_ == 0 else
                f"The brackets change {k_hi} and {k_} package ranks.")
    inv = pd.read_csv(RES / "emission_reconciliation.csv")
    de = inv[inv.country == "Germany"].iloc[0]
    n["inv_de_model"] = f(de.model_ttw_mt, 1)
    n["inv_de_err"] = f(abs(100 * (de.ratio_model_to_inventory - 1)), 0)
    n["inv_bd_model"] = f(inv[inv.country == "Bangladesh"].model_ttw_mt.iloc[0], 1)
    ldc_ = inv[inv.archetype == "underdeveloped"]
    n["inv_ldc_model"] = f(ldc_.model_ttw_mt.iloc[0], 1)
    n["inv_ldc_bounds"] = " and ".join(f"{v:.1f}" for v in sorted(ldc_.inventory_mt))
    n["inv_all_below"] = str(bool(inv[inv.comparison == "bound"].consistent.all()))
    assert inv[inv.comparison == "bound"].consistent.all(), "a modeled total exceeds its bound"
    lit = read("validation_converter_literature.csv")
    if lit is not None:
        ig = lit[lit.quantity.str.contains("Si IGBT traction inverter, peak")]
        n["igbt_peak"] = rng(100 * ig.model.min(), 100 * ig.model.max(), 1)
        rg_row = lit[lit.quantity.str.contains("SiC-MOSFET at 800 V")].iloc[0]
        n["range_gain_model"] = f(100 * rg_row.model, 1)
        m_ = re.search(r"UDDS ([+-][\d.]+) %, HWFET ([+-][\d.]+) %", rg_row.quantity)
        if m_:
            n["range_udds"] = m_.group(1).lstrip("+")
            n["range_hwfet"] = m_.group(2).lstrip("+")
        ig8 = lit[lit.quantity.str.contains("Si-IGBT at 800 V")]
        if not ig8.empty:
            n["range_gain_igbt800"] = f(100 * float(ig8.model.iloc[0]), 1)
        ch = lit[lit.quantity.str.contains("PFC|on-board|fast-charger", case=False)]
        dev = [max(0.0, r_.published_low - r_.model) if str(r_.published).startswith(">")
               else abs(r_.model - r_.published_low) for _, r_ in ch.iterrows()]
        n["conv_err_max"] = f(100 * max(dev), 1)
    ieee = read("validation_ieee33.csv")
    if ieee is not None:
        e = ieee.iloc[0]
        n["ieee_loss"] = f(e.losses_kw, 2)
        n["ieee_vmin"] = f(e.v_min_pu, 4)
        n["ieee_loss_err"] = f(100 * e.losses_relative_error, 3)
        n["ieee_v_err"] = f"{e.v_min_abs_error_pu:.0e}".replace("e-05", "×10⁻⁵").replace(
            "e-06", "×10⁻⁶")
    q = read("validation_queue.csv")
    if q is not None:
        n["q_err"] = f(100 * q.relative_error.max(), 1)
    eb = read("validation_energy_balance.csv")
    if eb is not None:
        v = eb.relative_residual.max()
        mant, ex = f"{v:.1e}".split("e")
        n["eb_res"] = f"${mant}\\times10^{{{int(ex)}}}$"
    sg_ = read("segment_economics.csv")
    if sg_ is not None:
        q_ = sg_[(sg_.archetype == "developing") & (sg_.policy == "S5") & (sg_.year == 2035)
                 & (sg_.segment == "two_wheeler")]
        n["whkm_bd_2w"] = f(float(q_.wh_per_km.iloc[0]), 0)
    pl = read("validation_plausibility.csv")
    if pl is not None:
        n["plaus_pass"] = str(int(pl.within_band.sum()))
        n["plaus_total"] = str(len(pl))
        bad = pl[~pl.within_band]
        if bad.empty:
            n["plaus_fail_text"] = ""
        else:
            items = []
            nice = {"Traction inverter, SiC MOSFET, weighted efficiency":
                        "load-weighted efficiency of the SiC traction inverter",
                    "Electric two-wheeler consumption (developing, 2035)":
                        "two-wheeler consumption in Bangladesh in 2035",
                    "Distribution network loss fraction (developed, 2035)":
                        "German distribution loss fraction in 2035"}
            why = {"two-wheeler": "which reflects low urban speeds",
                   "loss fraction": "which excludes the low-voltage networks where most "
                                    "losses arise"}
            for _, b in bad.iterrows():
                val = (f"{100 * b.model_value:.2f} %" if b.unit == "-" else
                       f"{b.model_value:.1f} {b.unit}")
                rng_ = (f"{100 * b.band_low:.1f}-{100 * b.band_high:.1f} %" if b.unit == "-"
                        else f"{b.band_low:.2f}-{b.band_high:.2f} {b.unit}" if b.band_high < 10
                        else f"{b.band_low:.0f}-{b.band_high:.0f} {b.unit}")
                q = nice.get(b.quantity, _lc(b.quantity))
                reason = next((r_ for k_, r_ in why.items() if k_ in b.quantity), "")
                items.append(f"{q} ({val} against {rng_})" + (f", {reason}" if reason else ""))
            joined = (items[0] if len(items) == 1 else
                      ", ".join(items[:-1]) + ", and the " + items[-1])
            n["plaus_fail_text"] = "Outside them lie the " + joined + "."

    # ---- converters -------------------------------------------------------
    car = VEHICLE_LIBRARY["passenger_car"]
    m_car = pe.mission_of(car, "wltc3b")          # the German car cycle of the model
    cyc = {(k, v): pe.cycle_efficiency(k, 150.0, v, m_car, 40.0)
           for k, v in (("Si-IGBT", 400.0), ("SiC-MOSFET", 400.0), ("Si-IGBT", 800.0),
                        ("SiC-MOSFET", 800.0))}
    n["cyc_igbt"] = pct(cyc[("Si-IGBT", 400.0)], 2)
    n["cyc_sic"] = pct(cyc[("SiC-MOSFET", 400.0)], 2)
    n["cyc_igbt800"] = pct(cyc[("Si-IGBT", 800.0)], 2)
    n["cyc_sic800"] = pct(cyc[("SiC-MOSFET", 800.0)], 2)
    n["cyc_gap"] = f(100 * (cyc[("SiC-MOSFET", 400.0)] - cyc[("Si-IGBT", 400.0)]), 2)
    d800 = cyc[("Si-IGBT", 800.0)] - cyc[("Si-IGBT", 400.0)]
    n["igbt800_text"] = (
        f"At 800 V the 1200 V IGBT converts {pct(cyc[('Si-IGBT', 800.0)], 2)} %, "
        + ("slightly more, because halving the current more than offsets the higher "
           "switching energy of the 1200 V part; SiC reaches "
           f"{pct(cyc[('SiC-MOSFET', 800.0)], 2)} %." if d800 > 0 else
           "so moving a silicon inverter to 800 V costs energy; SiC reaches "
           f"{pct(cyc[('SiC-MOSFET', 800.0)], 2)} %."))
    cs = pd.read_csv(RES / "converter_converter_summary.csv")

    def w(topo, dev):
        return float(cs[(cs.topology == topo) & (cs.device == dev)].weighted_efficiency.iloc[0])
    n["w_gap"] = f(100 * (w("traction_inverter_400V", "SiC-MOSFET")
                          - w("traction_inverter_400V", "Si-IGBT")), 2)
    # which device leads each stage (load-weighted), and whether every unipolar
    # device beats the Si IGBT in every hard-switched stage
    dname = {"Si-IGBT": "the Si IGBT", "Si-MOSFET": "the super-junction MOSFET",
             "SiC-MOSFET": "SiC", "GaN-HEMT": "GaN"}
    stages = [("traction_inverter_400V", "the traction inverter"),
              ("obc_pfc_11kW", "the totem-pole power-factor correction"),
              ("dcfc_afe_150kW", "the DC-charger front end"),
              ("obc_dab_11kW", "the soft-switched dual-active bridge"),
              ("dcfc_iso_150kW", "the isolated DC-charger stage")]
    lead_by: dict[str, list[str]] = {}
    for topo, lab in stages:
        sub = cs[cs.topology == topo]
        lead = str(sub.loc[sub.weighted_efficiency.idxmax(), "device"])
        lead_by.setdefault(lead, []).append(lab)
    hard = ("traction_inverter_400V", "obc_pfc_11kW", "dcfc_afe_150kW")
    uni_beat = all(w(t_, d_) > w(t_, "Si-IGBT")
                   for t_ in hard for d_ in ("Si-MOSFET", "SiC-MOSFET", "GaN-HEMT"))
    parts_ = []
    for dev_, labs in lead_by.items():
        labs_ = labs[0] if len(labs) == 1 else ", ".join(labs[:-1]) + " and " + labs[-1]
        parts_.append(f"{dname[dev_]} in {labs_}")
    lead_txt = (parts_[0] if len(parts_) == 1 else
                "; ".join(parts_[:-1]) + "; and " + parts_[-1])
    n["stage_leaders_text"] = (
        ("Every unipolar device beats the Si IGBT in the hard-switched stages, but which "
         "leads depends on the stage (Fig. 3(d)): " if uni_beat else
         "Which device leads depends on the stage (Fig. 3(d)): ") + lead_txt + "."
        + (" In the soft-switched bridge the higher frequencies of WBG devices raise "
           "magnetic losses." if lead_by.get("Si-MOSFET") and any(
               "dual-active" in x for x in lead_by["Si-MOSFET"]) else ""))
    n["w_sj_800"] = pct(w("traction_inverter_800V", "Si-MOSFET"), 2)
    n["w_sj_400"] = pct(w("traction_inverter_400V", "Si-MOSFET"), 2)
    tw = VEHICLE_LIBRARY["three_wheeler"]
    m3 = pe.mission_of(tw, 21.0 * 0.72)
    n["lv_gain"] = f(100 * (pe.cycle_efficiency("GaN-LV", 7.5, 60.0, m3, 50.0)
                            - pe.cycle_efficiency("Si-LV", 7.5, 60.0, m3, 50.0)), 2)
    rel = pd.read_csv(RES / "converter_reliability.csv")

    def dtj(mission, dev):
        return float(rel[(rel.mission == mission) & (rel.device == dev)]
                     .delta_tj_fast_p95_k.iloc[0])
    n["dtj_car_igbt"] = f(dtj("passenger_car_400V", "Si-IGBT"), 0)
    n["dtj_car_sic"] = f(dtj("passenger_car_400V", "SiC-MOSFET"), 0)
    n["dtj_chg_igbt"] = f(dtj("dc_charger_150kW_session", "Si-IGBT"), 0)
    n["dtj_chg_sic"] = f(dtj("dc_charger_150kW_session", "SiC-MOSFET"), 0)
    n["dtj_bus_igbt"] = f(dtj("bus_650V", "Si-IGBT"), 0)
    # which converters reach the 30 K lower bound of power-cycling tests
    names = {"passenger_car_400V": "car inverter", "passenger_car_800V": "800 V car inverter",
             "bus_650V": "city-bus inverter", "three_wheeler_60V": "three-wheeler drive",
             "two_wheeler_60V": "two-wheeler drive",
             "dc_charger_150kW_session": "fast-charger front end"}
    tech = {"Si-IGBT": "Si IGBT", "Si-MOSFET": "Si super-junction", "SiC-MOSFET": "SiC",
            "GaN-HEMT": "GaN", "Si-LV": "100 V Si", "GaN-LV": "100 V GaN"}
    over = rel[rel.delta_tj_fast_p95_k >= 29.5].sort_values("delta_tj_fast_p95_k",
                                                            ascending=False)
    items = [f"the {tech.get(o.device, o.device)} {names.get(o.mission, o.mission)} "
             f"({o.delta_tj_fast_p95_k:.0f} K)" for o in over.itertuples()]
    sic_max = rel[rel.device == "SiC-MOSFET"].delta_tj_fast_p95_k.max()
    if not items:
        n["swing_text"] = ("No converter reaches that bound, so power cycling does not "
                           "limit any of them.")
    else:
        joined = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
        light = {"passenger_car_400V", "passenger_car_800V", "two_wheeler_60V"}
        assert not light & set(over.mission), "a car or two-wheeler converter exceeds 30 K"
        n["swing_text"] = (f"Only {joined} reach{'es' if len(items) == 1 else ''} it; SiC "
                           f"stays below {f(sic_max + 0.5, 0)} K throughout.")

    # ---- representations ---------------------------------------------------
    marg = read("pe_lever_marginal.csv")
    if marg is not None:
        def mg(a, lever, mode, col):
            return float(marg[(marg.archetype == A3[a]) & (marg.lever == lever)
                              & (marg.pe_mode == mode)][col].iloc[0])
        ratio = (mg("bd", "wbg_mandate", "lookup", "d_eta_traction_pp")
                 / max(mg("bd", "wbg_mandate", "device", "d_eta_traction_pp"), 1e-9))
        n["wbg_bd_lookup_ratio"] = (f"a factor of {ratio:.1f}" if ratio >= 1.15
                                    else f"{100 * (ratio - 1):.0f} %")
        n["wbg_bd_lookup_under"] = f"{100 * (1 - ratio):.0f} %"
        all_ratio = (mg("de", "all_pe", "lookup", "d_eta_traction_pp")
                     / max(mg("de", "all_pe", "device", "d_eta_traction_pp"), 1e-9))
        n["pe_de_eta_lu_share"] = f"{100 * all_ratio:.0f} %"
        n["pe_de_eta_dev"] = f(mg("de", "all_pe", "device", "d_eta_traction_pp"), 2)
        n["pe_de_eta_lu"] = f(mg("de", "all_pe", "lookup", "d_eta_traction_pp"), 2)
        for a in A3:
            for mode, tag in (("device", "dev"), ("lookup", "lu"), ("constant", "const")):
                n[f"pe_{a}_co2_{tag}"] = f(mg(a, "all_pe", mode, "d_co2_mt"), 2)
                n[f"pe_{a}_npv_{tag}"] = f(mg(a, "all_pe", mode, "d_npv_musd") / 1e3, 1)
        n["pe_max_co2"] = f(max(mg(a, "all_pe", "device", "d_co2_mt") for a in A3), 1)
        n["pe_small_co2"] = f(max(mg(a, "all_pe", "device", "d_co2_mt")
                                  for a in ("bd", "ldc")), 2)
        wd =mg("de", "wbg_mandate", "device", "d_eta_traction_pp")
        wl = mg("de", "wbg_mandate", "lookup", "d_eta_traction_pp")
        n["wbg_de_lookup_diff"] = f"{abs(100 * (wl / wd - 1)):.1f} %"
        hv_share = (mg("de", "hv_architecture", "lookup", "d_eta_traction_pp")
                    / mg("de", "hv_architecture", "device", "d_eta_traction_pp"))
        n["hv_de_share"] = (f"about half" if 0.4 <= hv_share <= 0.6
                            else f"{100 * hv_share:.0f} %")
        n["pe_de_lu_share"] = (f"{100 * mg('de', 'all_pe', 'lookup', 'd_npv_musd') / mg('de', 'all_pe', 'device', 'd_npv_musd'):.0f} %")
        n["pe_de_npv_const_abs"] = f(abs(mg("de", "all_pe", "constant", "d_npv_musd")) / 1e3, 1)
        n["hv_de_dev"] = f(mg("de", "hv_architecture", "device", "d_eta_traction_pp"), 3)
        n["hv_de_lu"] = f(mg("de", "hv_architecture", "lookup", "d_eta_traction_pp"), 3)
    pmr = read("pe_mode_ranking.csv")
    if pmr is not None:
        p = pmr[pmr.policy != "S0"].pivot_table(index=["archetype", "policy"],
                                                columns="pe_mode", values="policy_rank")
        words = {0: "None", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}

        def changed(mode: str) -> list[tuple[str, str]]:
            d = p[p[mode] != p["device"]]
            return [(a, pol_) for a, pol_ in d.index]
        ch_lu, ch_co = changed("lookup"), changed("constant")
        n["rank_changes_lookup"] = words.get(len(ch_lu), str(len(ch_lu))).lower()
        n["rank_changes_const"] = words.get(len(ch_co), str(len(ch_co))).lower()

        def describe(ch: list[tuple[str, str]]) -> str:
            by: dict[str, list[str]] = {}
            for a, pol_ in ch:
                by.setdefault(a, []).append(pol_)
            return " and ".join(f"{' and '.join(sorted(v))} in {ANAME[a]}"
                                for a, v in by.items())
        if not ch_lu and not ch_co:
            n["rank_change_text"] = ("Neither the technology lookup nor the constant "
                                     "efficiency changes any package rank (Fig. 4(d)): the "
                                     "representation changes the value of the "
                                     "power-electronics instruments, not the order of the "
                                     "packages.")
            n["const_rank_clause"] = "although no package rank changes"
            n["const_rank_cover"] = "although no package rank changes"
            n["rank_change_followup"] = ""
        else:
            parts = []
            parts.append("The technology lookup changes no package rank" if not ch_lu else
                         f"The technology lookup changes {len(ch_lu)} of the eighteen "
                         f"package ranks ({describe(ch_lu)})")
            parts.append("the constant efficiency changes none" if not ch_co else
                         f"the constant efficiency changes "
                         f"{words.get(len(ch_co), len(ch_co)).lower()}: it swaps "
                         f"{describe(ch_co)}")
            n["rank_change_text"] = "; ".join(parts) + " (Fig. 4(d))."
            k_ = words.get(len(ch_co), str(len(ch_co))).lower()
            n["const_rank_clause"] = (f"and with a constant efficiency {k_} of eighteen "
                                      f"package ranks change" if ch_co else
                                      "although a constant efficiency changes no package rank")
            n["const_rank_cover"] = (f"and a constant efficiency reorders {k_} of eighteen "
                                     f"package ranks" if ch_co else
                                     "although a constant efficiency reorders no package")
            n["rank_change_followup"] = ("The changes concern adjacent packages, so the "
                                         "fixed-efficiency baseline misorders but does not "
                                         "overturn the rankings.")
        n["s2_de_bcr_dev"] = f(float(pmr[(pmr.archetype == "developed") & (pmr.policy == "S2")
                                         & (pmr.pe_mode == "device")].incremental_bcr.iloc[0]), 2)
        n["s2_de_bcr_const"] = f(float(pmr[(pmr.archetype == "developed")
                                           & (pmr.policy == "S2")
                                           & (pmr.pe_mode == "constant")]
                                       .incremental_bcr.iloc[0]), 2)

    # ---- network, queues, emissions ------------------------------------------
    ab = read("network_ablation.csv")
    if ab is not None:
        def abl(a, v, col):
            return float(ab[(ab.archetype == A3[a]) & (ab.variant == v)][col].iloc[0])
        n["abl_bd_s0"] = f(abl("bd", "S0", "tx_loading_2040_pu"), 2)
        n["abl_bd_s5"] = f(abl("bd", "S5", "tx_loading_2040_pu"), 2)
        n["abl_bd_s5_orig"] = f(abl("bd", "S5", "tx_loading_vs_original_rating_pu"), 2)
        n["abl_bd_s5r"] = f(abl("bd", "S5 without reinforcement", "tx_loading_2040_pu"), 2)
        n["abl_bd_s5f"] = f(abl("bd", "S5 without flexibility", "tx_loading_2040_pu"), 2)
        n["abl_de_s5_orig"] = f(abl("de", "S5", "tx_loading_vs_original_rating_pu"), 2)
        n["abl_de_s5f_orig"] = f(abl("de", "S5 without flexibility",
                                     "tx_loading_vs_original_rating_pu"), 2)
    fc = read("feeder_concentration.csv")
    if fc is not None:
        def cc(a, p, k):
            return float(fc[(fc.archetype == A3[a]) & (fc.policy == p)
                            & (fc.concentration == k)].tx_loading_2040_pu.iloc[0])
        n["conc_bd_s5_1"] = f(cc("bd", "S5", 1.0), 2)
        n["conc_bd_s5_3"] = f(cc("bd", "S5", 3.0), 2)
        n["conc_de_s5_3"] = f(cc("de", "S5", 3.0), 2)
        n["conc_de_s0_3"] = f(cc("de", "S0", 3.0), 2)
        n["conc_de_s0_3_uv"] = pct(float(fc[(fc.archetype == "developed")
                                             & (fc.policy == "S0")
                                             & (fc.concentration == 3.0)]
                                          .undervoltage_hours_frac.iloc[0]), 0)
    qm = read("queue_mode_comparison.csv")
    if qm is not None:
        def qq(a, p, mode):
            return float(qm[(qm.archetype == A3[a]) & (qm.policy == p)
                            & (qm.queue_mode == mode)].wait_2040_min.iloc[0])
        n["q_bd_s1_pooled"] = f(qq("bd", "S1", "pooled"), 0)
        n["q_bd_s1_site"] = f(qq("bd", "S1", "site"), 0)
        n["q_de_s0_pooled"] = f(qq("de", "S0", "pooled"), 0)
        n["q_de_s0_site"] = f(qq("de", "S0", "site"), 0)
    dec = read("emission_intensity_decomposition.csv")
    if dec is not None:
        d = dec[dec.archetype == "developing"].iloc[0]
        n["dec_bd_total"] = f"{d.change_g_km:+.1f}"
        n["dec_bd_timing"] = f"{d.timing_effect:+.1f}"
        n["dec_bd_grid"] = f"{d.grid_effect:+.1f}"
        n["dec_bd_energy"] = f"{d.energy_effect:+.1f}"
        n["night_bd_s0"] = pct(d.night_share_S0, 0)
        n["night_bd_s5"] = pct(d.night_share_S5, 0)
        n["solar_bd_s0"] = pct(d.solar_share_S0, 0)
        n["solar_bd_s5"] = pct(d.solar_share_S5, 0)
        n["dec_ldc_total"] = f"{dec[dec.archetype == 'underdeveloped'].change_g_km.iloc[0]:+.1f}"
        # the text says "rises by": an unsigned magnitude
        n["dec_ldc_rise"] = f(abs(dec[dec.archetype == "underdeveloped"].change_g_km.iloc[0]), 1)
        n["timing_all_negative"] = str(bool((dec.timing_effect < 0).all()))
    # night share of charging in the first submission's own Bangladesh results
    v1 = ROOT / "_archive_v1_submitted_TTE-Reg-2026-08-3015" / "results"
    if (v1 / "series_developing_S0_2035.csv").exists():
        for p in ("S0", "S5"):
            s = pd.read_csv(v1 / f"series_developing_{p}_2035.csv")
            e = s.ev_mw.to_numpy()
            h = np.arange(e.size) % 24
            n[f"v1_night_{p.lower()}"] = pct(e[(h < 6) | (h >= 22)].sum() / e.sum(), 0)

    # ---- robustness -------------------------------------------------------
    mc = read("monte_carlo_samples.csv")
    if mc is not None:
        for a in A3:
            s0 = mc[(mc.archetype == A3[a]) & (mc.policy == "S0")].set_index("sample").npv_musd
            s5 = mc[(mc.archetype == A3[a]) & (mc.policy == "S5")].set_index("sample").npv_musd
            n[f"mc_p_{a}"] = pct(float(((s5 - s0) > 0).mean()), 0)
    mcs = read("monte_carlo_summary.csv")
    if mcs is not None:
        n["cv_eta"] = f(float(mcs[mcs.metric == "mean_eta_traction"].cv.max()), 4)
    mo = read("sensitivity_morris.csv")
    if mo is not None:
        tops = {}
        for a in ("bd", "de", "ldc"):
            t = mo[(mo.archetype == A3[a]) & (mo.target == "npv_musd")]
            lab = str(t.sort_values("mu_star", ascending=False).label.iloc[0])
            n[f"morris_top_{a}"] = "the " + _lc(lab)
            tops[a] = n[f"morris_top_{a}"]
        groups: dict[str, list[str]] = {}
        for a in ("bd", "de", "ldc"):
            groups.setdefault(tops[a], []).append(ANAME[A3[a]])
        items = list(groups.items())
        if len(items) == 1:
            text = (f"Morris screening identifies {items[0][0]} as the main influence on "
                    f"NPV in all three archetypes")
        else:
            text = (f"Morris screening identifies {items[0][0]} as the main influence on "
                    f"NPV in {' and '.join(items[0][1])}")
            for lab, where in items[1:]:
                text += f", and {lab} in {' and '.join(where)}"
        n["morris_text"] = text + "."
    ad = read("adoption_structure_rank_agreement.csv")
    if ad is not None:
        # the analog-country variants replace only the transferred two-wheeler
        # coefficients; Germany keeps its own calibration, so its analog rows are
        # identical to the base case and are not counted as tests
        alt = ad[(ad.variant != "base")
                 & ~(ad.variant.str.startswith("analog") & (ad.archetype == "developed"))]
        n["adopt_same_first"] = str(int(alt.same_first.sum()))
        n["adopt_cases"] = str(len(alt))
        n["adopt_tau_min"] = f(float(alt.kendall_tau.min()), 2)
        sens = read("adoption_structure_sensitivity.csv")
        vname = {"elasticity x0.5": "with halved elasticities",
                 "elasticity x1.5": "with elasticities raised by half",
                 "hazard form": "under the speed form",
                 "analog India": "with India's coefficients",
                 "analog Indonesia": "with Indonesia's coefficients",
                 "analog Kenya": "with Kenya's coefficients"}
        # group the exceptions by new leader and archetype, so the sentence
        # reads "Bangladesh with India's or Kenya's coefficients, where S1 leads"
        by_lead: dict[str, dict[str, list[str]]] = {}
        n_exc = 0
        for row in alt[~alt.same_first].itertuples():
            lead = sens[(sens.variant == row.variant) & (sens.archetype == row.archetype)
                        & (sens.policy_rank == 1)].policy.iloc[0]
            by_lead.setdefault(lead, {}).setdefault(row.archetype, []).append(row.variant)
            n_exc += 1

        def _variants(vs: list[str]) -> str:
            if all(v.startswith("analog ") for v in vs):
                return ("with " + " or ".join(f"{v.split()[1]}'s" for v in vs)
                        + " coefficients")
            return " or ".join(vname.get(v, v) for v in vs)
        cases = []
        for lead, archs in by_lead.items():
            parts_ = [f"{ANAME[a]} {_variants(vs)}" for a, vs in archs.items()]
            joined_ = parts_[0] if len(parts_) == 1 else ", ".join(parts_[:-1]) + " and " + parts_[-1]
            cases.append(f"{joined_}, where {lead} leads")
        n["adopt_change_text"] = ("" if not cases else
                                  "The exception" + ("s are " if n_exc > 1 else " is ")
                                  + "; ".join(cases) + ".")
        # adoption with India's coefficients, and S1's benefit-cost ratio
        ind = sens[(sens.variant == "analog India") & (sens.archetype == "developing")]
        for p_ in ("S1", "S6"):
            n[f"bd_{p_.lower()}_ev_india"] = pct(float(
                ind[ind.policy == p_].final_ev_share.iloc[0]), 0)
        lost = []
        for (v_, a_), g_ in sens[sens.policy != "S0"].groupby(["variant", "archetype"]):
            best = g_.loc[g_.incremental_bcr.idxmax(), "policy"]
            if best != "S1":
                lost.append(f"{ANAME[a_]} {vname.get(v_, v_)} ({best})")
        n["s1_bcr_text"] = ("S1 keeps the highest benefit-cost ratio in every case." if not lost
                            else "S1 keeps the highest benefit-cost ratio except in "
                            + "; ".join(lost) + ".")
    rec_ = read("scenario_records.csv")
    if rec_ is not None and "v_min__in_rural28" in rec_:
        r_ = rec_[(rec_.archetype == "developing") & (rec_.policy == "S0") & (rec_.year == 2040)]
        n["bd_rural_vmin"] = f(float(r_.v_min__in_rural28.iloc[0]), 3)
        n["bd_urban_vmin"] = f(float(r_.v_min__ieee69.iloc[0]), 3)
    sur = read("surrogate_performance.csv")
    if sur is not None:
        n["r2_npv_range"] = rng(sur.r2_npv_musd.min(), sur.r2_npv_musd.max(), 2)
        n["r2_co2_range"] = rng(sur.r2_cumulative_emissions_saved_mt.min(),
                                sur.r2_cumulative_emissions_saved_mt.max(), 2)
        n["r2_tx_range"] = rng(sur.r2_final_transformer_loading.min(),
                               sur.r2_final_transformer_loading.max(), 2)
        if "r2_rf_npv_musd" in sur:
            n["r2_rf_npv_range"] = rng(sur.r2_rf_npv_musd.min(), sur.r2_rf_npv_musd.max(), 2)
    pv = read("pareto_verification.csv")
    if pv is not None:
        e_n = pv[pv.objective == "npv_musd"].median_abs_error_norm
        e_c = pv[pv.objective == "cumulative_emissions_saved_mt"].median_abs_error_norm
        n["pareto_err_npv"] = rng(100 * e_n.min(), 100 * e_n.max(), 0)
        n["pareto_err_co2"] = rng(100 * e_c.min(), 100 * e_c.max(), 0)
        for a in A3:
            q = pv[(pv.archetype == A3[a]) & (pv.objective == "npv_musd")]
            n[f"pareto_err_npv_{a}"] = f(100 * float(q.median_abs_error_norm.iloc[0]), 0)
        if sur is not None:
            for a in A3:
                n[f"r2_npv_{a}"] = f(float(sur[sur.archetype == A3[a]].r2_npv_musd.iloc[0]), 2)
    sob = read("sensitivity_sobol.csv")
    if sob is not None:
        from evdt.policy import LEVERS
        tops = []
        for a in A3:
            t = sob[(sob.archetype == A3[a]) & (sob.target == "npv_musd")]
            top = t.sort_values("ST", ascending=False).iloc[0]
            lab = LEVERS[top.lever].label
            tops.append((ANAME[A3[a]], _lc(lab), top.ST))
        grouped: dict[str, list[str]] = {}
        for an, lab, st in tops:
            grouped.setdefault(lab, []).append(f"{an} ({st:.2f})")
        parts = []
        for lab, wh in grouped.items():
            where_ = wh[0] if len(wh) == 1 else ", ".join(wh[:-1]) + " and " + wh[-1]
            parts.append(f"{'' if lab.endswith('electrification') else 'the '}{lab} in {where_}")
        n["sobol_text"] = ("The levers with the largest total Sobol index for NPV are "
                           + (parts[0] if len(parts) == 1
                              else parts[0] + ", and " + parts[1] if len(parts) == 2
                              else "; ".join(parts[:-1]) + "; and " + parts[-1])
                           + " (Supplementary Fig. S2(a)).")
    seq = read("sequencing.csv")
    if seq is not None:
        def sq(a, s):
            return float(seq[(seq.archetype == A3[a]) & (seq.sequence == s)].d_npv_musd.iloc[0])
        n["seq_bd_access_co2"] = f(float(seq[(seq.archetype == "developing")
                                             & (seq.sequence == "access first")].d_co2_mt.iloc[0]), 0)
        n["seq_bd_system_co2"] = f(float(seq[(seq.archetype == "developing")
                                             & (seq.sequence == "system first")].d_co2_mt.iloc[0]), 0)
        n["seq_access_best_all"] = str(bool(all(
            seq[seq.archetype == a].set_index("sequence").d_npv_musd.idxmax() == "access first"
            for a in seq.archetype.unique())))
        n["seq_bd_access"] = f(sq("bd", "access first") / 1e3, 1)
        n["seq_bd_system"] = f(sq("bd", "system first") / 1e3, 1)
        n["seq_bd_simul"] = f(sq("bd", "simultaneous") / 1e3, 1)

    meta_opt = RES / "optimization_meta.json"
    if meta_opt.exists():
        mo_ = json.loads(meta_opt.read_text(encoding="utf-8"))
        if "n_anchor" in mo_:            # written by the revised stage 3 only
            n["n_design"] = str(mo_["n_design"] + mo_["n_anchor"])
            n["n_test"] = str(mo_["n_test"])
            n["n_verify"] = str(mo_["n_verify"])

    # Typographic minus for negative values: Word may break a line after a hyphen,
    # separating the sign from its number.  Ranges (2025-2040, 0.66-0.93) and
    # exponents inside TeX math ({-17}) keep the hyphen.
    for k, v in n.items():
        if isinstance(v, str):
            n[k] = re.sub(r"(?<![\w)}{^])-(?=\d)", "−", v)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(n, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(n)} numbers -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
