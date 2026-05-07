"""LLM chat client.

Wraps the OpenAI Python SDK so it works against any OpenAI-compatible
endpoint: OpenAI itself, an Azure-style proxy, a local Ollama server, etc.

Configuration is read from environment variables:

    DIARY_API_KEY     (or OPENAI_API_KEY)  - API key, required for hosted
    DIARY_BASE_URL    (or OPENAI_BASE_URL) - e.g. http://localhost:11434/v1
    DIARY_MODEL       - e.g. gpt-4o-mini, llama3.1, etc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - import error surfaces at runtime
    OpenAI = None  # type: ignore


DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class ChatConfig:
    api_key: str | None
    base_url: str | None
    model: str

    @classmethod
    def from_env(cls) -> "ChatConfig":
        api_key = os.environ.get("DIARY_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("DIARY_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        model = os.environ.get("DIARY_MODEL", DEFAULT_MODEL)
        return cls(api_key=api_key, base_url=base_url, model=model)


class ChatClient:
    def __init__(self, config: ChatConfig | None = None):
        self.config = config or ChatConfig.from_env()
        if OpenAI is None:
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install -r requirements.txt"
            )
        if not self.config.api_key and not self.config.base_url:
            raise RuntimeError(
                "No API key found. Set DIARY_API_KEY (or OPENAI_API_KEY) "
                "in your environment or .env file. To use a local model, set "
                "DIARY_BASE_URL (e.g. http://localhost:11434/v1)."
            )
        kwargs: dict = {}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        else:
            kwargs["api_key"] = "not-needed"
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        self._client = OpenAI(**kwargs)

    def reply(
        self,
        system_prompt: str,
        history: Iterable[dict],
        user_message: str,
        context: str | None = None,
    ) -> str:
        """Send a single user turn and return the assistant's reply text.

        `history` is an iterable of {"role", "content"} dicts in chronological
        order. `context` is optional extra system text (e.g. current todo
        list) injected before the user turn.
        """
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for m in history:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": user_message})

        resp = self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=0.8,
        )
        choice = resp.choices[0]
        return (choice.message.content or "").strip()
