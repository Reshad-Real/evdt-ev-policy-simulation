"""Full pre-submission audit of the reference list against Crossref.
Every cited DOI is re-resolved and compared field by field with what the
manuscript prints: authors, title, journal, volume, issue, pages, year and
type. Formatting of the rendered Vancouver string is checked separately.

Usage:  py -3 literature/audit_references.py [--json out.json]
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
LIST = (ROOT / "manuscript" / "reference_list.md").read_text(encoding="utf-8")
from cited import cited_keys  # noqa: E402

# Crossref asks callers to identify themselves for its polite pool.
# Override with the CROSSREF_MAILTO environment variable.
MAILTO = os.environ.get("CROSSREF_MAILTO", "realreshad@gmail.com")

# Keys actually cited, in order of first appearance.
seen = cited_keys(REFS)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def resolve(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"EVDT-audit/1.0 (mailto:{MAILTO})"})
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


def cr_authors(msg: dict) -> list[str]:
    out = []
    for a in msg.get("author", []):
        fam = (a.get("family") or "").strip()
        giv = (a.get("given") or "").strip()
        if not fam:
            if a.get("name"):
                out.append(a["name"].strip())
            continue
        ini = "".join(p[0] for p in re.split(r"[\s.\-]+", giv) if p)
        out.append(f"{fam} {ini}".strip())
    return out


def year_of(msg: dict) -> int | None:
    for f in ("published-print", "published-online", "issued", "created"):
        parts = msg.get(f, {}).get("date-parts", [[None]])
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


rendered = {}
for block in LIST.strip().split("\n\n"):
    m = re.match(r"\[(\d+)\]\s*(.*)", block.replace("\n", " "), re.S)
    if m:
        rendered[int(m.group(1))] = re.sub(r"\s+", " ", m.group(2)).strip()

report = []
print(f"auditing {len(seen)} cited references against Crossref\n")
for n, key in enumerate(seen, 1):
    r = REFS[key]
    issues: list[str] = []
    msg = resolve(r["doi"])
    time.sleep(0.12)

    if msg is None:
        issues.append("CRITICAL: DOI does not resolve at Crossref")
        cr = {}
    else:
        cr = {
            "title": (msg.get("title") or [""])[0],
            "journal": (msg.get("container-title") or [""])[0],
            "short": (msg.get("short-container-title") or [""])[0],
            "volume": str(msg.get("volume", "") or ""),
            "issue": str(msg.get("issue", "") or ""),
            "pages": str(msg.get("page", "") or ""),
            "article": str(msg.get("article-number", "") or ""),
            "year": year_of(msg),
            "type": msg.get("type", ""),
            "authors": cr_authors(msg),
            "publisher": msg.get("publisher", ""),
        }
        if cr["type"] != "journal-article":
            issues.append(f"type is '{cr['type']}', not journal-article")
        if norm(cr["title"]) != norm(r["title"]):
            issues.append(f"TITLE differs\n        ours: {r['title']}\n        cref: {cr['title']}")
        if norm(cr["journal"]) != norm(r["journal"]):
            issues.append(f"JOURNAL differs\n        ours: {r['journal']}\n        cref: {cr['journal']}")
        ov = OVERRIDE.get(key, {})
        if cr["authors"] != r["authors"] and "authors" not in ov:
            issues.append(f"AUTHORS differ\n        ours ({len(r['authors'])}): {'; '.join(r['authors'])}"
                          f"\n        cref ({len(cr['authors'])}): {'; '.join(cr['authors'])}")
        for f in ("volume", "issue", "pages"):
            if f in ov:
                continue
            if str(r.get(f, "")) != cr[f]:
                issues.append(f"{f.upper()}: ours '{r.get(f, '')}' vs crossref '{cr[f]}'")
        if cr["year"] != r["year"]:
            issues.append(f"YEAR: ours {r['year']} vs crossref {cr['year']}")
        if (not cr["pages"] and not cr["article"]
                and not r.get("article_number") and not ov):
            issues.append("no page range and no article number")

    text = rendered.get(n, "")
    notes: list[str] = []
    if "et al.." in text:
        issues.append("STYLE: doubled period after 'et al.'")
    if ".." in text.replace("et al..", ""):
        issues.append("STYLE: doubled period")
    # Diacritics in author names and titles are correct, not defects; they are
    # reported for information so that the encoding can be eyeballed.
    bad = sorted({c for c in text if ord(c) > 127})
    if bad:
        notes.append('diacritics present (correct, kept): ' + ''.join(bad))
    if not text:
        issues.append("STYLE: reference not found in the rendered list")

    report.append({"n": n, "key": key, "doi": r["doi"], "issues": issues,
                   "notes": notes, "crossref": cr, "ours": r})
    flag = "OK " if not issues else "!! "
    print(f"{flag}[{n:>2}] {key:26s} {r['doi']}")
    for i in issues:
        print(f"        ISSUE: {i}")
    for i in notes:
        print(f"        note : {i}")

bad = [x for x in report if x["issues"]]
print(f"\n{'=' * 70}\n{len(report) - len(bad)} clean, {len(bad)} with issues")
out = ROOT / "literature" / "reference_audit.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"detail -> {out}")
