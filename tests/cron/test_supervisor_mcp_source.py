from pathlib import Path

import pytest

from athena_agent.cron.supervisor import SupervisorExecutor
from athena_agent.cron.types import CronJob, CronPayload, CronSchedule, CronSupervisorSpec
from athena_agent.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    async def chat(self, *args, **kwargs) -> LLMResponse:
        return LLMResponse(content="", tool_calls=[])

    def get_default_model(self) -> str:
        return "test-model"


def _make_job(*, source_kind: str = "inline", source_ref: str = "hello") -> CronJob:
    return CronJob(
        id="job1",
        name="supervisor",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        payload=CronPayload(
            kind="supervisor_turn",
            message="Summarize the source.",
            supervisor=CronSupervisorSpec(
                source_kind=source_kind,
                source_ref=source_ref,
                decision_mode="always_run",
                execution_prompt="Review the source.",
                notify_policy="never",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_mcp_note_loads_source_via_read_note_tool(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _mcp_call(name: str, args: dict[str, object]) -> str:
        calls.append((name, args))
        return "note text"

    executed: list[str] = []

    async def _on_execute(task: str, _job: CronJob) -> str:
        executed.append(task)
        return "done"

    executor = SupervisorExecutor(
        workspace=tmp_path,
        provider=DummyProvider(),
        model="test-model",
        on_execute=_on_execute,
        mcp_call=_mcp_call,
    )

    result = await executor.run_job(
        _make_job(source_kind="mcp_note", source_ref="obsidian:Notes/today.md")
    )

    assert result.status == "ok"
    assert result.source_content == "note text"
    assert calls == [("mcp_obsidian_read_note", {"path": "Notes/today.md"})]
    assert executed == ["Review the source.\n\nSource context:\nnote text"]


@pytest.mark.asyncio
async def test_mcp_query_loads_source_via_search_tool(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _mcp_call(name: str, args: dict[str, object]) -> str:
        calls.append((name, args))
        return "search result 1\nsearch result 2"

    async def _on_execute(task: str, _job: CronJob) -> str:
        return "done"

    executor = SupervisorExecutor(
        workspace=tmp_path,
        provider=DummyProvider(),
        model="test-model",
        on_execute=_on_execute,
        mcp_call=_mcp_call,
    )

    result = await executor.run_job(
        _make_job(source_kind="mcp_query", source_ref="obsidian:tag:#athena")
    )

    assert result.status == "ok"
    assert result.source_content == "search result 1\nsearch result 2"
    assert calls == [("mcp_obsidian_search_vault", {"query": "tag:#athena"})]


@pytest.mark.asyncio
async def test_mcp_missing_tool_returns_error_result(tmp_path: Path) -> None:
    async def _mcp_call(name: str, args: dict[str, object]) -> str:
        raise ValueError(f"MCP tool '{name}' is not registered")

    executor = SupervisorExecutor(
        workspace=tmp_path,
        provider=DummyProvider(),
        model="test-model",
        mcp_call=_mcp_call,
    )

    result = await executor.run_job(
        _make_job(source_kind="mcp_note", source_ref="obsidian:Notes/today.md")
    )

    assert result.status == "error"
    assert "mcp_obsidian_read_note" in (result.error or "")


@pytest.mark.asyncio
async def test_inline_and_file_sources_still_load(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("file text", encoding="utf-8")
    executed: list[str] = []

    async def _on_execute(task: str, _job: CronJob) -> str:
        executed.append(task)
        return "done"

    executor = SupervisorExecutor(
        workspace=tmp_path,
        provider=DummyProvider(),
        model="test-model",
        on_execute=_on_execute,
    )

    inline_result = await executor.run_job(_make_job(source_ref="inline text"))
    file_result = await executor.run_job(_make_job(source_kind="file", source_ref="note.md"))

    assert inline_result.status == "ok"
    assert inline_result.source_content == "inline text"
    assert file_result.status == "ok"
    assert file_result.source_content == "file text"
