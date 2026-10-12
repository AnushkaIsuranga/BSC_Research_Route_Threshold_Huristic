"""Embedding helpers for the FinQA embedding comparison (retrieval only; no chat/answer LLM).

* OpenRouterEmbedder: Qwen3-Embedding-8B through OpenRouter's /embeddings endpoint. The API key is read from the
  environment (OPENROUTER_API_KEY, loaded from the git-ignored .env by src.db_settings); it is never printed, logged or
  written. Every HTTP call is appended to an api-call log (timestamp, model, n inputs, tokens from the response usage
  field, cost = tokens x the model price listed by OpenRouter, status, latency) and a cumulative cost cap aborts the run.
* OllamaEmbedder: local nomic-embed-text through Ollama /api/embed (free).
* Qwen3 conventions (model card): documents get no prefix; queries use
  "Instruct: {task}\nQuery: {question}". Nomic conventions: "search_document: " for evidence, "search_query: " for questions.
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import src  # noqa: F401  (src.db_settings() loads .env into os.environ)
from src import db_settings

QWEN3_TASK = "Given a financial question, retrieve the report passages and table rows that answer it"
NOMIC_DOC_PREFIX, NOMIC_QUERY_PREFIX = "search_document: ", "search_query: "


def qwen3_query(question: str) -> str:
    return f"Instruct: {QWEN3_TASK}\nQuery: {question}"


class CostCapExceeded(RuntimeError):
    pass


class OpenRouterEmbedder:
    def __init__(self, model: str, log_path: Path, cost_cap_usd: float = 1.0, dimensions: int | None = None):
        db_settings()  # loads .env into os.environ
        self.key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in the environment / .env")
        self.base = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1").rstrip("/")
        self.model, self.cap, self.dimensions = model, cost_cap_usd, dimensions
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.spent, self.tokens = 0.0, 0
        self.price_per_token = self._price()

    def _price(self) -> float:
        r = requests.get(f"{self.base}/embeddings/models", timeout=30)
        r.raise_for_status()
        for m in r.json()["data"]:
            if m["id"] == self.model:
                return float(m["pricing"]["prompt"])
        raise RuntimeError(f"model {self.model} not listed by OpenRouter")

    def embed(self, texts: list[str], purpose: str) -> list[list[float]]:
        # Pre-call guard: worst-case tokens ~ chars/2 (conservative) must still fit under the cap.
        worst = sum(len(t) for t in texts) / 2 * self.price_per_token
        if self.spent + worst > self.cap:
            raise CostCapExceeded(f"next call could cost up to ${worst:.4f}; spent ${self.spent:.4f} of ${self.cap:.2f}")
        body = {"model": self.model, "input": texts, "encoding_format": "float"}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        t0 = time.perf_counter()
        r = requests.post(f"{self.base}/embeddings", json=body, headers={"Authorization": f"Bearer {self.key}"}, timeout=300)
        ms = (time.perf_counter() - t0) * 1000
        rec = {"utc": datetime.now(timezone.utc).isoformat(), "model": self.model, "purpose": purpose, "n_inputs": len(texts),
               "requested_dimensions": self.dimensions, "status": r.status_code, "latency_ms": round(ms, 1)}
        if r.status_code >= 400:
            rec["error"] = r.text[:300]
            self._log(rec)
            raise RuntimeError(f"OpenRouter embeddings HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        tok = d["usage"]["prompt_tokens"] if d.get("usage") else None
        if tok is None:
            self._log({**rec, "error": "no usage in response"})
            raise RuntimeError("OpenRouter response has no usage field; cannot compute cost")
        cost = tok * self.price_per_token
        self.spent += cost
        self.tokens += tok
        vecs = [x["embedding"] for x in sorted(d["data"], key=lambda x: x["index"])]
        rec.update({"prompt_tokens": tok, "cost_usd": cost, "cumulative_cost_usd": self.spent, "cumulative_tokens": self.tokens,
                    "returned_dimension": len(vecs[0]) if vecs else None, "provider": d.get("provider")})
        self._log(rec)
        return vecs

    def _log(self, rec: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def truncate_normalise(vec: list[float], dim: int) -> list[float]:
    v = vec[:dim]
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        raise ValueError("zero vector after truncation")
    return [x / n for x in v]


def ollama_embed(model: str, texts: list[str], base: str = "http://127.0.0.1:11434") -> list[list[float]]:
    r = requests.post(f"{base}/api/embed", json={"model": model, "input": texts}, timeout=600)
    r.raise_for_status()
    return r.json()["embeddings"]
