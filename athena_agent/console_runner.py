"""Console-compatible runner entry point for AthenaAgent."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from athena_agent.athena_agent import AthenaAgent
from athena_agent.config.schema import Config
from athena_agent.console_events import ConsoleEventHook, ConsoleJsonlEventSink
from athena_agent.console_runtime import (
    ConsoleRuntimeConfigError,
    config_from_console_model_provider,
)


class ConsoleRunnerError(ValueError):
    """Raised for operator-correctable Console runner failures."""


async def run_console_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Run AthenaAgent from a Console task envelope and return a result envelope."""
    task = _require_record(envelope.get("task"), "task")
    agent = _require_record(envelope.get("agent"), "agent")
    run = _require_record(envelope.get("run"), "run")
    task_id = _require_string(task, "id", "task.id")
    agent_id = _require_string(agent, "id", "agent.id")
    run_id = _require_string(run, "id", "run.id")
    inputs = _require_record(task.get("inputs"), "task.inputs")
    repo_path = _resolve_repo_path(inputs)

    config = config_from_console_model_provider(
        _require_record(envelope.get("modelProvider"), "modelProvider"),
        workspace=repo_path,
    )
    _apply_console_guardrails(config)

    capability = _resolve_console_capability(agent_id)
    prompt = _build_console_prompt(
        capability=capability,
        task=task,
        agent_id=agent_id,
        repo_path=repo_path,
        inputs=inputs,
    )
    event_sink, event_hook = _build_console_event_hook(
        task_id=task_id,
        run_id=run_id,
        agent_id=agent_id,
        model=config.agents.defaults.model,
    )
    try:
        bot = AthenaAgent.from_settings(config, workspace=repo_path)
        try:
            if event_hook:
                event_hook.emit_lifecycle("run.started", repositoryPath=str(repo_path))
            result = await bot.run(
                prompt,
                session_key=f"console:{task_id}:{run_id}",
                hooks=[event_hook] if event_hook else None,
            )
        except Exception as error:
            if event_hook:
                event_hook.emit_lifecycle(
                    "run.failed",
                    error=_safe_error(error, _collect_runtime_secrets(envelope)),
                )
            raise
        finally:
            await bot.close()

        markdown = result.content.strip() or "No repository summary content was returned."
        memory_requests = _build_memory_requests(inputs, envelope)
        artifact_id = f"artifact-{run_id}-{capability['artifact_slug']}"
        storage_uri = f"memory://athena-agent/{run_id}/{capability['artifact_slug']}.md"
        envelope_result = {
            "output": {
                "markdown": markdown,
            },
            "memoryRequests": memory_requests,
            "artifacts": [
                {
                    "id": artifact_id,
                    "label": capability["artifact_label"],
                    "kind": "primary",
                    "format": "markdown",
                    "storageUri": storage_uri,
                    "metadata": {
                        "contentKey": "markdown",
                        "repositoryPath": str(repo_path),
                        "agentId": agent_id,
                        "capability": capability["id"],
                    },
                }
            ],
        }
        if event_hook:
            event_hook.emit_lifecycle(
                "artifact.created",
                artifactId=artifact_id,
                label=capability["artifact_label"],
                format="markdown",
                storageUri=storage_uri,
            )
            event_hook.emit_lifecycle("run.completed", artifactCount=1)
        return envelope_result
    finally:
        if event_sink:
            event_sink.close()


def main(
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run the Console runner CLI."""
    envelope: dict[str, Any] | None = None
    secrets: list[str] = []
    try:
        envelope = _parse_stdin(stdin.read())
        secrets = _collect_runtime_secrets(envelope)
        result = asyncio.run(run_console_envelope(envelope))
    except (ConsoleRunnerError, ConsoleRuntimeConfigError) as error:
        stderr.write(f"Console runner input error: {_redact_text(str(error), secrets)}\n")
        return 2
    except Exception as error:
        stderr.write(f"Console runner failed: {_safe_error(error, secrets)}\n")
        return 1

    stdout.write(json.dumps(_redact_value(result, secrets), separators=(",", ":")))
    stdout.write("\n")
    return 0


def _parse_stdin(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConsoleRunnerError(f"stdin must be a JSON task envelope: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ConsoleRunnerError("stdin must be a JSON object.")
    return parsed


def _resolve_repo_path(inputs: dict[str, Any]) -> Path:
    repo = inputs.get("repo")
    candidates: list[Any] = []
    if isinstance(repo, dict):
        candidates.extend([
            repo.get("path"),
            repo.get("workspacePath"),
            repo.get("workspace_path"),
        ])
    candidates.extend([
        inputs.get("repoPath"),
        inputs.get("repositoryPath"),
    ])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            path = Path(candidate).expanduser().resolve()
            if not path.exists():
                raise ConsoleRunnerError(f"Repository path does not exist: {path}")
            if not path.is_dir():
                raise ConsoleRunnerError(f"Repository path is not a directory: {path}")
            return path
    raise ConsoleRunnerError("task.inputs.repo.path or task.inputs.repoPath is required.")


def _apply_console_guardrails(config: Config) -> None:
    defaults = config.agents.defaults
    defaults.max_tool_iterations = min(defaults.max_tool_iterations, 40)
    defaults.max_tool_result_chars = min(defaults.max_tool_result_chars, 12_000)
    config.tools.restrict_to_workspace = True
    config.tools.web.enable = False
    config.tools.exec.enable = False
    config.tools.exec.allowed_env_keys = []


def _resolve_console_capability(agent_id: str) -> dict[str, str]:
    if agent_id == "athena-agent.repo-summary":
        return {
            "id": "repo-summary",
            "artifact_slug": "repo-summary",
            "artifact_label": "Repository Summary",
            "task": "produce a concise, evidence-backed repository summary for an operator.",
            "sections": "\n".join([
                "- Repository purpose and product role.",
                "- Important directories and files inspected.",
                "- Architecture observations.",
                "- Development and validation commands discovered.",
                "- Risks, unknowns, or missing context.",
                "- Suggested next tasks.",
            ]),
        }
    if agent_id == "athena-agent.pr-diff-review":
        return {
            "id": "pr-diff-review",
            "artifact_slug": "pr-diff-review",
            "artifact_label": "PR Diff Review",
            "task": "review the supplied pull request or local diff for correctness, safety, and test risk.",
            "sections": "\n".join([
                "- Summary of the change.",
                "- Correctness and regression risks.",
                "- Security, secrets, and data-handling concerns.",
                "- Test coverage observations.",
                "- Concrete review comments or follow-up checks.",
            ]),
        }
    if agent_id == "athena-agent.test-failure-triage":
        return {
            "id": "test-failure-triage",
            "artifact_slug": "test-failure-triage",
            "artifact_label": "Test Failure Triage",
            "task": "triage the supplied test failure log and propose the next local diagnostic steps.",
            "sections": "\n".join([
                "- Failure summary.",
                "- Most likely root causes.",
                "- Repository areas or files to inspect.",
                "- Reproduction and diagnostic commands.",
                "- Suggested fix strategy and confidence.",
            ]),
        }
    raise ConsoleRunnerError(f"Unsupported AthenaAgent Console agent id: {agent_id}")


def _build_console_prompt(
    *,
    capability: dict[str, str],
    task: dict[str, Any],
    agent_id: str,
    repo_path: Path,
    inputs: dict[str, Any],
) -> str:
    objective = _optional_string(inputs, "objective") or _optional_string(task, "description")
    focus = _optional_string(inputs, "focus")
    memory_context = _optional_string(inputs, "memoryContext")
    memory_proposal = inputs.get("memoryProposal")
    lines = [
        "You are running as an AthenaAgent-powered Console capability.",
        f"Agent id: {agent_id}",
        f"Repository workspace: {repo_path}",
        "",
        f"Task: {capability['task']}",
        "Stay within the repository workspace. Do not modify files. Do not run destructive commands.",
        "Do not reveal provider secrets, environment secrets, or hidden runtime configuration.",
        "",
        "Include these sections:",
        capability["sections"],
    ]
    diff = _optional_string(inputs, "diff")
    test_log = _optional_string(inputs, "testLog") or _optional_string(inputs, "test_log")
    evidence = _optional_string(inputs, "evidence")
    if objective:
        lines.extend(["", f"Operator objective: {objective}"])
    if focus:
        lines.extend(["", f"Focus area: {focus}"])
    if diff:
        lines.extend(["", "Supplied diff:", diff])
    if test_log:
        lines.extend(["", "Supplied test failure log:", test_log])
    if evidence:
        lines.extend(["", "Additional evidence:", evidence])
    if memory_context:
        lines.extend(["", "Approved memory context:", memory_context])
    if isinstance(memory_proposal, dict) and memory_proposal.get("enabled") is True:
        lines.extend([
            "",
            "Memory proposal policy:",
            "Only propose durable memory for stable, reusable repository guidance explicitly requested by the operator.",
            "Do not propose secrets, one-off observations, or speculative conclusions.",
        ])
    return "\n".join(lines)


def _build_memory_requests(inputs: dict[str, Any], envelope: dict[str, Any]) -> list[dict[str, Any]]:
    proposal = inputs.get("memoryProposal")
    if not isinstance(proposal, dict) or proposal.get("enabled") is not True:
        return []

    target_namespace = proposal.get("targetNamespace")
    if not _is_namespace_ref(target_namespace):
        raise ConsoleRunnerError("task.inputs.memoryProposal.targetNamespace must include scope and id.")
    _assert_memory_namespace_allowed(envelope, target_namespace)

    memory_type = _required_input_string(proposal, "memoryType", "task.inputs.memoryProposal.memoryType")
    proposed_body = _required_input_string(proposal, "proposedBody", "task.inputs.memoryProposal.proposedBody")
    reason = _required_input_string(proposal, "reason", "task.inputs.memoryProposal.reason")
    request: dict[str, Any] = {
        "operation": "propose",
        "targetNamespace": target_namespace,
        "memoryType": memory_type,
        "proposedBody": proposed_body,
        "reason": reason,
    }
    evidence = _optional_string(proposal, "evidence")
    if evidence:
        request["evidence"] = evidence
    return [request]


def _assert_memory_namespace_allowed(envelope: dict[str, Any], namespace: dict[str, Any]) -> None:
    durable_memory = envelope.get("durableMemory")
    if not isinstance(durable_memory, dict) or durable_memory.get("status") != "permitted":
        raise ConsoleRunnerError("Durable memory proposal requested but propose access is not permitted.")
    operations = durable_memory.get("operations")
    propose = operations.get("propose") if isinstance(operations, dict) else None
    namespaces = propose.get("namespaces") if isinstance(propose, dict) else None
    if not isinstance(namespaces, list) or not any(
        isinstance(scope, str) and _namespace_matches(scope, namespace) for scope in namespaces
    ):
        raise ConsoleRunnerError(
            f"Durable memory proposal namespace is not permitted: {namespace['scope']}:{namespace['id']}"
        )


def _namespace_matches(scope: str, namespace: dict[str, Any]) -> bool:
    normalized = f"{namespace['scope']}:{namespace['id']}"
    if scope.endswith("/*"):
        prefix = scope[:-1]
        return normalized.startswith(prefix) or str(namespace["id"]).startswith(prefix)
    return scope == normalized or scope == namespace["id"]


def _is_namespace_ref(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("scope"), str)
        and bool(value["scope"].strip())
        and isinstance(value.get("id"), str)
        and bool(value["id"].strip())
    )


def _required_input_string(values: dict[str, Any], key: str, label: str) -> str:
    value = _optional_string(values, key)
    if not value:
        raise ConsoleRunnerError(f"{label} is required.")
    return value


def _build_console_event_hook(
    *,
    task_id: str,
    run_id: str,
    agent_id: str,
    model: str | None,
) -> tuple[ConsoleJsonlEventSink | None, ConsoleEventHook | None]:
    event_path = os.environ.get("ATHENA_AGENT_CONSOLE_EVENTS_PATH")
    if not event_path:
        return None, None
    sink = ConsoleJsonlEventSink(Path(event_path).expanduser().resolve())
    return sink, ConsoleEventHook(
        sink=sink,
        task_id=task_id,
        run_id=run_id,
        agent_id=agent_id,
        model=model,
    )


def _require_record(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConsoleRunnerError(f"{label} must be an object.")
    return value


def _require_string(values: dict[str, Any], key: str, label: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConsoleRunnerError(f"{label} is required.")
    return value.strip()


def _optional_string(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    return value.strip() if isinstance(value, str) else ""


def _collect_runtime_secrets(envelope: dict[str, Any]) -> list[str]:
    model_provider = envelope.get("modelProvider")
    if isinstance(model_provider, dict):
        api_key = model_provider.get("apiKey")
        if isinstance(api_key, str) and api_key:
            return [api_key]
    return []


def _redact_value(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if isinstance(value, list):
        return [_redact_value(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, secrets) for key, item in value.items()}
    return value


def _redact_text(value: str, secrets: list[str]) -> str:
    redacted = value
    for secret in secrets:
        redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _safe_error(error: Exception, secrets: list[str]) -> str:
    message = str(error).strip()
    safe_message = message if message else error.__class__.__name__
    return _redact_text(safe_message, secrets)


if __name__ == "__main__":
    raise SystemExit(main())
