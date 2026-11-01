"""Phase F Task 3 report: decided routes of router (edgar T) and router_hmT (H&M T) over the 160 evaluation pairs.

  python -m src.phase_f_edgar.route_counts_edgar --out outputs/edgar_calibration_2026-11-01/route_counts_160.json

Decision only (policy_v3.1 band decision: stats check, estimate, capped count); nothing is retrieved or timed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from src import PROJECT_ROOT
from src.phase_e_router import policy_v3_1 as V
from src.phase_e_router import retriever as R
from src.phase_f_edgar import session_tools as S
from src.phase_f_edgar.compare_edgar import BREADTHS, TABLE, configs, load_pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg, cfg_hm = configs()
    conn = R.connect()
    R.configure_session(conn, cfg)
    per_pair, counts = [], {"router": Counter(), "router_hmT": Counter()}
    by_breadth = {m: defaultdict(Counter) for m in counts}
    for p in load_pairs():
        rec = {"pair_id": p["pair_id"], "breadth": p["breadth"], "selectivity": float(p["selectivity"])}
        for mode, T in (("router", cfg.T_default), ("router_hmT", cfg_hm.T_default)):
            tr = {}
            route = V.band_decision(conn, TABLE, p["filters"], T, cfg, tr)
            rec[mode] = {"route": route, "band": tr["band"], "s_est": tr.get("s_est"), "count": tr.get("count"),
                         "no_stats": tr[V.SKIP_FIELD]}
            counts[mode][route] += 1
            by_breadth[mode][p["breadth"]][route] += 1
        per_pair.append(rec)
    out = {"T_edgar": cfg.T_default, "T_hm": cfg_hm.T_default, "n_pairs": len(per_pair),
           "routes": {m: dict(c) for m, c in counts.items()},
           "routes_by_breadth": {m: {b: dict(by_breadth[m][b]) for b in BREADTHS} for m in counts},
           "same_route_pairs": sum(1 for r in per_pair if r["router"]["route"] == r["router_hmT"]["route"]),
           "pairs": per_pair}
    S.write_json(PROJECT_ROOT / a.out, out)
    print({k: out[k] for k in ("T_edgar", "T_hm", "routes", "routes_by_breadth", "same_route_pairs")})


if __name__ == "__main__":
    main()
