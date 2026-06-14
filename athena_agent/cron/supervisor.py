"""Supervisor-style cron job execution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from athena_agent.cron.types import CronJob

if TYPE_CHECKING:
    from athena_agent.providers.base import LLMProvider

MCPCall = Callable[[str, dict[str, object]], Awaitable[str]]

_SUPERVISOR_DECISION_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "supervisor_decision",
            "description": "Decide whether a scheduled supervisor job should run now.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                        "description": "skip = nothing actionable, run = execute the supervisor job",
                    },
                    "task": {
                        "type": "string",
                        "description": "Optional execution task distilled from the source context.",
                    },
                },
                "required": ["action"],
            },
        },
    }
]


@dataclass(slots=True)
class SupervisorRunResult:
    """Result of executing a supervisor job."""

    status: str
    task: str = ""
    response: str | None = None
    error: str | None = None
    source_content: str = ""
    should_notify: bool | None = None


class SupervisorExecutor:
    """Execute cron supervisor jobs with source loading, gating, and notify policy."""

    def __init__(
        self,
        *,
        workspace: Path,
        provider: "LLMProvider",
        model: str,
        timezone: str | None = None,
        on_execute: Callable[[str, CronJob], Awaitable[str | None]] | None = None,
        on_notify: Callable[[str, CronJob], Awaitable[None]] | None = None,
        mcp_call: MCPCall | None = None,
    ) -> None:
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.timezone = timezone
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.mcp_call = mcp_call

    @staticmethod
    def _parse_mcp_source_ref(source_ref: str) -> tuple[str, str]:
        server, sep, ref = source_ref.partition(":")
        if not sep or not server.strip() or not ref.strip():
            raise ValueError(
                "MCP supervisor source_ref must use 'server:ref' format"
            )
        return server.strip(), ref.strip()

    async def _load_source(self, job: CronJob) -> str:
        spec = job.payload.supervisor
        if spec is None:
            return job.payload.message
        if spec.source_kind == "inline":
            return spec.source_ref or job.payload.message
        if spec.source_kind == "file":
            ref = Path(spec.source_ref).expanduser()
            path = ref if ref.is_absolute() else (self.workspace / ref)
            return path.read_text(encoding="utf-8")
        if spec.source_kind in ("mcp_note", "mcp_query"):
            if self.mcp_call is None:
                raise ValueError("MCP source loading is not configured")
            server, ref = self._parse_mcp_source_ref(spec.source_ref)
            if spec.source_kind == "mcp_note":
                return await self.mcp_call(f"mcp_{server}_read_note", {"path": ref})
            return await self.mcp_call(f"mcp_{server}_search_vault", {"query": ref})
        raise ValueError(f"Unsupported supervisor source_kind '{spec.source_kind}'")

    async def _decide(self, job: CronJob, source_content: str) -> tuple[str, str]:
        spec = job.payload.supervisor
        if spec is None or spec.decision_mode == "always_run":
            return "run", ""

        from athena_agent.utils.helpers import current_time_str

        response = await self.provider.chat_with_retry(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a scheduled supervisor gate. "
                        "Call the supervisor_decision tool to decide whether to run."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Current Time: {current_time_str(self.timezone)}\n\n"
                        f"Job: {job.name}\n"
                        f"Decision Prompt: {spec.decision_prompt or '(none)'}\n"
                        f"Execution Prompt: {spec.execution_prompt or job.payload.message or '(none)'}\n\n"
                        "Source Context:\n"
                        f"{source_content}"
                    ),
                },
            ],
            tools=_SUPERVISOR_DECISION_TOOL,
            model=self.model,
            max_tokens=256,
            temperature=0.0,
        )
        if not response.has_tool_calls:
            return "skip", ""
        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("task", "")

    @staticmethod
    def _build_task(job: CronJob, source_content: str, gated_task: str) -> str:
        if gated_task:
            return gated_task
        spec = job.payload.supervisor
        prompt = ""
        if spec and spec.execution_prompt:
            prompt = spec.execution_prompt
        elif job.payload.message:
            prompt = job.payload.message
        if source_content:
            if prompt:
                return f"{prompt}\n\nSource context:\n{source_content}"
            return source_content
        return prompt

    async def run_job(self, job: CronJob) -> SupervisorRunResult:
        """Run a supervisor job and return structured result metadata."""
        from athena_agent.utils.evaluator import evaluate_response

        if job.payload.kind != "supervisor_turn":
            raise ValueError("SupervisorExecutor can only run supervisor_turn jobs")

        try:
            source_content = await self._load_source(job)
        except Exception as exc:
            return SupervisorRunResult(status="error", error=str(exc))

        action, gated_task = await self._decide(job, source_content)
        if action != "run":
            return SupervisorRunResult(status="skipped", source_content=source_content)

        task = self._build_task(job, source_content, gated_task)
        if not task:
            return SupervisorRunResult(
                status="error",
                error="Supervisor job produced no execution task",
                source_content=source_content,
            )
        if self.on_execute is None:
            return SupervisorRunResult(
                status="error",
                error="Supervisor execute callback is not configured",
                task=task,
                source_content=source_content,
            )

        response = await self.on_execute(task, job)
        result = SupervisorRunResult(
            status="ok",
            task=task,
            response=response,
            source_content=source_content,
        )

        spec = job.payload.supervisor
        policy = spec.notify_policy if spec else "evaluate"
        if response and self.on_notify and policy != "never":
            should_notify = True
            if policy == "evaluate":
                should_notify = await evaluate_response(
                    response, task, self.provider, self.model,
                )
            result.should_notify = should_notify
            if should_notify:
                await self.on_notify(response, job)

        return result
