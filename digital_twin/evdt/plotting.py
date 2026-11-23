"""Publication figure styling and reusable graphical primitives.

Design rules applied throughout
-------------------------------
* Categorical hues are assigned in a fixed order and never cycled.  The set is
  the Okabe-Ito palette, which is designed for colour-vision deficiency; the
  yellow step is dropped because it is too light against a white page.
* Sequential magnitude uses a single hue running light to dark; polarity uses a
  two-hue diverging ramp with a neutral grey midpoint.  No rainbow ramps.
* Series colour follows the entity, never its rank, so a subset of scenarios
  keeps its colours.
* Only one value axis per panel; two measures of different scale are shown as
  two panels, never as a twin axis.
* Grid and spines are recessive; text uses ink greys rather than series colours;
  every panel with two or more series carries a legend.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Polygon as MplPolygon

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
CATEGORICAL = ["#0072B2", "#D55E00", "#009E73", "#CC79A7",
               "#E69F00", "#56B4E9", "#6A3D9A", "#44546A"]

INK = "#1A1A1A"
INK_2 = "#4D4D4D"
INK_MUTED = "#7A7A7A"
GRID = "#D9D9D9"
SURFACE = "#FFFFFF"

ARCHETYPE_COLOR = {
    "underdeveloped": "#D55E00",
    "developing": "#0072B2",
    "developed": "#009E73",
}
ARCHETYPE_LABEL = {
    "underdeveloped": "Underdeveloped",
    "developing": "Developing (Bangladesh)",
    "developed": "Developed",
}

POLICY_COLOR = {
    "S0": "#8C8C8C", "S1": "#E69F00", "S2": "#D55E00", "S3": "#56B4E9",
    "S4": "#CC79A7", "S5": "#0072B2", "S6": "#009E73",
}
POLICY_LABEL = {
    "S0": "S0 no policy", "S1": "S1 fiscal & access",
    "S2": "S2 power electronics", "S3": "S3 grid & digital",
    "S4": "S4 conservative", "S5": "S5 aggressive", "S6": "S6 frontier",
}
POLICY_SHORT = {
    "S0": "S0", "S1": "S1", "S2": "S2", "S3": "S3", "S4": "S4", "S5": "S5", "S6": "S6",
}

DEVICE_COLOR = {
    "Si-IGBT": "#8C8C8C", "Si-MOSFET": "#E69F00",
    "SiC-MOSFET": "#0072B2", "GaN-HEMT": "#009E73",
}
DEVICE_LABEL = {
    "Si-IGBT": "Si IGBT", "Si-MOSFET": "Si SJ MOSFET",
    "SiC-MOSFET": "SiC MOSFET", "GaN-HEMT": "GaN HEMT",
}

SEQ = LinearSegmentedColormap.from_list(
    "evdt_seq", ["#EAF2F8", "#AFCBE3", "#6FA3CC", "#2E77B0", "#0B4F81", "#062F4D"])
SEQ_WARM = LinearSegmentedColormap.from_list(
    "evdt_warm", ["#FDF0E6", "#F8CDA8", "#EFA268", "#DE7433", "#B7521A", "#7A3410"])
DIVERGING = LinearSegmentedColormap.from_list(
    "evdt_div", ["#7A3410", "#DE7433", "#F3D9C4", "#E8E8E8", "#B7D2E6",
                 "#2E77B0", "#062F4D"])

# Elsevier column widths
COL1 = 3.54          # inches, 90 mm single column
COL15 = 5.51         # inches, 140 mm
COL2 = 7.48          # inches, 190 mm double column

FIGDIR = Path(__file__).resolve().parents[2] / "figures"
DATADIR = Path(__file__).resolve().parents[1] / "data"


def setup() -> None:
    """Apply the manuscript-wide matplotlib style."""
    mpl.rcParams.update({
        "figure.dpi": 120,
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 8.0,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8.0,
        "axes.titleweight": "bold",
        "axes.labelcolor": INK,
        "axes.edgecolor": INK_2,
        "axes.linewidth": 0.6,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.45,
        "grid.alpha": 0.9,
        "xtick.labelsize": 7.2,
        "ytick.labelsize": 7.2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.major.width": 0.55,
        "ytick.major.width": 0.55,
        "xtick.major.size": 2.4,
        "ytick.major.size": 2.4,
        "legend.fontsize": 7.0,
        "legend.frameon": False,
        "legend.handlelength": 1.5,
        "legend.columnspacing": 1.0,
        "legend.labelspacing": 0.35,
        "lines.linewidth": 1.4,
        "lines.markersize": 3.4,
        "patch.linewidth": 0.5,
        "text.color": INK,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def despine(ax, left: bool = False, bottom: bool = False) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if left:
        ax.spines["left"].set_visible(False)
    if bottom:
        ax.spines["bottom"].set_visible(False)


_SUBDIR = ""


def set_output_subdir(name: str = "") -> None:
    """Route subsequent save() calls into ``figures/<name>``.

    The twelve composite manuscript figures live at the top of ``figures``;
    the single-topic supplementary set is written under ``supplementary``.
    """
    global _SUBDIR
    _SUBDIR = name


def output_dir() -> Path:
    return FIGDIR / _SUBDIR if _SUBDIR else FIGDIR


def save(fig, name: str, formats: tuple[str, ...] = ("png", "pdf")) -> None:
    out = output_dir()
    out.mkdir(exist_ok=True, parents=True)
    for ext in formats:
        fig.savefig(out / f"{name}.{ext}")
    plt.close(fig)
    print(f"  wrote {name}." + "/".join(formats))


def panel_label(ax, text: str, dx: float = -0.13, dy: float = 1.06) -> None:
    ax.text(dx, dy, text, transform=ax.transAxes, fontsize=9, fontweight="bold",
            va="top", ha="left", color=INK)


def bar_ends(ax, orientation: str = "v") -> None:
    """Round the data-end of every bar and keep the baseline square."""
    for patch in ax.patches:
        patch.set_joinstyle("round")


# ---------------------------------------------------------------------------
# Geographic primitives
# ---------------------------------------------------------------------------
def _load_geojson(name: str) -> dict:
    return json.loads((DATADIR / name).read_text(encoding="utf-8"))


def _polygons(geometry: dict) -> list[np.ndarray]:
    out = []
    if geometry["type"] == "Polygon":
        rings = [geometry["coordinates"][0]]
    elif geometry["type"] == "MultiPolygon":
        rings = [poly[0] for poly in geometry["coordinates"]]
    else:
        return out
    for ring in rings:
        arr = np.asarray(ring, dtype=float)
        if arr.ndim == 2 and arr.shape[0] >= 3:
            out.append(arr[:, :2])
    return out


def draw_world(ax, values: dict[str, float] | None = None,
               categories: dict[str, str] | None = None,
               category_colors: dict[str, str] | None = None,
               cmap=SEQ, vmin: float | None = None, vmax: float | None = None,
               default_color: str = "#F0F0F0", edge: str = "#FFFFFF",
               lw: float = 0.25) -> None:
    """Equirectangular choropleth keyed on ISO alpha-3 codes."""
    gj = _load_geojson("world_countries.geojson")
    if values:
        vals = np.array(list(values.values()), dtype=float)
        vmin = float(np.nanmin(vals)) if vmin is None else vmin
        vmax = float(np.nanmax(vals)) if vmax is None else vmax
    for feat in gj["features"]:
        iso = feat["properties"]["iso_a3"]
        if categories is not None and iso in categories:
            color = (category_colors or {}).get(categories[iso], default_color)
        elif values is not None and iso in values:
            t = (values[iso] - vmin) / max(vmax - vmin, 1e-9)
            color = cmap(float(np.clip(t, 0.0, 1.0)))
        else:
            color = default_color
        for poly in _polygons(feat["geometry"]):
            ax.add_patch(MplPolygon(poly, closed=True, facecolor=color,
                                    edgecolor=edge, linewidth=lw))
    ax.set_xlim(-180, 180)
    ax.set_ylim(-58, 84)
    ax.set_aspect(1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)


def draw_bangladesh(ax, values: dict[str, float] | None = None, cmap=SEQ,
                    vmin: float | None = None, vmax: float | None = None,
                    label: bool = True, fmt: str = "{:.0f}",
                    edge: str = "#FFFFFF", lw: float = 0.5,
                    fontsize: float = 5.6) -> None:
    """Choropleth of the administrative divisions of Bangladesh."""
    gj = _load_geojson("bangladesh_divisions.geojson")
    if values:
        vals = np.array(list(values.values()), dtype=float)
        vmin = float(np.nanmin(vals)) if vmin is None else vmin
        vmax = float(np.nanmax(vals)) if vmax is None else vmax
    # Two passes: every polygon first, then every label. Drawn in one pass, a
    # division plotted later would paint over the label of an earlier one.
    labels = []
    for feat in gj["features"]:
        name = feat["properties"]["name"]
        if values is not None and name in values:
            t = (values[name] - vmin) / max(vmax - vmin, 1e-9)
            color = cmap(float(np.clip(t, 0.0, 1.0)))
        else:
            t, color = 0.0, "#E8E8E8"
        polys = _polygons(feat["geometry"])
        for poly in polys:
            ax.add_patch(MplPolygon(poly, closed=True, facecolor=color,
                                    edgecolor=edge, linewidth=lw, zorder=1))
        if label and polys:
            biggest = max(polys, key=lambda p: p.shape[0])
            txt = name if values is None else f"{name}\n{fmt.format(values.get(name, 0))}"
            labels.append((biggest[:, 0].mean(), biggest[:, 1].mean(), txt,
                           float(np.clip(t, 0.0, 1.0))))
    for cx, cy, txt, t in labels:
        ax.text(cx, cy, txt, ha="center", va="center", fontsize=fontsize,
                color="#FFFFFF" if t > 0.55 else INK, linespacing=1.15, zorder=3)
    ax.set_xlim(87.8, 92.9)
    ax.set_ylim(20.5, 26.8)
    ax.set_aspect(1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)


def colorbar(fig, ax, cmap, vmin: float, vmax: float, label: str,
             orientation: str = "vertical", fraction: float = 0.03,
             pad: float = 0.02):
    sm = mpl.cm.ScalarMappable(cmap=cmap, norm=mpl.colors.Normalize(vmin, vmax))
    cb = fig.colorbar(sm, ax=ax, orientation=orientation, fraction=fraction, pad=pad)
    cb.set_label(label, fontsize=7.2, color=INK)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=6.6, width=0.5, length=2, color=INK_2)
    return cb


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------
def radar(ax, categories: list[str], series: dict[str, np.ndarray],
          colors: dict[str, str] | None = None, rmax: float = 1.0,
          fill_alpha: float = 0.10, label_pad: float = 1.16) -> None:
    """Radar (spider) plot on a polar axis."""
    n = len(categories)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    closed = np.concatenate([angles, angles[:1]])
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels([])
    ax.set_ylim(0, rmax)
    ax.set_yticks(np.linspace(0, rmax, 5)[1:])
    ax.set_yticklabels([f"{v:.2f}" for v in np.linspace(0, rmax, 5)[1:]],
                       fontsize=5.8, color=INK_MUTED)
    ax.grid(color=GRID, linewidth=0.45)
    ax.spines["polar"].set_color(GRID)
    ax.spines["polar"].set_linewidth(0.5)
    for name, vals in series.items():
        v = np.concatenate([np.asarray(vals, float), np.asarray(vals, float)[:1]])
        c = (colors or {}).get(name, CATEGORICAL[0])
        ax.plot(closed, v, color=c, linewidth=1.3, label=name, zorder=3)
        ax.fill(closed, v, color=c, alpha=fill_alpha, zorder=2)
    for ang, cat in zip(angles, categories):
        ha = "center"
        if 0.05 < ang < np.pi - 0.05:
            ha = "left"
        elif np.pi + 0.05 < ang < 2 * np.pi - 0.05:
            ha = "right"
        ax.text(ang, rmax * label_pad, cat, ha=ha, va="center", fontsize=6.4,
                color=INK)


# ---------------------------------------------------------------------------
# Sankey
# ---------------------------------------------------------------------------
def sankey(ax, nodes: list[str], flows: list[tuple[int, int, float]],
           node_layer: list[int], colors: list[str] | None = None,
           node_width: float = 0.055, gap: float = 0.022,
           label_fmt: str = "{name}\n{value:,.0f}",
           min_label_gap: float = 0.085) -> None:
    """Minimal multi-layer Sankey diagram.

    ``flows`` are ``(source_index, target_index, value)`` triples and
    ``node_layer`` gives the horizontal layer of each node.
    """
    n_layers = max(node_layer) + 1
    inflow = np.zeros(len(nodes))
    outflow = np.zeros(len(nodes))
    for s, t, v in flows:
        outflow[s] += v
        inflow[t] += v
    size = np.maximum(inflow, outflow)

    layers: dict[int, list[int]] = {}
    for i, layer in enumerate(node_layer):
        layers.setdefault(layer, []).append(i)

    total = max(size[layers[0]].sum(), 1e-9)
    y_pos: dict[int, tuple[float, float]] = {}
    for layer, idxs in layers.items():
        heights = size[idxs] / total
        span = heights.sum() + gap * (len(idxs) - 1)
        y = 0.5 + span / 2.0
        for i, hgt in zip(idxs, heights):
            y_pos[i] = (y - hgt, y)
            y -= hgt + gap

    xs = np.linspace(0.02, 0.98 - node_width, n_layers)
    cursor_out = {i: y_pos[i][1] for i in range(len(nodes))}
    cursor_in = {i: y_pos[i][1] for i in range(len(nodes))}

    # Stack each node's ribbons in the vertical order of the node they connect
    # to, which is what removes avoidable crossings in a layered diagram.
    for s, t, v in sorted(flows, key=lambda f: (node_layer[f[0]], -y_pos[f[0]][1],
                                                -y_pos[f[1]][1])):
        h = v / total
        x0 = xs[node_layer[s]] + node_width
        x1 = xs[node_layer[t]]
        y0a, y0b = cursor_out[s], cursor_out[s] - h
        y1a, y1b = cursor_in[t], cursor_in[t] - h
        cursor_out[s] -= h
        cursor_in[t] -= h
        tt = np.linspace(0, 1, 60)
        smooth = tt * tt * (3 - 2 * tt)
        xx = x0 + (x1 - x0) * tt
        upper = y0a + (y1a - y0a) * smooth
        lower = y0b + (y1b - y0b) * smooth
        col = (colors or CATEGORICAL)[s % len(colors or CATEGORICAL)]
        ax.fill_between(xx, lower, upper, color=col, alpha=0.34, linewidth=0)

    for i in range(len(nodes)):
        y0, y1 = y_pos[i]
        col = (colors or CATEGORICAL)[i % len(colors or CATEGORICAL)]
        ax.add_patch(plt.Rectangle((xs[node_layer[i]], y0), node_width, y1 - y0,
                                   facecolor=col, edgecolor="none"))

    # Label placement.  Source and sink labels sit outside the diagram; the
    # labels of intermediate nodes sit above their node so that no text is ever
    # drawn over a ribbon.  Within the outer layers, labels that would collide
    # are pushed apart while preserving their vertical order.
    min_gap = min_label_gap
    for layer, idxs in layers.items():
        outer = layer in (0, n_layers - 1)
        idxs_sorted = sorted(idxs, key=lambda i: -0.5 * (y_pos[i][0] + y_pos[i][1]))
        label_y = [0.5 * (y_pos[i][0] + y_pos[i][1]) for i in idxs_sorted]
        if outer:
            for k in range(1, len(label_y)):
                if label_y[k - 1] - label_y[k] < min_gap:
                    label_y[k] = label_y[k - 1] - min_gap
            shift = max(0.0, -min(label_y) + 0.01)
            label_y = [y + shift for y in label_y]
        for i, ly in zip(idxs_sorted, label_y):
            text = label_fmt.format(name=nodes[i], value=size[i])
            if layer == 0:
                ax.text(xs[layer] - 0.012, ly, text, ha="right", va="center",
                        fontsize=6.0, color=INK, linespacing=1.2)
            elif layer == n_layers - 1:
                ax.text(xs[layer] + node_width + 0.012, ly, text, ha="left",
                        va="center", fontsize=6.0, color=INK, linespacing=1.2)
            else:
                # Intermediate layers often reach nearly the same height, so
                # their labels are staggered by layer parity to keep them apart.
                dy = 0.020 + 0.085 * (layer % 2)
                ax.text(xs[layer] + node_width / 2.0, y_pos[i][1] + dy, text,
                        ha="center", va="bottom", fontsize=6.0, color=INK,
                        linespacing=1.2)

    ax.set_xlim(-0.34, 1.32)
    ax.set_ylim(-0.06, 1.16)
    ax.axis("off")


# ---------------------------------------------------------------------------
# Diagram primitives
# ---------------------------------------------------------------------------
def box(ax, x: float, y: float, w: float, h: float, text: str,
        facecolor: str = "#EFF4F9", edgecolor: str = "#0072B2",
        fontsize: float = 6.6, weight: str = "normal", radius: float = 0.012,
        textcolor: str | None = None, lw: float = 0.8) -> None:
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, fontweight=weight, color=textcolor or INK,
            linespacing=1.28, zorder=3)


def arrow(ax, x0: float, y0: float, x1: float, y1: float,
          color: str = INK_2, lw: float = 0.9, style: str = "-|>",
          connection: str = "arc3,rad=0.0", alpha: float = 1.0) -> None:
    from matplotlib.patches import FancyArrowPatch
    ax.add_patch(FancyArrowPatch(
        (x0, y0), (x1, y1), arrowstyle=style, mutation_scale=7,
        color=color, linewidth=lw, connectionstyle=connection, alpha=alpha,
        zorder=1, shrinkA=1.0, shrinkB=1.0))


def blank_axes(ax) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.grid(False)
