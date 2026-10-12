"""One LLM interface, several backends.

  ollama           working, local, free.
  vertex_gemini    LOCKED paid backend.
  vertex_claude    LOCKED paid backend (global endpoint).
  vertex_openmaas  LOCKED paid backend (gpt-oss via the OpenAI-compatible MaaS endpoint).

Paid backends refuse to be constructed unless ALL hold: allow_paid=True (the --allow-paid flag),
config/prices.json has verified=true with numeric prices for the model, and a positive budget_usd
cap is set. Cost = tokens from the raw API response usage fields x prices.json (no LangChain
callbacks). Before every call the worst case (estimated input tokens + max output tokens) is added
to the cumulative cost; if that could exceed the cap the run aborts with BudgetExceeded.

Vertex request formats (docs read 2026-10-12; model IDs per the docs model lists):
  Claude   https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude/use-claude
           POST https://LOCATION-aiplatform.googleapis.com/v1/projects/P/locations/LOCATION/publishers/anthropic/models/MODEL:rawPredict
           body {anthropic_version: "vertex-2023-10-16", messages, max_tokens, system}; usage.input_tokens/output_tokens.
           GLOBAL endpoint: host aiplatform.googleapis.com with LOCATION=global. The docs section "Specify the
           global endpoint" could not be retrieved; the URL below follows the regional pattern and the documented
           global MaaS pattern. UNVERIFIED until the paid pilot. The page does not document `temperature`; if the
           API rejects it the call raises (no silent drop) and the setting must be recorded as not allowed.
  Gemini   https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash  (id gemini-3.8-flash)
           https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-5-flash-lite (id gemini-3.5-flash-lite)
           thinking_level LOW/MEDIUM/HIGH (3.8 Flash; MINIMAL not available) and MINIMAL/MEDIUM/HIGH (3.5 Flash-Lite).
           POST https://aiplatform.googleapis.com/v1/projects/P/locations/global/publishers/google/models/ID:generateContent
           usageMetadata.promptTokenCount / candidatesTokenCount / thoughtsTokenCount (field names from the
           generateContent API; not shown on the model pages). UNVERIFIED until the paid pilot.
  gpt-oss  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/call-open-model-apis  (id openai/gpt-oss-120b-maas, region global)
           POST https://aiplatform.googleapis.com/v1/projects/P/locations/global/endpoints/openapi/chat/completions
           usage.prompt_tokens / completion_tokens. `reasoning_effort` is NOT shown in the fetched doc text: unverified.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
PRICES_PATH = ROOT / "config" / "prices.json"
GENERATION_PATH = ROOT / "config" / "generation.json"


class PaidLockError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class LLMCallError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None
    cost_usd: float
    latency_ms: float
    settings_used: dict[str, Any]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


def load_generation_config(path: Path = GENERATION_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class CostGuard:
    """Enforces the paid lock and the budget cap; accumulates cost from raw usage."""

    def __init__(self, price_key: str, allow_paid: bool, budget_usd: float | None, prices_path: Path = PRICES_PATH):
        if not allow_paid:
            raise PaidLockError("paid backend refused: --allow-paid was not passed")
        if budget_usd is None or not budget_usd > 0:
            raise PaidLockError("paid backend refused: --budget-usd cap is not set")
        prices = json.loads(Path(prices_path).read_text(encoding="utf-8"))
        entry = prices.get(price_key)
        if not isinstance(entry, dict) or entry.get("verified") is not True:
            raise PaidLockError(f"paid backend refused: config/prices.json has no verified=true entry for {price_key!r}")
        for k in ("input_usd_per_1m", "output_usd_per_1m"):
            v = entry.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise PaidLockError(f"paid backend refused: {k} for {price_key!r} is not a non-negative number")
        self.in_price, self.out_price = float(entry["input_usd_per_1m"]), float(entry["output_usd_per_1m"])
        self.budget, self.spent = float(budget_usd), 0.0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return input_tokens / 1e6 * self.in_price + output_tokens / 1e6 * self.out_price

    def check_before(self, prompt_chars: int, max_output_tokens: int) -> None:
        worst = self.cost(math.ceil(prompt_chars / 2.5), max_output_tokens)  # conservative: 2.5 chars/token
        if self.spent + worst > self.budget:
            raise BudgetExceeded(f"next call could cost up to ${worst:.4f}; spent ${self.spent:.4f} of ${self.budget:.2f} cap")

    def add(self, cost: float) -> None:
        self.spent += cost


class LLMClient:
    backend = ""
    paid = False
    thinking_billed_separately = False  # Gemini reports thoughtsTokenCount outside candidatesTokenCount

    def __init__(self, name: str, cfg: dict, guard: CostGuard | None = None):
        self.name, self.cfg, self.guard = name, cfg, guard

    @property
    def spent_usd(self) -> float:
        return self.guard.spent if self.guard else 0.0

    def generate(self, system: str, user: str, *, max_output_tokens: int, json_mode: bool = False) -> LLMResponse:
        if self.guard:
            self.guard.check_before(len(system) + len(user), max_output_tokens)
        t0 = time.perf_counter()
        try:
            text, i, o, th, raw, used = self._call(system, user, max_output_tokens, json_mode)
        except Exception as exc:
            raise LLMCallError(f"{self.backend}/{self.name}: {type(exc).__name__}: {exc}") from exc
        ms = (time.perf_counter() - t0) * 1000
        cost = 0.0
        if self.guard:
            if i is None or o is None:
                raise LLMCallError(f"{self.backend}/{self.name}: response has no usage fields; cannot compute cost")
            billed_out = o + ((th or 0) if self.thinking_billed_separately else 0)
            cost = self.guard.cost(i, billed_out)
            self.guard.add(cost)
        return LLMResponse(text, i, o, th, cost, ms, used, raw)

    def _call(self, system, user, max_out, json_mode):
        raise NotImplementedError


class OllamaBackend(LLMClient):
    backend = "ollama"

    def __init__(self, name: str, cfg: dict, base_url: str | None = None, timeout: int = 300):
        super().__init__(name, cfg, None)
        self.base = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout

    def _call(self, system, user, max_out, json_mode):
        options = {"temperature": self.cfg["temperature"], "seed": self.cfg["seed"], "num_ctx": self.cfg["num_ctx"],
                   "num_predict": max_out}
        payload: dict[str, Any] = {"model": self.name, "stream": False, "options": options,
                                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            payload["format"] = "json"
        r = requests.post(f"{self.base}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        used = {"temperature": options["temperature"], "temperature_applied": True, "seed": options["seed"],
                "num_ctx": options["num_ctx"], "max_output_tokens": max_out, "thinking": self.cfg["thinking"]}
        return d["message"]["content"], d.get("prompt_eval_count"), d.get("eval_count"), 0, d, used


class _VertexBase(LLMClient):
    paid = True

    def __init__(self, name, cfg, guard, project: str | None = None, session=None):
        super().__init__(name, cfg, guard)
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project:
            raise PaidLockError("GOOGLE_CLOUD_PROJECT is not set")
        self.session = session or requests

    def _token(self) -> str:
        import google.auth
        import google.auth.transport.requests as gr
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(gr.Request())
        return creds.token

    def _post(self, url, body):
        r = self.session.post(url, json=body, headers={"Authorization": f"Bearer {self._token()}"}, timeout=300)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    def _used(self, max_out):
        return {"temperature": self.cfg["temperature"], "temperature_applied": True, "max_output_tokens": max_out,
                "thinking": self.cfg["thinking"], "endpoint": "global"}


class VertexClaudeBackend(_VertexBase):
    backend = "vertex_claude"

    def _call(self, system, user, max_out, json_mode):
        url = (f"https://aiplatform.googleapis.com/v1/projects/{self.project}/locations/global/"
               f"publishers/anthropic/models/{self.cfg['model_id']}:rawPredict")
        body = {"anthropic_version": "vertex-2023-10-16", "max_tokens": max_out, "system": system,
                "messages": [{"role": "user", "content": user}], "temperature": self.cfg["temperature"]}
        d = self._post(url, body)
        u = d.get("usage", {})
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        return text, u.get("input_tokens"), u.get("output_tokens"), 0, d, self._used(max_out)


class VertexGeminiBackend(_VertexBase):
    backend = "vertex_gemini"
    thinking_billed_separately = True

    def _call(self, system, user, max_out, json_mode):
        url = (f"https://aiplatform.googleapis.com/v1/projects/{self.project}/locations/global/"
               f"publishers/google/models/{self.cfg['model_id']}:generateContent")
        gen = {"temperature": self.cfg["temperature"], "maxOutputTokens": max_out,
               "thinkingConfig": {"thinkingLevel": self.cfg["thinking"]["thinking_level"]}}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen}
        d = self._post(url, body)
        u = d.get("usageMetadata", {})
        parts = d["candidates"][0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return text, u.get("promptTokenCount"), u.get("candidatesTokenCount"), u.get("thoughtsTokenCount", 0), d, self._used(max_out)


class VertexOpenMaaSBackend(_VertexBase):
    backend = "vertex_openmaas"

    def _call(self, system, user, max_out, json_mode):
        url = f"https://aiplatform.googleapis.com/v1/projects/{self.project}/locations/global/endpoints/openapi/chat/completions"
        body = {"model": self.cfg["model_id"], "stream": False, "max_tokens": max_out, "temperature": self.cfg["temperature"],
                "reasoning_effort": self.cfg["thinking"]["reasoning_effort"],
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        d = self._post(url, body)
        u = d.get("usage", {})
        return d["choices"][0]["message"]["content"] or "", u.get("prompt_tokens"), u.get("completion_tokens"), 0, d, self._used(max_out)


def make_client(model: str, *, allow_paid: bool = False, budget_usd: float | None = None, config: dict | None = None,
                prices_path: Path = PRICES_PATH, base_url: str | None = None, project: str | None = None,
                session=None) -> LLMClient:
    cfg = (config or load_generation_config())["models"].get(model)
    if cfg is None:
        raise KeyError(f"model {model!r} not in config/generation.json")
    backend = cfg["backend"]
    if backend == "ollama":
        return OllamaBackend(model, cfg, base_url)
    cls = {"vertex_gemini": VertexGeminiBackend, "vertex_claude": VertexClaudeBackend,
           "vertex_openmaas": VertexOpenMaaSBackend}.get(backend)
    if cls is None:
        raise ValueError(f"unknown backend {backend!r}")
    guard = CostGuard(cfg["price_key"], allow_paid, budget_usd, prices_path)
    return cls(model, cfg, guard, project, session)
