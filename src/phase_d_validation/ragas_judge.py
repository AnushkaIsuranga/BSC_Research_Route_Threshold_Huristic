"""Amendment 8: RAGAS 0.4.3 Faithfulness judged by gpt-oss-120b on Vertex AI. Runs ONLY in .venv-ragas:

  .venv-ragas/Scripts/python -I src/phase_d_validation/ragas_judge.py --stage 1 --allow-paid --budget-usd 3 \
      --inputs outputs/ragas_judge_2026-10-23/judge_inputs.jsonl --out-dir outputs/ragas_judge_2026-10-23

Stage 1 judges the 40 labelled rows; stage 2 judges the other 960 (the stage-1 judgments are reused, never re-judged). One attempt
per call (instructor max_retries=1, OpenAI client max_retries=0); a failed, unparseable or truncated call is recorded as
judge_error with its raw output and the run moves on. Rows without context are not sent (scored 0 by the analysis). Cost is
tracked at USD 0.15 / 0.60 per 1M input / output tokens; before each row the run stops if tracked spend + the largest per-row
cost so far would exceed the budget. Stops if 5 or more of the first 20 rows end in judge_error. Telemetry off.
"""

from __future__ import annotations

import os

os.environ["RAGAS_DO_NOT_TRACK"] = "true"            # before ragas is imported

import argparse
import asyncio
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MODEL = "openai/gpt-oss-120b-maas"
PROJECT, LOCATION = "bsc-research-project-511410", "us-central1"
BASE_URL = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}/endpoints/openapi"
PRICE_IN, PRICE_OUT = 0.15e-6, 0.60e-6
SETTINGS = {"temperature": 0.0, "max_tokens": 4096, "max_retries": 1}
TIMEOUT_S = 180
TOKEN_REFRESH_S = 1800
EARLY_ROWS, EARLY_MAX_ERRORS = 20, 5
CONCURRENCY = 4


def row_key(r: dict) -> str:
    return f"{r['pass']}|{r['arm']}|{r['query_id']}"


class Budget:
    def __init__(self, cap: float, spent: float = 0.0):
        self.cap, self.spent, self.max_row = cap, spent, 0.0

    def can_start_row(self) -> bool:
        return self.spent + CONCURRENCY * self.max_row <= self.cap      # up to CONCURRENCY rows in flight

    def add_row(self, cost: float) -> None:
        self.spent += cost
        self.max_row = max(self.max_row, cost)


def access_token() -> str:
    gcloud = "gcloud.cmd" if sys.platform == "win32" else "gcloud"
    return subprocess.run([gcloud, "auth", "application-default", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()


def make_llm(client_factory, log_call):
    """Wrap the client's create so every call is logged (usage, finish reason, raw content, error), then build the RAGAS LLM."""
    from ragas.llms import llm_factory
    client = client_factory()
    orig = client.chat.completions.create

    async def logged(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            resp = await orig(*args, **kwargs)
        except Exception as exc:
            log_call({"error": f"{type(exc).__name__}: {exc}", "latency_s": time.perf_counter() - t0})
            raise
        u = resp.usage
        details = getattr(u, "completion_tokens_details", None) if u else None
        log_call({"input_tokens": u.prompt_tokens if u else None, "output_tokens": u.completion_tokens if u else None,
                  "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
                  "finish_reason": resp.choices[0].finish_reason if resp.choices else None,
                  "content": resp.choices[0].message.content if resp.choices else None, "latency_s": time.perf_counter() - t0,
                  "error": None})
        return resp
    client.chat.completions.create = logged
    return llm_factory(MODEL, provider="openai", client=client, **SETTINGS)


async def judge_row(metric_factory, r: dict, calls_fh, calls_lock) -> dict:
    calls: list[dict] = []

    def log_call(c: dict) -> None:
        step = "statements" if not calls else "verdicts"
        c = {"row": row_key(r), "step": step, "utc": datetime.now(timezone.utc).isoformat(), **c}
        c["cost_usd"] = (c.get("input_tokens") or 0) * PRICE_IN + (c.get("output_tokens") or 0) * PRICE_OUT
        calls.append(c)

    metric = metric_factory(log_call)
    status, score, err = "ok", None, None
    try:
        res = await metric.ascore(user_input=r["user_input"], response=r["response"], retrieved_contexts=r["retrieved_contexts"])
        score = res.value
        if score is None or (isinstance(score, float) and math.isnan(score)):
            status, score = "no_statements", None
    except Exception as exc:
        status, err = "judge_error", f"{type(exc).__name__}: {exc}"[:2000]
    if status == "ok" and any(c.get("finish_reason") == "length" for c in calls):
        status, err = "judge_error", "truncated (finish_reason=length)"
    async with calls_lock:
        for c in calls:
            calls_fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        calls_fh.flush()
    return {"row": row_key(r), "pass": r["pass"], "arm": r["arm"], "query_id": r["query_id"], "sample_id": r["sample_id"],
            "label_scn": r["label_scn"], "status": status, "faithfulness": score, "error": err, "n_calls": len(calls),
            "cost_usd": sum(c["cost_usd"] for c in calls), "input_tokens": sum(c.get("input_tokens") or 0 for c in calls),
            "output_tokens": sum(c.get("output_tokens") or 0 for c in calls)}


async def run(rows: list[dict], out: Path, stage: int, budget: Budget, metric_factory_builder) -> dict:
    out_rows = out / f"judged_stage{stage}.jsonl"
    if out_rows.exists():
        raise SystemExit(f"{out_rows} exists; refusing to overwrite")
    lock, sem = asyncio.Lock(), asyncio.Semaphore(CONCURRENCY)
    state = {"done": 0, "errors_early": 0, "stopped": None, "t_token": 0.0, "factory": None}
    results: list[dict] = []

    def factory():
        if state["factory"] is None or time.time() - state["t_token"] > TOKEN_REFRESH_S:
            state["factory"], state["t_token"] = metric_factory_builder(), time.time()
        return state["factory"]

    with (out / f"judge_calls_stage{stage}.jsonl").open("w", encoding="utf-8") as calls_fh, out_rows.open("w", encoding="utf-8") as rows_fh:
        async def one(r):
            async with sem:
                if state["stopped"]:
                    return
                if not budget.can_start_row():
                    state["stopped"] = f"budget: spent {budget.spent:.4f} + max row {budget.max_row:.4f} > cap {budget.cap}"
                    return
                res = await judge_row(factory(), r, calls_fh, lock)
                async with lock:
                    budget.add_row(res["cost_usd"])
                    results.append(res)
                    rows_fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                    rows_fh.flush()
                    state["done"] += 1
                    if state["done"] <= EARLY_ROWS and res["status"] == "judge_error":
                        state["errors_early"] += 1
                        if state["errors_early"] >= EARLY_MAX_ERRORS:
                            state["stopped"] = f"setup failure: {state['errors_early']} judge errors in the first {EARLY_ROWS} rows"
                    if state["done"] % 50 == 0:
                        print(f"stage {stage}: {state['done']}/{len(rows)} rows, tracked USD {budget.spent:.4f}", flush=True)
        # the first rows run one at a time so a setup failure stops early
        for r in rows[:4]:
            await one(r)
        await asyncio.gather(*(one(r) for r in rows[4:]))
    return {"stage": stage, "rows_requested": len(rows), "rows_judged": len(results), "stopped": state["stopped"],
            "tracked_spend_usd_total": budget.spent, "status_counts": {s: sum(1 for x in results if x["status"] == s) for s in ("ok", "no_statements", "judge_error")}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", type=int, choices=[1, 2], required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--allow-paid", action="store_true")
    a = ap.parse_args()
    if not a.allow_paid:
        raise SystemExit("--allow-paid is required for any judge call")
    if a.budget_usd > 3.0:
        raise SystemExit("budget above the USD 3 cap of Amendment 8")
    import ragas
    if ragas.__version__ != "0.4.3":
        raise SystemExit(f"ragas {ragas.__version__} is not the pinned 0.4.3")
    from openai import AsyncOpenAI
    from ragas.metrics.collections import Faithfulness
    out = Path(a.out_dir)
    rows = [json.loads(l) for l in open(a.inputs, encoding="utf-8")]
    judgeable = [r for r in rows if r["retrieved_contexts"]]
    prior = 0.0
    if a.stage == 1:
        todo = [r for r in judgeable if r["sample_id"]]
        if len(todo) != 40:
            raise SystemExit(f"{len(todo)} labelled rows, expected 40")
    else:
        s1 = out / "judged_stage1.jsonl"
        summ = json.loads((out / "judge_run_stage1.json").read_text(encoding="utf-8"))
        prior = summ["tracked_spend_usd_total"]
        done = {json.loads(l)["row"] for l in open(s1, encoding="utf-8")}
        todo = [r for r in judgeable if row_key(r) not in done]
        if any(r["sample_id"] for r in todo) or len(todo) != len(judgeable) - 40:
            raise SystemExit("stage 2 rows do not equal the judgeable rows minus the 40 stage-1 rows")
    budget = Budget(a.budget_usd, prior)

    def builder():
        token = access_token()

        def metric_factory(log_call):
            llm = make_llm(lambda: AsyncOpenAI(base_url=BASE_URL, api_key=token, max_retries=0, timeout=TIMEOUT_S), log_call)
            return Faithfulness(llm=llm)
        return metric_factory
    t0 = datetime.now(timezone.utc).isoformat()
    summary = asyncio.run(run(todo, out, a.stage, budget, builder))
    summary |= {"started_utc": t0, "ended_utc": datetime.now(timezone.utc).isoformat(), "model": MODEL, "base_url": BASE_URL,
                "settings": SETTINGS | {"top_p": "ragas default 0.1", "client_max_retries": 0, "timeout_s": TIMEOUT_S, "concurrency": CONCURRENCY},
                "price_per_token_tracked": [PRICE_IN, PRICE_OUT], "ragas_version": ragas.__version__, "prior_stage_spend_usd": prior,
                "inputs": a.inputs}
    (out / f"judge_run_stage{a.stage}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
