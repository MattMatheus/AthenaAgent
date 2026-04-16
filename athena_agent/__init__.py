"""AthenaAgent runtime package."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib


def _read_pyproject_version() -> str | None:
    """Read the source-tree version when package metadata is unavailable."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _resolve_version() -> str:
    for package_name in ("athena-agent",):
        try:
            return _pkg_version(package_name)
        except PackageNotFoundError:
            continue
    # Source checkouts often import the runtime without installed dist-info.
    return _read_pyproject_version() or "0.1.5.post1"


__version__ = _resolve_version()
__logo__ = "🐈"

from athena_agent.athena_agent import AthenaAgent, RunResult

__all__ = ["AthenaAgent", "RunResult"]
