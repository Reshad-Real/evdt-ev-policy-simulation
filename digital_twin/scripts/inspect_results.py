import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd, numpy as np
R = pathlib.Path(__file__).resolve().parents[2] / "results"
pd.set_option("display.width", 250, "display.max_columns", 60)

rk = pd.read_csv(R / "policy_ranking.csv")
cols = ["archetype", "policy", "final_ev_share", "final_wbg_share", "mean_eta_traction",
        "final_wait_min", "npv_musd", "bcr", "incremental_bcr", "payback_years",
        "cumulative_emissions_saved_mt", "abatement_cost_usd_t", "policy_score",
        "policy_rank", "sustainability_score", "technology_readiness"]
for a in ("underdeveloped", "developing", "developed"):
    print(f"\n===== {a} =====")
    print(rk[rk.archetype == a][cols].to_string(index=False,
          float_format=lambda v: f"{v:,.3f}"))

print("\n===== converter summary (traction inverter 400 V) =====")
cs = pd.read_csv(R / "converter_converter_summary.csv")
print(cs[cs.topology == "traction_inverter_400V"][
    ["device", "f_sw_khz", "weighted_efficiency", "efficiency_at_rated", "p_total_w",
     "t_junction_c", "kw_per_litre", "cost_usd", "n_parallel"]].to_string(index=False))

print("\n===== reliability =====")
print(pd.read_csv(R / "converter_reliability.csv").to_string(index=False))

print("\n===== battery EOL =====")
be = pd.read_csv(R / "battery_eol.csv")
print(be[be.dc_share.isin([0.0, 0.7])].to_string(index=False))
