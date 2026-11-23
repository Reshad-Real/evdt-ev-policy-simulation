"""Which references the manuscript cites, and in what order.

The order is normally derived from the manuscript source. The reproduction
package does not carry the manuscript text, so ``build_manuscript.py`` also
writes ``cited_keys.json`` beside this file and the audit tools fall back to
it. Both routes give the same list.
"""
from __future__ import annotations

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "manuscript" / "manuscript_src.md"
KEYS = HERE / "cited_keys.json"

MARKER = re.compile(r"\[([a-z0-9][a-z0-9\-]*(?:\s*;\s*[a-z0-9][a-z0-9\-]*)*)\]")


def cited_keys(refs: dict) -> list[str]:
    """Citation keys in order of first appearance."""
    if SRC.exists():
        order: list[str] = []
        text = SRC.read_text(encoding="utf-8")
        for group in MARKER.findall(text):
            for key in (k.strip() for k in group.split(";")):
                if key in refs and key not in order:
                    order.append(key)
        return order

    if KEYS.exists():
        order = json.loads(KEYS.read_text(encoding="utf-8"))
        missing = [k for k in order if k not in refs]
        if missing:
            raise SystemExit(f"cited_keys.json names unknown keys: {missing[:5]}")
        return order

    raise SystemExit(
        "Neither manuscript/manuscript_src.md nor literature/cited_keys.json "
        "is present, so the cited reference order cannot be determined.")


def write_keys(order: list[str]) -> None:
    KEYS.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
