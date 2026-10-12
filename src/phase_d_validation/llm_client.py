"""One LLM interface, several backends.

  ollama           working, local, free.
  vertex_gemini    LOCKED paid backend (google-genai library, Vertex mode).
  vertex_claude    LOCKED paid backend (global endpoint), not used in the current plan.
  vertex_openmaas  LOCKED paid backend (gpt-oss), not used in the current plan.

Paid backends refuse to be constructed unless ALL hold: allow_paid=True (the --allow-paid flag), config/prices.json has
verified=true with numeric prices for the model (and today is not after its `valid_through` date), and a positive
budget_usd cap is set. Cost = tokens from the raw API response usage fields x prices.json (no LangChain callbacks).
Before every call the worst case (estimated input tokens + max output tokens) is added to the cumulative cost; if that
could exceed the cap the run aborts with BudgetExceeded. Every response records finish_reason; a truncated answer
(finish_reason MAX_TOKENS / length) is scored as given, never retried.

Gemini  google-genai library (Vertex mode: genai.Client(vertexai=True, project=..., location="global"), Application Default
        Credentials, no API key; GOOGLE_API_KEY / GEMINI_API_KEY set in the environment makes construction refuse).
        Model gemini-3.8-flash, https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash :
        "The supported values for 3.8 Flash are LOW, MEDIUM (default), and HIGH"; MINIMAL is not available (API
        validation error). google-genai 2.29.0 ThinkingConfig fields: include_thoughts, thinking_budget, thinking_level
        (enum THINKING_LEVEL_UNSPECIFIED, MINIMAL, LOW, MEDIUM, HIGH); only thinking_level is sent.
        Usage fields VERIFIED by a real Vertex call on 2026-10-12 (gemini-3.8-flash, global, traffic_type ON_DEMAND):
        prompt_token_count, candidates_token_count, thoughts_token_count, cached_content_token_count, total_token_count
        (total = prompt + candidates + thoughts: 7 + 1 + 44 = 52).
        Cost = (prompt - cached) x input price + (candidates + thoughts) x output price; thinking tokens are billed at the
        output rate.
Claude  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude/use-claude (global endpoint URL
        unverified; temperature not documented there).
gpt-oss https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/call-open-model-apis (model openai/gpt-oss-120b-maas,
        global; `reasoning_effort` unverified).
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
PRICES_PATH = ROOT / "config" / "prices.json"
GENERATION_PATH = ROOT / "config" / "generation.json"
TRUNCATED_REASONS = {"MAX_TOKENS", "length", "max_tokens"}


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
    finish_reason: str | None = None
    cached_tokens: int = 0
    traffic_type: str | None = None


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
        valid_through = entry.get("valid_through")
        if valid_through and datetime.now(timezone.utc).date().isoformat() > valid_through:
            raise PaidLockError(f"paid backend refused: prices for {price_key!r} are valid through {valid_through} only")
        self.in_price, self.out_price = float(entry["input_usd_per_1m"]), float(entry["output_usd_per_1m"])
        self.budget, self.spent = float(budget_usd), 0.0

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        """(prompt - cached) x input price + output (candidates + thinking) x output price; prices per 1M tokens."""
        return (input_tokens - cached_tokens) / 1e6 * self.in_price + output_tokens / 1e6 * self.out_price

    def check_before(self, prompt_chars: int, max_output_tokens: int) -> None:
        worst = self.cost(math.ceil(prompt_chars / 2.5), max_output_tokens)  # conservative: 2.5 chars/token
        if self.spent + worst > self.budget:
            raise BudgetExceeded(f"next call could cost up to ${worst:.4f}; spent ${self.spent:.4f} of ${self.budget:.2f} cap")

    def add(self, cost: float) -> None:
        self.spent += cost


class Pacer:
    """Fixed pace (Amendment 4, addendum 1): at most `max_calls_per_minute` calls, enforced as a minimum spacing of
    60 / max_calls_per_minute seconds between the STARTS of consecutive calls (router and answer calls share one pacer).
    No retries and no backoff: it only waits before a call. `clock` / `sleep` are injectable for tests."""

    def __init__(self, max_calls_per_minute: float, clock=time.monotonic, sleep=time.sleep):
        if not max_calls_per_minute > 0:
            raise ValueError("max_calls_per_minute must be > 0")
        self.max_calls_per_minute = float(max_calls_per_minute)
        self.min_interval_s = 60.0 / self.max_calls_per_minute
        self._clock, self._sleep = clock, sleep
        self._last_start = None
        self.n_calls, self.total_wait_s = 0, 0.0

    def wait(self) -> float:
        waited = 0.0
        now = self._clock()
        if self._last_start is not None:
            gap = self._last_start + self.min_interval_s - now
            if gap > 0:
                self._sleep(gap)
                waited = gap
        self._last_start = self._clock()
        self.n_calls += 1
        self.total_wait_s += waited
        return waited

    def describe(self) -> dict:
        return {"max_calls_per_minute": self.max_calls_per_minute, "min_interval_seconds": self.min_interval_s,
                "spacing": "minimum time between the starts of consecutive calls; no retries, no backoff"}


class LLMClient:
    backend = ""
    paid = False
    thinking_billed_separately = False  # Gemini reports thoughts_token_count outside candidates_token_count

    def __init__(self, name: str, cfg: dict, guard: CostGuard | None = None):
        self.name, self.cfg, self.guard = name, cfg, guard
        self.pacer: Pacer | None = None

    @property
    def spent_usd(self) -> float:
        return self.guard.spent if self.guard else 0.0

    def generate(self, system: str, user: str, *, max_output_tokens: int, json_mode: bool = False) -> LLMResponse:
        if self.guard:
            self.guard.check_before(len(system) + len(user), max_output_tokens)
        if self.pacer is not None:
            self.pacer.wait()
        t0 = time.perf_counter()
        try:
            text, i, o, th, raw, used = self._call(system, user, max_output_tokens, json_mode)
        except Exception as exc:
            raise LLMCallError(f"{self.backend}/{self.name}: {type(exc).__name__}: {exc}") from exc
        ms = (time.perf_counter() - t0) * 1000
        extra = used.pop("_extra", {})
        cost = 0.0
        if self.guard:
            if i is None or o is None:
                raise LLMCallError(f"{self.backend}/{self.name}: response has no usage fields; cannot compute cost")
            billed_out = o + ((th or 0) if self.thinking_billed_separately else 0)
            cost = self.guard.cost(i, billed_out, extra.get("cached_tokens", 0))
            self.guard.add(cost)
        return LLMResponse(text, i, o, th, cost, ms, used, raw, extra.get("finish_reason"), extra.get("cached_tokens", 0),
                           extra.get("traffic_type"))

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
                "num_ctx": options["num_ctx"], "max_output_tokens": max_out, "thinking": self.cfg["thinking"],
                "_extra": {"finish_reason": d.get("done_reason")}}
        return d["message"]["content"], d.get("prompt_eval_count"), d.get("eval_count"), 0, d, used


class VertexGeminiBackend(LLMClient):
    """Gemini on Vertex AI through the google-genai library (ADC, global endpoint). Paid: needs a CostGuard."""
    backend = "vertex_gemini"
    paid = True
    thinking_billed_separately = True

    def __init__(self, name, cfg, guard, project: str | None = None, client=None):
        super().__init__(name, cfg, guard)
        self.project = project or cfg.get("project")
        self.location = cfg.get("location", "global")
        if client is None:
            for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                if os.environ.get(var):
                    raise PaidLockError(f"{var} is set: this backend must use Application Default Credentials, not an API key")
            if not self.project:
                raise PaidLockError("no Vertex project configured (config/generation.json 'project')")
            from google import genai
            client = genai.Client(vertexai=True, project=self.project, location=self.location, http_options=self.http_options())
        self.client = client

    @staticmethod
    def http_options():
        """Single attempt per call (Amendment 4, addendum 1): client-side retries are disabled explicitly, so an HTTP 429 or
        5xx is raised at once and handled by the runner (stop, log, manual --resume). No timeout is set here."""
        from google.genai import types
        return types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))

    def _call(self, system, user, max_out, json_mode):
        from google.genai import types
        level = self.cfg["thinking"]["thinking_level"]
        if level not in self.cfg.get("allowed_thinking_levels", ["LOW", "MEDIUM", "HIGH"]):
            raise ValueError(f"thinking_level {level!r} is not allowed for {self.name}")
        conf = types.GenerateContentConfig(
            system_instruction=system, temperature=self.cfg["temperature"], max_output_tokens=max_out,
            thinking_config=types.ThinkingConfig(thinking_level=level),
            response_mime_type="application/json" if json_mode else None)
        r = self.client.models.generate_content(model=self.cfg["model_id"], contents=user, config=conf)
        u = r.usage_metadata
        cand = r.candidates[0] if r.candidates else None
        fr = None
        if cand is not None and cand.finish_reason is not None:
            fr = getattr(cand.finish_reason, "name", str(cand.finish_reason))
        tt = None
        if u is not None and u.traffic_type is not None:
            tt = getattr(u.traffic_type, "name", str(u.traffic_type))
        used = {"temperature": self.cfg["temperature"], "temperature_applied": True, "max_output_tokens": max_out,
                "thinking": self.cfg["thinking"], "location": self.location, "project": self.project,
                "_extra": {"finish_reason": fr, "cached_tokens": (u.cached_content_token_count or 0) if u else 0, "traffic_type": tt}}
        if u is None:
            return r.text or "", None, None, None, {}, used
        raw = {"usage": {k: getattr(u, k) for k in ("prompt_token_count", "candidates_token_count", "thoughts_token_count",
                                                    "cached_content_token_count", "total_token_count")},
               "traffic_type": tt, "finish_reason": fr}
        return r.text or "", u.prompt_token_count, u.candidates_token_count or 0, u.thoughts_token_count or 0, raw, used


class _VertexRestBase(LLMClient):
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

    def _used(self, max_out, extra):
        return {"temperature": self.cfg["temperature"], "temperature_applied": True, "max_output_tokens": max_out,
                "thinking": self.cfg["thinking"], "endpoint": "global", "_extra": extra}


class VertexClaudeBackend(_VertexRestBase):
    backend = "vertex_claude"

    def _call(self, system, user, max_out, json_mode):
        url = (f"https://aiplatform.googleapis.com/v1/projects/{self.project}/locations/global/"
               f"publishers/anthropic/models/{self.cfg['model_id']}:rawPredict")
        body = {"anthropic_version": "vertex-2023-10-16", "max_tokens": max_out, "system": system,
                "messages": [{"role": "user", "content": user}], "temperature": self.cfg["temperature"]}
        d = self._post(url, body)
        u = d.get("usage", {})
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        extra = {"finish_reason": d.get("stop_reason"), "cached_tokens": u.get("cache_read_input_tokens", 0) or 0}
        return text, u.get("input_tokens"), u.get("output_tokens"), 0, d, self._used(max_out, extra)


class VertexOpenMaaSBackend(_VertexRestBase):
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
        extra = {"finish_reason": d["choices"][0].get("finish_reason")}
        return d["choices"][0]["message"]["content"] or "", u.get("prompt_tokens"), u.get("completion_tokens"), 0, d, self._used(max_out, extra)


def make_client(model: str, *, allow_paid: bool = False, budget_usd: float | None = None, config: dict | None = None,
                prices_path: Path = PRICES_PATH, base_url: str | None = None, project: str | None = None,
                session=None, genai_client=None) -> LLMClient:
    cfg = (config or load_generation_config())["models"].get(model)
    if cfg is None:
        raise KeyError(f"model {model!r} not in config/generation.json")
    backend = cfg["backend"]
    if backend == "ollama":
        return OllamaBackend(model, cfg, base_url)
    guard = CostGuard(cfg["price_key"], allow_paid, budget_usd, prices_path)
    if backend == "vertex_gemini":
        return VertexGeminiBackend(model, cfg, guard, project, genai_client)
    cls = {"vertex_claude": VertexClaudeBackend, "vertex_openmaas": VertexOpenMaaSBackend}.get(backend)
    if cls is None:
        raise ValueError(f"unknown backend {backend!r}")
    return cls(model, cfg, guard, project, session)
