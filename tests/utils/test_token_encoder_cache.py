import json

import tiktoken

from athena_agent.utils import helpers


def test_cl100k_encoder_is_cached():
    helpers._get_cl100k_encoder.cache_clear()

    assert helpers._get_cl100k_encoder() is helpers._get_cl100k_encoder()


def test_estimate_message_tokens_matches_tiktoken_count():
    message = {
        "role": "user",
        "content": "hello world",
        "name": "alice",
        "tool_call_id": "call_123",
        "reasoning_content": "scratch",
    }
    payload = "\n".join(
        [
            "hello world",
            "alice",
            "call_123",
            "scratch",
        ]
    )
    enc = tiktoken.get_encoding("cl100k_base")

    assert helpers.estimate_message_tokens(message) == max(4, len(enc.encode(payload)) + 4)


def test_estimate_prompt_tokens_matches_tiktoken_count():
    messages = [
        {"role": "user", "content": "hello world", "name": "alice"},
        {
            "role": "assistant",
            "content": "done",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "x"}}],
        },
    ]
    tools = [{"type": "function", "function": {"name": "x"}}]
    parts = [
        "hello world",
        "alice",
        "done",
        json.dumps(messages[1]["tool_calls"], ensure_ascii=False),
        json.dumps(tools, ensure_ascii=False),
    ]
    enc = tiktoken.get_encoding("cl100k_base")

    assert helpers.estimate_prompt_tokens(messages, tools) == len(enc.encode("\n".join(parts))) + 8


def test_estimate_message_tokens_falls_back_when_encoder_raises(monkeypatch):
    def fail_encoder():
        raise RuntimeError("no encoder")

    monkeypatch.setattr(helpers, "_get_cl100k_encoder", fail_encoder)

    assert helpers.estimate_message_tokens({"role": "user", "content": "hello world"}) == 6
