"""Read-only mechanism check for one pass of a Phase D run: discordant queries between two arms, and the accuracy of a
naive arm split by its route and by passage-level gold hit.

  python -m src.phase_d_validation.mechanism_check outputs/phase_d_gemini_full_2026-10-12/results.jsonl --pass 1 \
      --out outputs/mechanism_check_2026-10-12/gemini_pass1.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--pass", dest="pass_no", type=int, default=1)
    ap.add_argument("--x", default="policy_v2")
    ap.add_argument("--y", default="naive_llm")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = [json.loads(l) for l in Path(a.results).read_text(encoding="utf-8").splitlines() if l.strip()]
    P = {(r["arm"], r["query_id"]): r for r in rows if r["pass"] == a.pass_no}
    qids = sorted({q for (_, q) in P})
    o = [f"# Mechanism check: {a.x} vs {a.y}, pass {a.pass_no}\n", f"Source: `{a.results}` (read-only). Primary scoring labels (`correct`).\n"]
    disc = [q for q in qids if P[(a.x, q)]["correct"] != P[(a.y, q)]["correct"]]
    o.append(f"## Discordant queries ({len(disc)}: b = {sum(P[(a.x, q)]['correct'] for q in disc)} {a.x} only correct, c = {sum(P[(a.y, q)]['correct'] for q in disc)} {a.y} only correct)\n")
    o.append(f"| query | correct by | {a.y} route | rows returned {a.x} / {a.y} | passage gold hit {a.x} / {a.y} | {a.x} raw answer | {a.y} raw answer | gold |\n|---|---|---|---|---|---|---|---|")
    for q in disc:
        x, y = P[(a.x, q)], P[(a.y, q)]
        o.append(f"| {q} | {a.x if x['correct'] else a.y} | {y['route']} | {x['rows_returned']} / {y['rows_returned']} | {x['retrieval_hit_passage']} / {y['retrieval_hit_passage']} | `{(x['raw_output'] or '').strip()[:80]}` | `{(y['raw_output'] or '').strip()[:80]}` | {x['gold_answer']} |")
    o.append(f"\n## {a.y} accuracy over all {len(qids)} queries, split by its route and by passage-level gold hit\n")
    o.append("| group | n | correct | accuracy | mean rows returned |\n|---|---|---|---|---|")

    def grp(name, sel):
        rs = [P[(a.y, q)] for q in qids if sel(P[(a.y, q)])]
        if rs:
            o.append(f"| {name} | {len(rs)} | {sum(r['correct'] for r in rs)} | {sum(r['correct'] for r in rs) / len(rs):.2f} | {sum(r['rows_returned'] or 0 for r in rs) / len(rs):.1f} |")
        else:
            o.append(f"| {name} | 0 | - | - | - |")
    for route in ("post-filter", "pre-filter"):
        grp(f"route = {route}", lambda r, route=route: r["route"] == route)
    for h in (1, 0):
        grp(f"gold hit = {h}", lambda r, h=h: r["retrieval_hit_passage"] == h)
    for route in ("post-filter", "pre-filter"):
        for h in (1, 0):
            grp(f"route = {route}, gold hit = {h}", lambda r, route=route, h=h: r["route"] == route and r["retrieval_hit_passage"] == h)
    o.append(f"\nFor comparison, {a.x} on the same queries split by {a.y}'s route:\n\n| group ({a.y} route) | n | {a.x} correct | {a.y} correct |\n|---|---|---|---|")
    for route in ("post-filter", "pre-filter"):
        qs = [q for q in qids if P[(a.y, q)]["route"] == route]
        o.append(f"| {route} | {len(qs)} | {sum(P[(a.x, q)]['correct'] for q in qs)} | {sum(P[(a.y, q)]['correct'] for q in qs)} |")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(o) + "\n", encoding="utf-8")
    print("\n".join(o))


if __name__ == "__main__":
    main()
