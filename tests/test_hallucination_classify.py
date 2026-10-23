"""Amendment 5 classifier: synthetic rows only (no model, no API, no DB)."""
import json
import subprocess
import sys

import pytest

from src.phase_d_validation.hallucination_classify import (CLASSES, SAMPLE_SEED, build_label_sample, classify_row, classify_run,
                                                           counts_table, paired_comparison, route_split, rows_returned_ungrounded)


def row(correct=0, pf=0, passage=1, strict=1, arm="policy_v2", q="q1", p=1, route="exact", rows=15, raw="5"):
    return {"arm": arm, "query_id": q, "pass": p, "route": route, "rows_returned": rows, "correct": correct, "parse_failure": pf,
            "retrieval_hit": strict, "retrieval_hit_passage": passage, "parsed_answer": None if pf else 1.0, "gold_answer": "9",
            "raw_output": raw, "retrieved_ids": [1, 2, 3], "route_parse_failure": 0}


def test_every_class_in_order():
    assert classify_row(row(correct=1), "retrieval_hit_passage") == "correct"
    assert classify_row(row(correct=0, pf=1), "retrieval_hit_passage") == "abstain_or_parse_fail"
    assert classify_row(row(correct=0, passage=0), "retrieval_hit_passage") == "wrong_ungrounded"
    assert classify_row(row(correct=0, passage=1), "retrieval_hit_passage") == "wrong_grounded"


def test_order_edge_cases():
    # parse failure wins over groundedness, whatever the hit value
    assert classify_row(row(correct=0, pf=1, passage=1), "retrieval_hit_passage") == "abstain_or_parse_fail"
    assert classify_row(row(correct=0, pf=1, passage=0), "retrieval_hit_passage") == "abstain_or_parse_fail"
    # correct wins over everything
    assert classify_row(row(correct=1, pf=1, passage=0), "retrieval_hit_passage") == "correct"


def test_correct_ungrounded_is_reported_but_not_a_class():
    cl = classify_run([row(correct=1, passage=0), row(correct=1, passage=1, q="q2")], "retrieval_hit_passage")
    assert [r["class"] for r in cl] == ["correct", "correct"] and [r["correct_ungrounded"] for r in cl] == [1, 0]
    t = {(r["class"]): r for r in counts_table(cl) if r["pass"] == "all"}
    assert t["correct_ungrounded (subset of correct)"]["n"] == 1 and t["correct"]["n"] == 2


@pytest.mark.parametrize("field", ["correct", "parse_failure", "retrieval_hit_passage"])
def test_null_or_missing_field_stops(field):
    r = row()
    r[field] = None
    with pytest.raises(ValueError, match=field):
        classify_row(r, "retrieval_hit_passage")
    r2 = row()
    del r2[field]
    with pytest.raises(ValueError, match=field):
        classify_row(r2, "retrieval_hit_passage")


def test_null_strict_field_stops_even_when_passage_field_exists():
    with pytest.raises(ValueError, match="retrieval_hit"):
        classify_run([row(strict=None)], "retrieval_hit_passage")


def test_grounding_field_choice_and_strict_sensitivity():
    r = row(correct=0, passage=1, strict=0)           # gold text in the prompt but under another page id
    assert classify_row(r, "retrieval_hit_passage") == "wrong_grounded"
    assert classify_row(r, "retrieval_hit") == "wrong_ungrounded"
    cl = classify_run([r], "retrieval_hit_passage")[0]
    assert cl["class"] == "wrong_grounded" and cl["strict_class"] == "wrong_ungrounded" and cl["grounding_field"] == "retrieval_hit_passage"
    base = classify_run([r], "retrieval_hit")[0]            # 12 Oct baseline style: strict field is the grounding field
    assert base["class"] == base["strict_class"] == "wrong_ungrounded"


def test_naive_router_schema_failure_row_stops_with_explanation():
    r = row()
    r.update({"retrieval_hit": None, "retrieval_hit_passage": None, "route_parse_failure": 1, "correct": 0, "parse_failure": 0})
    with pytest.raises(ValueError, match="schema failure"):
        classify_row(r, "retrieval_hit_passage")


def test_counts_wilson_and_pooling():
    rows = [row(correct=1, q=f"q{i}", p=p) for i in range(5) for p in (1, 2)] + [row(correct=0, passage=0, q=f"u{i}", p=p) for i in range(3) for p in (1, 2)]
    t = {(r["pass"], r["class"]): r for r in counts_table(classify_run(rows, "retrieval_hit_passage"))}
    assert t[(1, "correct")]["n"] == 5 and t[(1, "correct")]["of"] == 8 and t[(2, "wrong_ungrounded")]["n"] == 3
    assert t[("all", "correct")]["n"] == 10 and t[("all", "correct")]["of"] == 16
    lo, hi = t[("all", "correct")]["ci95"]
    assert lo < 10 / 16 < hi and 0 <= lo and hi <= 1
    assert sum(t[("all", k)]["n"] for k in CLASSES) == 16


def _paired_rows(spec):
    """spec: {(arm, query, pass): (correct, pf, passage)}"""
    return [row(correct=c, pf=pf, passage=g, arm=a, q=q, p=p) for (a, q, p), (c, pf, g) in spec.items()]


def test_paired_comparison_discordant_counts_and_pooled_bootstrap():
    spec = {}
    for q in range(6):
        for p in (1, 2, 3):
            spec[("policy_v2", f"q{q}", p)] = (1, 0, 1)                                   # always correct
            # naive: q0, q1 wrong_ungrounded in every pass; q2 wrong_grounded; rest correct
            spec[("naive_llm", f"q{q}", p)] = (0, 0, 0) if q < 2 else (0, 0, 1) if q == 2 else (1, 0, 1)
    res = paired_comparison(classify_run(_paired_rows(spec), "retrieval_hit_passage"))
    wu = res["classes"]["wrong_ungrounded"]
    assert (wu["pass1"]["b_x_only"], wu["pass1"]["c_y_only"]) == (0, 2) and wu["pass1"]["mcnemar_exact_p"] == pytest.approx(0.5)
    assert wu["pooled"]["mean_rate_y"] == pytest.approx(2 / 6) and wu["pooled"]["diff_x_minus_y"] == pytest.approx(-2 / 6)
    lo, hi = wu["pooled"]["ci95"]
    assert lo <= wu["pooled"]["diff_x_minus_y"] <= hi
    assert res["classes"]["wrong_grounded"]["pass1"]["c_y_only"] == 1
    assert res["classes"]["abstain_or_parse_fail"]["pass1"]["c_y_only"] == 0


def test_paired_comparison_refuses_missing_rows():
    spec = {(a, "q", p): (1, 0, 1) for a in ("policy_v2", "naive_llm") for p in (1, 2)}
    del spec[("naive_llm", "q", 2)]
    with pytest.raises(ValueError, match="missing"):
        paired_comparison(classify_run(_paired_rows(spec), "retrieval_hit_passage"))


def test_route_split_and_zero_row_counts():
    rows = [row(arm="naive_llm", route="post-filter", rows=0, passage=0, q="a"), row(arm="naive_llm", route="post-filter", rows=4, passage=1, q="b"),
            row(arm="naive_llm", route="pre-filter", rows=15, passage=1, q="c"), row(arm="naive_llm", route="pre-filter", rows=15, correct=1, q="d"),
            row(arm="naive_llm", route="post-filter", rows=7, passage=0, q="e")]
    cl = classify_run(rows, "retrieval_hit_passage")
    s = {(r["scope"], r["route"]): r for r in route_split(cl, "naive_llm")}
    assert s[("pass1", "post-filter")]["n"] == 3 and s[("pass1", "post-filter")]["wrong_ungrounded"] == 2
    assert s[("pass1", "post-filter")]["mean_rows_returned"] == pytest.approx((0 + 4 + 7) / 3)
    assert s[("pass1", "pre-filter")]["correct"] == 1 and s[("pass1", "pre-filter")]["wrong_grounded"] == 1
    rr = rows_returned_ungrounded(cl)[0]
    assert rr["n_wrong_ungrounded"] == 2 and rr["zero_row_cases"] == 1 and rr["rows_0"] == 1 and rr["rows_4-7"] == 1


def _pool():
    rows = []
    for i in range(30):
        rows.append(row(arm="naive_llm" if i % 2 else "policy_v2", q=f"u{i:02d}", passage=0, raw=f"ans-u{i}"))
    for i in range(25):
        rows.append(row(arm="policy_v2", q=f"g{i:02d}", passage=1, raw=f"ans-g{i}"))
    rows.append(row(correct=1, q="c1"))
    rows.append(row(correct=0, pf=1, q="a1"))
    return rows


def test_label_sample_is_blind_deterministic_and_capped():
    rows = _pool()
    cl = classify_run(rows, "retrieval_hit_passage")
    texts = lambda ids: [f"passage {i}" for i in ids]
    sheet, key = build_label_sample(cl, rows, texts, lambda q: f"question of {q}")
    assert len(sheet) == len(key) == 40
    assert {k["proxy_class"] for k in key} == {"wrong_ungrounded", "wrong_grounded"}
    assert sum(1 for k in key if k["proxy_class"] == "wrong_ungrounded") == 20 and sum(1 for k in key if k["proxy_class"] == "wrong_grounded") == 20
    assert set(sheet[0]) == {"sample_id", "question", "gold_answer", "model_answer", "retrieved_passages"}   # no class / arm / route
    blob = json.dumps(sheet).lower()
    assert "wrong_" not in blob and "policy_v2" not in blob and "naive_llm" not in blob and "post-filter" not in blob
    assert sheet[0]["retrieved_passages"].startswith("[1] passage 1")
    assert [s["sample_id"] for s in sheet] == [f"S{i:03d}" for i in range(1, 41)] and all(s["sample_id"] == k["sample_id"] for s, k in zip(sheet, key))
    sheet2, key2 = build_label_sample(cl, rows, texts, lambda q: f"question of {q}")
    assert sheet == sheet2 and key == key2                                   # same seed -> same sample and order
    sheet3, key3 = build_label_sample(cl, rows, texts, lambda q: f"question of {q}", seed=1)
    assert key3 != key and SAMPLE_SEED == 20261023
    shuffled = [k["proxy_class"] for k in key]
    assert shuffled != sorted(shuffled)                                      # rows are shuffled, not grouped by class


def test_label_sample_takes_all_when_fewer_than_20():
    rows = [row(q="u1", passage=0), row(q="u2", passage=0), row(q="g1", passage=1)]
    cl = classify_run(rows, "retrieval_hit_passage")
    sheet, key = build_label_sample(cl, rows, lambda ids: ["t"], lambda q: q)
    assert len(sheet) == 3 and sorted(k["proxy_class"] for k in key) == ["wrong_grounded", "wrong_ungrounded", "wrong_ungrounded"]


def test_label_sample_uses_pass_1_only():
    rows = [row(q="a", p=1, passage=0), row(q="a", p=2, passage=0), row(q="b", p=2, passage=1)]
    cl = classify_run(rows, "retrieval_hit_passage")
    sheet, key = build_label_sample(cl, rows, lambda ids: ["t"], lambda q: q)
    assert [(k["query_id"], k["pass"]) for k in key] == [("a", 1)]


def test_cli_requires_explicit_hit_field_and_stops_on_null(tmp_path):
    f = tmp_path / "r.jsonl"
    good = [row(arm=a, q=f"q{i}") for a in ("policy_v2", "naive_llm") for i in range(3)]
    f.write_text("\n".join(json.dumps(r) for r in good))
    base = [sys.executable, "-m", "src.phase_d_validation.hallucination_classify", str(f), "--label", "t", "--out-dir", str(tmp_path / "o")]
    assert subprocess.run(base, capture_output=True).returncode == 2                               # --hit-field is required
    ok = subprocess.run(base + ["--hit-field", "retrieval_hit_passage"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert (tmp_path / "o" / "classified_rows_t.csv").exists() and (tmp_path / "o" / "summary_t.json").exists()
    bad = [dict(r) for r in good]
    bad[2]["retrieval_hit_passage"] = None
    f.write_text("\n".join(json.dumps(r) for r in bad))
    r = subprocess.run(base[:-1] + [str(tmp_path / "o2"), "--hit-field", "retrieval_hit_passage"], capture_output=True, text=True)
    assert r.returncode != 0 and "retrieval_hit_passage" in r.stderr and "stopping" in r.stderr
