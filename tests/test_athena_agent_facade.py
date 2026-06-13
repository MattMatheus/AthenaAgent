"""Tests for the AthenaAgent programmatic facade."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from athena_agent.athena_agent import AthenaAgent, RunResult


def _write_config(tmp_path: Path, overrides: dict | None = None) -> Path:
    data = {
        "providers": {"openrouter": {"apiKey": "sk-test-key"}},
        "agents": {"defaults": {"model": "openai/gpt-4.1"}},
    }
    if overrides:
        data.update(overrides)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


def test_from_config_missing_file():
    with pytest.raises(FileNotFoundError):
        AthenaAgent.from_config("/nonexistent/config.json")


def test_from_config_creates_instance(tmp_path):
    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)
    assert bot._loop is not None
    assert bot._loop.workspace == tmp_path


def test_from_settings_creates_instance_without_global_config(tmp_path, monkeypatch):
    from athena_agent.config.schema import Config

    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()
    workspace = tmp_path / "workspace"
    config = Config.model_validate(
        {
            "providers": {
                "custom": {
                    "apiKey": "sk-console-runtime-key",
                    "apiBase": "https://provider.example/v1",
                }
            },
            "agents": {
                "defaults": {
                    "provider": "custom",
                    "model": "console-model",
                    "workspace": str(tmp_path / "original-workspace"),
                }
            },
        }
    )

    monkeypatch.setenv("HOME", str(empty_home))
    with patch("athena_agent.providers.openai_compat_provider.AsyncOpenAI"):
        bot = AthenaAgent.from_settings(config, workspace=workspace)

    assert bot._loop is not None
    assert bot._loop.workspace == workspace
    assert config.agents.defaults.workspace == str(tmp_path / "original-workspace")


def test_from_settings_respects_in_memory_workspace_when_not_overridden(tmp_path):
    from athena_agent.config.schema import Config

    workspace = tmp_path / "configured-workspace"
    config = Config.model_validate(
        {
            "providers": {"custom": {"apiKey": "sk-test-key"}},
            "agents": {
                "defaults": {
                    "provider": "custom",
                    "model": "plain-console-model",
                    "workspace": str(workspace),
                }
            },
        }
    )

    with patch("athena_agent.providers.openai_compat_provider.AsyncOpenAI"):
        bot = AthenaAgent.from_settings(config)

    assert bot._loop.workspace == workspace


def test_from_config_default_path():
    from athena_agent.config.schema import Config

    with patch("athena_agent.config.loader.load_config") as mock_load, \
         patch("athena_agent.athena_agent._make_provider") as mock_prov:
        mock_load.return_value = Config()
        mock_prov.return_value = MagicMock()
        mock_prov.return_value.get_default_model.return_value = "test"
        mock_prov.return_value.generation.max_tokens = 4096
        AthenaAgent.from_config()
        mock_load.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_run_returns_result(tmp_path):
    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)

    from athena_agent.bus.events import OutboundMessage

    mock_response = OutboundMessage(
        channel="cli", chat_id="direct", content="Hello back!"
    )
    bot._loop.process_direct = AsyncMock(return_value=mock_response)

    result = await bot.run("hi")

    assert isinstance(result, RunResult)
    assert result.content == "Hello back!"
    bot._loop.process_direct.assert_awaited_once_with("hi", session_key="sdk:default")


@pytest.mark.asyncio
async def test_run_starts_and_stops_cron_for_one_shot_calls(tmp_path):
    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)

    from athena_agent.bus.events import OutboundMessage

    bot._cron.start = AsyncMock(return_value=None)
    bot._cron.stop = MagicMock(return_value=None)
    bot._loop.close_mcp = AsyncMock(return_value=None)
    bot._loop.process_direct = AsyncMock(
        return_value=OutboundMessage(channel="cli", chat_id="direct", content="ok")
    )

    await bot.run("hi")

    bot._cron.start.assert_awaited_once()
    bot._cron.stop.assert_called_once()
    bot._loop.close_mcp.assert_awaited_once()


@pytest.mark.asyncio
async def test_context_manager_keeps_cron_running_until_exit(tmp_path):
    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)

    from athena_agent.bus.events import OutboundMessage

    bot._cron.start = AsyncMock(return_value=None)
    bot._cron.stop = MagicMock(return_value=None)
    bot._loop.close_mcp = AsyncMock(return_value=None)
    bot._loop.process_direct = AsyncMock(
        return_value=OutboundMessage(channel="cli", chat_id="direct", content="ok")
    )

    async with bot:
        await bot.run("hi")

    bot._cron.start.assert_awaited_once()
    bot._cron.stop.assert_called_once()
    bot._loop.close_mcp.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_with_hooks(tmp_path):
    from athena_agent.agent.hook import AgentHook, AgentHookContext
    from athena_agent.bus.events import OutboundMessage

    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)

    class TestHook(AgentHook):
        async def before_iteration(self, context: AgentHookContext) -> None:
            pass

    mock_response = OutboundMessage(
        channel="cli", chat_id="direct", content="done"
    )
    bot._loop.process_direct = AsyncMock(return_value=mock_response)

    result = await bot.run("hi", hooks=[TestHook()])

    assert result.content == "done"
    assert bot._loop._extra_hooks == []


@pytest.mark.asyncio
async def test_run_hooks_restored_on_error(tmp_path):
    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)

    from athena_agent.agent.hook import AgentHook

    bot._loop.process_direct = AsyncMock(side_effect=RuntimeError("boom"))
    original_hooks = bot._loop._extra_hooks

    with pytest.raises(RuntimeError):
        await bot.run("hi", hooks=[AgentHook()])

    assert bot._loop._extra_hooks is original_hooks


@pytest.mark.asyncio
async def test_run_none_response(tmp_path):
    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)
    bot._loop.process_direct = AsyncMock(return_value=None)

    result = await bot.run("hi")
    assert result.content == ""


def test_workspace_override(tmp_path):
    config_path = _write_config(tmp_path)
    custom_ws = tmp_path / "custom_workspace"
    custom_ws.mkdir()

    bot = AthenaAgent.from_config(config_path, workspace=custom_ws)
    assert bot._loop.workspace == custom_ws


def test_sdk_make_provider_uses_github_copilot_backend():
    from athena_agent.config.schema import Config
    from athena_agent.athena_agent import _make_provider

    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "github-copilot",
                    "model": "github-copilot/gpt-4.1",
                }
            }
        }
    )

    with patch("athena_agent.providers.openai_compat_provider.AsyncOpenAI"):
        provider = _make_provider(config)

    assert provider.__class__.__name__ == "GitHubCopilotProvider"


@pytest.mark.asyncio
async def test_run_custom_session_key(tmp_path):
    from athena_agent.bus.events import OutboundMessage

    config_path = _write_config(tmp_path)
    bot = AthenaAgent.from_config(config_path, workspace=tmp_path)

    mock_response = OutboundMessage(
        channel="cli", chat_id="direct", content="ok"
    )
    bot._loop.process_direct = AsyncMock(return_value=mock_response)

    await bot.run("hi", session_key="user-alice")
    bot._loop.process_direct.assert_awaited_once_with("hi", session_key="user-alice")


def test_import_from_top_level():
    from athena_agent import AthenaAgent as A, RunResult as R

    assert A is AthenaAgent
    assert R is RunResult
