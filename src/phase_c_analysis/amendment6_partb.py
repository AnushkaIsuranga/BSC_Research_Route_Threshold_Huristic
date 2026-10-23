"""Amendment 6 Part B (offline): published routing rules B1-B4b re-implemented on the existing per-query H&M measurements.

  .venv/Scripts/python -m src.phase_c_analysis.amendment6_partb --out-dir outputs/phase_a_amendment6_2026-10-23

Read-only; no database access. Each rule picks a route per query from the filter's exact selectivity; the outcome is the measured
recall@10 and latency of that route for that (table, filter, vector). Cell pass = mean recall@10 >= 0.90 over all 20 vectors and
median of the per-vector median latencies <= 500 ms (as the held-out protocols). A needed route missing for a vector makes the cell
"not scored" for that rule (no substitute). B4/B4b: scikit-learn MLPClassifier (64, 32), ReLU, Adam lr 1e-3, alpha 1e-4, batch 200,
max 500 epochs, early stopping (validation fraction 0.1, patience 10), seed 20261023; feature = z-scored selectivity; trained on the
1,300 in-sample queries only.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

EXACT, ITER = "forced-exact", "iterative-relaxed"
N_ROWS = 105_100
DIMS = 2048
B3_ROWS = 10000 / (DIMS / 256)          # 1,250 rows
SEED = 20261023
RECALL_SLA, LATENCY_SLA_MS, N_VECTORS = 0.90, 500.0, 20
SETS = {"in-sample": "outputs/phase_a_arms/results.jsonl",
        "held-out 1": "outputs/phase_a_holdout/results.jsonl",
        "held-out 2": "outputs/phase_a_holdout2/results.jsonl",
        "held-out 1 quiet rerun (sensitivity)": "outputs/phase_a_holdout_rerun/results.jsonl"}


def load(path: str) -> dict:
    """{(table, filter_id): {"s": s, "rows": matched rows, "q": {vector_idx: {arm: (recall, latency_ms)}}}}; errors raise."""
    cells: dict = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if r["arm"] not in (EXACT, ITER):
            continue
        if r.get("error") or r.get("recall_error") or r.get("plan_as_intended") is False:
            raise SystemExit(f"{path}: invalid row {r['table']} {r['filter_id']} v{r['vector_idx']} {r['arm']}")
        c = cells.setdefault((r["table"], r["filter_id"]), {"s": r["selectivity"], "q": defaultdict(dict)})
        if abs(c["s"] - r["selectivity"]) > 1e-12:
            raise SystemExit(f"{path}: selectivity differs within cell {r['table']} {r['filter_id']}")
        if r["arm"] in c["q"][r["vector_idx"]]:
            raise SystemExit(f"{path}: duplicate row {r['table']} {r['filter_id']} v{r['vector_idx']} {r['arm']}")
        c["q"][r["vector_idx"]][r["arm"]] = (float(r["recall"]), float(r["latency_ms"]))
    for c in cells.values():
        c["rows"] = round(c["s"] * N_ROWS)
    return cells


def threshold_rules() -> dict:
    return {"policy_v2": lambda s, n: EXACT if s < 0.1 else ITER,
            "B1 VBASE (s < 0.18)": lambda s, n: EXACT if s < 0.18 else ITER,
            "B2 Milvus via NaviX (s <= 0.05)": lambda s, n: EXACT if s <= 0.05 else ITER,
            "B3 Qdrant (rows < 1,250)": lambda s, n: EXACT if n < B3_ROWS else ITER}


def labels(cells: dict, kind: str) -> tuple[list, list]:
    X, y = [], []
    for c in cells.values():
        for v, m in sorted(c["q"].items()):
            (re, le), (ri, li) = m[EXACT], m[ITER]
            if kind == "ratio":                       # Gan & Wang: higher recall / latency; tie -> exact
                lab = EXACT if re / le >= ri / li else ITER
            else:                                     # SLA: faster plan with recall >= 0.9, else exact
                ok = [(l, a) for a, r, l in ((EXACT, re, le), (ITER, ri, li)) if r >= RECALL_SLA - 1e-12]
                lab = min(ok, key=lambda t: (t[0], t[1] != EXACT))[1] if ok else EXACT
            X.append(c["s"])
            y.append(lab)
    return X, y


def fit_mlp(X: list, y: list):
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    counts = Counter(y)
    if len(counts) < 2:
        return None, dict(counts)
    m = make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 32), activation="relu", solver="adam", learning_rate_init=1e-3,
                                                      alpha=1e-4, batch_size=200, max_iter=500, early_stopping=True, validation_fraction=0.1,
                                                      n_iter_no_change=10, random_state=SEED))
    m.fit(np.array(X).reshape(-1, 1), np.array(y))
    return m, dict(counts)


def boundary(model) -> list:
    """Selectivities on a fine log grid where the predicted route changes."""
    grid = np.unique(np.concatenate([np.logspace(-5, 0, 4001), np.linspace(0, 1, 2001)]))
    p = model.predict(grid.reshape(-1, 1))
    return [{"between": [float(grid[i - 1]), float(grid[i])], "from": p[i - 1], "to": p[i]} for i in range(1, len(grid)) if p[i] != p[i - 1]]


def score(cells: dict, rule) -> list[dict]:
    out = []
    for (t, f), c in sorted(cells.items()):
        routes = {v: rule(c["s"], c["rows"]) if not callable(getattr(rule, "predict", None)) else None for v in c["q"]}
        if hasattr(rule, "predict"):
            pred = rule.predict(np.array([[c["s"]]] * len(c["q"])))
            routes = dict(zip(sorted(c["q"]), pred))
        missing = [v for v, a in routes.items() if a not in c["q"][v]]
        row = {"table": t, "filter_id": f, "selectivity": c["s"], "matched_rows": c["rows"], "routes": dict(Counter(routes.values())), "n_vectors": len(c["q"])}
        if missing or len(c["q"]) != N_VECTORS:
            out.append({**row, "status": "not scored", "reason": f"route not measured for vectors {missing}" if missing else f"{len(c['q'])} vectors"})
            continue
        rec = [c["q"][v][routes[v]][0] for v in sorted(c["q"])]
        lat = [c["q"][v][routes[v]][1] for v in sorted(c["q"])]
        mr, ml = statistics.fmean(rec), statistics.median(lat)
        rf, lf = mr < RECALL_SLA - 1e-12, ml > LATENCY_SLA_MS
        out.append({**row, "status": "fail" if rf or lf else "pass", "mean_recall": mr, "median_latency_ms": ml,
                    "reason": "recall and latency" if rf and lf else "recall" if rf else "latency" if lf else ""})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    data = {k: load(p) for k, p in SETS.items()}
    rules = threshold_rules()
    models = {}
    for name, kind in (("B4 Gan & Wang (recall/latency labels)", "ratio"), ("B4b Gan & Wang (SLA labels)", "sla")):
        X, y = labels(data["in-sample"], kind)
        m, counts = fit_mlp(X, y)
        models[name] = {"model": m, "train_label_counts": counts, "n_train": len(y)}
        if m is not None:
            rules[name] = m
            models[name]["boundary"] = boundary(m)
            models[name]["n_iter"] = int(m[-1].n_iter_)
            models[name]["train_accuracy"] = float((m.predict(np.array(X).reshape(-1, 1)) == np.array(y)).mean())
    results = {name: {k: score(cells, r) for k, cells in data.items()} for name, r in rules.items()}
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "partb_cells.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rule", "set", "table", "filter_id", "selectivity", "matched_rows", "routes", "status", "mean_recall", "median_latency_ms", "reason"])
        for name, by in results.items():
            for k, rows in by.items():
                for r in rows:
                    w.writerow([name, k, r["table"], r["filter_id"], r["selectivity"], r["matched_rows"], json.dumps(r["routes"]), r["status"],
                                r.get("mean_recall", ""), r.get("median_latency_ms", ""), r["reason"]])
    summary = {"pass_counts": {name: {k: dict(Counter(r["status"] for r in rows)) | {"cells": len(rows)} for k, rows in by.items()} for name, by in results.items()},
               "models": {n: {k: v for k, v in d.items() if k != "model"} for n, d in models.items()},
               "b3_row_threshold": B3_ROWS, "inputs": SETS}
    (out / "partb_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary["pass_counts"], indent=1))
    print(json.dumps(summary["models"], indent=1, default=str))


if __name__ == "__main__":
    main()
