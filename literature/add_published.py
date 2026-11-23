"""Add the author's own published papers to the verified bibliography.

The PDFs in ``E:/Published`` carry their DOI in the embedded PRISM metadata.
Each DOI is re-resolved against Crossref here, exactly as every other entry in
``refs.json`` was, so authors, journal, volume and pages are publisher-deposited
rather than transcribed from the PDF.

Usage:  py -3 literature/add_published.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REFS = ROOT / "refs.json"
# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

# key -> DOI, taken from the PRISM metadata embedded in each PDF.
PUBLISHED = {
    "own-dt-anomaly":     "10.1016/j.est.2026.122795",
    "own-grid-cyber":     "10.1016/j.ecmx.2025.101416",
    "own-wams":           "10.1016/j.ecmx.2025.101424",
    "own-storage":        "10.1016/j.ecmx.2026.101771",
    "own-soc-charging":   "10.1016/j.ecmx.2026.101775",
    "own-ev-cyber-tea":   "10.1016/j.ecmx.2026.102107",
}


def resolve(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"EVDT-bib/1.0 (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)["message"]


def fmt_authors(msg: dict) -> list[str]:
    out = []
    for a in msg.get("author", []):
        family = a.get("family", "").strip()
        given = a.get("given", "").strip()
        if not family:
            continue
        initials = "".join(p[0] for p in re.split(r"[\s.\-]+", given) if p)
        out.append(f"{family} {initials}".strip())
    return out


def year_of(msg: dict) -> int:
    for f in ("published-print", "published-online", "issued", "created"):
        parts = msg.get(f, {}).get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return 0


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    added, skipped = [], []
    for key, doi in PUBLISHED.items():
        if any(r["doi"].lower() == doi.lower() for r in refs.values()):
            skipped.append(doi)
            continue
        m = resolve(doi)
        title = clean(m["title"][0]) if m.get("title") else ""
        journal = clean(m["container-title"][0]) if m.get("container-title") else ""
        pages = m.get("page", "")
        art = str(m.get("article-number", "") or "")
        refs[key] = {
            "key": key,
            "doi": m["DOI"],
            "title": title,
            "authors": fmt_authors(m),
            "journal": journal,
            "journal_short": clean(m["short-container-title"][0])
                             if m.get("short-container-title") else journal,
            "volume": str(m.get("volume", "") or ""),
            "issue": str(m.get("issue", "") or ""),
            "pages": pages,
            "article_number": art,
            "year": year_of(m),
            "publisher": clean(m.get("publisher", "")),
            "type": m.get("type", "journal-article"),
        }
        added.append(key)
        print(f"  {key:18s} {m['DOI']}")
        print(f"     {title[:96]}")
        print(f"     {refs[key]['journal_short']} {refs[key]['year']};"
              f"{refs[key]['volume']}:{pages or art}  "
              f"({len(refs[key]['authors'])} authors)")

    REFS.write_text(json.dumps(refs, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"\nadded {len(added)}, already present {len(skipped)}, "
          f"total {len(refs)} references in refs.json")
    if any(refs[k]["year"] < 2021 or refs[k]["year"] > 2026 for k in added):
        sys.exit("a resolved year falls outside the 2021-2026 window")


if __name__ == "__main__":
    main()
