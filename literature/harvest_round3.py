"""Round 3: precision Crossref queries using query.title to lock onto
Bangladesh / South-Asia / LDC-specific peer-reviewed work."""
from __future__ import annotations
import json, time, urllib.parse, urllib.request
from pathlib import Path
from harvest_crossref import tidy, PREFERRED_PUBLISHERS

HERE = Path(__file__).resolve().parent
# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

TITLE_QUERIES = [
    ("bd", "Bangladesh electric vehicle"),
    ("bd", "Bangladesh energy"),
    ("bd", "Bangladesh power"),
    ("bd", "Bangladesh renewable"),
    ("bd", "Bangladesh solar"),
    ("bd", "Bangladesh grid"),
    ("bd", "Bangladesh transport emission"),
    ("bd", "Bangladesh electricity"),
    ("bd", "Dhaka air quality transport"),
    ("bd", "Bangladesh battery"),
    ("bd", "Bangladesh charging"),
    ("sa", "India electric vehicle charging infrastructure"),
    ("sa", "Pakistan electric vehicle"),
    ("sa", "Sri Lanka electric vehicle"),
    ("sa", "Nepal electric vehicle"),
    ("sea", "Vietnam electric vehicle"),
    ("sea", "Indonesia electric vehicle"),
    ("sea", "Philippines electric vehicle"),
    ("af", "Africa electric vehicle"),
    ("af", "Ethiopia electric vehicle"),
    ("af", "Kenya electric mobility"),
    ("af", "Nigeria electricity grid"),
    ("af", "sub-Saharan Africa electricity access"),
]


def crossref_title(query: str, rows: int = 10) -> list[dict]:
    params = {
        "query.bibliographic": query,
        "rows": str(rows),
        "sort": "relevance",
        "filter": "type:journal-article,from-pub-date:2021-01-01,until-pub-date:2026-12-31",
        "select": "title,author,container-title,volume,issue,page,issued,DOI,publisher,type,"
                  "article-number,short-container-title,is-referenced-by-count",
        "mailto": MAILTO,
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": f"EVDT-lit/1.0 (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)["message"]["items"]


def main() -> None:
    pool = {}
    for topic, q in TITLE_QUERIES:
        key = q.split()[0].lower()
        try:
            items = crossref_title(q)
        except Exception as exc:
            print(f"!! {q}: {exc}")
            continue
        for it in items:
            rec = tidy(it, topic, q)
            if not (rec["doi"] and rec["title"] and rec["year"] and rec["journal"]):
                continue
            if not (2021 <= rec["year"] <= 2026):
                continue
            # precision guard: the country/region token must appear in the title
            if key not in rec["title"].lower() and key not in ("sub-saharan",):
                continue
            rec["preferred"] = any(p in rec["publisher"].lower() for p in PREFERRED_PUBLISHERS)
            if rec["preferred"] and rec["authors"]:
                pool.setdefault(rec["doi"], rec)
        time.sleep(0.35)

    recs = sorted(pool.values(), key=lambda r: (r["topic"], -r["year"], -r["cited_by"]))
    (HERE / "crossref_round3.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False),
                                               encoding="utf-8")
    lines, cur = [], None
    for r in recs:
        if r["topic"] != cur:
            cur = r["topic"]
            lines.append(f"\n===== {cur.upper()} =====")
        lines.append(f"{r['year']}|c{r['cited_by']:<4d}|{r['short_journal'][:22]:22s}|"
                     f"{r['title'][:92]}|{r['doi']}")
    (HERE / "shortlist3.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"round3: {len(recs)}")


if __name__ == "__main__":
    main()
