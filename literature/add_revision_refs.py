"""Add the references introduced in the revision of TTE-Reg-2026-08-3015.

Three were named by Reviewer 4 (R1-R3); the rest are the original sources of
the standard methods that the first submission cited only through applications
(Sobol, Saltelli, Morris, NSGA-II, Bass, random forests, TOPSIS), the IEEE
33-bus benchmark used to validate the power flow, the digital-twin taxonomy
used to define what the model is and is not, and the power-cycling and
transformer-ageing sources.

Every DOI is resolved against Crossref, exactly as the existing entries were,
and written to both refs.json (the bibliography) and ieee_source.json (the
fields IEEE style needs).  Crossref is queried without a personal contact
address unless CROSSREF_MAILTO is set.

Usage:  py -3 literature/add_revision_refs.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).resolve().parent
REFS = HERE / "refs.json"
SRC = HERE / "ieee_source.json"
MAILTO = os.environ.get("CROSSREF_MAILTO", "")

NEW = {
    "allca-2024": "10.1109/TTE.2023.3300669",
    "gai-2019": "10.1021/acs.est.9b01519",
    "tang-2021": "10.1016/j.isci.2021.103499",
    "sobol-2001": "10.1016/S0378-4754(00)00270-6",
    "saltelli-2010": "10.1016/j.cpc.2009.09.018",
    "morris-1991": "10.1080/00401706.1991.10484804",
    "deb-2002": "10.1109/4235.996017",
    "bass-1969": "10.1287/mnsc.15.5.215",
    "baran-wu-1989": "10.1109/61.25627",
    "kritzinger-2018": "10.1016/j.ifacol.2018.08.474",
    "breiman-2001": "10.1023/A:1010933404324",
    "hwang-yoon-1981": "10.1007/978-3-642-48318-9_3",
    "goel-2015": "10.1016/j.trd.2015.05.006",
    "piasecki-2021": "10.3390/en14196369",
    "held-1997": "10.1109/PEDS.1997.618742",
    "liu-2016": "10.1109/ECCE.2016.7855024",
    "ornl-prius-2011": "10.2172/1007833",
    "munzel-2019": "10.1016/j.eneco.2019.104493",
    "kalish-1985": "10.1287/mnsc.31.12.1569",
    # third revision: benchmark feeders, surrogate and Sobol estimator
    "simbench-2020": "10.3390/en13123290",
    "baran-wu-1989b": "10.1109/61.19265",
    "das-1994": "10.1049/ip-gtd:19949966",
    "kersting-2001": "10.1109/PESW.2001.916993",
    "rasmussen-2006": "10.7551/mitpress/3206.001.0001",
    "janon-2014": "10.1051/ps/2013040",
}
ONLINE = HERE / "online_sources.json"
MONTH = ["", "Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.",
         "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]


def _context():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def resolve(doi: str) -> dict:
    q = f"?mailto={urllib.parse.quote(MAILTO)}" if MAILTO else ""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "EVDT-bib/2.0"})
    err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45, context=_context()) as r:
                return json.load(r)["message"]
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 + 3 * attempt)
    raise SystemExit(f"{doi}: {err}")


def clean(text: str) -> str:
    import html
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip())


def main() -> None:
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    src = json.loads(SRC.read_text(encoding="utf-8"))
    have = {r["key"] for r in src}
    for key, doi in NEW.items():
        m = resolve(doi)
        time.sleep(0.2)
        year = month = None
        for f in ("published-print", "issued", "published-online", "created"):
            dp = m.get(f, {}).get("date-parts", [[None]])
            if dp and dp[0] and dp[0][0]:
                year = year or int(dp[0][0])
                if month is None and len(dp[0]) > 1 and dp[0][1]:
                    month = int(dp[0][1])
                if f in ("published-print", "issued") and month:
                    break
        authors = [{"given": (a.get("given") or "").strip(),
                    "family": (a.get("family") or a.get("name") or "").strip()}
                   for a in m.get("author", [])]
        title = clean((m.get("title") or [""])[0])
        journal = clean((m.get("container-title") or [""])[0])
        refs[key] = {
            "key": key, "doi": m["DOI"], "title": title,
            "authors": [f"{a['family']} {''.join(p[0] for p in re.split(r'[\\s.\\-]+', a['given']) if p)}".strip()
                        for a in authors],
            "journal": journal,
            "journal_short": clean((m.get("short-container-title") or [journal])[0]),
            "volume": str(m.get("volume", "") or ""),
            "issue": str(m.get("issue", "") or ""),
            "pages": str(m.get("page", "") or ""),
            "article_number": str(m.get("article-number", "") or ""),
            "year": year, "publisher": clean(m.get("publisher", "")),
            "type": m.get("type", ""),
        }
        rec = {"n": 0, "key": key, "doi": m["DOI"], "title": title, "journal": journal,
               "volume": str(m.get("volume", "") or ""),
               "issue": str(m.get("issue", "") or ""),
               "page": str(m.get("page", "") or ""),
               "article": str(m.get("article-number", "") or ""),
               "alt_id": (m.get("alternative-id") or [""])[0],
               "year": year, "month": month, "month_abbr": MONTH[month] if month else "",
               "type": m.get("type", ""), "authors": authors,
               "publisher": clean(m.get("publisher", "")),
               "isbn": (m.get("ISBN") or [""])[0]}
        if key in have:
            src = [rec if r["key"] == key else r for r in src]
        else:
            src.append(rec)
        print(f"  {key:16s} {rec['type']:18s} {year}  {journal[:40]:40s} {title[:70]}")
    # data sources without a Crossref record, checked by hand
    online = {k: v for k, v in json.loads(ONLINE.read_text(encoding="utf-8-sig")).items()
              if not k.startswith("_")}
    for key, o in online.items():
        rec = {"n": 0, "key": key, "doi": o.get("doi", ""), "title": o["title"],
               "journal": o.get("org", ""), "volume": "", "issue": "", "page": "",
               "article": "", "alt_id": "", "year": o["year"], "month": None,
               "month_abbr": "", "type": o["type"], "authors": o.get("authors", []),
               "publisher": o.get("org", ""), "org": o.get("org", ""),
               "place": o.get("place", ""), "number": o.get("number", ""),
               "url": o.get("url", "")}
        src = [r for r in src if r["key"] != key] + [rec]
        refs[key] = {"key": key, "doi": o.get("doi", ""), "title": o["title"],
                     "authors": [f"{a['family']} {a['given']}" for a in o.get("authors", [])]
                     or [o.get("org", "")],
                     "journal": o.get("org", ""), "journal_short": o.get("org", ""),
                     "volume": "", "issue": "", "pages": "", "article_number": "",
                     "year": o["year"], "publisher": o.get("org", ""), "type": o["type"],
                     "url": o.get("url", "")}
        print(f"  {key:16s} {o['type']:18s} {o['year']}  {o['title'][:70]}")
    REFS.write_text(json.dumps(refs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SRC.write_text(json.dumps(src, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"refs.json: {len(refs)} entries; ieee_source.json: {len(src)} entries")


if __name__ == "__main__":
    main()
