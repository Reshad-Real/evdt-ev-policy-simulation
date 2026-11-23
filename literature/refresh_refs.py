"""Refresh the cited entries of refs.json from Crossref and report changes.

Publishers re-deposit records: a volume, issue or article number absent at
first harvest can appear later. This re-resolves every cited DOI, updates the
stored record and prints a field-level diff so nothing changes silently.

Usage:  py -3 literature/refresh_refs.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFS_PATH = ROOT / "literature" / "refs.json"
REFS = json.loads(REFS_PATH.read_text(encoding="utf-8"))
from cited import cited_keys  # noqa: E402

# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

order = cited_keys(REFS)


def resolve(doi):
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"EVDT-refresh/1.0 (mailto:{MAILTO})"})
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


def authors(msg):
    out = []
    for a in msg.get("author", []):
        fam, giv = (a.get("family") or "").strip(), (a.get("given") or "").strip()
        if not fam:
            if a.get("name"):
                out.append(a["name"].strip())
            continue
        ini = "".join(p[0] for p in re.split(r"[\s.\-]+", giv) if p)
        out.append(f"{fam} {ini}".strip())
    return out


def year_of(msg):
    for f in ("published-print", "published-online", "issued", "created"):
        dp = msg.get(f, {}).get("date-parts", [[None]])
        if dp and dp[0] and dp[0][0]:
            return int(dp[0][0])
    return None


def clean(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t or "")).strip()


changes = 0
for n, key in enumerate(order, 1):
    r = REFS[key]
    m = resolve(r["doi"])
    time.sleep(0.12)
    if m is None:
        print(f"  [{n:>2}] {key}: DOI DOES NOT RESOLVE")
        continue
    fresh = {
        "title": clean((m.get("title") or [""])[0]),
        "authors": authors(m),
        "journal": clean((m.get("container-title") or [""])[0]),
        "journal_short": clean((m.get("short-container-title") or [""])[0])
                         or clean((m.get("container-title") or [""])[0]),
        "volume": str(m.get("volume", "") or ""),
        "issue": str(m.get("issue", "") or ""),
        "pages": str(m.get("page", "") or ""),
        "article_number": str(m.get("article-number", "") or ""),
        "year": year_of(m),
        "publisher": clean(m.get("publisher", "")),
        "type": m.get("type", "journal-article"),
    }
    diff = {f: (r.get(f), v) for f, v in fresh.items() if r.get(f) != v}
    if diff:
        changes += 1
        print(f"  [{n:>2}] {key}  {r['doi']}")
        for f, (old, new) in diff.items():
            print(f"        {f}: {old!r} -> {new!r}")
        r.update(fresh)

REFS_PATH.write_text(json.dumps(REFS, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
print(f"\n{len(order)} cited entries re-resolved; {changes} updated")
