# ObsidianMCP Integration

AthenaAgent should use `obsidianMCP` as an external MCP server, not as code folded into the runtime package.

## Recommendation

Keep `obsidianMCP` separated.

Why:

- AthenaAgent already has a generic MCP client/runtime path through `tools.mcpServers`.
- `obsidianMCP` is intentionally a standalone server process with its own lifecycle, release flow, tests, and desktop plugin.
- The Obsidian bridge plugin is part of the `obsidianMCP` architecture, not part of AthenaAgent.
- Folding the Go server into the Python runtime would create packaging and release coupling without adding capability.

The clean boundary is:

- AthenaAgent owns agent orchestration, sessions, tools, scheduler, and MCP client wiring.
- `obsidianMCP` owns vault access, indexing, and the optional Obsidian desktop bridge.

## What AthenaAgent Already Supports

AthenaAgent's MCP config already supports exactly what `obsidianMCP` needs:

- stdio servers
- command + args
- environment variables
- optional tool allowlisting

That means wiring it in is configuration work, not runtime code work.

## Recommended Wiring

Build or install the `obsidianMCP` binary, then register it under `tools.mcpServers`.

Example `~/.athena-agent/config.json` fragment:

```json
{
  "tools": {
    "mcpServers": {
      "obsidian": {
        "type": "stdio",
        "command": "/absolute/path/to/obsidianMCP",
        "args": ["mcp"],
        "env": {
          "OBSIDIAN_VAULT": "SharedKnowledge",
          "OBSIDIAN_CONFIG": "/absolute/path/to/obsidianmcp.json",
          "OBSIDIAN_RPC_URL": "http://127.0.0.1:27124",
          "OBSIDIAN_COMMAND_TIMEOUT": "1m0s"
        }
      }
    }
  }
}
```

If you only want a subset of tools exposed, add `enabledTools`:

```json
{
  "tools": {
    "mcpServers": {
      "obsidian": {
        "type": "stdio",
        "command": "/absolute/path/to/obsidianMCP",
        "args": ["mcp"],
        "env": {
          "OBSIDIAN_VAULT": "SharedKnowledge",
          "OBSIDIAN_CONFIG": "/absolute/path/to/obsidianmcp.json"
        },
        "enabledTools": [
          "read_note",
          "search_vault",
          "append_note",
          "mcp_obsidian_create_note"
        ]
      }
    }
  }
}
```

`enabledTools` accepts either:

- raw MCP names like `read_note`
- wrapped AthenaAgent names like `mcp_obsidian_create_note`

## Practical Setup

Use a built or installed `obsidianMCP` binary and point AthenaAgent at it through config or onboarding.

That keeps the dependency boundary simple:

- AthenaAgent launches the MCP server as an external process.
- `obsidianMCP` remains independently installable and releasable.

## Suggested Operating Pattern

Use `obsidianMCP` for:

- project notes
- research notes
- plans and checklists
- supervisor inputs/outputs that should stay human-visible

Use AthenaAgent internal memory for:

- recent execution continuity
- compact retained runtime memory
- session state that should not be edited manually

## What Not To Do

Avoid:

- copying `obsidianMCP` Go code into the AthenaAgent Python package
- re-implementing Obsidian note tools natively inside AthenaAgent
- coupling AthenaAgent releases to the Obsidian plugin lifecycle

That would make the architecture worse, not better.

## If We Want Better UX Later

The right future improvements are lightweight helpers, not deeper coupling:

- add an onboarding shortcut that writes an `obsidian` MCP server block
- add a canned config/example generator for local `obsidianMCP`
- add supervisor examples that read from and write to Obsidian notes

Those would improve setup while keeping the runtime boundary clean.
