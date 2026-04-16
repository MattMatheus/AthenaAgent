from pathlib import Path

import pytest

from athena_agent.cron.supervisor import SupervisorExecutor
from athena_agent.cron.types import CronJob, CronPayload, CronSchedule, CronSupervisorSpec
from athena_agent.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class DummyProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse]):
        super().__init__()
        self._responses = list(responses)

    async def chat(self, *args, **kwargs) -> LLMResponse:
        if self._responses:
            return self._responses.pop(0)
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
                decision_mode="llm_gate",
                decision_prompt="Should this run?",
                execution_prompt="Review the source and summarize it.",
                notify_policy="evaluate",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_supervisor_executor_skips_when_gate_says_skip(tmp_path: Path) -> None:
    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[ToolCallRequest(id="d1", name="supervisor_decision", arguments={"action": "skip"})],
        )
    ])
    executor = SupervisorExecutor(workspace=tmp_path, provider=provider, model="test-model")

    result = await executor.run_job(_make_job())

    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_supervisor_executor_loads_file_source_and_executes(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("Important repo context", encoding="utf-8")
    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="d1",
                    name="supervisor_decision",
                    arguments={"action": "run", "task": "Summarize the repo note"},
                )
            ],
        )
    ])
    executed: list[str] = []

    async def _on_execute(task: str, _job: CronJob) -> str:
        executed.append(task)
        return "summary"

    executor = SupervisorExecutor(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        on_execute=_on_execute,
    )

    result = await executor.run_job(_make_job(source_kind="file", source_ref="note.md"))

    assert result.status == "ok"
    assert result.source_content == "Important repo context"
    assert executed == ["Summarize the repo note"]
    assert result.response == "summary"


@pytest.mark.asyncio
async def test_supervisor_executor_evaluates_notify_policy(tmp_path: Path, monkeypatch) -> None:
    provider = DummyProvider([])
    notified: list[str] = []

    async def _on_execute(task: str, _job: CronJob) -> str:
        return f"result for {task}"

    async def _on_notify(response: str, _job: CronJob) -> None:
        notified.append(response)

    async def _always_notify(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr("athena_agent.utils.evaluator.evaluate_response", _always_notify)

    executor = SupervisorExecutor(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        on_execute=_on_execute,
        on_notify=_on_notify,
    )
    job = _make_job()
    assert job.payload.supervisor is not None
    job.payload.supervisor.decision_mode = "always_run"

    result = await executor.run_job(job)

    assert result.status == "ok"
    assert result.should_notify is True
    assert notified == ["result for Review the source and summarize it.\n\nSource context:\nhello"]


@pytest.mark.asyncio
async def test_supervisor_executor_errors_on_unsupported_source_kind(tmp_path: Path) -> None:
    provider = DummyProvider([])
    executor = SupervisorExecutor(workspace=tmp_path, provider=provider, model="test-model")

    result = await executor.run_job(_make_job(source_kind="mcp_note", source_ref="vault://note"))

    assert result.status == "error"
    assert "Unsupported supervisor source_kind" in (result.error or "")
