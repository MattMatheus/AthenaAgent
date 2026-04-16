from pathlib import Path
from unittest.mock import MagicMock

from athena_agent.agent.loop import AgentLoop
from athena_agent.agent.tool_profiles import resolve_tool_profile
from athena_agent.bus.queue import MessageBus
from athena_agent.cron.service import CronService


def test_resolve_research_profile_expands_expected_tools() -> None:
    assert resolve_tool_profile("research") == {
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "glob",
        "grep",
        "exec",
        "web_search",
        "web_fetch",
    }


def test_resolve_custom_profile_can_reference_builtin_profiles() -> None:
    profile = resolve_tool_profile(
        "repo_ops",
        {"repo_ops": ["core", "spawn"]},
    )

    assert "read_file" in profile
    assert "spawn" in profile
    assert "web_search" not in profile


def test_agent_loop_research_profile_omits_spawn_cron_and_notebook(tmp_path: Path) -> None:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        tool_profile="research",
    )

    assert loop.tools.get("read_file") is not None
    assert loop.tools.get("web_search") is not None
    assert loop.tools.get("spawn") is None
    assert loop.tools.get("cron") is None
    assert loop.tools.get("notebook") is None
    assert loop.tools.get("message") is None


def test_agent_loop_scheduled_profile_registers_cron_without_web(tmp_path: Path) -> None:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        cron_service=CronService(tmp_path / "cron" / "jobs.json"),
        tool_profile="scheduled",
    )

    assert loop.tools.get("cron") is not None
    assert loop.tools.get("spawn") is not None
    assert loop.tools.get("web_search") is None
