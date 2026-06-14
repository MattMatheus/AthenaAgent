import os

import pytest

from athena_agent.session.manager import Session, SessionManager


def test_session_save_round_trips_messages_and_last_consolidated(tmp_path):
    manager = SessionManager(workspace=tmp_path)
    session = Session(
        key="cli:atomic",
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        last_consolidated=1,
    )

    manager.save(session)
    manager.invalidate(session.key)
    loaded = manager.get_or_create(session.key)

    assert loaded.messages == session.messages
    assert loaded.last_consolidated == 1


def test_session_save_leaves_no_temp_files(tmp_path):
    manager = SessionManager(workspace=tmp_path)
    session = Session(key="cli:temp", messages=[{"role": "user", "content": "hello"}])

    manager.save(session)

    assert list(manager.sessions_dir.glob("*.tmp")) == []


def test_failed_atomic_replace_preserves_previous_session_file(tmp_path, monkeypatch):
    manager = SessionManager(workspace=tmp_path)
    original = Session(key="cli:replace", messages=[{"role": "user", "content": "old"}])
    manager.save(original)

    updated = Session(key="cli:replace", messages=[{"role": "user", "content": "new"}])

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        manager.save(updated)

    manager.invalidate(original.key)
    loaded = manager.get_or_create(original.key)
    assert loaded.messages == original.messages
    assert list(manager.sessions_dir.glob("*.tmp")) == []
