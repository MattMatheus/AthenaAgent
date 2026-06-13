"""High-level programmatic interface to the AthenaAgent runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from athena_agent.agent.hook import AgentHook
from athena_agent.agent.loop import AgentLoop
from athena_agent.bus.queue import MessageBus
from athena_agent.cron.service import CronService


@dataclass(slots=True)
class RunResult:
    """Result of a single agent run."""

    content: str
    tools_used: list[str]
    messages: list[dict[str, Any]]


class AthenaAgent:
    """Programmatic facade for running the AthenaAgent runtime.

    Usage::

        bot = AthenaAgent.from_config()
        result = await bot.run("Summarize this repo", hooks=[MyHook()])
        print(result.content)
    """

    def __init__(self, loop: AgentLoop, cron_service: CronService | None = None) -> None:
        self._loop = loop
        self._cron = cron_service
        self._cron_started = False

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
        *,
        workspace: str | Path | None = None,
    ) -> "AthenaAgent":
        """Create an AthenaAgent instance from a config file.

        Args:
            config_path: Path to ``config.json``.  Defaults to
                ``~/.athena-agent/config.json``.
            workspace: Override the workspace directory from config.
        """
        from athena_agent.config.loader import load_config, resolve_config_env_vars
        from athena_agent.config.schema import Config

        resolved: Path | None = None
        if config_path is not None:
            resolved = Path(config_path).expanduser().resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Config not found: {resolved}")

        config: Config = resolve_config_env_vars(load_config(resolved))
        if workspace is not None:
            config.agents.defaults.workspace = str(
                Path(workspace).expanduser().resolve()
            )

        return cls.from_settings(config, workspace=None)

    @classmethod
    def from_settings(
        cls,
        config: Any,
        *,
        workspace: str | Path | None = None,
    ) -> "AthenaAgent":
        """Create an AthenaAgent instance from an in-memory config object.

        This entry point is intended for embedded runtimes that already own
        configuration resolution, such as Console-launched task runners. It
        does not read ``~/.athena-agent/config.json``.
        """
        from athena_agent.config.loader import resolve_config_env_vars

        resolved_config = resolve_config_env_vars(config.model_copy(deep=True))
        if workspace is not None:
            resolved_config.agents.defaults.workspace = str(
                Path(workspace).expanduser().resolve()
            )
        loop, cron = _build_loop(resolved_config)
        return cls(loop, cron_service=cron)

    async def start(self) -> None:
        """Start background scheduler services when available."""
        if self._cron and not self._cron_started:
            await self._cron.start()
            self._cron_started = True

    async def close(self) -> None:
        """Stop background services and close runtime resources."""
        if self._cron and self._cron_started:
            self._cron.stop()
            self._cron_started = False
        await self._loop.close_mcp()

    async def __aenter__(self) -> "AthenaAgent":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def run(
        self,
        message: str,
        *,
        session_key: str = "sdk:default",
        hooks: list[AgentHook] | None = None,
    ) -> RunResult:
        """Run the agent once and return the result.

        Args:
            message: The user message to process.
            session_key: Session identifier for conversation isolation.
                Different keys get independent history.
            hooks: Optional lifecycle hooks for this run.
        """
        prev = self._loop._extra_hooks
        started_here = False
        if hooks is not None:
            self._loop._extra_hooks = list(hooks)
        try:
            if self._cron and not self._cron_started:
                await self.start()
                started_here = True
            response = await self._loop.process_direct(
                message, session_key=session_key,
            )
        finally:
            self._loop._extra_hooks = prev
            if started_here:
                await self.close()

        content = (response.content if response else None) or ""
        return RunResult(content=content, tools_used=[], messages=[])


def _build_loop(config: Any) -> tuple[AgentLoop, CronService]:
    """Build the runtime loop and cron service from resolved settings."""
    provider = _make_provider(config)
    bus = MessageBus()
    defaults = config.agents.defaults
    cron = CronService(config.workspace_path / "cron" / "jobs.json")

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=defaults.model,
        max_iterations=defaults.max_tool_iterations,
        context_window_tokens=defaults.context_window_tokens,
        context_block_limit=defaults.context_block_limit,
        max_tool_result_chars=defaults.max_tool_result_chars,
        provider_retry_mode=defaults.provider_retry_mode,
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        timezone=defaults.timezone,
        unified_session=defaults.unified_session,
        disabled_skills=defaults.disabled_skills,
        session_ttl_minutes=defaults.session_ttl_minutes,
        tool_profile=config.tools.profiles.default_profile,
        subagent_tool_profile=config.tools.profiles.subagent_profile,
        custom_tool_profiles=config.tools.profiles.custom_profiles,
    )
    from athena_agent.cron.runtime import make_cron_runtime_callback

    cron.on_job = make_cron_runtime_callback(loop)
    return loop, cron

def _make_provider(config: Any) -> Any:
    """Create the LLM provider from config (extracted from CLI)."""
    from athena_agent.providers.base import GenerationSettings
    from athena_agent.providers.registry import find_by_name

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    spec = find_by_name(provider_name) if provider_name else None
    backend = spec.backend if spec else "openai_compat"

    if backend == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            raise ValueError("Azure OpenAI requires api_key and api_base in config.")
    elif backend == "openai_compat" and not model.startswith("bedrock/"):
        needs_key = not (p and p.api_key)
        exempt = spec and (spec.is_oauth or spec.is_local or spec.is_direct)
        if needs_key and not exempt:
            from athena_agent.providers.github_copilot_provider import get_github_copilot_login_status
            from athena_agent.providers.openai_codex_provider import get_openai_codex_login_status

            message = (
                f"No API key configured for provider '{provider_name}'. "
                f"The current default model is '{model}'."
            )
            if get_openai_codex_login_status():
                message += (
                    " OpenAI Codex OAuth is available; set agents.defaults.model to "
                    "'openai-codex/gpt-5.1-codex' to use your ChatGPT/Codex subscription."
                )
            elif get_github_copilot_login_status():
                message += (
                    " GitHub Copilot OAuth is available; set agents.defaults.model to "
                    "'github-copilot/gpt-5.3-codex' to use that login."
                )
            raise ValueError(message)

    if backend == "openai_codex":
        from athena_agent.providers.openai_codex_provider import OpenAICodexProvider

        provider = OpenAICodexProvider(default_model=model)
    elif backend == "github_copilot":
        from athena_agent.providers.github_copilot_provider import GitHubCopilotProvider

        provider = GitHubCopilotProvider(default_model=model)
    elif backend == "azure_openai":
        from athena_agent.providers.azure_openai_provider import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            api_key=p.api_key, api_base=p.api_base, default_model=model
        )
    elif backend == "anthropic":
        from athena_agent.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
        )
    else:
        from athena_agent.providers.openai_compat_provider import OpenAICompatProvider

        provider = OpenAICompatProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            spec=spec,
        )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider
