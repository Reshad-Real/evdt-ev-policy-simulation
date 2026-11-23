"""Second, gap-filling Crossref harvest (Bangladesh/LDC, power electronics depth,
cybersecurity, standards, workforce, semiconductors)."""
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from pathlib import Path
from harvest_crossref import crossref, tidy, PREFERRED_PUBLISHERS  # reuse verified helpers

HERE = Path(__file__).resolve().parent

QUERIES = [
    ("bd", "Bangladesh electric vehicle adoption"),
    ("bd", "Bangladesh easy bike three wheeler electric rickshaw"),
    ("bd", "Bangladesh electricity generation renewable solar potential"),
    ("bd", "Bangladesh power system load forecasting distribution"),
    ("bd", "Bangladesh energy security transition net zero"),
    ("bd", "Bangladesh transport sector carbon emissions Dhaka"),
    ("bd", "Bangladesh solar home system rooftop photovoltaic"),
    ("bd", "Bangladesh electric vehicle charging station"),
    ("ldc", "least developed countries electricity access energy poverty"),
    ("ldc", "Africa electric vehicle transition policy"),
    ("ldc", "Nigeria Kenya Ethiopia electricity grid reliability"),
    ("ldc", "off-grid solar mini-grid electric mobility Africa"),
    ("ldc", "informal transport paratransit electrification Africa"),
    ("ldc", "grid instability voltage fluctuation developing country distribution network"),
    ("pe2", "SiC MOSFET traction inverter electric vehicle experimental"),
    ("pe2", "silicon carbide power module electric vehicle drivetrain efficiency"),
    ("pe2", "GaN power device converter high frequency electric vehicle"),
    ("pe2", "gallium nitride totem pole PFC on board charger"),
    ("pe2", "800V battery electric vehicle high voltage architecture"),
    ("pe2", "integrated on-board charger bidirectional V2G converter"),
    ("pe2", "dual active bridge converter electric vehicle"),
    ("pe2", "interleaved boost converter electric vehicle fuel cell"),
    ("pe2", "switching loss conduction loss model SiC MOSFET"),
    ("pe2", "converter efficiency measurement drive cycle electric vehicle inverter"),
    ("pe2", "permanent magnet synchronous motor drive electric vehicle efficiency map"),
    ("pe2", "SiC device reliability degradation gate oxide"),
    ("pe2", "power electronics packaging sintering wide bandgap"),
    ("pe2", "electromagnetic compatibility conducted emission electric vehicle charger"),
    ("pe2", "common mode noise suppression electric vehicle inverter"),
    ("pe2", "power converter Weibull lifetime thermal cycling reliability"),
    ("pe2", "modular multilevel converter medium voltage charging"),
    ("pe2", "silicon carbide semiconductor market cost manufacturing wafer"),
    ("cyb", "cyber attack electric vehicle charging station detection"),
    ("cyb", "security vulnerability OCPP electric vehicle supply equipment"),
    ("cyb", "cyber physical security smart grid electric vehicle"),
    ("std", "IEC 61851 IEEE 1547 electric vehicle charging standard"),
    ("std", "grid code requirements distributed energy resources inverter"),
    ("std", "power quality standard IEEE 519 harmonic limits"),
    ("std", "interoperability electric vehicle charging communication protocol ISO 15118"),
    ("wf", "workforce skills training electric vehicle transition employment"),
    ("wf", "university industry collaboration engineering education energy"),
    ("wf", "technology readiness level assessment energy technology"),
    ("v2g", "vehicle to grid battery degradation impact"),
    ("v2g", "vehicle to grid economic value ancillary services"),
    ("v2g", "bidirectional charging pilot project field trial"),
    ("dt2", "digital twin manufacturing framework architecture review"),
    ("dt2", "digital twin electric motor drive real time simulation"),
    ("dt2", "hardware in the loop real time simulation power electronics"),
    ("dt2", "co-simulation transport energy system model coupling"),
    ("dt2", "digital twin national energy infrastructure planning"),
    ("dem", "electric vehicle charging load profile modelling stochastic"),
    ("dem", "travel survey driving pattern electric vehicle energy consumption"),
    ("dem", "temperature effect electric vehicle range energy consumption"),
    ("dem", "urban rural charging infrastructure disparity equity"),
    ("dem", "electric vehicle equity justice charging access low income"),
]


def main() -> None:
    pool = {}
    for topic, q in QUERIES:
        try:
            items = crossref(q, rows=8)
        except Exception:
            time.sleep(3)
            try:
                items = crossref(q, rows=8)
            except Exception as exc:
                print(f"!! {q}: {exc}")
                continue
        for it in items:
            rec = tidy(it, topic, q)
            if not (rec["doi"] and rec["title"] and rec["year"] and rec["journal"]):
                continue
            if not (2021 <= rec["year"] <= 2026):
                continue
            rec["preferred"] = any(p in rec["publisher"].lower() for p in PREFERRED_PUBLISHERS)
            pool.setdefault(rec["doi"], rec)
        time.sleep(0.35)

    recs = [r for r in pool.values() if r["preferred"] and r["authors"]]
    recs.sort(key=lambda r: (r["topic"], -r["year"], -r["cited_by"]))
    (HERE / "crossref_round2.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False),
                                               encoding="utf-8")
    lines, cur = [], None
    for r in recs:
        if r["topic"] != cur:
            cur = r["topic"]
            lines.append(f"\n===== {cur.upper()} =====")
        lines.append(f"{r['year']}|c{r['cited_by']:<4d}|{r['short_journal'][:24]:24s}|"
                     f"{r['title'][:86]}|{r['doi']}")
    (HERE / "shortlist2.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"round2 pool: {len(recs)}")


if __name__ == "__main__":
    main()
