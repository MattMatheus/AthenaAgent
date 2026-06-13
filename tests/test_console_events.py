import io
import json

import pytest

from athena_agent.agent.hook import AgentHook, AgentHookContext, CompositeHook
from athena_agent.console_events import ConsoleEventHook, ConsoleJsonlEventSink
from athena_agent.providers.base import LLMResponse, ToolCallRequest


def _events(buffer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines()]


@pytest.mark.asyncio
async def test_console_event_hook_emits_model_and_tool_jsonl_records() -> None:
    buffer = io.StringIO()
    hook = ConsoleEventHook(
        sink=ConsoleJsonlEventSink(buffer),
        task_id="task-1",
        run_id="run-1",
        agent_id="athena-agent.repo-summary",
        model="gpt-test",
    )
    context = AgentHookContext(iteration=0, messages=[{"role": "user", "content": "hi"}])
    context.tool_calls = [ToolCallRequest(id="call-1", name="list_dir", arguments={"path": "."})]

    await hook.before_iteration(context)
    await hook.before_execute_tools(context)
    context.response = LLMResponse(content="", tool_calls=context.tool_calls, usage={"prompt_tokens": 5})
    context.usage = {"prompt_tokens": 5}
    context.tool_events = [{"name": "list_dir", "status": "ok", "detail": "listed"}]
    await hook.after_iteration(context)

    records = _events(buffer)
    assert [record["type"] for record in records] == [
        "model.request",
        "tool.started",
        "model.response",
        "tool.completed",
    ]
    assert records[0]["taskId"] == "task-1"
    assert records[1]["payload"]["tools"] == [{"id": "call-1", "name": "list_dir"}]
    assert records[3]["payload"]["events"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_console_event_hook_marks_failed_tool_batches() -> None:
    buffer = io.StringIO()
    hook = ConsoleEventHook(
        sink=ConsoleJsonlEventSink(buffer),
        task_id="task-1",
        run_id="run-1",
        agent_id="athena-agent.repo-summary",
    )
    context = AgentHookContext(iteration=0, messages=[])
    context.response = LLMResponse(content="", usage={})
    context.tool_events = [{"name": "read_file", "status": "error", "detail": "denied"}]

    await hook.after_iteration(context)

    records = _events(buffer)
    assert [record["type"] for record in records] == ["model.response", "tool.failed"]
    assert records[1]["payload"]["events"][0]["detail"] == "denied"


@pytest.mark.asyncio
async def test_console_event_hook_failure_is_isolated_by_composite_hook() -> None:
    calls: list[str] = []

    class BadSink:
        def emit(self, _event):
            raise RuntimeError("sidecar unavailable")

    class GoodHook(AgentHook):
        async def before_iteration(self, _context: AgentHookContext) -> None:
            calls.append("good")

    hook = ConsoleEventHook(
        sink=BadSink(),
        task_id="task-1",
        run_id="run-1",
        agent_id="athena-agent.repo-summary",
    )

    await CompositeHook([hook, GoodHook()]).before_iteration(AgentHookContext(iteration=0, messages=[]))

    assert calls == ["good"]
