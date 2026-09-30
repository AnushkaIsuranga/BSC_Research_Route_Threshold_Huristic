"""Small Ollama HTTP client used by the local FinQA validation harness.

This deliberately uses Ollama's HTTP API instead of a LangChain integration so
the local evaluation does not require an additional provider package.
"""

from __future__ import annotations

import os
from typing import Any

import requests


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: int = 180):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout

    def tags(self) -> list[str]:
        response = requests.get(f"{self.base_url}/api/tags", timeout=10)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]

    def version(self) -> str:
        response = requests.get(f"{self.base_url}/api/version", timeout=10)
        response.raise_for_status()
        return response.json().get("version", "unknown")

    def show(self, model: str) -> dict[str, Any]:
        response = requests.post(f"{self.base_url}/api/show", json={"name": model}, timeout=30)
        response.raise_for_status()
        return response.json()

    def chat_response(
        self,
        model: str,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        num_ctx: int = 8192,
        seed: int = 0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0, "seed": seed, "num_ctx": num_ctx},
        }
        if json_mode:
            payload["format"] = "json"
        response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        data["_request"] = {"num_ctx": num_ctx, "seed": seed, "temperature": 0}
        return data

    def chat(self, model: str, system: str, user: str, *, json_mode: bool = False, num_ctx: int = 8192, seed: int = 0) -> str:
        return self.chat_response(model, system, user, json_mode=json_mode, num_ctx=num_ctx, seed=seed)["message"]["content"].strip()

    def embed(self, model: str, text: str | list[str]) -> list[float] | list[list[float]]:
        response = requests.post(
            f"{self.base_url}/api/embed",
            json={"model": model, "input": text},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if "embeddings" in data:
            return data["embeddings"] if isinstance(text, list) else data["embeddings"][0]
        return data["embedding"]
