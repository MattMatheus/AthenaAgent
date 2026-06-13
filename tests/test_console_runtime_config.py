from pathlib import Path
from unittest.mock import patch

import pytest

from athena_agent.athena_agent import AthenaAgent
from athena_agent.console_runtime import (
    ConsoleRuntimeConfigError,
    config_from_console_model_provider,
)


def test_console_model_provider_maps_to_forced_custom_provider(tmp_path: Path) -> None:
    config = config_from_console_model_provider(
        {
            "id": "provider-1",
            "providerKind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "defaultModel": "github-copilot/gpt-5.3-codex",
            "apiKey": "sk-console-secret",
        },
        workspace=tmp_path,
    )

    assert config.agents.defaults.provider == "custom"
    assert config.agents.defaults.model == "github-copilot/gpt-5.3-codex"
    assert config.providers.custom.api_key == "sk-console-secret"
    assert config.providers.custom.api_base == "https://provider.example/v1"
    assert config.get_provider_name() == "custom"
    assert config.get_api_base() == "https://provider.example/v1"

    with patch("athena_agent.providers.openai_compat_provider.AsyncOpenAI"):
        bot = AthenaAgent.from_settings(config)

    assert bot._loop.workspace == tmp_path
    assert bot._loop.provider.__class__.__name__ == "OpenAICompatProvider"


def test_console_model_provider_does_not_require_base_url(tmp_path: Path) -> None:
    config = config_from_console_model_provider(
        {
            "providerKind": "openai-compatible",
            "defaultModel": "plain-model",
            "apiKey": "sk-console-secret",
        },
        workspace=tmp_path,
    )

    assert config.agents.defaults.provider == "custom"
    assert config.providers.custom.api_base is None


@pytest.mark.parametrize(
    ("model_provider", "message"),
    [
        ({}, "providerKind"),
        ({"providerKind": "anthropic"}, "Unsupported"),
        ({"providerKind": "openai-compatible"}, "apiKey"),
        ({"providerKind": "openai-compatible", "apiKey": "sk-secret"}, "defaultModel"),
    ],
)
def test_console_model_provider_validation_errors_are_secret_safe(
    model_provider: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ConsoleRuntimeConfigError, match=message) as error:
        config_from_console_model_provider(model_provider)

    assert "sk-secret" not in str(error.value)
