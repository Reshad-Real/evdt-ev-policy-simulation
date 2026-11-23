"""Import the benchmark feeders into data/feeders in the format of
evdt.grid.load_benchmark (third revision).

Branch and load data are copied as published, with buses relabelled 1..N from
the source bus; re-basing to another voltage and calibration of electrical
length are not applied here but by each archetype's FeederType (z_scale,
base_kv), so they stay visible in the configuration.  Sources and the
load-flow verification of every feeder are in data/feeders/FEEDERS.md.

Usage:  py -3 scripts/import_feeders.py <research folder>
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "feeders"

FEEDERS = {
    # key: (subfolder, file stem, root bus, native kV, peak note, source)
    "ieee69": ("ieee69", "ieee69", "1", 12.66,
               "M. E. Baran and F. F. Wu, IEEE Trans. Power Del. 4(1):725-734, 1989; "
               "MATPOWER case69"),
    "in_rural28": ("in_rural28", "in_rural28", "1", 11.0,
                   "D. Das, H. S. Nagi and D. P. Kothari, IEE Proc. GTD 141(1), 1994 "
                   "(Indian rural 11 kV); MATPOWER case28da"),
    "ieee34_mv": ("ieee34_balanced", "ieee34_balanced", "800", 24.9,
                  "IEEE PES 34-node test feeder (Kersting), balanced positive-sequence "
                  "equivalent, medium-voltage part (4.16 kV branch folded into bus 832)"),
    "simbench_mv_urban": ("simbench/simbench_mv_urban", "simbench_mv_urban", "SOURCE", 10.0,
                          "SimBench 1-MV-urban--0-sw (Meinecke et al., Energies 2020)"),
    "simbench_mv_semiurb": ("simbench/simbench_mv_semiurb", "simbench_mv_semiurb", "SOURCE",
                            20.0, "SimBench 1-MV-semiurb--0-sw"),
    "simbench_mv_rural": ("simbench/simbench_mv_rural", "simbench_mv_rural", "SOURCE", 20.0,
                          "SimBench 1-MV-rural--0-sw"),
}


def relabel(br: pd.DataFrame, ld: pd.DataFrame, root: str):
    br = br.astype({"from_bus": str, "to_bus": str})
    ld = ld.astype({"bus": str})
    children: dict[str, list[str]] = {}
    for f, t in zip(br.from_bus, br.to_bus):
        children.setdefault(f, []).append(t)
    order, seen, q = [], {root}, deque([root])
    while q:                                   # breadth first from the source
        n = q.popleft()
        order.append(n)
        for c in children.get(n, []):
            if c not in seen:
                seen.add(c)
                q.append(c)
    idx = {b: i + 1 for i, b in enumerate(order)}
    missing = set(br.to_bus) - set(idx)
    if missing:
        raise ValueError(f"buses not reachable from {root}: {sorted(missing)[:5]}")
    out_br = pd.DataFrame({"from_bus": br.from_bus.map(idx), "to_bus": br.to_bus.map(idx),
                           "r_ohm": br.r_ohm, "x_ohm": br.x_ohm})
    ld = ld[ld.bus.isin(idx)]
    out_ld = pd.DataFrame({"bus": ld.bus.map(idx), "p_kw": ld.p_kw, "q_kvar": ld.q_kvar})
    return out_br.sort_values("to_bus"), out_ld.sort_values("bus"), idx


def main() -> None:
    src = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    for key, (folder, stem, root, kv, source) in FEEDERS.items():
        br = pd.read_csv(src / folder / f"{stem}_branches.csv")
        ld = pd.read_csv(src / folder / f"{stem}_loads.csv")
        if key == "ieee34_mv":
            # medium-voltage part only: drop the 24.9/4.16 kV transformer and
            # its 4.16 kV line, and serve the 4.16 kV load from bus 832
            br = br[~br.to_bus.astype(str).isin(["888", "890"])]
            ld = ld.copy()
            ld["bus"] = ld.bus.astype(str).replace({"888": "832", "890": "832"})
            ld = ld.groupby("bus", as_index=False)[["p_kw", "q_kvar"]].sum()
        b, l_, idx = relabel(br, ld, root)
        b.to_csv(OUT / f"{key}_branches.csv", index=False)
        l_.to_csv(OUT / f"{key}_loads.csv", index=False)
        meta = {"name": key, "base_kv": kv, "source": source,
                "buses": len(idx), "load_kw": float(l_.p_kw.sum()),
                "bus_labels": {str(v): k for k, v in idx.items()}}
        (OUT / f"{key}_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(f"{key:22s} {len(idx):4d} buses  {l_.p_kw.sum() / 1e3:7.2f} MW  {kv} kV")


if __name__ == "__main__":
    main()
