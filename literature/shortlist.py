"""Filter the Crossref candidate pool down to a reviewable shortlist."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
recs = json.loads((HERE / "crossref_candidates.json").read_text(encoding="utf-8"))

by_topic = defaultdict(list)
for r in recs:
    if not r["preferred"]:
        continue
    if len(r["authors"]) == 0:
        continue
    by_topic[r["topic"]].append(r)

out = []
for topic in sorted(by_topic):
    rows = by_topic[topic]
    recent = sorted([r for r in rows if r["year"] >= 2024], key=lambda r: -r["cited_by"])[:9]
    older = sorted([r for r in rows if r["year"] < 2024], key=lambda r: -r["cited_by"])[:9]
    sel = sorted(recent + older, key=lambda r: (-r["year"], -r["cited_by"]))
    out.append(f"\n===== {topic.upper()} ({len(rows)} candidates) =====")
    for r in sel:
        out.append(f"{r['year']}|c{r['cited_by']:<4d}|{r['short_journal'][:24]:24s}|"
                   f"{r['title'][:86]}|{r['doi']}")
(HERE / "shortlist.txt").write_text("\n".join(out), encoding="utf-8")
print(f"topics: {len(by_topic)}, shortlisted lines: {len(out)}")
