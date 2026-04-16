from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from athena_agent.bus.events import OutboundMessage
from athena_agent.cron.runtime import make_cron_runtime_callback
from athena_agent.cron.types import CronJob, CronPayload, CronSchedule, CronSupervisorSpec
from athena_agent.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from athena_agent.session.manager import SessionManager


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


@pytest.mark.asyncio
async def test_agent_turn_callback_executes_and_notifies(tmp_path: Path, monkeypatch) -> None:
    bus = SimpleNamespace(publish_outbound=AsyncMock())
    loop = SimpleNamespace(
        workspace=tmp_path,
        provider=object(),
        model="test-model",
        context=SimpleNamespace(timezone="UTC"),
        bus=bus,
        tools={"cron": SimpleNamespace(set_cron_context=lambda _v: "tok", reset_cron_context=lambda _t: None), "message": SimpleNamespace(_sent_in_turn=False)},
        sessions=SessionManager(tmp_path),
        process_direct=AsyncMock(return_value=OutboundMessage(channel="cli", chat_id="direct", content="done")),
    )

    async def _always_notify(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr("athena_agent.utils.evaluator.evaluate_response", _always_notify)

    callback = make_cron_runtime_callback(loop)
    job = CronJob(
        id="job1",
        name="stretch",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        payload=CronPayload(
            kind="agent_turn",
            message="Remind me to stretch.",
            deliver=True,
            channel="telegram",
            to="user-1",
        ),
    )

    result = await callback(job)

    assert result == "done"
    loop.process_direct.assert_awaited_once_with(
        "[Scheduled Task] Timer finished.\n\nTask 'stretch' has been triggered.\nScheduled instruction: Remind me to stretch.",
        session_key="cron:job1",
        channel="telegram",
        chat_id="user-1",
    )
    bus.publish_outbound.assert_awaited_once_with(
        OutboundMessage(channel="telegram", chat_id="user-1", content="done")
    )


@pytest.mark.asyncio
async def test_supervisor_turn_callback_runs_through_executor_and_trims_session(
    tmp_path: Path, monkeypatch
) -> None:
    bus = SimpleNamespace(publish_outbound=AsyncMock())
    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="d1",
                    name="supervisor_decision",
                    arguments={"action": "run", "task": "Summarize the source"},
                )
            ],
        )
    ])
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("supervisor:repo")
    session.add_message("user", "a")
    session.add_message("assistant", "b")
    session.add_message("user", "c")
    sessions.save(session)

    loop = SimpleNamespace(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        context=SimpleNamespace(timezone="UTC"),
        bus=bus,
        tools={"message": SimpleNamespace(_sent_in_turn=False)},
        sessions=sessions,
        process_direct=AsyncMock(return_value=OutboundMessage(channel="cli", chat_id="direct", content="summary")),
    )

    async def _always_notify(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr("athena_agent.utils.evaluator.evaluate_response", _always_notify)

    callback = make_cron_runtime_callback(loop)
    job = CronJob(
        id="job2",
        name="repo-walk",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        payload=CronPayload(
            kind="supervisor_turn",
            message="Review repo",
            deliver=True,
            channel="telegram",
            to="user-2",
            supervisor=CronSupervisorSpec(
                source_kind="inline",
                source_ref="Important repo context",
                decision_mode="llm_gate",
                decision_prompt="Should this run?",
                execution_prompt="Review the source and summarize it.",
                notify_policy="evaluate",
                session_key="supervisor:repo",
                keep_recent_messages=1,
            ),
        ),
    )

    result = await callback(job)

    assert result == {"status": "ok", "error": None}
    loop.process_direct.assert_awaited_once_with(
        "Summarize the source",
        session_key="supervisor:repo",
        channel="telegram",
        chat_id="user-2",
    )
    trimmed = sessions.get_or_create("supervisor:repo")
    assert len(trimmed.messages) <= 1
    bus.publish_outbound.assert_awaited_once_with(
        OutboundMessage(channel="telegram", chat_id="user-2", content="summary")
    )


@pytest.mark.asyncio
async def test_supervisor_turn_callback_returns_skipped_without_execution(tmp_path: Path) -> None:
    bus = SimpleNamespace(publish_outbound=AsyncMock())
    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="d1",
                    name="supervisor_decision",
                    arguments={"action": "skip"},
                )
            ],
        )
    ])
    loop = SimpleNamespace(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        context=SimpleNamespace(timezone="UTC"),
        bus=bus,
        tools={},
        sessions=SessionManager(tmp_path),
        process_direct=AsyncMock(),
    )

    callback = make_cron_runtime_callback(loop)
    job = CronJob(
        id="job3",
        name="repo-walk",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        payload=CronPayload(
            kind="supervisor_turn",
            supervisor=CronSupervisorSpec(
                source_kind="inline",
                source_ref="Important repo context",
                decision_mode="llm_gate",
            ),
        ),
    )

    result = await callback(job)

    assert result == {"status": "skipped", "error": None}
    loop.process_direct.assert_not_called()
    bus.publish_outbound.assert_not_awaited()
