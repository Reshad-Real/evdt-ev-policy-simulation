"""Re-resolve every cited DOI and capture the fields IEEE style needs.

IEEE wants given-name initials spaced ("J. K. Author"), an abbreviated and
italicised journal, volume, issue, either a page range or an article number,
the month where the publisher deposits one, and the DOI.

Usage:  py -3 literature/fetch_ieee_source.py
Output: literature/ieee_source.json
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS = json.loads((ROOT / "literature" / "refs.json").read_text(encoding="utf-8"))
OVERRIDE = {k: v for k, v in json.loads(
    (ROOT / "literature" / "corrections.json").read_text(encoding="utf-8")).items()
    if not k.startswith("_")}
from cited import cited_keys  # noqa: E402

# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

order = cited_keys(REFS)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"<[^>]+>", "", s).lower()).strip()


def resolve(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"EVDT-ieee/1.0 (mailto:{MAILTO})"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)["message"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 + 3 * attempt)
        except Exception:
            time.sleep(2 + 3 * attempt)
    return None


MONTH = ["", "Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.",
         "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]

out, problems = [], []
print(f"resolving {len(order)} DOIs\n")
for n, key in enumerate(order, 1):
    r = REFS[key]
    m = resolve(r["doi"])
    time.sleep(0.12)
    if m is None:
        problems.append((n, key, "DOI does not resolve"))
        continue

    # issue date preferred over the online date for month and year
    month = year = None
    for f in ("published-print", "issued", "published-online", "created"):
        dp = m.get(f, {}).get("date-parts", [[None]])
        if dp and dp[0] and dp[0][0]:
            year = year or int(dp[0][0])
            if month is None and len(dp[0]) > 1 and dp[0][1]:
                month = int(dp[0][1])
            if f in ("published-print", "issued") and month:
                break

    authors = []
    for a in m.get("author", []):
        fam = (a.get("family") or "").strip()
        giv = (a.get("given") or "").strip()
        if not fam and a.get("name"):
            authors.append({"given": "", "family": a["name"].strip()})
        elif fam:
            authors.append({"given": giv, "family": fam})

    rec = {
        "n": n, "key": key, "doi": m["DOI"],
        "title": (m.get("title") or [""])[0],
        "journal": (m.get("container-title") or [""])[0],
        "volume": str(m.get("volume", "") or ""),
        "issue": str(m.get("issue", "") or ""),
        "page": str(m.get("page", "") or ""),
        "article": str(m.get("article-number", "") or ""),
        "alt_id": (m.get("alternative-id") or [""])[0],
        "year": year, "month": month, "month_abbr": MONTH[month] if month else "",
        "type": m.get("type", ""),
        "authors": authors,
    }
    rec.update({k: v for k, v in OVERRIDE.get(key, {}).items() if k != "why"})
    out.append(rec)

    # substance must still agree with what the manuscript carries
    if norm(rec["title"]) != norm(r["title"]):
        problems.append((n, key, "title differs from refs.json"))
    if rec["type"] != "journal-article":
        problems.append((n, key, f"type {rec['type']}"))
    print(f"  [{n:>2}] {key:26s} {rec['year']}"
          f"{'/' + str(rec['month']) if rec['month'] else '':>4}  "
          f"vol {rec['volume'] or '-':>4}  "
          f"page {rec['page'] or '-':>12}  art {rec['article'] or rec['alt_id'] or '-'}")

(ROOT / "literature" / "ieee_source.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
have_month = sum(1 for r in out if r["month"])
print(f"\nresolved {len(out)}/{len(order)}   problems: {len(problems)}")
for p in problems:
    print("   ", p)
print(f"month available for {have_month} of {len(out)} entries")
