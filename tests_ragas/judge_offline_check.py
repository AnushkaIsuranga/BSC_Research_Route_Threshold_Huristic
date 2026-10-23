# Offline check of src/phase_d_validation/ragas_judge.py (no network). Run in .venv-ragas only:
#   .venv-ragas/Scripts/python -I tests_ragas/judge_offline_check.py src/phase_d_validation
import asyncio, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import ragas_judge as J
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

def completion(content, finish="stop"):
    return ChatCompletion.model_validate({"id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}})

def scripted(replies):
    it = iter(replies)
    def client():
        c = AsyncOpenAI(base_url="http://invalid.local", api_key="x", max_retries=0)
        async def fake(*a, **k):
            r = next(it)
            if isinstance(r, Exception): raise r
            return completion(*r) if isinstance(r, tuple) else completion(r)
        c.chat.completions.create = fake
        return c
    return client

rows = [{"pass": 1, "arm": "policy_v2", "query_id": f"Q{i}", "sample_id": f"S{i}", "label_scn": "C", "user_input": "what is x?",
         "response": "5", "retrieved_contexts": ["[a::b] x is 5"]} for i in range(3)]
stm = json.dumps({"statements": ["x is 5."]})
ok = json.dumps({"statements": [{"statement": "x is 5.", "reason": "stated", "verdict": 1}]})
replies = [stm, ok, "not json at all", stm, (ok, "length")]
cf = scripted(replies)
def builder():
    def mf(log_call):
        from ragas.metrics.collections import Faithfulness
        return Faithfulness(llm=J.make_llm(cf, log_call))
    return mf
out = Path(tempfile.mkdtemp())
s = asyncio.run(J.run(rows, out, 1, J.Budget(3.0), builder))
res = [json.loads(l) for l in open(out / "judged_stage1.jsonl")]
calls = [json.loads(l) for l in open(out / "judge_calls_stage1.jsonl")]
print(s); print([(r["row"], r["status"], r["faithfulness"], r["n_calls"], round(r["cost_usd"], 6), (r["error"] or "")[:60]) for r in res]); print(len(calls))
assert [r["status"] for r in res] == ["ok", "judge_error", "judge_error"] and res[0]["faithfulness"] == 1.0
assert res[1]["n_calls"] == 1 and len(calls) == 5          # unparseable output: one call, no retry
b = J.Budget(0.001); b.add_row(0.0005); assert not b.can_start_row()
print("OFFLINE OK")
