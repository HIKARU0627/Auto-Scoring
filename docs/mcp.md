# MCP server configuration

Different agents read Model Context Protocol server config from different files.
This template keeps three files that must stay in sync:

| File                      | Agent(s)                          |
| ------------------------- | --------------------------------- |
| `.mcp.json`               | Claude Code                       |
| `.cursor/mcp.json`        | Cursor                            |
| `.agents/mcp_config.json` | Antigravity / OpenCode / Codex 系 |

They all describe the same servers; only the surrounding key differs
(`mcpServers` entry uses `url` vs `serverUrl` vs `type`+`url` depending on the
agent). When you add or change a server, edit all three.

## Example: adding an HTTP MCP server

`.mcp.json` and `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "example": { "type": "http", "url": "https://mcp.example.com/mcp?..." }
  }
}
```

`.agents/mcp_config.json`:

```json
{
  "mcpServers": {
    "example": { "serverUrl": "https://mcp.example.com/mcp?..." }
  }
}
```

Keep secrets out of these files — they are committed. Use per-agent local
overrides or environment variables for tokens.
