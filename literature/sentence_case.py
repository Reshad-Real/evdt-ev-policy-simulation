"""Convert publisher Title Case to Vancouver sentence case.

Vancouver capitalises only the first word of the title, the first word after a
colon, and proper nouns. Publisher metadata for MDPI, IEEE and Springer arrives
in Title Case, so the reference list would otherwise mix two conventions.

The conversion is deliberately conservative: acronyms, element symbols, tokens
containing digits or internal capitals, and an explicit list of proper nouns
are preserved. Hyphenated compounds are decided part by part.
"""
from __future__ import annotations

import re

# Proper nouns, demonyms, places, named methods and standards bodies.
PROTECT = {
    # places and demonyms
    "africa", "african", "saharan", "china", "chinese", "india", "indian",
    "indonesia", "bangladesh", "pakistan", "nepal", "thailand", "lao", "pdr",
    "vietnam", "germany", "german", "denmark", "danish", "norway", "europe",
    "european", "asean", "dhaka", "asia", "asian", "ethiopia", "ethiopian",
    "america", "american", "brazil", "japan", "japanese", "korea", "korean",
    "netherlands", "sweden", "swedish", "italy", "spain", "france", "french",
    "poland", "turkey", "connecticut", "california", "texas", "britain",
    "british", "australia", "canada", "canadian", "global", "south", "north",
    # people and named methods
    "monte", "carlo", "sobol", "morris", "bass", "erlang", "weibull", "pareto",
    "kalman", "arrhenius", "coffin", "manson", "miner", "kirchhoff", "latin",
    "hypercube", "nsga", "topsis", "prisma", "gaussian", "schottky", "bayesian",
    "markov", "poisson", "fourier", "laplace", "newton", "raphson", "nyquist",
    # organisations, standards, laws
    "ieee", "iec", "iso", "ocpp", "chademo", "sae", "nrel", "ipcc",
    # places, products and German titles added in the revision
    "ontario", "ontario’s", "ontario's", "toyota", "prius", "nissan", "honda",
    "chevrolet", "fahrzeugbestand", "zeitreihen", "umwelt", "verkehr", "kilometern",
    "kraftfahrzeuge", "kurzbericht", "deutschen",
    # unit symbol in compounds such as 800-V
    "v",
    # element and material symbols that are not all-caps
    "si", "ge", "ga", "li", "ni", "mn", "fe", "al", "cu", "zn", "ag", "sn",
    "ti", "pb", "pt", "gan", "sic",
    # months
    "january", "february", "march", "april", "june", "july", "august",
    "september", "october", "november", "december",
}

# Multi-word names that only make sense capitalised together.
PHRASES = ["Global South", "Bipartisan Infrastructure Law", "Sub-Saharan Africa",
           "Lao PDR", "Nature Communications", "Hybrid Synergy Drive",
           "Our World in Data", "Global EV Outlook", "Global EV outlook",
           "Honda Accord",
           # German titles: nouns keep their capitals
           "Fahrzeugzulassungen im Dezember - Jahresbilanz",
           "Umweltbonus endet mit Ablauf des 17. Dezember 2023",
           "Richtlinie zur Förderung des Absatzes von elektrisch betriebenen "
           "Fahrzeugen (Umweltbonus)"]


def _keep(core: str) -> bool:
    """Is this token already correctly capitalised and should it stay?"""
    if not core:
        return True
    if core.isupper() and len(core) > 1:          # acronym: EV, MOSFET, ANPC
        return True
    if any(c.isupper() for c in core[1:]):        # internal caps: SiC, GaN, MOSFETs
        return True
    if re.search(r"\d", core):                    # 5G, 61000-3-6, CO2
        return True
    return core.lower() in PROTECT


def _split_case(tok: str, keep_first: bool = False) -> str:
    """Lower-case a token unless it must keep its capital; respect hyphens."""
    core_h = tok.strip("()[]{}\"'.,;:!?")
    if "-" in core_h and any(c.isalnum() for c in core_h):
        lead = re.match(r"^\W*", tok).group(0)
        trail = re.search(r"\W*$", tok).group(0)
        body = tok[len(lead):len(tok) - len(trail) or None]
        parts = body.split("-")
        out = []
        for i, p in enumerate(parts):
            if i == 0 and keep_first:
                out.append(p)
            else:
                out.append(p if _keep(p) else p.lower())
        return lead + "-".join(out) + trail
    core = tok.strip("()[]{}\"'.,;:!?")
    if keep_first:
        return tok
    return tok if _keep(core) else tok.lower()


def sentence_case(title: str) -> str:
    # Long dashes are not used in this manuscript. An unspaced en dash joins a
    # compound ("DC-DC", "demand-supply") and becomes a hyphen; an em dash, or
    # any spaced long dash, is punctuation and becomes a spaced hyphen.
    for ch in ("‐", "‑", "‒", "−"):
        title = title.replace(ch, "-")
    title = re.sub(r"(?<=\w)–(?=\w)", "-", title)
    title = re.sub(r"\s*[–—]\s*", " - ", title)
    holes: list[str] = []
    for ph in PHRASES:                            # shield multi-word names
        if ph in title:
            title = title.replace(ph, f"\x00{len(holes)}\x00")
            holes.append(ph)

    out, first = [], True
    for tok in re.split(r"(\s+)", title):
        if not tok.strip():
            out.append(tok)
            continue
        out.append(_split_case(tok, keep_first=first))
        first = tok.rstrip().endswith((":", ".", "?", "!"))
    s = "".join(out)

    for i, ph in enumerate(holes):
        s = s.replace(f"\x00{i}\x00", ph)
    return s[0].upper() + s[1:] if s else s
