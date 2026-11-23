"""Figures of the revised TTE manuscript (resubmission of TTE-Reg-2026-08-3015).

Every figure is drawn at its final printed size (IEEE two-column text width
7.16 in) so that the lettering prints at the sizes set below: at least 8 pt
everywhere (tick labels 8.5 pt, axis labels and titles 9 pt, panel letters
10 pt), legible at 100 % zoom.  Everything is drawn from the result files in
``results/``; nothing is hand-entered.  Captions live in build_tte.py.

    F1  model structure and the three representations of power electronics
    F2  calibration and validation against independent data
    F3  converter performance and sub-hourly thermal swings
    F4  what device-level modelling changes (representation comparison)
    F5  package outcomes: adoption, additional abatement, economics, emissions
    F6  network, queues and robustness
    S1  (supplement) inventory reconciliation, IEEE 33-bus and queue verification

Usage:  py -3 literature/tte_figures.py [F1 ... S1]
Output: "Manuscript TTE/build/figures/F*.png|pdf" and S1_verification.png|pdf
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digital_twin"))

import matplotlib                                        # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402
import numpy as np                                       # noqa: E402
import pandas as pd                                      # noqa: E402
from matplotlib.lines import Line2D                      # noqa: E402
from matplotlib.patches import Patch                     # noqa: E402
from matplotlib.ticker import (FixedLocator, FuncFormatter, LogLocator,  # noqa: E402
                               NullFormatter, NullLocator)

from evdt import plotting as P                           # noqa: E402
from evdt import powerelectronics as pe                  # noqa: E402
from evdt.config import VEHICLE_LIBRARY                  # noqa: E402

RES = ROOT / "results"
# In the public reproduction package there is no manuscript folder: write to figures/.
OUT = (ROOT / "Manuscript TTE" / "build" / "figures"
       if (ROOT / "Manuscript TTE").exists() else ROOT / "figures")
W2, W1 = 7.16, 3.50
WS = 6.5                       # text width of the supplementary document
# lettering at print size [pt]
FS_LAB, FS_TICK, FS_LEG, FS_NOTE, FS_TAG = 9.0, 8.5, 8.0, 8.0, 10.0

ARCHS = ["underdeveloped", "developing", "developed"]
AB = {"underdeveloped": "LDC", "developing": "BD", "developed": "DE"}
ANAME = {"underdeveloped": "Least-developed", "developing": "Developing (BD)",
         "developed": "Developed (DE)"}
DEV = ["Si-IGBT", "Si-MOSFET", "SiC-MOSFET", "GaN-HEMT"]
DEVN = {"Si-IGBT": "Si IGBT", "Si-MOSFET": "Si SJ", "SiC-MOSFET": "SiC",
        "GaN-HEMT": "GaN", "Si-LV": "Si 100 V", "GaN-LV": "GaN 100 V"}
DCOL = dict(P.DEVICE_COLOR, **{"Si-LV": "#8C8C8C", "GaN-LV": "#009E73"})
POLS = [f"S{i}" for i in range(7)]
MODES = ["device", "lookup", "constant"]
MCOL = {"device": "#0072B2", "lookup": "#E69F00", "constant": "#8C8C8C"}
MNAME = {"device": "device level", "lookup": "technology lookup",
         "constant": "constant efficiency"}


def style() -> None:
    P.setup()
    matplotlib.rcParams.update({
        "font.size": FS_LAB, "axes.titlesize": FS_LAB, "axes.labelsize": FS_LAB,
        "xtick.labelsize": FS_TICK, "ytick.labelsize": FS_TICK,
        "legend.fontsize": FS_LEG, "axes.titleweight": "bold", "axes.titlepad": 5.0,
        "lines.linewidth": 1.4, "axes.linewidth": 0.8, "savefig.dpi": 600,
        "legend.handlelength": 1.4, "legend.columnspacing": 0.9,
        "legend.handletextpad": 0.4, "legend.borderaxespad": 0.3})


def _plain_log(ax, subs=(1.0, 2.0, 5.0)) -> None:
    """Log axis with plain decimal tick labels (0.1, 1, 10) instead of powers."""
    ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=subs))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())


def tag_auto(fig, axes_letters) -> None:
    """Panel letters level with each title, left of the y-axis label and tick labels,
    so that a letter never collides with an axis label or a neighbouring panel."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    inv = fig.transFigure.inverted()
    for ax, letter in axes_letters:
        x0 = min(ax.yaxis.get_tightbbox(r).x0, ax.get_window_extent(r).x0)
        y0 = ax.title.get_window_extent(r).y0
        fx, fy = inv.transform((x0, y0))
        fig.text(fx, fy, f"({letter})", fontsize=FS_TAG, fontweight="bold",
                 va="bottom", ha="left")


def legend_below(ax, ncol: int, dy: float = -0.16, **kw):
    opts = {"handlelength": 1.1, "columnspacing": 0.8}
    opts.update(kw)
    return ax.legend(ncol=ncol, loc="upper center", bbox_to_anchor=(0.5, dy), **opts)


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=600, bbox_inches="tight",
                    pad_inches=0.03)
    plt.close(fig)
    print(f"  wrote {name}")


# ---------------------------------------------------------------------------
def f1_structure(name: str = "F1_structure", table_ref: str = "Table S0",
                 section_ref: str = "Section IV-B") -> None:
    """Model structure. The labels name the instrument table and the section of
    the comparison, which differ between the TTE and Applied Energy versions."""
    fig = plt.figure(figsize=(W2, 2.0))
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    P.blank_axes(ax)
    blue, orange, green, purple, grey = ("#0072B2", "#D55E00", "#009E73",
                                         "#6A3D9A", "#44546A")
    y, h = 0.465, 0.33
    boxes = [
        (0.003, 0.128, f"Instruments\n20 levers\n({table_ref})", orange),
        (0.146, 0.130, "Power\nelectronics\n(1)-(3)", blue),
        (0.291, 0.130, "Energy and\nadoption\n(4)-(5)", green),
        (0.436, 0.128, "Charging\nqueues\n(6)", purple),
        (0.579, 0.128, "Feeders,\n3 types\n(7)", blue),
        (0.722, 0.135, "CO$_2$ and\ncost-benefit\n(8)-(9)", grey),
        (0.872, 0.125, "TOPSIS,\nMAC\n(10)", grey),
    ]
    for x, w, txt, c in boxes:
        P.box(ax, x, y, w, h, txt, "#FFFFFF", c, fontsize=8.5)
    for i in range(len(boxes) - 1):
        x0 = boxes[i][0] + boxes[i][1]
        P.arrow(ax, x0 + 0.002, y + h / 2, boxes[i + 1][0] - 0.002, y + h / 2,
                color=grey, lw=1.0)
    below = [
        (0.090, 0.245, "Datasheet-fitted modules;\nthree representations\n"
                       f"compared ({section_ref})", "#F2F7FB", blue, 0.211),
        (0.350, 0.222, "Calibration and hold-out:\nKBA (DE), 2W panel (IN,\n"
                       "ID, KE); CRF, Climate Watch", "#F4FAF6", green, 0.400),
        (0.587, 0.165, "Weather, solar,\nsupply availability,\nhourly prices",
         "#F7F7F7", grey, 0.643),
        (0.768, 0.229, "Robustness: weights,\nadoption structure, Monte\n"
                       "Carlo, Sobol, NSGA-II", "#F7F7F7", grey, 0.934),
    ]
    for x, w, txt, fc, ec, xa in below:
        P.box(ax, x, 0.03, w, 0.31, txt, fc, ec, fontsize=8.0)
        P.arrow(ax, xa, 0.345, xa, y - 0.005, color=ec, lw=0.9)
    ax.text(0.5, 0.89, "Annual steps 2025-2040; hourly network, charging and emission "
            "profiles within each year", ha="center", fontsize=8.5, color=grey,
            style="italic")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    save(fig, name)


# ---------------------------------------------------------------------------
def f2_validation() -> None:
    cal = pd.read_csv(RES / "calibration_adoption.csv")
    lit = pd.read_csv(RES / "validation_converter_literature.csv")
    fig, axes = plt.subplots(1, 3, figsize=(W2, 2.65),
                             gridspec_kw={"width_ratios": [1.0, 1.0, 1.12]})
    fig.subplots_adjust(left=0.075, right=0.975, top=0.883, bottom=0.358, wspace=0.62)
    for ax, akey, title in ((axes[0], "developed", "Germany, BEV new cars"),
                            (axes[1], "developing", "India, e-2W sales")):
        sub = cal[(cal.archetype == akey) & (cal.series == "sales")]
        c = sub[sub.set == "calibration"]
        v = sub[sub.set == "validation"]
        ax.axvspan(v.year.min() - 0.5, v.year.max() + 0.5, color="#EBEBEB", zorder=0)
        ax.text(v.year.mean(), 0.42, "hold-\nout", transform=ax.get_xaxis_transform(),
                ha="center", va="center", fontsize=FS_NOTE, color="#666666")
        ax.plot(sub.year, 100 * sub.fitted, color="#0072B2", lw=1.5)
        ax.plot(sub.year, 100 * sub.fitted_all_years, color="#0072B2", lw=1.1, ls="--")
        ax.scatter(c.year, 100 * c.observed, s=20, color="#1A1A1A", zorder=3)
        ax.scatter(v.year, 100 * v.observed, s=24, facecolor="white", edgecolor="#D55E00",
                   lw=1.3, zorder=3)
        ax.set_yscale("log")
        _plain_log(ax)
        ax.set_title(title)
        ax.set_ylabel("Sales share (%)")
        if akey == "developing":
            ax.set_xticks([2019, 2021, 2023, 2025])
        ax2 = ax.twinx()
        ax2.step(sub.year, 100 * sub.incentive_fraction, where="mid", color="#E69F00",
                 lw=1.2)
        ax2.set_ylim(0, 4 * max(100 * sub.incentive_fraction.max(), 1.0))
        ax2.set_yticks([0, 20, 40])
        ax2.tick_params(axis="y", labelsize=FS_NOTE, colors="#A86F00", length=2.5, pad=1.5)
        for s in ("top", "left"):
            ax2.spines[s].set_visible(False)
        ax2.grid(False)
        P.despine(ax)
    handles = [Line2D([], [], color="#0072B2", lw=1.5),
               Line2D([], [], color="#0072B2", lw=1.1, ls="--"),
               Line2D([], [], ls="", marker="o", ms=5, color="#1A1A1A"),
               Line2D([], [], ls="", marker="o", ms=5, mfc="white", mec="#D55E00", mew=1.3),
               Line2D([], [], color="#E69F00", lw=1.2)]
    labels = ["fit, calibration years", "refit, all years", "observed (fit)",
              "observed (hold-out)", "incentive, % of price (right)"]
    fig.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.36, -0.01),
               frameon=False, handlelength=1.6, columnspacing=1.0)

    ax = axes[2]
    eff = lit[~lit.quantity.str.contains("range gain|light load")]
    names = ["IGBT 375 V", "IGBT 650 V", "IGBT 700 V", "SiC PFC", "WBG OBC",
             "SiC DC iso.", "Si DC iso."]
    pos = ax.get_position()
    ax.set_position([pos.x0 + 0.055, pos.y0, pos.width - 0.055, pos.height])
    yy = np.arange(len(eff))[::-1]
    for yi, (_, r) in zip(yy, eff.iterrows()):
        if r.published_high - r.published_low > 1e-6:
            ax.plot([100 * r.published_low, 100 * min(r.published_high, 1.0)], [yi, yi],
                    color="#BBBBBB", lw=5, solid_capstyle="butt")
        else:
            ax.scatter(100 * r.published_low, yi, marker="D", color="#888888", s=26,
                       zorder=2)
        ax.scatter(100 * r.model, yi, color="#0072B2", s=26, zorder=3)
    ax.set_yticks(yy)
    ax.set_yticklabels(names[:len(eff)])
    ax.set_xlabel("Peak efficiency (%)")
    ax.set_title("Converters vs measurements")
    ax.set_xlim(93.5, 100.2)
    ax.set_ylim(-0.6, len(eff) - 0.4)
    legend_below(ax, 1, dy=-0.29, handletextpad=0.6,
                 handles=[Line2D([], [], ls="", marker="o", ms=5.5, color="#0072B2"),
                          Line2D([], [], color="#BBBBBB", lw=5),
                          Line2D([], [], ls="", marker="D", ms=5, color="#888888")],
                 labels=["model", "published range", "published value"])
    P.despine(ax)
    tag_auto(fig, zip(axes, "abc"))
    save(fig, "F2_validation")


def _ieee33_profile() -> np.ndarray:
    import run_validation as rv
    from evdt import grid as gridmod
    from evdt.config import FeederConfig
    n = 33
    parent = np.full(n, -1, dtype=int)
    r = np.zeros(n); x = np.zeros(n); p = np.zeros(n); q = np.zeros(n)
    for f, t, rr, xx, pp, qq in rv.IEEE33:
        parent[t - 1] = f - 1
        r[t - 1], x[t - 1], p[t - 1], q[t - 1] = rr, xx, pp, qq
    depth = np.zeros(n, dtype=int)
    for i in range(1, n):
        depth[i] = depth[parent[i]] + 1
    order = np.argsort(depth, kind="stable")
    path = np.zeros((n, n))
    for node in order:
        if parent[node] >= 0:
            path[node] = path[parent[node]]
            path[node, node] = 1.0
    cfg = FeederConfig(n_nodes=n, base_voltage=12.66e3, base_power=10e6)
    fd = gridmod.Feeder(parent, r, x, np.ones(n) / n, order, cfg, np.ones(n), path)
    pf = gridmod.power_flow(fd, p[:, None] / 1e3, q[:, None] / 1e3, v_slack_pu=1.0,
                            tol=1e-10, max_iter=100)
    return pf["v_pu"][:, 0]


def fs1_verification() -> None:
    """Supplementary Fig. S1: inventory reconciliation, IEEE 33-bus profile and
    queue verification (moved from Fig. 2 of the paper to keep it legible)."""
    rec = pd.read_csv(RES / "emission_reconciliation.csv")
    q = pd.read_csv(RES / "validation_queue.csv")
    fig, axes = plt.subplots(1, 3, figsize=(WS, 2.6))
    fig.subplots_adjust(left=0.08, right=0.985, top=0.88, bottom=0.30, wspace=0.55)

    ax = axes[0]
    iso = {"Germany": "DE", "Bangladesh": "BD", "Tanzania": "TZ", "Ethiopia": "ET"}
    lab = [f"{iso.get(r.country, r.country[:2])}\n"
           f"{'CRF' if r.comparison == 'match' else 'bound'}" for _, r in rec.iterrows()]
    x = np.arange(len(rec))
    ax.bar(x - 0.19, rec.inventory_mt, width=0.36, color="#BBBBBB", label="inventory")
    ax.bar(x + 0.19, rec.model_ttw_mt, width=0.36, color="#0072B2", label="model")
    ax.set_yscale("log")
    _plain_log(ax, subs=(1.0, 2.0, 5.0))
    ax.set_xticks(x)
    ax.set_xticklabels(lab, fontsize=FS_NOTE)
    ax.set_ylabel("Road CO$_2$ (Mt/yr)")
    ax.set_title("Emissions vs inventories")
    ax.legend(loc="upper right")
    P.despine(ax)
    ax.grid(axis="x", visible=False)

    ax = axes[1]
    v = _ieee33_profile()
    for buses in ([*range(1, 19)], [*range(19, 23)], [*range(23, 26)], [*range(26, 34)]):
        ax.plot(buses, v[np.array(buses) - 1], color="#0072B2", marker="o", ms=3, lw=1.1)
    ax.scatter([18], [0.9131], marker="x", color="#D55E00", s=50, zorder=3, lw=1.6)
    ax.annotate("published\n$V_{min}$ 0.9131\nat bus 18", xy=(18, 0.9131),
                xytext=(9.0, 0.957), fontsize=FS_NOTE, color="#B7521A", ha="left",
                va="bottom", arrowprops=dict(arrowstyle="-", color="#B7521A", lw=0.8))
    ax.set_xlabel("Bus")
    ax.set_ylabel("Voltage (pu)")
    ax.set_title("IEEE 33-bus")
    P.despine(ax)

    ax = axes[2]
    ax.errorbar(q.simulated_wait_min, q.analytic_wait_min, xerr=1.96 * q.simulated_sd_min
                / np.sqrt(40), fmt="o", ms=4.5, color="#6A3D9A", lw=1.0)
    m = max(q.simulated_wait_min.max(), q.analytic_wait_min.max()) * 1.1
    ax.plot([0, m], [0, m], color="#999999", lw=0.9, ls="--")
    ax.set_xlabel("Simulated wait (min)")
    ax.set_ylabel("Erlang-C (6) (min)")
    ax.set_title("Queue check")
    P.despine(ax)
    tag_auto(fig, zip(axes, "abc"))
    save(fig, "S1_verification")


# ---------------------------------------------------------------------------
def f3_converters() -> None:
    """Efficiency curves of three drives and the stage comparison in one row
    (8-page version); the thermal panels are Supplementary Fig. S5."""
    eff = pd.read_csv(RES / "converter_efficiency_curves.csv")
    s = pd.read_csv(RES / "converter_converter_summary.csv")
    fig, axes = plt.subplots(1, 4, figsize=(W2, 2.45),
                             gridspec_kw={"width_ratios": [1.0, 1.0, 1.0, 1.5]})
    fig.subplots_adjust(left=0.065, right=0.99, top=0.87, bottom=0.235, wspace=0.48)

    panels = [("traction_inverter_400V", "150 kW, 400 V", DEV),
              ("traction_inverter_800V", "150 kW, 800 V", DEV),
              ("lv_drive_7p5kW_60V", "7.5 kW, 60 V", ["Si-LV", "GaN-LV"])]
    for ax, (topo, title, devs) in zip(axes[:3], panels):
        sub = eff[eff.topology == topo]
        legs = s[s.topology == topo].set_index("device").leg
        for d in devs:
            q = sub[sub.device == d]
            lab = DEVN[d] + (" (3L)" if legs.get(d) == "three-level" else "")
            ax.plot(q.load_pu * 100, q.efficiency * 100, color=DCOL[d], label=lab, lw=1.6)
        ax.set_title(title)
        ax.set_xlim(0, 100)
        ax.set_ylim(93, 100)
        ax.set_xticks([0, 50, 100])
        ax.set_xlabel("Load (% of rating)")
        P.despine(ax)
        ax.legend(loc="lower right", ncol=1, handlelength=1.0, labelspacing=0.2,
                  borderaxespad=0.1)
    axes[0].set_ylabel("Efficiency (%)")

    ax = axes[3]
    stages = [("traction_inverter_400V", "Inv\n400"), ("traction_inverter_800V", "Inv\n800"),
              ("obc_pfc_11kW", "PFC"), ("obc_dab_11kW", "DAB"),
              ("dcfc_afe_150kW", "AFE"), ("dcfc_iso_150kW", "DC\niso")]
    x = np.arange(len(stages))
    w = 0.2
    for k, d in enumerate(DEV):
        v = [s[(s.topology == t_) & (s.device == d)].weighted_efficiency.iloc[0] * 100
             for t_, _ in stages]
        ax.bar(x + (k - 1.5) * w, v, width=w, color=DCOL[d], label=DEVN[d])
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in stages], fontsize=FS_NOTE)
    ax.set_ylim(97.0, 99.6)
    ax.set_ylabel("Weighted eff. (%)")
    ax.set_title("By stage")
    # the tall inverter bars are at the left; the upper right is free
    ax.legend(loc="upper right", ncol=2, handlelength=0.8, columnspacing=0.5,
              handletextpad=0.3, labelspacing=0.2, borderaxespad=0.1)
    P.despine(ax)
    ax.grid(axis="x", visible=False)
    tag_auto(fig, zip(axes, "abcd"))
    save(fig, "F3_converters")


def fs5_thermal() -> None:
    """Junction temperature on a drive cycle and thermal swings per mission
    (Fig. 3(e), (f) of the 10-page version)."""
    rel = pd.read_csv(RES / "converter_reliability.csv")
    fig, axes = plt.subplots(1, 2, figsize=(WS, 2.7))
    fig.subplots_adjust(left=0.10, right=0.985, top=0.88, bottom=0.27, wspace=0.42)
    ax = axes[0]
    car = VEHICLE_LIBRARY["passenger_car"]
    for d in ("Si-IGBT", "SiC-MOSFET"):
        tr = pe.drive_cycle_trace(d, 150.0, 400.0, car, 30.0, 25.0, seconds=150.0)
        ax.plot(tr["t_s"], tr["tj_c"], color=DCOL[d], lw=1.2, label=DEVN[d])
    ax2 = ax.twinx()
    ax2.plot(tr["t_s"], tr["speed_kmh"], color="#BBBBBB", lw=0.9, zorder=0)
    ax2.tick_params(axis="y", colors="#777777", labelsize=FS_NOTE)
    ax2.text(1.0, 1.02, "km/h", transform=ax2.transAxes, fontsize=FS_NOTE,
             color="#777777", ha="center", va="bottom")
    ax2.set_ylim(0, 160)
    ax2.set_yticks([0, 50, 100, 150])
    ax2.grid(False)
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Junction temp. (Â°C)")
    ax.set_title("Car, 0.1 s urban cycle")
    lo_, hi_ = ax.get_ylim()
    ax.set_ylim(lo_, hi_ + 0.45 * (hi_ - lo_))
    ax.legend(loc="upper left", ncol=2, handlelength=1.2, columnspacing=0.8)
    ax.spines["top"].set_visible(False)
    ax2.spines["top"].set_visible(False)

    ax = axes[1]
    missions = [("two_wheeler_60V", "2W"), ("three_wheeler_60V", "3W"),
                ("passenger_car_400V", "Car"), ("bus_650V", "Bus"),
                ("dc_charger_150kW_session", "DC\nchg.")]
    x = np.arange(len(missions))
    for j_, (m, _) in enumerate(missions):
        sub = rel[rel.mission == m]
        devs = list(sub.device)
        for k, d in enumerate(devs):
            off = (k - (len(devs) - 1) / 2) * 0.19
            v_ = sub[sub.device == d].delta_tj_fast_p95_k.iloc[0]
            ax.bar(j_ + off, v_, width=0.18, color=DCOL[d])
            if v_ > 70:   # clipped by the axis: print the value
                ax.text(j_ + off + 0.12, 66, f"{v_:.0f}", fontsize=FS_NOTE, ha="left",
                        va="top", color="#333333")
    lo = 30.0
    ax.axhspan(lo, 80, color="#F3D9C4", alpha=0.5, zorder=0)
    ax.axhline(lo, color="#B7521A", lw=1.0, ls="--")
    ax.text(4.45, 64, "lifetime-law\ntest range", fontsize=FS_NOTE, ha="right",
            va="top", color="#B7521A")
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in missions], fontsize=FS_NOTE)
    ax.set_ylabel(r"95th-pct. $\Delta T_j$ (K)")
    ax.set_title("Thermal swings per cycle")
    ax.set_ylim(0, 70)
    legend_below(ax, 4, dy=-0.30, handles=[Patch(color=DCOL[d]) for d in DEV],
                 labels=[DEVN[d] for d in DEV], handlelength=0.8, columnspacing=0.6)
    P.despine(ax)
    ax.grid(axis="x", visible=False)
    tag_auto(fig, zip(axes, "ab"))
    save(fig, "S5_thermal")


# ---------------------------------------------------------------------------
def f4_representation() -> None:
    marg = pd.read_csv(RES / "pe_lever_marginal.csv")
    rk = pd.read_csv(RES / "pe_mode_ranking.csv")
    # 2.5 in tall: 0.49 in above the axes, 0.72 in below for the rotated labels
    fig, axes = plt.subplots(1, 4, figsize=(W2, 2.5),
                             gridspec_kw={"width_ratios": [1.45, 0.85, 0.85, 1.15]})
    fig.subplots_adjust(left=0.07, right=0.99, top=0.804, bottom=0.288, wspace=0.78)
    levers = [("wbg_mandate", "WBG"), ("efficiency_standard", "Std."),
              ("hv_architecture", "800 V"), ("all_pe", "All")]
    ax = axes[0]
    x = np.arange(len(levers) * 3)
    w = 0.40
    labels = []
    for i, a in enumerate(ARCHS):
        for j, (lv, ln) in enumerate(levers):
            k = i * len(levers) + j
            for dm, mode in ((-w / 2, "device"), (w / 2, "lookup")):
                val = marg[(marg.archetype == a) & (marg.lever == lv)
                           & (marg.pe_mode == mode)].d_eta_traction_pp.iloc[0]
                ax.bar(k + dm, val, width=w, color=MCOL[mode])
            labels.append(ln)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=90, fontsize=FS_NOTE)
    for i, a in enumerate(ARCHS):
        ax.text(i * 4 + 1.5, -0.45, AB[a], transform=ax.get_xaxis_transform(),
                ha="center", fontsize=FS_TICK, fontweight="bold")
    for b in (3.5, 7.5):
        ax.axvline(b, color="#CCCCCC", lw=0.8)
    ax.axhline(0, color="#555555", lw=0.6)
    ax.set_ylabel("Traction eff. gain (pp)")
    ax.set_title("Per instrument")
    P.despine(ax)
    ax.grid(axis="x", visible=False)

    for ax, col, scale, ylab, title in (
            (axes[1], "d_co2_mt", 1.0, "Additional CO$_2$ (Mt)", "All PE: CO$_2$"),
            (axes[2], "d_npv_musd", 1e-3, "NPV change (bn USD)", "All PE: NPV")):
        sub = marg[marg.lever == "all_pe"]
        xx = np.arange(3)
        for j, mode in enumerate(MODES):
            vals = [sub[(sub.archetype == a) & (sub.pe_mode == mode)][col].iloc[0] * scale
                    for a in ARCHS]
            ax.bar(xx + (j - 1) * 0.27, vals, width=0.26, color=MCOL[mode])
        ax.set_xticks(xx)
        ax.set_xticklabels([AB[a] for a in ARCHS])
        ax.axhline(0, color="#555555", lw=0.6)
        ax.set_ylabel(ylab)
        ax.set_title(title)
        P.despine(ax)
        ax.grid(axis="x", visible=False)
    # the low values of LDC and BD leave panel (b) empty at upper left
    axes[1].legend(handles=[Patch(color=MCOL[m]) for m in MODES],
                   labels=[{"device": "dev.", "lookup": "lookup",
                            "constant": "const."}[m] for m in MODES],
                   loc="upper left", frameon=False, handlelength=0.8,
                   handletextpad=0.4, borderaxespad=0.1, labelspacing=0.3)

    # ranks as a 9 x 6 grid: rows archetype x representation, columns packages
    ax = axes[3]
    mat = np.full((9, 6), np.nan)
    dev_rank = np.full((9, 6), np.nan)
    ylabels = []
    short = {"device": "dev.", "lookup": "lookup", "constant": "const."}
    for i, a in enumerate(ARCHS):
        for k, mode in enumerate(MODES):
            ylabels.append(f"{AB[a]} {short[mode]}")
            for j, p in enumerate(POLS[1:]):
                mat[i * 3 + k, j] = rk[(rk.archetype == a) & (rk.policy == p)
                                       & (rk.pe_mode == mode)].policy_rank.iloc[0]
                dev_rank[i * 3 + k, j] = rk[(rk.archetype == a) & (rk.policy == p)
                                            & (rk.pe_mode == "device")].policy_rank.iloc[0]
    ax.imshow(7 - mat, cmap="Blues", vmin=0, vmax=11, aspect="auto")
    for (r_, c_), v in np.ndenumerate(mat):
        changed = v != dev_rank[r_, c_]
        ax.text(c_, r_, f"{int(v)}", ha="center", va="center", fontsize=FS_NOTE,
                color="#D55E00" if changed else "#1A1A1A",
                fontweight="bold" if changed else "normal")
    ax.set_xticks(range(6))
    ax.set_xticklabels(POLS[1:], fontsize=FS_NOTE)
    ax.xaxis.tick_top()
    ax.set_yticks(range(9))
    ax.set_yticklabels(ylabels, fontsize=FS_NOTE)
    for b in (2.5, 5.5):
        ax.axhline(b, color="white", lw=2.0)
    ax.tick_params(length=0)
    ax.set_title("TOPSIS rank", pad=18)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    tag_auto(fig, zip(axes, "abcd"))
    save(fig, "F4_representation")


# ---------------------------------------------------------------------------
def f5_outcomes() -> None:
    rec = pd.read_csv(RES / "scenario_records.csv")
    rank = pd.read_csv(RES / "policy_ranking.csv")
    hs = pd.read_csv(RES / "horizon_summary.csv")
    dec = pd.read_csv(RES / "emission_intensity_decomposition.csv")
    cal = pd.read_csv(RES / "calibration_adoption.csv")
    # 8-page version: adoption paths and the Bangladeshi benefit-cost split in
    # one row; abatement and the intensity decomposition are Supplementary Fig. S6
    fig, axm = plt.subplots(1, 4, figsize=(W2, 2.75),
                            gridspec_kw={"width_ratios": [1.0, 1.0, 1.0, 1.05]})
    fig.subplots_adjust(left=0.065, right=0.99, top=0.885, bottom=0.25, wspace=0.42)
    fig_s, axs = plt.subplots(1, 2, figsize=(WS, 2.7))
    fig_s.subplots_adjust(left=0.10, right=0.985, top=0.88, bottom=0.30, wspace=0.40)
    for ax, a in zip(axm[:3], ARCHS):
        for p in POLS:
            s = rec[(rec.archetype == a) & (rec.policy == p)]
            ax.plot(s.year, 100 * s.ev_share, color=P.POLICY_COLOR[p], lw=1.4, label=p)
        if a == "developed":
            g = cal[(cal.archetype == "developed") & (cal.series == "stock")]
            ax.scatter(g.year, 100 * g.observed, s=10, color="#1A1A1A", zorder=3,
                       label="KBA")
            ax.set_xlim(2013, 2040)
            ax.set_xticks([2015, 2025, 2035])
        else:
            ax.set_xticks([2025, 2030, 2035, 2040])
        ax.set_title(ANAME[a])
        ax.set_xlabel("Year")
        P.despine(ax)
    axm[0].set_ylabel("EV share of stock (%)")
    axm[2].legend(ncol=2, loc="upper left", handlelength=1.0, columnspacing=0.6,
                      labelspacing=0.25)

    ax = axs[0]
    xx = np.arange(6)
    for i, a in enumerate(ARCHS):
        vals = [max(rank[(rank.archetype == a) & (rank.policy == p)].delta_emissions_mt.iloc[0],
                    1e-3) for p in POLS[1:]]
        ax.bar(xx + (i - 1) * 0.27, vals, width=0.26, color=P.ARCHETYPE_COLOR[a],
               label=AB[a])
    ax.set_yscale("log")
    _plain_log(ax, subs=(1.0,))
    ax.yaxis.set_major_locator(FixedLocator([0.01, 0.1, 1, 10, 100, 1000]))
    ax.set_ylim(3e-3, 8e3)
    ax.set_xticks(xx)
    ax.set_xticklabels(POLS[1:])
    ax.set_ylabel("$\\Delta$CO$_2$ vs S0 (Mt)")
    ax.set_title("Abatement, 2025-2040")
    ax.legend(loc="upper left", ncol=3, columnspacing=0.6, handlelength=0.9)
    P.despine(ax)
    ax.grid(axis="x", visible=False)

    ax = axm[3]
    comp = [("Fuel", ["b_fuel_musd"]), ("Maintenance", ["b_maintenance_musd"]),
            ("Health", ["b_health_musd"]), ("Carbon", ["b_carbon_musd"]),
            ("Service quality", ["b_queue_musd", "b_reliability_musd"]),
            ("Vehicle capital", ["c_vehicle_capital_musd"]),
            ("Electricity", ["c_electricity_musd"]),
            ("Chargers", ["c_charging_capex_musd", "c_charging_opex_musd"]),
            ("Grid, solar, V2G", ["c_grid_capex_musd", "c_pv_capex_musd",
                                  "c_v2g_degradation_musd"]),
            ("Programs", ["c_programme_musd"])]
    h5 = hs[(hs.archetype == "developing") & (hs.policy == "S5")].iloc[0]
    h0 = hs[(hs.archetype == "developing") & (hs.policy == "S0")].iloc[0]
    vals = [sum((h5[f"pv_{k}"] - h0[f"pv_{k}"]) / 1e3 * (1 if k.startswith("b_") else -1)
                for k in keys) for _, keys in comp]
    yy = np.arange(len(comp))[::-1]
    ax.barh(yy, vals, color=["#009E73" if v >= 0 else "#D55E00" for v in vals], height=0.72)
    ax.set_yticks(yy)
    ax.set_yticklabels([n for n, _ in comp], fontsize=FS_NOTE)
    ax.axvline(0, color="#555555", lw=0.6)
    ax.set_xlabel("S5 - S0 (bn USD)")
    ax.set_title("BD S5: benefits, costs")
    P.despine(ax)
    pos = ax.get_position()
    ax.set_position([pos.x0 + 0.075, pos.y0, pos.width - 0.075, pos.height])

    ax = axs[1]
    xx = np.arange(3)
    parts = [("timing_effect", "timing", "#E69F00"), ("grid_effect", "grid", "#009E73"),
             ("energy_effect", "energy/km", "#0072B2")]
    for i, a in enumerate(ARCHS):
        r = dec[dec.archetype == a].iloc[0]
        pos_, neg = 0.0, 0.0
        for col, lab, c in parts:
            v = r[col]
            ax.bar(i, v, bottom=pos_ if v >= 0 else neg, color=c, width=0.58,
                   label=lab if i == 0 else None)
            if v >= 0:
                pos_ += v
            else:
                neg += v
        ax.scatter(i, r.change_g_km, marker="D", color="#1A1A1A", s=24, zorder=3,
                   label="total" if i == 0 else None)
    ax.axhline(0, color="#555555", lw=0.6)
    ax.set_xticks(xx)
    ax.set_xticklabels([AB[a] for a in ARCHS])
    ax.set_ylabel("S5 - S0 (g CO$_2$/km)")
    ax.set_title("Charging intensity, 2035")
    legend_below(ax, 2, dy=-0.17, handlelength=0.9)
    P.despine(ax)
    ax.grid(axis="x", visible=False)
    tag_auto(fig, zip(axm, "abcd"))
    save(fig, "F5_outcomes")
    tag_auto(fig_s, zip(axs, "ab"))
    save(fig_s, "S6_outcomes")


# ---------------------------------------------------------------------------
SHORT_LEVER = {"bus_electrification": "Bus electrif.", "charger_rollout": "Public charging",
               "dc_share": "DC share", "renewable_target": "Renewables",
               "duty_relief": "Duty relief", "workforce": "PE workforce",
               "local_manufacturing": "Local mfg.", "purchase_incentive": "Purchase subsidy",
               "ultrafast_share": "Ultra-fast share", "tou_tariff": "ToU tariff",
               "grid_investment": "Reinforcement", "smart_charging": "Smart charging",
               "digital_twin": "Monitoring", "efficiency_standard": "Eff. standard",
               "wbg_mandate": "WBG requirement", "hv_architecture": "800 V support",
               "grid_code": "Grid code", "v2g_enablement": "V2G", "recycling": "Recycling",
               "cybersecurity": "Cybersecurity"}


def f6_robustness(name: str = "S4_robustness", width: float = WS) -> None:
    ab = pd.read_csv(RES / "network_ablation.csv")
    fc = pd.read_csv(RES / "feeder_concentration.csv")
    mc = pd.read_csv(RES / "monte_carlo_samples.csv")
    ws = json.loads((RES / "topsis_weight_sensitivity.json").read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 4, figsize=(width, 2.7),
                             gridspec_kw={"width_ratios": [1.35, 1.0, 0.95, 0.85]})
    # 2.6 in tall; margins kept in inches (0.35 top, 1.05 bottom)
    fig.subplots_adjust(left=0.07, right=0.99, top=0.865, bottom=0.404, wspace=0.62)

    ax = axes[0]
    variants = ["S0", "S5", "S5 without reinforcement", "S5 without flexibility",
                "S5 without both"]
    short = ["S0", "S5", "S5 no reinf.", "S5 no flex.", "S5 neither"]
    cols = ["#8C8C8C", "#0072B2", "#56B4E9", "#E69F00", "#D55E00"]
    for i, a in enumerate(ARCHS):
        for j, vname in enumerate(variants):
            r = ab[(ab.archetype == a) & (ab.variant == vname)].iloc[0]
            xpos = i * 6 + j
            ax.bar(xpos, r.tx_loading_vs_original_rating_pu, color=cols[j], width=0.85,
                   label=short[j] if i == 0 else None)
            ax.scatter(xpos, r.tx_loading_2040_pu, marker="_", color="#1A1A1A", s=45,
                       lw=1.6, zorder=3)
    ax.set_xticks([2, 8, 14])
    ax.set_xticklabels([AB[a] for a in ARCHS])
    ax.axhline(1.0, color="#B7521A", lw=0.9, ls="--")
    ax.set_ylabel("2040 peak (pu)")
    ax.set_title("What lowers the peak")
    legend_below(ax, 2, dy=-0.175, handlelength=0.9, columnspacing=0.6)
    P.despine(ax)
    ax.grid(axis="x", visible=False)

    ax = axes[1]
    for a in ARCHS:
        for p, ls in (("S0", "--"), ("S5", "-")):
            s = fc[(fc.archetype == a) & (fc.policy == p)]
            ax.plot(s.concentration, s.tx_loading_2040_pu, ls=ls, marker="o", ms=3.5,
                    color=P.ARCHETYPE_COLOR[a], lw=1.3)
    ax.axhline(1.0, color="#B7521A", lw=0.9, ls=":")
    handles = ([Line2D([], [], color=P.ARCHETYPE_COLOR[a], lw=1.3) for a in ARCHS]
               + [Line2D([], [], color="#1A1A1A", lw=1.3, ls="--"),
                  Line2D([], [], color="#1A1A1A", lw=1.3)])
    legend_below(ax, 3, dy=-0.35, handles=handles,
                 labels=[AB[a] for a in ARCHS] + ["S0", "S5"], handlelength=1.4,
                 columnspacing=0.6)
    ax.set_xticks([1, 2, 3])
    ax.set_xlabel("Feeder load / mean")
    ax.set_ylabel("2040 peak (pu)")
    ax.set_title("Concentrated load")
    P.despine(ax)

    ax = axes[2]
    data = []
    for a in ARCHS:
        s0 = mc[(mc.archetype == a) & (mc.policy == "S0")].set_index("sample").npv_musd
        s5 = mc[(mc.archetype == a) & (mc.policy == "S5")].set_index("sample").npv_musd
        data.append(((s5 - s0) / 1e3).dropna().to_numpy())
    parts = ax.violinplot(data, showmedians=True, widths=0.75)
    for b, a in zip(parts["bodies"], ARCHS):
        b.set_facecolor(P.ARCHETYPE_COLOR[a])
        b.set_alpha(0.55)
    ax.axhline(0, color="#555555", lw=0.7)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels([AB[a] for a in ARCHS])
    ax.set_yscale("symlog", linthresh=1.0)
    ax.yaxis.set_major_locator(FixedLocator([-100, -10, -1, 0, 1, 10, 100]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_ylabel("$\\Delta$NPV (bn USD)")
    ax.set_title("Monte Carlo")
    P.despine(ax)

    ax = axes[3]
    bottom = np.zeros(3)
    for p in POLS[1:]:
        vals = np.array([dict(zip(ws[a]["keys"], ws[a]["p_first"]))[p] for a in ARCHS])
        ax.bar(np.arange(3), vals, bottom=bottom, color=P.POLICY_COLOR[p], width=0.65,
               label=p)
        bottom += vals
    ax.set_xticks(range(3))
    ax.set_xticklabels([AB[a] for a in ARCHS])
    ax.set_ylabel("Share ranked first")
    ax.set_title("Weights")
    legend_below(ax, 3, dy=-0.175, handlelength=0.8, columnspacing=0.5)
    P.despine(ax)
    ax.grid(axis="x", visible=False)
    tag_auto(fig, zip(axes, "abcd"))
    save(fig, name)


def fs3_calibration() -> None:
    """Supplementary Fig. S3: light-load efficiency of the Prius inverter and
    the two-wheeler adoption panel."""
    ll = pd.read_csv(RES / "light_load_fit.csv")
    ca = pd.read_csv(RES / "calibration_adoption.csv")
    panel = pd.read_csv(ROOT / "digital_twin" / "data" / "adoption_panel.csv", comment="#")
    tr = pd.read_csv(RES / "calibration_transfer.csv")
    fig, axes = plt.subplots(1, 2, figsize=(WS, 2.8), gridspec_kw={"width_ratios": [1, 1.25]})
    fig.subplots_adjust(left=0.10, right=0.985, top=0.88, bottom=0.36, wspace=0.38)

    ax = axes[0]
    for s_, mk in (("fit", "o"), ("held out", "s")):
        g = ll[ll.set == s_]
        ax.scatter(100 * g.measured, 100 * g.model_without_ripple, marker=mk, s=18,
                   facecolor="white", edgecolor="#888888", lw=1.0)
        ax.scatter(100 * g.measured, 100 * g.model, marker=mk, s=18, color="#0072B2")
    ax.plot([82, 100], [82, 100], color="#999999", lw=0.9, ls="--")
    ax.set_xlim(82, 100)
    ax.set_ylim(82, 100)
    ax.set_xlabel("Measured efficiency (%)")
    ax.set_ylabel("Model (%)")
    ax.set_title("Prius inverter, light load")
    legend_below(ax, 2, dy=-0.30, handlelength=0.8, columnspacing=0.6,
                 handles=[Line2D([], [], ls="", marker="o", ms=5, color="#0072B2"),
                          Line2D([], [], ls="", marker="o", ms=5, mfc="white", mec="#888888"),
                          Line2D([], [], ls="", marker="o", ms=5, color="#1A1A1A"),
                          Line2D([], [], ls="", marker="s", ms=5, color="#1A1A1A")],
                 labels=["with ripple", "without", "650/500 V (fit)", "225 V (held out)"])
    P.despine(ax)

    ax = axes[1]
    cols = {"India": "#0072B2", "Indonesia": "#E69F00", "Kenya": "#009E73",
            "Vietnam": "#CC79A7"}
    for c, col in cols.items():
        obs = panel[panel.country == c].sort_values("year")
        ax.scatter(obs.year, 100 * obs.ev_sales_share, s=16, color=col, zorder=3)
        fit = ca[(ca.country == c) & (ca.series == "sales")].sort_values("year")
        if not fit.empty and c == "Vietnam":
            ax.plot(fit.year, 100 * fit.fitted, color=col, lw=1.1, ls=":",
                    label="Vietnam (transfer)")
        elif not fit.empty:
            ax.plot(fit.year, 100 * fit.fitted_all_years, color=col, lw=1.3, label=c)
        elif c == "Vietnam":
            row = tr[tr.country.str.contains("Vietnam")].iloc[0]
            ax.plot([obs.year.iloc[0], obs.year.iloc[-1]],
                    [100 * obs.ev_sales_share.iloc[0], 100 * row.predicted_last],
                    color=col, lw=1.1, ls=":", label="Vietnam (transfer)")
    ax.set_yscale("log")
    _plain_log(ax)
    ax.set_xlabel("Year")
    ax.set_ylabel("e-2W sales share (%)")
    ax.set_title("Two-wheeler panel")
    legend_below(ax, 2, dy=-0.30, handlelength=1.2, columnspacing=0.8)
    P.despine(ax)
    tag_auto(fig, zip(axes, "ab"))
    save(fig, "S3_calibration")


def fs2_surrogate() -> None:
    """Supplementary Fig. S2: Sobol indices on the surrogate and surrogate accuracy."""
    sob = pd.read_csv(RES / "sensitivity_sobol.csv")
    sur = pd.read_csv(RES / "surrogate_performance.csv")
    pv = pd.read_csv(RES / "pareto_verification.csv")
    fig, axes = plt.subplots(1, 2, figsize=(WS, 2.9), gridspec_kw={"width_ratios": [1.2, 1]})
    fig.subplots_adjust(left=0.19, right=0.985, top=0.88, bottom=0.36, wspace=0.42)

    ax = axes[0]
    s = sob[sob.target == "npv_musd"]
    top = s.groupby("lever").ST.max().sort_values(ascending=False).index[:6]
    yy = np.arange(len(top))[::-1]
    for k, a in enumerate(ARCHS):
        q = s[s.archetype == a].set_index("lever")
        y_ = yy + (k - 1) * 0.24
        if "ST_lo" in q:                      # 95 % bootstrap intervals
            ax.hlines(y_, q.loc[top, "ST_lo"], q.loc[top, "ST_hi"],
                      color=P.ARCHETYPE_COLOR[a], lw=1.0)
            ax.hlines(y_, q.loc[top, "S1_lo"], q.loc[top, "S1_hi"],
                      color=P.ARCHETYPE_COLOR[a], lw=1.0, alpha=0.5)
        ax.scatter(q.loc[top, "ST"], y_, s=24, color=P.ARCHETYPE_COLOR[a], zorder=3)
        ax.scatter(q.loc[top, "S1"], y_, s=24, facecolor="white",
                   edgecolor=P.ARCHETYPE_COLOR[a], lw=1.0, zorder=3)
    from evdt.policy import LEVERS
    ax.set_yticks(yy)
    ax.set_yticklabels([SHORT_LEVER.get(k, LEVERS[k].label[:14]) for k in top],
                       fontsize=FS_NOTE)
    ax.set_xlim(-0.05, 1.05)
    ax.set_xlabel("Sobol index of NPV")
    ax.set_title("Lever sensitivity")
    legend_below(ax, 3, dy=-0.25, handlelength=0.8,
                 handles=[Line2D([], [], ls="", marker="o", ms=5, color=P.ARCHETYPE_COLOR[a])
                          for a in ARCHS]
                 + [Line2D([], [], ls="", marker="o", ms=5, mfc="white", mec="#555555"),
                    Line2D([], [], ls="", marker="o", ms=5, color="#555555")],
                 labels=[AB[a] for a in ARCHS] + ["first order", "total"])
    P.despine(ax)

    ax = axes[1]
    objs = [("npv_musd", "NPV"), ("cumulative_emissions_saved_mt", "CO$_2$"),
            ("final_transformer_loading", "Load")]
    xx = np.arange(3)
    for k, a in enumerate(ARCHS):
        r2 = [sur[sur.archetype == a][f"r2_{o}"].iloc[0] for o, _ in objs]
        ax.bar(xx + (k - 1) * 0.27, r2, width=0.26, color=P.ARCHETYPE_COLOR[a],
               label=AB[a])
        err = [pv[(pv.archetype == a) & (pv.objective == o)].median_abs_error_norm.iloc[0]
               for o, _ in objs]
        ax.scatter(xx + (k - 1) * 0.27, 1 - np.array(err), marker="_", s=55, lw=1.6,
                   color="#1A1A1A", zorder=3)
        if f"r2_rf_{objs[0][0]}" in sur:      # random-forest baseline of version 2
            rf = [sur[sur.archetype == a][f"r2_rf_{o}"].iloc[0] for o, _ in objs]
            ax.scatter(xx + (k - 1) * 0.27, np.clip(rf, 0, None), marker="D", s=14,
                       facecolor="white", edgecolor="#1A1A1A", lw=0.8, zorder=4)
    ax.set_xticks(xx)
    ax.set_xticklabels([n for _, n in objs])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("R$^2$; 1 - Pareto error")
    ax.set_title("Surrogate accuracy")
    legend_below(ax, 3, dy=-0.15, handlelength=0.9, columnspacing=0.6)
    P.despine(ax)
    ax.grid(axis="x", visible=False)
    tag_auto(fig, zip(axes, "ab"))
    save(fig, "S2_surrogate")


FIGURES = {"F1": f1_structure, "F2": f2_validation, "F3": f3_converters,
           "F4": f4_representation, "F5": f5_outcomes,
           "S1": fs1_verification, "S2": fs2_surrogate, "S3": fs3_calibration,
           "S4": f6_robustness, "S5": fs5_thermal}


def main(which: list[str] | None = None) -> None:
    style()
    for key, fn in FIGURES.items():
        if which and key not in which:
            continue
        fn()


if __name__ == "__main__":
    main(sys.argv[1:] or None)


