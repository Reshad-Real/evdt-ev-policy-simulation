"""Harvest candidate references from the Crossref REST API.

Every candidate returned by this script corresponds to a registered DOI with
publisher-deposited metadata, so no bibliographic detail is invented.  The
script writes a machine-readable candidate pool plus a compact human-readable
digest that is manually curated into the final reference list.

Usage:  py -3 harvest_crossref.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

# Publisher families explicitly requested by the study protocol.
PREFERRED_PUBLISHERS = (
    "elsevier", "ieee", "springer", "mdpi", "wiley", "nature",
    "informa", "taylor", "american chemical", "institution of engineering",
    "public library of science", "plos", "sage", "iop publishing",
    "frontiers", "oxford university press", "cambridge university press",
)

QUERIES = [
    ("policy", "electric vehicle charging infrastructure policy review"),
    ("policy", "electric vehicle adoption incentives policy comparative analysis countries"),
    ("policy", "electric vehicle policy instruments effectiveness evaluation"),
    ("dt", "digital twin electric vehicle battery state of health estimation"),
    ("dt", "digital twin power electronics converter condition monitoring"),
    ("dt", "digital twin electric vehicle charging infrastructure"),
    ("dt", "digital twin power system distribution network review"),
    ("dt", "digital twin fleet management electric vehicles"),
    ("dt", "digital twin energy system review applications"),
    ("pe", "silicon carbide MOSFET traction inverter electric vehicle efficiency"),
    ("pe", "GaN HEMT on-board charger electric vehicle"),
    ("pe", "wide bandgap semiconductor power electronics electric vehicle review"),
    ("pe", "800 V electric vehicle powertrain architecture fast charging"),
    ("pe", "bidirectional DC-DC converter electric vehicle review"),
    ("pe", "on-board charger topology electric vehicle review"),
    ("pe", "multilevel converter electric vehicle motor drive"),
    ("pe", "solid state transformer fast charging station medium voltage"),
    ("pe", "gate driver silicon carbide MOSFET switching"),
    ("pe", "power module thermal management electric vehicle inverter"),
    ("pe", "electromagnetic interference electric vehicle powertrain converter"),
    ("pe", "reliability lifetime prediction power electronic converter"),
    ("pe", "power density efficiency comparison SiC GaN converter"),
    ("pe", "traction motor drive control electric vehicle review"),
    ("pe", "silicon carbide versus silicon inverter loss drive cycle electric vehicle"),
    ("pe", "power semiconductor device manufacturing supply chain"),
    ("charge", "extreme fast charging electric vehicle grid impact"),
    ("charge", "electric vehicle charging station siting optimization"),
    ("charge", "smart charging coordination optimization electric vehicles"),
    ("charge", "electric vehicle charging queueing waiting time model"),
    ("charge", "wireless power transfer electric vehicle charging"),
    ("charge", "battery swapping station electric vehicle"),
    ("charge", "electric vehicle charging standards CCS CHAdeMO comparison"),
    ("charge", "real world electric vehicle charging behaviour data analysis"),
    ("grid", "vehicle-to-grid technology review services"),
    ("grid", "vehicle-to-home energy management system"),
    ("grid", "electric vehicle charging impact distribution network voltage"),
    ("grid", "power quality harmonic distortion electric vehicle charging"),
    ("grid", "distribution transformer loss of life electric vehicle charging"),
    ("grid", "grid flexibility demand response electric vehicles aggregator"),
    ("grid", "microgrid electric vehicle renewable energy integration"),
    ("grid", "photovoltaic powered electric vehicle charging station design"),
    ("grid", "renewable energy intermittency grid stability energy storage"),
    ("grid", "electric vehicle grid code interconnection standards"),
    ("grid", "power system reliability resilience assessment distribution"),
    ("batt", "lithium-ion battery degradation calendar cycle aging model"),
    ("batt", "electric vehicle battery capacity fade semi-empirical model"),
    ("batt", "second life electric vehicle battery energy storage"),
    ("batt", "lithium-ion battery recycling review sustainability"),
    ("batt", "hybrid energy storage supercapacitor battery electric vehicle"),
    ("batt", "battery thermal management electric vehicle fast charging"),
    ("ai", "machine learning electric vehicle charging demand forecasting"),
    ("ai", "deep learning state of charge estimation lithium-ion battery"),
    ("ai", "physics-informed neural network battery modelling"),
    ("ai", "predictive maintenance machine learning electric vehicle"),
    ("ai", "artificial intelligence smart grid energy management review"),
    ("ai", "internet of things smart charging monitoring electric vehicle"),
    ("ai", "reinforcement learning electric vehicle charging scheduling"),
    ("cyber", "cybersecurity electric vehicle charging infrastructure"),
    ("env", "life cycle assessment electric vehicle carbon emissions"),
    ("env", "well-to-wheel greenhouse gas emissions electric vehicle grid mix"),
    ("env", "transport decarbonization pathway carbon neutrality"),
    ("econ", "electric vehicle total cost of ownership analysis"),
    ("econ", "cost benefit analysis charging infrastructure investment"),
    ("econ", "multi-objective optimization charging infrastructure planning"),
    ("dev", "electric mobility Africa barriers developing countries"),
    ("dev", "electric two-wheeler three-wheeler developing country adoption"),
    ("dev", "Bangladesh renewable energy policy transition"),
    ("dev", "Bangladesh power sector electricity generation planning"),
    ("dev", "Bangladesh electric vehicle transport emissions"),
    ("dev", "India electric vehicle policy adoption barriers"),
    ("dev", "Pakistan electric vehicle policy energy"),
    ("dev", "Vietnam Indonesia electric vehicle adoption Southeast Asia"),
    ("dev", "Sri Lanka energy transition electricity"),
    ("dev", "electricity access rural electrification Sub-Saharan Africa mini-grid"),
    ("dev", "least developed countries energy access sustainable development"),
    ("dev", "electric bus fleet public transport electrification"),
    ("devd", "China new energy vehicle policy evaluation"),
    ("devd", "Norway electric vehicle incentives adoption"),
    ("devd", "Germany Netherlands electric vehicle charging policy"),
    ("devd", "Japan South Korea electric vehicle industry policy"),
    ("devd", "United States electric vehicle infrastructure federal policy"),
    ("meth", "Monte Carlo uncertainty analysis electric vehicle charging load"),
    ("meth", "global sensitivity analysis Sobol energy system model"),
    ("meth", "scenario analysis energy transition modelling"),
    ("meth", "multi-criteria decision analysis energy policy TOPSIS"),
    ("meth", "agent-based model electric vehicle adoption diffusion"),
    ("meth", "energy management strategy optimization electric vehicle"),
]


def crossref(query: str, rows: int = 8) -> list[dict]:
    params = {
        "query.bibliographic": query,
        "rows": str(rows),
        "sort": "relevance",
        "filter": "type:journal-article,from-pub-date:2021-01-01,until-pub-date:2026-12-31",
        "select": "title,author,container-title,volume,issue,page,issued,DOI,publisher,"
                  "type,article-number,short-container-title,is-referenced-by-count",
        "mailto": MAILTO,
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": f"EVDT-lit-harvest/1.0 (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.load(resp)
    return payload["message"]["items"]


def tidy(item: dict, topic: str, query: str) -> dict:
    authors = []
    for a in item.get("author", [])[:12]:
        fam = a.get("family", "").strip()
        given = a.get("given", "").strip()
        if fam:
            initials = "".join(p[0] for p in given.replace("-", " ").split() if p)
            authors.append(f"{fam} {initials}".strip())
    year = None
    for key in ("issued", "published-print", "published-online"):
        dp = item.get(key, {}).get("date-parts", [[None]])
        if dp and dp[0] and dp[0][0]:
            year = dp[0][0]
            break
    return {
        "topic": topic,
        "query": query,
        "title": (item.get("title") or [""])[0].strip(),
        "authors": authors,
        "journal": (item.get("container-title") or [""])[0].strip(),
        "short_journal": (item.get("short-container-title") or [""])[0].strip(),
        "volume": item.get("volume", ""),
        "issue": item.get("issue", ""),
        "pages": item.get("page", ""),
        "article_number": item.get("article-number", ""),
        "year": year,
        "doi": item.get("DOI", ""),
        "publisher": item.get("publisher", ""),
        "cited_by": item.get("is-referenced-by-count", 0),
    }


def main() -> None:
    pool: dict[str, dict] = {}
    for topic, q in QUERIES:
        try:
            items = crossref(q)
        except Exception as exc:  # network hiccup -> retry once
            time.sleep(3)
            try:
                items = crossref(q)
            except Exception:
                print(f"!! failed: {q} ({exc})")
                continue
        for it in items:
            rec = tidy(it, topic, q)
            if not rec["doi"] or not rec["title"] or rec["year"] is None:
                continue
            if not (2021 <= rec["year"] <= 2026):
                continue
            if not rec["journal"]:
                continue
            pub = rec["publisher"].lower()
            rec["preferred"] = any(p in pub for p in PREFERRED_PUBLISHERS)
            if rec["doi"] not in pool:
                pool[rec["doi"]] = rec
        time.sleep(0.35)

    records = sorted(pool.values(), key=lambda r: (r["topic"], -r["cited_by"]))
    (HERE / "crossref_candidates.json").write_text(
        json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = []
    cur = None
    for i, r in enumerate(records):
        if r["topic"] != cur:
            cur = r["topic"]
            lines.append(f"\n===== TOPIC {cur.upper()} =====")
        flag = "*" if r["preferred"] else " "
        lines.append(
            f"{i:3d}{flag}|{r['year']}|c{r['cited_by']:<5d}|{r['short_journal'][:26]:26s}|"
            f"{r['title'][:88]}|{r['doi']}")
    (HERE / "digest.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"pool size: {len(records)} unique DOIs; preferred: "
          f"{sum(1 for r in records if r['preferred'])}")


if __name__ == "__main__":
    main()
