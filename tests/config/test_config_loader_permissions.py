import os
import stat

import pytest

from athena_agent.config.loader import save_config
from athena_agent.config.schema import Config


@pytest.mark.skipif(os.name == "nt", reason="POSIX perms")
def test_save_config_creates_owner_only_file_and_directory(tmp_path):
    config_path = tmp_path / "nested" / "config.json"

    save_config(Config(), config_path)

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX perms")
def test_save_config_tightens_existing_file_permissions(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    os.chmod(config_path, 0o644)

    save_config(Config(), config_path)

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
