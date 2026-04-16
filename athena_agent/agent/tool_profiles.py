"""Tool profile definitions and resolution helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

TOOL_IDENTS = {
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "glob",
    "grep",
    "exec",
    "web_search",
    "web_fetch",
    "spawn",
    "cron",
    "mcp",
    "message",
    "notebook",
}

BUILTIN_TOOL_PROFILES: dict[str, list[str]] = {
    "core": [
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "glob",
        "grep",
        "exec",
    ],
    "research": ["core", "web_search", "web_fetch"],
    "orchestrator": ["core", "spawn"],
    "scheduled": ["core", "cron", "spawn"],
    "mcp_first": ["core", "mcp"],
    # Compatibility profile for direct AgentLoop(...) construction during migration.
    "legacy_full": [
        "research",
        "scheduled",
        "mcp",
        "message",
        "notebook",
    ],
}


def resolve_tool_profile(
    profile_name: str,
    custom_profiles: Mapping[str, Sequence[str]] | None = None,
) -> set[str]:
    """Resolve a profile name into a concrete set of tool identifiers."""
    custom = custom_profiles or {}
    resolved: set[str] = set()
    stack: set[str] = set()

    def _expand(entry: str) -> None:
        if entry in TOOL_IDENTS:
            resolved.add(entry)
            return
        if entry in stack:
            raise ValueError(f"Cycle detected in tool profile resolution at '{entry}'")
        profile = custom.get(entry)
        if profile is None:
            profile = BUILTIN_TOOL_PROFILES.get(entry)
        if profile is None:
            raise ValueError(f"Unknown tool profile or tool id '{entry}'")
        stack.add(entry)
        for item in profile:
            _expand(item)
        stack.remove(entry)

    _expand(profile_name)
    return resolved
