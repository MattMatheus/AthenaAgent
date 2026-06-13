"""Console JSONL event hook for AthenaAgent runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from athena_agent.agent.hook import AgentHook, AgentHookContext


class ConsoleJsonlEventSink:
    """Append Console-compatible events as JSON lines."""

    def __init__(self, target: Path | TextIO) -> None:
        self._owns_file = isinstance(target, Path)
        self._file: TextIO
        if isinstance(target, Path):
            target.parent.mkdir(parents=True, exist_ok=True)
            self._file = target.open("a", encoding="utf-8")
        else:
            self._file = target

    def emit(self, event: dict[str, Any]) -> None:
        self._file.write(json.dumps(event, separators=(",", ":"), sort_keys=True))
        self._file.write("\n")
        self._file.flush()

    def close(self) -> None:
        if self._owns_file:
            self._file.close()


class ConsoleEventHook(AgentHook):
    """Emit structured Console sidecar events from AthenaAgent hook callbacks."""

    def __init__(
        self,
        *,
        sink: ConsoleJsonlEventSink,
        task_id: str,
        run_id: str,
        agent_id: str,
        model: str | None = None,
    ) -> None:
        super().__init__()
        self._sink = sink
        self._task_id = task_id
        self._run_id = run_id
        self._agent_id = agent_id
        self._model = model

    def emit_lifecycle(self, event_type: str, **payload: Any) -> None:
        self._emit(event_type, payload)

    async def before_iteration(self, context: AgentHookContext) -> None:
        self._emit(
            "model.request",
            {
                "iteration": context.iteration,
                "messageCount": len(context.messages),
                **({"model": self._model} if self._model else {}),
            },
        )

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        if not context.tool_calls:
            return
        self._emit(
            "tool.started",
            {
                "iteration": context.iteration,
                "count": len(context.tool_calls),
                "tools": [
                    {
                        "id": tool_call.id,
                        "name": tool_call.name,
                    }
                    for tool_call in context.tool_calls
                ],
            },
        )

    async def after_iteration(self, context: AgentHookContext) -> None:
        if context.response is not None:
            self._emit(
                "model.response",
                {
                    "iteration": context.iteration,
                    "finishReason": context.response.finish_reason,
                    "usage": context.usage,
                    "toolCallCount": len(context.tool_calls),
                },
            )
        if context.tool_events:
            failed = [event for event in context.tool_events if event.get("status") != "ok"]
            self._emit(
                "tool.failed" if failed else "tool.completed",
                {
                    "iteration": context.iteration,
                    "count": len(context.tool_events),
                    "events": context.tool_events,
                },
            )
        if context.stop_reason and context.error:
            self._emit(
                "run.failed",
                {
                    "iteration": context.iteration,
                    "stopReason": context.stop_reason,
                    "error": context.error,
                },
            )

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._sink.emit(
            {
                "type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "taskId": self._task_id,
                "runId": self._run_id,
                "agentId": self._agent_id,
                "payload": payload,
            }
        )
