"""Stage 0: calibration of the adoption model and reconciliation of emissions.

Adoption (second revision).  Adoption is modelled as the electric share of new
registrations (mobility.adoption_multipliers, engine.adoption_step).  The Bass
coefficients of the underlying diffusion are fitted to the historical sales
share of an anchor country with the purchase incentive it actually paid
entering through the ownership-cost ratio, using only the years up to and
including ``CAL_END``; later years are held out and predicted, so the reported
error is out of sample (for Germany the held-out years contain the cut and the
end of the purchase premium).  The price elasticity is set from the European
panel estimate of Muenzel et al. (2019) and compared with the value the German
series alone gives.  After the fit, the reference package S0 is run with every
policy multiplier at one and its parity, adequacy and awareness are logged for
each year; other packages are measured against that path, so S0 reproduces the
fitted diffusion exactly and every policy response is a departure from it.

Emissions.  The tank-to-wheel CO2 of the modelled segments in the base year,
if every vehicle burned fuel, is compared with the national road-transport
inventory of the anchor country (for the share of the inventory the modelled
segments represent).

Data and sources: ``data/calibration_data.csv`` and ``data/inventory_data.csv``
(every row names its source); results: ``results/calibration_*.csv`` and
``results/emission_reconciliation.csv``.

Usage:  py -3 calibrate.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evdt import economics as eco, engine, mobility as mob, policy as pol  # noqa: E402
from evdt import scenarios as sc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
RESULTS = ROOT / "results"


#: segment whose economics translate a purchase premium into parity
PREMIUM_SEGMENT = {"developed": "passenger_car", "developing": "two_wheeler",
                   "underdeveloped": "two_wheeler"}
#: Muenzel et al. (Energy Econ. 2019): 5-7 % relative increase of the sales
#: share per 1,000 EUR of incentive across 32 European countries, 2010-2017
INCENTIVE_EFFECT = (0.05, 0.06, 0.07)
AVG_BEV_PRICE_EUR = 40000.0


def reference_conditions(arch) -> dict:
    """Parity, adequacy, awareness and ceiling of S0 in the base year, and the
    segment economics used to translate a purchase premium into parity."""
    s0 = sc.policy_packages(arch.key)["S0"]
    levels = s0.resolve(2025)
    p = pol.apply(arch, levels, 2025)
    state = engine.TwinState()
    rec = engine.simulate_year(replace(arch, parity_ref=1.0, adequacy_ref=1.0,
                                       awareness_ref=None, reference_path={}),
                               s0, 2025, state, seed=1)
    seg = PREMIUM_SEGMENT.get(arch.key, "passenger_car")
    return {"parity": rec["price_parity"],
            "adequacy": float(np.clip(p["connectors_per_1000"] / 28.0, 0.05, 1.8)),
            "awareness": p["awareness"],
            "ceiling": float(np.clip(arch.market_potential * p["supply_constraint"],
                                     0.0, 1.0)),
            "car": rec["segment_economics"][seg],
            "car_segment": engine.segment(arch, seg)}


def premium_ratio(ref: dict, arch, fraction: np.ndarray) -> np.ndarray:
    """Ownership-cost ratio with a purchase premium relative to none, pi(f)/pi(0).

    A premium of ``fraction`` of the price lowers the purchase price and, with
    it, the discounted residual value; running costs are unchanged.
    """
    car, seg = ref["car"], ref["car_segment"]
    resid = 0.30 / (1.0 + arch.discount_rate) ** seg.ownership_years
    tco0 = car["tco_ev"]
    tco_f = tco0 - np.asarray(fraction, float) * car["price_ev"] * (1.0 - resid)
    return tco0 / tco_f


def simulate_sales(years: np.ndarray, s_first: float, m0: float, ratio: np.ndarray,
                   p: float, q: float, beta: float) -> np.ndarray:
    """Sales-share path of the second-revision adoption model from an observed
    first year: F diffuses (Bass), s = min(1, m0 ratio^beta F)."""
    f = s_first / (m0 * ratio[0] ** beta)
    out = [s_first]
    for i in range(1, len(years)):
        f = mob.bass_step(f, p, q, float(years[i] - years[i - 1]))
        out.append(min(1.0, m0 * ratio[i] ** beta * f))
    return np.array(out)


def fit_sales(years, sales, ratio, m0, fit_beta: bool, beta_fixed: float = 0.0):
    """Least squares on log sales share; returns (p, q, beta, se_beta, result)."""
    def unpack(th):
        return np.exp(th[0]), np.exp(th[1]), (th[2] if fit_beta else beta_fixed)

    def resid(th):
        p, q, b = unpack(th)
        pred = simulate_sales(years, sales[0], m0, ratio, p, q, b)
        return np.log(np.maximum(pred[1:], 1e-7)) - np.log(sales[1:])

    best = None
    for p0 in (1e-4, 1e-3, 1e-2):
        for q0 in (0.2, 0.5, 0.9):
            x0 = [np.log(p0), np.log(q0)] + ([1.5] if fit_beta else [])
            lo = [np.log(1e-6), np.log(1e-3)] + ([0.0] if fit_beta else [])
            hi = [np.log(0.2), np.log(2.0)] + ([8.0] if fit_beta else [])
            r = least_squares(resid, x0, bounds=(lo, hi))
            if best is None or r.cost < best.cost:
                best = r
    p, q, b = unpack(best.x)
    se_b = np.nan
    if fit_beta:
        n, k = best.fun.size, best.x.size
        if n > k:
            s2 = 2.0 * best.cost / (n - k)
            try:
                cov = s2 * np.linalg.inv(best.jac.T @ best.jac)
                se_b = float(np.sqrt(max(cov[2, 2], 0.0)))
            except np.linalg.LinAlgError:
                pass
    return float(p), float(q), float(b), se_b, best


#: two-wheeler markets with a price incentive inside the series
PANEL_COUNTRIES = ("India", "Indonesia", "Kenya")


def _panel_series(panel: pd.DataFrame, ref: dict, arch, countries) -> list:
    out = []
    for c in countries:
        sub = panel[panel.country == c].sort_values("year")
        out.append((c, sub.year.to_numpy(float), sub.ev_sales_share.to_numpy(float),
                    premium_ratio(ref, arch, sub.incentive_fraction.to_numpy(float))))
    return out


def panel_fit(series: list, m0: float, beta: float | None = None):
    """Joint least squares on log sales share: one price elasticity shared by
    all countries (estimated unless ``beta`` is given), Bass p and q per
    country.  Returns (beta, se_beta, {country: (p, q)}, result)."""
    k = len(series)
    nb = 1 if beta is None else 0

    def unpack(th):
        b = th[0] if beta is None else beta
        pq = np.asarray(th[nb:]).reshape(k, 2)
        return b, np.exp(pq[:, 0]), np.exp(pq[:, 1])

    def resid(th):
        b, p, q = unpack(th)
        out = []
        for j, (_, yrs, obs, ratio) in enumerate(series):
            pred = simulate_sales(yrs, obs[0], m0, ratio, p[j], q[j], b)
            out.append(np.log(np.maximum(pred[1:], 1e-7)) - np.log(obs[1:]))
        return np.concatenate(out)

    best = None
    for b0 in ((1.0, 3.0, 6.0) if beta is None else (None,)):
        for p0 in (1e-4, 1e-3, 1e-2):
            for q0 in (0.3, 0.8):
                x0 = ([b0] if beta is None else []) + [np.log(p0), np.log(q0)] * k
                lo = ([0.0] if beta is None else []) + [np.log(1e-6), np.log(1e-3)] * k
                hi = ([12.0] if beta is None else []) + [np.log(0.2), np.log(3.0)] * k
                r = least_squares(resid, x0, bounds=(lo, hi))
                if best is None or r.cost < best.cost:
                    best = r
    b, p, q = unpack(best.x)
    se_b = np.nan
    if beta is None:
        n, npar = best.fun.size, best.x.size
        if n > npar:
            s2 = 2.0 * best.cost / (n - npar)
            try:
                se_b = float(np.sqrt(max((s2 * np.linalg.inv(best.jac.T @ best.jac))[0, 0], 0)))
            except np.linalg.LinAlgError:
                pass
    coef = {c: (float(p[j]), float(q[j])) for j, (c, *_rest) in enumerate(series)}
    return float(b), se_b, coef, best


def panel_means(coef: dict) -> tuple[float, float, float, float]:
    """Geometric means of p and q across countries and the between-country
    standard deviations of log p and log q (the transfer distribution)."""
    lp = np.log([v[0] for v in coef.values()])
    lq = np.log([v[1] for v in coef.values()])
    return (float(np.exp(lp.mean())), float(np.exp(lq.mean())),
            float(lp.std(ddof=1)) if lp.size > 1 else np.nan,
            float(lq.std(ddof=1)) if lq.size > 1 else np.nan)


def transfer_errors(series: list, m0: float) -> list[dict]:
    """Leave-one-country-out: fit the panel without country c and predict c
    from its first observation with the other countries' mean coefficients."""
    rows = []
    for j, (c, yrs, obs, ratio) in enumerate(series):
        others = [s for i, s in enumerate(series) if i != j]
        b, _, coef, _ = panel_fit(others, m0)
        p, q, _, _ = panel_means(coef)
        pred = simulate_sales(yrs, obs[0], m0, ratio, p, q, b)
        ape = np.abs(pred[1:] - obs[1:]) / obs[1:]
        rows.append({"country": c, "years": f"{int(yrs[1])}-{int(yrs[-1])}",
                     "beta_without": b, "p_mean_without": p, "q_mean_without": q,
                     "mape": float(np.mean(ape)),
                     "rmse_log": float(np.sqrt(np.mean((np.log(np.maximum(pred[1:], 1e-7))
                                                        - np.log(obs[1:])) ** 2))),
                     "predicted_last": float(pred[-1]), "observed_last": float(obs[-1])})
    return rows


CAL_END = 2022          # calibration years end here; later years are held out
REF_SEED = 20260801     # seed of the deterministic campaign (run_deterministic.SEED)


def main() -> None:
    cal = pd.read_csv(DATA / "calibration_data.csv", comment="#")
    rows, summary = [], []
    params = {}
    beta_hat = beta_se = None
    # Two-wheeler panel (third revision): developing and least-developed
    # archetypes take the panel's shared price elasticity and mean Bass
    # coefficients; the transfer error is measured by leaving each country out.
    panel = pd.read_csv(DATA / "adoption_panel.csv", comment="#")
    dev = sc.ARCHETYPES["developing"]
    ref_dev = reference_conditions(dev)
    m0_dev = ref_dev["ceiling"]
    series = _panel_series(panel[panel.set == "fit"], ref_dev, dev, PANEL_COUNTRIES)
    beta_p, beta_p_se, coef, _ = panel_fit(series, m0_dev)
    p_bar, q_bar, sd_lp, sd_lq = panel_means(coef)
    transfer = transfer_errors(series, m0_dev)
    # India's own hold-out inside the panel: its years after CAL_END removed
    series_ho = [(c, y[y <= CAL_END], o[y <= CAL_END], r[y <= CAL_END]) if c == "India"
                 else (c, y, o, r) for c, y, o, r in series]
    beta_ho, _, coef_ho, _ = panel_fit(series_ho, m0_dev)
    for c, yrs, obs, ratio in series:
        p_c, q_c = coef[c]
        fit_all = simulate_sales(yrs, obs[0], m0_dev, ratio, p_c, q_c, beta_p)
        if c == "India":
            p_h, q_h = coef_ho[c]
            ho = simulate_sales(yrs, obs[0], m0_dev, ratio, p_h, q_h, beta_ho)
        else:
            ho = fit_all
        for y, o, f, fa, fr in zip(yrs, obs, ho, fit_all,
                                   panel[panel.country == c].sort_values("year")
                                   .incentive_fraction.to_numpy(float)):
            rows.append({"archetype": "developing" if c == "India" else "panel",
                         "country": c, "series": "sales", "year": int(y), "observed": o,
                         "fitted": f, "fitted_all_years": fa, "incentive_fraction": fr,
                         "set": ("calibration" if (c != "India" or y <= CAL_END)
                                 else "validation")})
    india = series[[s[0] for s in series].index("India")]
    val_in = india[1] > CAL_END
    p_h, q_h = coef_ho["India"]
    pred_in = simulate_sales(india[1], india[2][0], m0_dev, india[3], p_h, q_h, beta_ho)
    ape_in = np.abs(pred_in[val_in] - india[2][val_in]) / india[2][val_in]
    # checks: Vietnam (no incentive) from the panel means; Bangladesh level
    vn = panel[panel.country == "Vietnam"].sort_values("year")
    vn_pred = simulate_sales(vn.year.to_numpy(float), float(vn.ev_sales_share.iloc[0]),
                             m0_dev, np.ones(len(vn)), p_bar, q_bar, beta_p)
    transfer.append({"country": "Vietnam (check, no incentive)",
                     "years": f"{int(vn.year.iloc[1])}-{int(vn.year.iloc[-1])}",
                     "beta_without": beta_p, "p_mean_without": p_bar, "q_mean_without": q_bar,
                     "mape": float(np.mean(np.abs(vn_pred[1:] - vn.ev_sales_share.to_numpy()[1:])
                                           / vn.ev_sales_share.to_numpy()[1:])),
                     "rmse_log": float(np.sqrt(np.mean((np.log(vn_pred[1:])
                                                        - np.log(vn.ev_sales_share.to_numpy()[1:]))
                                                       ** 2))),
                     "predicted_last": float(vn_pred[-1]),
                     "observed_last": float(vn.ev_sales_share.iloc[-1])})
    for y, o, pr_ in zip(vn.year, vn.ev_sales_share, vn_pred):
        rows.append({"archetype": "panel_check", "country": "Vietnam", "series": "sales",
                     "year": int(y), "observed": float(o), "fitted": float(pr_),
                     "fitted_all_years": float(pr_), "incentive_fraction": 0.0,
                     "set": "check"})
    pd.DataFrame(transfer).to_csv(RESULTS / "calibration_transfer.csv", index=False)
    panel_meta = {"countries": list(PANEL_COUNTRIES), "beta": beta_p, "beta_se": beta_p_se,
                  "p_mean": p_bar, "q_mean": q_bar, "sd_log_p": sd_lp, "sd_log_q": sd_lq,
                  "coefficients": {c: {"p": v[0], "q": v[1]} for c, v in coef.items()},
                  "india_holdout_mape": float(np.mean(ape_in)),
                  "india_holdout_beta": beta_ho,
                  "transfer_mape_mean": float(np.mean([t["mape"] for t in transfer[:3]]))}
    (RESULTS / "calibration_panel.json").write_text(json.dumps(panel_meta, indent=1),
                                                    encoding="utf-8")

    # Germany first: its premium history identifies the car price elasticity.
    order = ["developed"] + [a for a in sc.ARCHETYPE_ORDER if a != "developed"]
    for akey in order:
        sub = cal[(cal.archetype == akey) & (cal.series == "sales")].sort_values("year")
        arch = sc.ARCHETYPES[akey]
        ref = reference_conditions(arch)
        m0 = ref["ceiling"]
        common = {"parity_ref": ref["parity"], "adequacy_ref": ref["adequacy"],
                  "awareness_ref": ref["awareness"]}
        if akey in ("developing", "underdeveloped"):
            params[akey] = {"bass_p": p_bar, "bass_q": q_bar, "price_elasticity": beta_p,
                            "base_sales_share": None, **common}
            summary.append({
                "archetype": akey,
                "country": "two-wheeler panel (" + ", ".join(PANEL_COUNTRIES) + ")",
                "series": "sales", "source": "data/adoption_panel.csv",
                "calibration_years": "India 2018-2025, Indonesia 2020-2025, Kenya 2021-2025",
                "validation_years": "leave-one-country-out; India 2023-2025",
                "ceiling_m": m0, "p": p_bar, "q": q_bar, "beta": beta_p,
                "beta_own_se": beta_p_se, "sd_log_p": sd_lp, "sd_log_q": sd_lq,
                "mape_validation": float(np.mean(ape_in)),
                "max_ape_validation": float(np.max(ape_in)),
                "transfer_mape_mean": panel_meta["transfer_mape_mean"],
                **common})
            continue
        if sub.empty:
            # No usable history: prior coefficients, interpreted like the fitted
            # ones (sales-share diffusion at reference conditions).
            params[akey] = {"bass_p": arch.bass_p, "bass_q": arch.bass_q,
                            "price_elasticity": beta_hat, "base_sales_share": None,
                            **common}
            summary.append({"archetype": akey, "country": "none (prior)", "series": "",
                            "source": "no historical series; prior values",
                            "ceiling_m": m0, "p": arch.bass_p, "q": arch.bass_q,
                            "beta": beta_hat, **common})
            continue
        yrs = sub.year.to_numpy(float)
        obs = sub.ev_sales_share.to_numpy(float)
        frac = sub.incentive_fraction.fillna(0.0).to_numpy(float)
        ratio = premium_ratio(ref, arch, frac)
        calm = yrs <= CAL_END
        extra = {}
        if akey == "developed":
            # The price elasticity is set from the European panel estimate of
            # Muenzel et al. (6 % per 1,000 EUR, range 5-7 %), translated through
            # the model's own car economics; the German series alone gives a
            # consistent but much less precise estimate, reported as a check.
            r1 = float(premium_ratio(ref, arch,
                                     np.array([1000.0 / AVG_BEV_PRICE_EUR]))[0])
            b_lo, beta_hat, b_hi = (float(np.log1p(e) / np.log(r1)) for e in INCENTIVE_EFFECT)
            _, _, b_own, se_own, _ = fit_sales(yrs, obs, ratio, m0, True)
            extra = {"beta_literature_low": b_lo, "beta_literature_high": b_hi,
                     "beta_own_estimate": b_own, "beta_own_se": se_own,
                     "own_effect_per_1000eur": r1 ** b_own - 1.0}
        # hold-out test: fit p and q on the calibration years and predict the
        # rest with the observed premium history (Germany: the 2023 cut and the
        # December 2023 end of the premium; India: the June 2023 FAME-II cut)
        p_h, q_h, b_h, _, _ = fit_sales(yrs[calm], obs[calm], ratio[calm], m0, False,
                                        beta_hat)
        pred = simulate_sales(yrs, obs[0], m0, ratio, p_h, q_h, b_h)
        # projection coefficients: refit on all years
        p_a, q_a, b_a, se_a, res = fit_sales(yrs, obs, ratio, m0, False, beta_hat)
        pred_all = simulate_sales(yrs, obs[0], m0, ratio, p_a, q_a, b_a)
        for y, o, f, fa, c, fr in zip(yrs, obs, pred, pred_all, calm, frac):
            rows.append({"archetype": akey, "country": sub.country.iloc[0],
                         "series": "sales", "year": int(y), "observed": o, "fitted": f,
                         "fitted_all_years": fa, "incentive_fraction": fr,
                         "set": "calibration" if c else "validation"})
        val = ~calm
        ape = np.abs(pred[val] - obs[val]) / obs[val]
        if akey == "developed":
            # stock implied by the fitted sales through turnover, from the
            # observed stock at the end of the year before the series starts
            st = cal[(cal.archetype == akey) & (cal.series == "stock")].set_index("year")
            life = float(sub.lifetime_y.iloc[0])
            g = float(sub.stock_growth.iloc[0])
            x = float(st.ev_stock_share.loc[int(yrs[0]) - 1])
            for y, s in zip(yrs, pred_all):
                x = mob.turnover_step(x, s, life, g)
                rows.append({"archetype": akey, "country": sub.country.iloc[0],
                             "series": "stock", "year": int(y),
                             "observed": float(st.ev_stock_share.get(int(y), np.nan)),
                             "fitted": np.nan, "fitted_all_years": x,
                             "incentive_fraction": np.nan, "set": "check"})
            extra.update({"stock_2025_model": x,
                          "stock_2025_observed": float(st.ev_stock_share.loc[2025]),
                          "sales_effect_per_1000eur": r1 ** b_a - 1.0})
        summary.append({
            "archetype": akey, "country": sub.country.iloc[0], "series": "sales",
            "source": sub.source.iloc[0],
            "calibration_years": f"{int(yrs[calm][0])}-{int(yrs[calm][-1])}",
            "validation_years": f"{int(yrs[val][0])}-{int(yrs[val][-1])}" if val.any() else "",
            "ceiling_m": m0, "p_holdout_fit": p_h, "q_holdout_fit": q_h,
            "beta_holdout_fit": b_h, "p": p_a, "q": q_a, "beta": b_a,
            "rmse_log_all_years": float(np.sqrt(np.mean(
                (np.log(pred_all[1:]) - np.log(obs[1:])) ** 2))),
            "rmse_log_calibration": float(np.sqrt(np.mean(
                (np.log(pred[1:][calm[1:]]) - np.log(obs[1:][calm[1:]])) ** 2))),
            "mape_validation": float(np.mean(ape)) if val.any() else np.nan,
            "max_ape_validation": float(np.max(ape)) if val.any() else np.nan,
            **extra, **common})
        params[akey] = {"bass_p": p_a, "bass_q": q_a,
                        "price_elasticity": beta_hat if beta_hat is not None else b_a,
                        "base_sales_share": float(obs[-1]) if akey == "developed" else None,
                        **common}

    # Reference paths: S0 with every policy multiplier at one (the fitted
    # diffusion), logging the parity, adequacy and awareness each year.
    for akey in sc.ARCHETYPE_ORDER:
        arch = replace(sc.ARCHETYPES[akey], **params[akey], reference_path={})
        s0 = sc.policy_packages(akey)["S0"]
        out = engine.simulate_horizon(arch, s0, sc.HORIZON, seed=REF_SEED,
                                      reference_run=True)
        params[akey]["reference_path"] = out["state"].reference_log

    pd.DataFrame(rows).to_csv(RESULTS / "calibration_adoption.csv", index=False)
    pd.DataFrame(summary).to_csv(RESULTS / "calibration_summary.csv", index=False)
    (Path(__file__).resolve().parent / "configs" / "calibrated_adoption.json").write_text(
        json.dumps(params, indent=1), encoding="utf-8")

    # --- emission reconciliation ----------------------------------------
    inv = pd.read_csv(DATA / "inventory_data.csv", comment="#")
    rec_rows = []
    for _, r in inv.iterrows():
        arch = sc.ARCHETYPES[r.archetype]
        stock = arch.vehicle_stock_million * 1e6 * (1 + arch.vehicle_stock_growth) ** (
            int(r.model_year) - 2025)
        tot = 0.0
        for s in str(r.segments).split(";"):
            share = arch.segment_shares.get(s, 0.0)
            if share <= 0:
                continue
            seg = engine.segment(arch, s)
            # only the combustion part of the base-year fleet emits
            n_ice = stock * share * (1.0 - arch.base_ev_share)
            litres = n_ice * seg.annual_km * seg.ice_l_per_100km / 100.0
            tot += litres * eco.FUEL_TTW_KG_PER_L[seg.fuel]
        model_mt = tot / 1e9
        rec_rows.append({"archetype": r.archetype, "country": r.country,
                         "inventory_year": int(r.year), "segments": r.segments,
                         "comparison": r.comparison,
                         "inventory_mt": float(r.inventory_mt),
                         "model_ttw_mt": model_mt,
                         "ratio_model_to_inventory": model_mt / float(r.inventory_mt),
                         "consistent": bool(abs(model_mt / float(r.inventory_mt) - 1) <= 0.10
                                            if r.comparison == "match"
                                            else model_mt <= float(r.inventory_mt)),
                         "source": r.source})
    pd.DataFrame(rec_rows).to_csv(RESULTS / "emission_reconciliation.csv", index=False)
    print(pd.DataFrame(summary).to_string())
    print(pd.DataFrame(rec_rows).to_string())


if __name__ == "__main__":
    main()
