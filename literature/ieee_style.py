"""Render references in IEEE style from Crossref-verified records.

IEEE Reference Guide, journal article:

    [1] J. K. Author, A. N. Writer, and B. Reader, "Name of paper," Abbrev.
        Title of Periodical, vol. 12, no. 3, pp. 34-39, Mar. 2020,
        doi: 10.1109/xxxx.

Rules applied here: given-name initials are spaced; two authors are joined by
"and"; three to six take a serial comma before "and"; more than six collapse to
the first author followed by "et al."; the title is sentence case in double
quotation marks with the comma inside; the journal is abbreviated and italic;
an article number is given as "Art. no." where the publisher has no page range.
"""
from __future__ import annotations

import json
import pathlib
import re

_HERE = pathlib.Path(__file__).resolve().parent
ABBREV = {k: v for k, v in json.loads(
    (_HERE / "journal_abbreviations.json").read_text(encoding="utf-8")).items()
    if not k.startswith("_")}
CORRECTIONS = {k: v for k, v in json.loads(
    (_HERE / "corrections.json").read_text(encoding="utf-8")).items()
    if not k.startswith("_")}

import sys
sys.path.insert(0, str(_HERE))
from sentence_case import sentence_case  # noqa: E402


def ieee_name(given: str, family: str) -> str:
    """'Anubhav Kumar', 'Pandey' -> 'A. K. Pandey'; hyphens are preserved."""
    given = (given or "").strip()
    if not given:
        return family.strip()
    parts = []
    for word in re.split(r"\s+", given):
        subs = [s for s in word.split("-") if s]
        parts.append("-".join(f"{s[0]}." for s in subs))
    return " ".join(parts) + " " + family.strip()


def author_block(names: list[str]) -> str:
    """IEEE joining: 'A and B'; 'A, B, and C'; first author plus et al. past six."""
    if not names:
        return ""
    if len(names) > 6:
        return f"{names[0]} et al."
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def locus(rec: dict) -> str:
    """vol./no./pages or article number, as IEEE orders them."""
    bits = []
    if rec.get("volume"):
        bits.append(f"vol. {rec['volume']}")
    if rec.get("issue"):
        bits.append(f"no. {rec['issue']}")
    page = (rec.get("page") or "").strip()
    # Crossref's article-number is a real locator ("8455", "e70013");
    # alternative-id often holds a DOI suffix, so it is used only if numeric.
    art = (rec.get("article_number") or rec.get("article") or "").strip()
    alt = (rec.get("alt_id") or "").strip()
    if "-" in page:
        bits.append(f"pp. {page}")
    elif page:
        bits.append(f"Art. no. {page}")
    elif art:
        bits.append(f"Art. no. {art}")
    elif alt.isdigit():
        bits.append(f"Art. no. {alt}")
    return ", ".join(bits)


def ieee_parts(n: int, rec: dict) -> tuple[str, str, str]:
    """Return the three pieces of an entry: before the journal, the journal
    (which the caller sets in italics), and the remainder."""
    override = CORRECTIONS.get(rec.get("key", ""), {})
    names = override.get("authors_ieee") or [
        ieee_name(a.get("given", ""), a["family"]) for a in rec["authors"]]
    title = sentence_case(rec["title"]).rstrip(".")
    journal = ABBREV.get(rec["journal"], rec["journal"])

    kind = rec.get("type")
    if kind == "proceedings-article":
        # [n] A. Author, "Title," in *Proc. Conference*, year, pp. x-y, doi: ...
        conf = override.get("proceedings", rec["journal"])
        head = f"[{n}] {author_block(names)}, “{title},” in "
        page = (rec.get("page") or "").strip()
        tail = (f", {override.get('year', rec['year'])}"
                + (f", pp. {page}" if "-" in page else "") + f", doi: {rec['doi']}.")
        return head, conf, tail
    if kind in ("online", "report"):
        # [n] Author or Organisation, "Title," Organisation, Place, Rep. no.,
        #     year. [Online]. Available: URL  (or doi)
        who = author_block(names) if rec.get("authors") else rec.get("org", "")
        org = override.get("org", rec.get("org") or rec.get("publisher", ""))
        bits = [org] if org and org != who else []
        place = override.get("place", rec.get("place", ""))
        if place:
            bits.append(place)
        num = override.get("number", rec.get("number", ""))
        year = str(override.get("year", rec["year"]))
        date = year
        if num and not num[0].isdigit() and num.endswith(year):
            date = num            # a month and year ("Jan. 2025"), not a report number
        elif num:
            bits.append(num if not num[0].isdigit() else f"Rep. {num}")
        head = f"[{n}] {who}, “{title.rstrip('.')},” "
        body = ", ".join(bits + [date])
        if rec.get("doi"):
            tail = f", doi: {rec['doi']}."
        else:
            tail = f". Accessed: Nov. 2026. [Online]. Available: {rec.get('url', '')}"
        return head, "", body + tail
    if kind == "monograph":
        # [n] A. Author and B. Author, *Title of Book*. City: Publisher, year,
        #     doi: ...
        head = f"[{n}] {author_block(names)}, "
        tail = (f". {override.get('city', '')}: "
                f"{override.get('publisher_short', rec.get('publisher', ''))}, "
                f"{override.get('year', rec['year'])}, doi: {rec['doi']}.")
        return head, rec["title"].rstrip("."), tail
    if kind == "book-chapter":
        # [n] A. Author, "Chapter," in *Book* (Series). City: Publisher, year,
        #     pp. x-y, doi: ...
        book = override.get("book_title", rec["journal"])
        series = override.get("series", "")
        head = f"[{n}] {author_block(names)}, “{title},” in "
        page = (rec.get("page") or "").strip()
        tail = (f" ({series}). {override.get('city', '')}: "
                f"{override.get('publisher_short', rec.get('publisher', ''))}, "
                f"{rec['year']}" + (f", pp. {page}" if page else "")
                + f", doi: {rec['doi']}.")
        return head, book, tail
    head = f"[{n}] {author_block(names)}, “{title},” "
    if "page" in override:
        rec = {**rec, "page": override["page"]}
    tail_bits = [b for b in (locus(rec),) if b]
    when = f"{rec['month_abbr']} {rec['year']}" if rec.get("month_abbr") else str(rec["year"])
    tail_bits.append(when)
    tail = ", " + ", ".join(tail_bits) + f", doi: {rec['doi']}."
    return head, journal, tail


def ieee_entry(n: int, rec: dict) -> str:
    head, journal, tail = ieee_parts(n, rec)
    return head + journal + tail
