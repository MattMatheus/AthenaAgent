"""Helpers for Console-launched AthenaAgent runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from athena_agent.config.schema import Config


class ConsoleRuntimeConfigError(ValueError):
    """Raised when Console runtime configuration is missing or unsupported."""


def config_from_console_model_provider(
    model_provider: Mapping[str, Any],
    *,
    workspace: str | Path | None = None,
) -> Config:
    """Build an AthenaAgent config from Console's resolved provider block.

    Console passes a live provider runtime object in the task envelope. The
    Agent runtime must force the direct ``custom`` provider so model names do
    not trigger registry auto-detection.
    """
    if not isinstance(model_provider, Mapping):
        raise ConsoleRuntimeConfigError("Console modelProvider must be an object.")

    provider_kind = _read_string(model_provider, "providerKind")
    if provider_kind != "openai-compatible":
        raise ConsoleRuntimeConfigError(
            f"Unsupported Console modelProvider.providerKind: {provider_kind or 'missing'}."
        )

    api_key = _read_string(model_provider, "apiKey")
    if not api_key:
        raise ConsoleRuntimeConfigError("Console modelProvider.apiKey is required.")

    default_model = _read_string(model_provider, "defaultModel")
    if not default_model:
        raise ConsoleRuntimeConfigError("Console modelProvider.defaultModel is required.")

    base_url = _read_string(model_provider, "baseUrl")
    config = Config.model_validate(
        {
            "providers": {
                "custom": {
                    "apiKey": api_key,
                    **({"apiBase": base_url} if base_url else {}),
                }
            },
            "agents": {
                "defaults": {
                    "provider": "custom",
                    "model": default_model,
                    **({"workspace": str(Path(workspace).expanduser().resolve())} if workspace else {}),
                }
            },
        }
    )
    return config


def _read_string(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    return value.strip() if isinstance(value, str) else ""
