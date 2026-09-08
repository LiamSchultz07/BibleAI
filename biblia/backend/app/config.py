"""Runtime configuration, read from the environment.

Nothing here is required for the system to boot. With no keys set, the corpus,
reference lookup, search and passage comparison all work; only the conversational
layer needs a model key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    return default


def _ephemeral_secret() -> str:
    import secrets

    return secrets.token_urlsafe(48)


@dataclass
class Settings:
    # --- models
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    voyage_api_key: str = field(default_factory=lambda: _env("VOYAGE_API_KEY"))

    llm_provider: str = field(default_factory=lambda: _env("BIBLIA_LLM_PROVIDER", default="anthropic"))
    llm_model: str = field(default_factory=lambda: _env("BIBLIA_LLM_MODEL", default="claude-sonnet-4-5"))
    embed_provider: str = field(default_factory=lambda: _env("BIBLIA_EMBED_PROVIDER", default="lsa"))

    # --- retrieval
    default_translation: str = field(default_factory=lambda: _env("BIBLIA_DEFAULT_TRANSLATION", default="BSB"))
    max_context_verses: int = 220
    max_pericopes: int = 6

    # --- server
    cors_origins: str = field(default_factory=lambda: _env("BIBLIA_CORS", default="*"))

    # Signing key for session tokens. A generated ephemeral key keeps local
    # development zero-config, at the cost of invalidating sessions on restart;
    # any real deployment must set BIBLIA_SECRET_KEY.
    secret_key: str = field(
        default_factory=lambda: _env("BIBLIA_SECRET_KEY") or _ephemeral_secret()
    )

    @property
    def secret_is_ephemeral(self) -> bool:
        return not _env("BIBLIA_SECRET_KEY")

    @property
    def has_llm(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return False


settings = Settings()
