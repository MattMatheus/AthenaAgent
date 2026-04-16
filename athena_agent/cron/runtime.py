"""Runtime callback helpers for executing cron jobs through AgentLoop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from athena_agent.bus.events import OutboundMessage
from athena_agent.cron.supervisor import SupervisorExecutor
from athena_agent.cron.types import CronJob

if TYPE_CHECKING:
    from athena_agent.agent.loop import AgentLoop


def make_cron_runtime_callback(agent_loop: "AgentLoop"):
    """Build a CronService callback that executes jobs through AgentLoop."""

    async def _run_task(task: str, job: CronJob) -> str | None:
        session_key = f"cron:{job.id}"
        if job.payload.supervisor and job.payload.supervisor.session_key:
            session_key = job.payload.supervisor.session_key
        channel = job.payload.channel or "cli"
        chat_id = job.payload.to or "direct"

        cron_tool = agent_loop.tools.get("cron")
        token = None
        if cron_tool and hasattr(cron_tool, "set_cron_context"):
            token = cron_tool.set_cron_context(True)
        try:
            response = await agent_loop.process_direct(
                task,
                session_key=session_key,
                channel=channel,
                chat_id=chat_id,
            )
        finally:
            if cron_tool and token is not None and hasattr(cron_tool, "reset_cron_context"):
                cron_tool.reset_cron_context(token)

        if job.payload.supervisor and job.payload.supervisor.keep_recent_messages > 0:
            session = agent_loop.sessions.get_or_create(session_key)
            session.retain_recent_legal_suffix(job.payload.supervisor.keep_recent_messages)
            agent_loop.sessions.save(session)

        return response.content if response else None

    async def _notify(response: str, job: CronJob) -> None:
        if not job.payload.deliver or not job.payload.to:
            return
        await agent_loop.bus.publish_outbound(
            OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response,
            )
        )

    async def _on_job(job: CronJob) -> str | dict[str, str | None] | None:
        from athena_agent.utils.evaluator import evaluate_response

        if job.payload.kind == "system_event":
            return None

        if job.payload.kind == "supervisor_turn":
            executor = SupervisorExecutor(
                workspace=agent_loop.workspace,
                provider=agent_loop.provider,
                model=agent_loop.model,
                timezone=agent_loop.context.timezone,
                on_execute=_run_task,
                on_notify=_notify,
            )
            result = await executor.run_job(job)
            return {"status": result.status, "error": result.error}

        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )
        response = await _run_task(reminder_note, job)
        if not response:
            return None

        message_tool = agent_loop.tools.get("message")
        if job.payload.deliver and getattr(message_tool, "_sent_in_turn", False):
            return response

        if job.payload.deliver and job.payload.to:
            should_notify = await evaluate_response(
                response, reminder_note, agent_loop.provider, agent_loop.model,
            )
            if should_notify:
                await _notify(response, job)
        return response

    return _on_job
