"""Download and cache the geographic boundaries used by the map figures.

Source: Natural Earth (https://www.naturalearthdata.com), public domain.
Only two small extracts are retained in the repository: world country outlines
at 1:110m, and the eight administrative divisions of Bangladesh taken from the
1:10m admin-1 layer.

Usage:  py -3 scripts/fetch_geodata.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DATA.mkdir(exist_ok=True)

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
WORLD = f"{BASE}/ne_110m_admin_0_countries.geojson"
ADMIN1 = f"{BASE}/ne_10m_admin_1_states_provinces.geojson"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "evdt-geodata/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def slim_country(feature: dict) -> dict:
    p = feature["properties"]
    return {"type": "Feature",
            "properties": {"name": p.get("NAME"), "iso_a3": p.get("ADM0_A3"),
                           "continent": p.get("CONTINENT"),
                           "region": p.get("REGION_UN")},
            "geometry": feature["geometry"]}


def main() -> None:
    world_path = DATA / "world_countries.geojson"
    if not world_path.exists():
        print("downloading world country outlines ...")
        gj = fetch(WORLD)
        out = {"type": "FeatureCollection",
               "features": [slim_country(f) for f in gj["features"]]}
        world_path.write_text(json.dumps(out), encoding="utf-8")
    print(f"world outlines: {world_path.stat().st_size // 1024} KB")

    bd_path = DATA / "bangladesh_divisions.geojson"
    if not bd_path.exists():
        print("downloading admin-1 layer (large, extracting Bangladesh only) ...")
        gj = fetch(ADMIN1)
        feats = []
        for f in gj["features"]:
            p = f["properties"]
            if p.get("admin") == "Bangladesh" or p.get("adm0_a3") == "BGD":
                feats.append({"type": "Feature",
                              "properties": {"name": p.get("name"),
                                             "type_en": p.get("type_en"),
                                             "latitude": p.get("latitude"),
                                             "longitude": p.get("longitude")},
                              "geometry": f["geometry"]})
        bd_path.write_text(json.dumps({"type": "FeatureCollection",
                                       "features": feats}), encoding="utf-8")
    bd = json.loads(bd_path.read_text(encoding="utf-8"))
    print(f"Bangladesh divisions: {len(bd['features'])} -> "
          f"{[f['properties']['name'] for f in bd['features']]}")

    (DATA / "SOURCES.txt").write_text(
        "Geographic boundaries\n"
        "---------------------\n"
        "Source : Natural Earth (naturalearthdata.com), public domain.\n"
        "Files  : ne_110m_admin_0_countries.geojson (world outlines)\n"
        "         ne_10m_admin_1_states_provinces.geojson (Bangladesh extract)\n"
        "Vendor : github.com/nvkelso/natural-earth-vector\n"
        "Retrieved by scripts/fetch_geodata.py; only the fields required by the\n"
        "figure scripts are retained.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
