# Guest MCP JSON packs

Signed-in users can import a pack in **Чат → Свой MCP → Подключения**.

## Formats

AIChallenge:

```json
{
  "servers": [
    { "name": "kit", "url": "https://….trycloudflare.com/mcp", "token": "optional" }
  ]
}
```

Cursor / Claude style:

```json
{
  "mcpServers": {
    "kit": {
      "url": "https://….trycloudflare.com/mcp",
      "headers": { "Authorization": "Bearer optional" }
    }
  }
}
```

Stdio servers (`command` / `args`) are skipped — the cloud API cannot reach your laptop process. Publish them as Streamable HTTP (see `aichallenge-mcp-kit` plan) and put the tunnel URL in the pack.

Example file: `configs/guest-mcp-pack.example.json` (placeholders only, no secrets).
