import io
import json
from pathlib import Path

import pytest

from athena_agent.athena_agent import RunResult
from athena_agent.agent.hook import AgentHookContext
from athena_agent.console_runner import main, run_console_envelope
from athena_agent.providers.base import LLMResponse, ToolCallRequest


def _envelope(repo_path: Path, agent_id: str = "athena-agent.repo-summary") -> dict[str, object]:
    return {
        "task": {
            "id": "task-1",
            "title": "Summarize repo",
            "description": "Pilot summary",
            "inputs": {
                "repo": {"path": str(repo_path)},
                "objective": "Explain the repo for onboarding.",
                "focus": "runtime bridge",
                "diff": "diff --git a/example.py b/example.py\n+ENABLED = True",
                "testLog": "FAIL tests/test_example.py\nExpected true but received false",
                "evidence": "Fixture evidence.",
                "memoryContext": "Prefer read-only workflows.",
            },
        },
        "agent": {"id": agent_id, "version": "0.1.0"},
        "run": {"id": "run-1"},
        "durableMemory": {
            "status": "permitted",
            "operations": {
                "propose": {
                    "namespaces": ["repository:demo"],
                    "maxSensitivity": "internal",
                }
            },
        },
        "modelProvider": {
            "id": "provider-1",
            "providerKind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "defaultModel": "github-copilot/gpt-5.3-codex",
            "apiKey": "sk-secret-value",
        },
    }


@pytest.mark.asyncio
async def test_run_console_envelope_returns_result_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    class FakeAgent:
        @classmethod
        def from_settings(cls, config, *, workspace=None):
            seen["provider"] = config.agents.defaults.provider
            seen["model"] = config.agents.defaults.model
            seen["api_base"] = config.providers.custom.api_base
            seen["restrict"] = config.tools.restrict_to_workspace
            seen["web"] = config.tools.web.enable
            seen["exec"] = config.tools.exec.enable
            seen["workspace"] = workspace
            return cls()

        async def run(self, message: str, *, session_key: str, hooks=None):
            seen["message"] = message
            seen["session_key"] = session_key
            seen["hooks"] = hooks
            return RunResult(content="# Summary\n\nLooks good.", tools_used=[], messages=[])

        async def close(self):
            seen["closed"] = True

    monkeypatch.setattr("athena_agent.console_runner.AthenaAgent", FakeAgent)

    result = await run_console_envelope(_envelope(tmp_path))

    assert result["output"]["markdown"] == "# Summary\n\nLooks good."
    assert result["artifacts"][0]["metadata"]["contentKey"] == "markdown"
    assert result["artifacts"][0]["storageUri"] == "memory://athena-agent/run-1/repo-summary.md"
    assert result["memoryRequests"] == []
    assert seen["provider"] == "custom"
    assert seen["model"] == "github-copilot/gpt-5.3-codex"
    assert seen["api_base"] == "https://provider.example/v1"
    assert seen["restrict"] is True
    assert seen["web"] is False
    assert seen["exec"] is False
    assert seen["workspace"] == tmp_path.resolve()
    assert seen["session_key"] == "console:task-1:run-1"
    assert seen["hooks"] is None
    assert seen["closed"] is True
    assert "Explain the repo for onboarding." in seen["message"]
    assert "Prefer read-only workflows." in seen["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_id", "expected_task", "expected_artifact"),
    [
        ("athena-agent.pr-diff-review", "review the supplied pull request or local diff", "pr-diff-review"),
        ("athena-agent.test-failure-triage", "triage the supplied test failure log", "test-failure-triage"),
    ],
)
async def test_run_console_envelope_supports_software_team_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_id: str,
    expected_task: str,
    expected_artifact: str,
) -> None:
    seen = {}

    class FakeAgent:
        @classmethod
        def from_settings(cls, _config, *, workspace=None):
            return cls()

        async def run(self, message: str, *, session_key: str, hooks=None):
            seen["message"] = message
            return RunResult(content="# Capability Output", tools_used=[], messages=[])

        async def close(self):
            pass

    monkeypatch.setattr("athena_agent.console_runner.AthenaAgent", FakeAgent)

    result = await run_console_envelope(_envelope(tmp_path, agent_id=agent_id))

    assert expected_task in seen["message"]
    assert "Supplied diff:" in seen["message"]
    assert "Supplied test failure log:" in seen["message"]
    assert result["artifacts"][0]["metadata"]["agentId"] == agent_id
    assert result["artifacts"][0]["metadata"]["capability"] == expected_artifact
    assert result["artifacts"][0]["storageUri"] == f"memory://athena-agent/run-1/{expected_artifact}.md"


@pytest.mark.asyncio
async def test_run_console_envelope_emits_opt_in_memory_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _envelope(tmp_path)
    envelope["task"]["inputs"]["memoryProposal"] = {
        "enabled": True,
        "targetNamespace": {"scope": "repository", "id": "demo"},
        "memoryType": "repo-convention",
        "proposedBody": "Prefer targeted authz tests for provider-backed agents.",
        "reason": "Stable convention observed during the run.",
        "evidence": "The run reviewed provider-backed authz coverage.",
    }

    class FakeAgent:
        @classmethod
        def from_settings(cls, _config, *, workspace=None):
            return cls()

        async def run(self, message: str, *, session_key: str, hooks=None):
            assert "Memory proposal policy:" in message
            return RunResult(content="# Summary", tools_used=[], messages=[])

        async def close(self):
            pass

    monkeypatch.setattr("athena_agent.console_runner.AthenaAgent", FakeAgent)

    result = await run_console_envelope(envelope)

    assert result["memoryRequests"] == [
        {
            "operation": "propose",
            "targetNamespace": {"scope": "repository", "id": "demo"},
            "memoryType": "repo-convention",
            "proposedBody": "Prefer targeted authz tests for provider-backed agents.",
            "reason": "Stable convention observed during the run.",
            "evidence": "The run reviewed provider-backed authz coverage.",
        }
    ]


@pytest.mark.asyncio
async def test_run_console_envelope_rejects_unpermitted_memory_proposal_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _envelope(tmp_path)
    envelope["task"]["inputs"]["memoryProposal"] = {
        "enabled": True,
        "targetNamespace": {"scope": "repository", "id": "other"},
        "memoryType": "repo-convention",
        "proposedBody": "Do not emit this.",
        "reason": "Wrong namespace.",
    }

    class FakeAgent:
        @classmethod
        def from_settings(cls, _config, *, workspace=None):
            return cls()

        async def run(self, message: str, *, session_key: str, hooks=None):
            return RunResult(content="# Summary", tools_used=[], messages=[])

        async def close(self):
            pass

    monkeypatch.setattr("athena_agent.console_runner.AthenaAgent", FakeAgent)

    with pytest.raises(Exception, match="namespace is not permitted"):
        await run_console_envelope(envelope)


@pytest.mark.asyncio
async def test_run_console_envelope_writes_sidecar_tool_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events_path = tmp_path / "events" / "run.jsonl"
    monkeypatch.setenv("ATHENA_AGENT_CONSOLE_EVENTS_PATH", str(events_path))

    class FakeAgent:
        @classmethod
        def from_settings(cls, _config, *, workspace=None):
            return cls()

        async def run(self, _message: str, *, session_key: str, hooks=None):
            hook = hooks[0]
            context = AgentHookContext(iteration=0, messages=[{"role": "user", "content": "hi"}])
            await hook.before_iteration(context)
            context.tool_calls = [ToolCallRequest(id="call-1", name="list_dir", arguments={"path": "."})]
            await hook.before_execute_tools(context)
            context.response = LLMResponse(content="", tool_calls=context.tool_calls, usage={"prompt_tokens": 7})
            context.usage = {"prompt_tokens": 7}
            context.tool_events = [{"name": "list_dir", "status": "ok", "detail": "listed"}]
            await hook.after_iteration(context)
            return RunResult(content="# Summary", tools_used=["list_dir"], messages=[])

        async def close(self):
            pass

    monkeypatch.setattr("athena_agent.console_runner.AthenaAgent", FakeAgent)

    result = await run_console_envelope(_envelope(tmp_path))

    assert result["output"]["markdown"] == "# Summary"
    records = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert [record["type"] for record in records] == [
        "run.started",
        "model.request",
        "tool.started",
        "model.response",
        "tool.completed",
        "artifact.created",
        "run.completed",
    ]
    assert records[2]["payload"]["tools"] == [{"id": "call-1", "name": "list_dir"}]
    assert records[4]["payload"]["events"][0]["status"] == "ok"


def test_main_writes_exactly_one_json_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(envelope):
        assert envelope["task"]["id"] == "task-1"
        return {"output": {"markdown": "ok"}, "artifacts": []}

    monkeypatch.setattr("athena_agent.console_runner.run_console_envelope", fake_run)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        stdin=io.StringIO(json.dumps(_envelope(tmp_path))),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue()) == {"output": {"markdown": "ok"}, "artifacts": []}
    assert stdout.getvalue().endswith("\n")


def test_main_redacts_provider_secret_from_success_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(envelope):
        secret = envelope["modelProvider"]["apiKey"]
        return {
            "output": {"markdown": f"summary includes {secret}"},
            "artifacts": [
                {
                    "label": "Summary",
                    "kind": "primary",
                    "format": "markdown",
                    "storageUri": "memory://athena-agent/run-1/repo-summary.md",
                    "metadata": {"leaked": secret},
                }
            ],
        }

    monkeypatch.setattr("athena_agent.console_runner.run_console_envelope", fake_run)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        stdin=io.StringIO(json.dumps(_envelope(tmp_path))),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "sk-secret-value" not in stdout.getvalue()
    assert "[redacted]" in stdout.getvalue()


def test_main_redacts_provider_secret_from_runtime_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(_envelope):
        raise RuntimeError("provider rejected sk-secret-value")

    monkeypatch.setattr("athena_agent.console_runner.run_console_envelope", fake_run)
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        stdin=io.StringIO(json.dumps(_envelope(tmp_path))),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "sk-secret-value" not in stderr.getvalue()
    assert "provider rejected [redacted]" in stderr.getvalue()


def test_main_reports_input_errors_without_echoing_secret(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    envelope["task"]["inputs"] = {}
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        stdin=io.StringIO(json.dumps(envelope)),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "repo.path" in stderr.getvalue()
    assert "sk-secret-value" not in stderr.getvalue()


def test_main_reports_invalid_repo_path_as_input_error(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    envelope["task"]["inputs"]["repo"]["path"] = str(tmp_path / "missing")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        stdin=io.StringIO(json.dumps(envelope)),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "Repository path does not exist" in stderr.getvalue()
    assert "sk-secret-value" not in stderr.getvalue()


def test_main_reports_missing_model_provider_as_input_error(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    del envelope["modelProvider"]
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        stdin=io.StringIO(json.dumps(envelope)),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "modelProvider" in stderr.getvalue()
