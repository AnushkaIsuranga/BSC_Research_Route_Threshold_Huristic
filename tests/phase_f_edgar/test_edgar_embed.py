"""Phase F embedding step: batch validation and retry (no network, no database)."""

import json

import numpy as np
import pytest

from src.phase_d_validation.embedding_tools import CostCapExceeded
from src.phase_f_edgar import embed as E
from src.phase_f_edgar.common import EMBED_DIM


def unit(i=0):
    v = np.zeros(EMBED_DIM)
    v[i] = 1.0
    return v.tolist()


def test_validate_rejects_bad_batches():
    assert len(E.validate([unit(), unit(1)], 2)) == 2
    with pytest.raises(E.InvalidBatch):
        E.validate([unit()], 2)
    with pytest.raises(E.InvalidBatch):
        E.validate([[1.0] * (EMBED_DIM - 1)], 1)
    with pytest.raises(E.InvalidBatch):
        E.validate([[0.0] * EMBED_DIM], 1)
    with pytest.raises(E.InvalidBatch):
        E.validate([[float("nan")] + [0.0] * (EMBED_DIM - 1)], 1)


class FlakyClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0

    def embed(self, texts, purpose):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_retry_then_success_with_backoff():
    c = FlakyClient([RuntimeError("HTTP 502"), [[0.0] * EMBED_DIM], [unit()]])
    logged, slept = [], []
    out = E.embed_with_retry(c, ["a"], "t", logged.append, sleep=slept.append)
    assert c.calls == 3 and len(out) == 1
    assert slept == [E.BACKOFF_S, 2 * E.BACKOFF_S]
    assert [x["attempt"] for x in logged] == [1, 2]


def test_retry_gives_up_and_raises():
    c = FlakyClient([RuntimeError("x")] * E.ATTEMPTS)
    with pytest.raises(RuntimeError):
        E.embed_with_retry(c, ["a"], "t", lambda r: None, sleep=lambda s: None)
    assert c.calls == E.ATTEMPTS


def test_cost_cap_is_not_retried():
    c = FlakyClient([CostCapExceeded("cap")])
    with pytest.raises(CostCapExceeded):
        E.embed_with_retry(c, ["a"], "t", lambda r: None, sleep=lambda s: None)
    assert c.calls == 1


def test_spent_so_far_sums_api_log(tmp_path):
    p = tmp_path / "api_calls.jsonl"
    assert E.spent_so_far(p) == (0.0, 0)
    p.write_text("\n".join(json.dumps(r) for r in [{"cost_usd": 0.1, "prompt_tokens": 10}, {"status": 500, "error": "x"},
                                                    {"cost_usd": 0.2, "prompt_tokens": 20}]) + "\n", encoding="utf-8")
    cost, tok = E.spent_so_far(p)
    assert abs(cost - 0.3) < 1e-12 and tok == 30


def test_shards_partition_hashes():
    from src.phase_f_edgar.common import text_hash
    hs = [text_hash(str(i)) for i in range(400)]
    owners = [[k for k in range(4) if E.in_shard(h, k, 4)] for h in hs]
    assert all(len(o) == 1 for o in owners)
    assert all(E.in_shard(h, 0, 1) for h in hs)
