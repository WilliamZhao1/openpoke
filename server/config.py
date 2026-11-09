"""Simplified configuration management."""

import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, StrictInt, model_validator


def _load_env_file() -> None:
    """Load .env from root directory if present."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                key, value = key.strip(), value.strip().strip("'\"")
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_env_file()


DEFAULT_APP_NAME = "OpenPoke Server"
DEFAULT_APP_VERSION = "0.3.0"
BUNDLED_LLM_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_LLM_MODEL = os.getenv("OPENROUTER_MODEL") or BUNDLED_LLM_MODEL
# Release-tested application allowance, not an inferred provider context capacity.
DEFAULT_MODEL_CONTEXT_WINDOWS = {BUNDLED_LLM_MODEL: 65536}


def _model_context_windows_from_env() -> Dict[str, int]:
    configured = os.getenv("OPENPOKE_MODEL_CONTEXT_WINDOWS")
    return json.loads(configured) if configured is not None else dict(DEFAULT_MODEL_CONTEXT_WINDOWS)


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _data_dir_from_env() -> Path:
    configured = os.getenv("OPENPOKE_DATA_DIR")
    if configured is None:
        return Path(__file__).resolve().parent / "data"
    if not configured.strip():
        raise ValueError("OPENPOKE_DATA_DIR must be a non-empty path")
    return Path(configured)


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    server_port: int = Field(default=_env_int("OPENPOKE_PORT", 8001))
    data_dir: Path = Field(default_factory=_data_dir_from_env)
    worker_discovery_strategy: Literal["legacy", "bounded"] = Field(
        default_factory=lambda: os.getenv("OPENPOKE_WORKER_DISCOVERY", "bounded"), validate_default=True,
    )
    context_strategy: Literal["legacy", "bounded"] = Field(
        default_factory=lambda: os.getenv("OPENPOKE_CONTEXT_STRATEGY", "bounded"), validate_default=True,
    )
    model_context_windows: Dict[str, StrictInt] = Field(
        default_factory=_model_context_windows_from_env, validate_default=True,
    )
    context_input_tokens: int = Field(
        default_factory=lambda: int(os.getenv("OPENPOKE_CONTEXT_INPUT_TOKENS", "32768")),
        gt=0, strict=True, validate_default=True,
    )
    context_headroom_tokens: int = Field(
        default_factory=lambda: int(os.getenv("OPENPOKE_CONTEXT_HEADROOM_TOKENS", "1024")),
        ge=0, strict=True, validate_default=True,
    )

    # LLM model selection
    openrouter_max_tokens: int = Field(default=_env_int("OPENROUTER_MAX_TOKENS", 2048), gt=0)
    interaction_agent_model: str = Field(default=DEFAULT_LLM_MODEL)
    execution_agent_model: str = Field(default=DEFAULT_LLM_MODEL)
    execution_agent_search_model: str = Field(default=DEFAULT_LLM_MODEL)
    summarizer_model: str = Field(default=DEFAULT_LLM_MODEL)
    email_classifier_model: str = Field(default=DEFAULT_LLM_MODEL)

    # Credentials / integrations
    openrouter_api_key: Optional[str] = Field(default=os.getenv("OPENROUTER_API_KEY"))
    composio_gmail_auth_config_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID"))
    composio_api_key: Optional[str] = Field(default=os.getenv("COMPOSIO_API_KEY"))

    # HTTP behaviour
    cors_allow_origins_raw: str = Field(default=os.getenv("OPENPOKE_CORS_ALLOW_ORIGINS", "*"))
    enable_docs: bool = Field(default=os.getenv("OPENPOKE_ENABLE_DOCS", "1") != "0")
    docs_url: Optional[str] = Field(default=os.getenv("OPENPOKE_DOCS_URL", "/docs"))

    # Summarisation controls
    conversation_summary_threshold: int = Field(default=100)
    conversation_summary_tail_size: int = Field(default=10)

    @model_validator(mode="after")
    def validate_context_configuration(self):
        if any(not model.strip() or window <= 0 for model, window in self.model_context_windows.items()):
            raise ValueError("Model context allowances must have nonempty names and positive integer values")
        if self.context_strategy == "bounded":
            models = {self.interaction_agent_model, self.execution_agent_model, self.execution_agent_search_model,
                      self.summarizer_model, self.email_classifier_model}
            if not models.issubset(self.model_context_windows):
                raise ValueError("OPENPOKE_MODEL_CONTEXT_WINDOWS must cover every configured model in bounded context mode; set explicit allowances for custom models or select OPENPOKE_CONTEXT_STRATEGY=legacy")
            if any(self.model_context_windows[model] <= self.openrouter_max_tokens + self.context_headroom_tokens for model in models):
                raise ValueError("Model context allowances must exceed output reservation plus headroom")
        return self

    @property
    def cors_allow_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_allow_origins_raw.strip() in {"", "*"}:
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins_raw.split(",") if origin.strip()]

    @property
    def resolved_docs_url(self) -> Optional[str]:
        """Return documentation URL when docs are enabled."""
        return (self.docs_url or "/docs") if self.enable_docs else None

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
