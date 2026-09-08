"""Pluggable chat model providers with streaming.

The API surface is one function — `stream_chat` — yielding text deltas. Which
model serves it is configuration, so the retrieval and prompt layers never
import a vendor SDK.

With no key configured, `EchoProvider` streams the assembled context back. That
keeps the whole application testable and demoable offline, and makes the
retrieval layer inspectable on its own, which is where most quality problems
actually live.
"""

from __future__ import annotations

from typing import Iterator, Protocol

from .. import config


class ChatProvider(Protocol):
    name: str

    def stream(self, system: str, messages: list[dict], max_tokens: int) -> Iterator[str]: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None):
        self.model = model or config.settings.llm_model

    def stream(self, system: str, messages: list[dict], max_tokens: int = 2000) -> Iterator[str]:
        import anthropic

        client = anthropic.Anthropic(api_key=config.settings.anthropic_api_key)
        with client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str | None = None):
        self.model = model or config.settings.llm_model

    def stream(self, system: str, messages: list[dict], max_tokens: int = 2000) -> Iterator[str]:
        import httpx

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        with httpx.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.settings.openai_api_key}"},
            json=payload,
            timeout=120,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                import json

                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, ValueError):
                    continue
                if delta:
                    yield delta


class EchoProvider:
    """Offline stand-in. Streams the retrieved evidence instead of a generated
    answer, so the pipeline can be exercised and inspected without a key."""

    name = "echo"

    def stream(self, system: str, messages: list[dict], max_tokens: int = 2000) -> Iterator[str]:
        last = messages[-1]["content"] if messages else ""
        yield (
            "_No model key is configured, so this is the retrieval layer's raw "
            "output rather than a generated answer. Set `ANTHROPIC_API_KEY` to "
            "enable conversation._\n\n"
        )
        for chunk in last.split("\n"):
            yield chunk + "\n"


def get_provider() -> ChatProvider:
    s = config.settings
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider()
    if s.llm_provider == "openai" and s.openai_api_key:
        return OpenAIProvider()
    return EchoProvider()
