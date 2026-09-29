# MCP Kit Hub — design (public repo)

**Date:** 2026-09-28  
**Status:** approved (approach 2 + hierarchical groups + Python sandbox)  
**Repo:** public GitHub `aichallenge-mcp-kit` (separate from AIChallenge monorepo)  
**Related:** `docs/superpowers/specs/2026-09-27-guest-mcp-design.md` §3

## 1. Problem

AIChallenge guest MCP speaks only **URL + Bearer** (Streamable HTTP). Local stdio tools (filesystem, git, montage, Godot, Blender) and “run Python on my machine” cannot reach production chat until something on the user’s computer publishes one HTTPS endpoint.

Visitors also need:

- **Hierarchical** attach of arbitrary child MCPs (dev, media, apps)
- **File in → process on PC → file out** (montage, builds) without stuffing large binaries through chat SSE
- **Sandboxed Python** execution under the same hub URL

## 2. Decision

Ship a **separate public repo** `aichallenge-mcp-kit`:

| Concern | Where |
|---|---|
| Chat / guest registry / SSRF | AIChallenge only |
| Hub gateway, children, sandbox, artifacts | `aichallenge-mcp-kit` only |

AIChallenge never vendors kit processes. Kit never talks to AIChallenge Postgres or stand `/mcp/*`.

**Approach:** Hub + artifact HTTP (not multi-URL mesh, not thin gateway without blobs).

## 3. Architecture

```text
AIChallenge chat  --Bearer-->  https://tunnel…/mcp  (kit hub)
                                    |
                    +---------------+----------------+
                    |               |                |
                 groups/dev     groups/media    /artifacts
                 fs,git,python   montage…       PUT/GET bytes
                    |
              child MCP (stdio|http)
```

- One bind: `127.0.0.1:3100` (tunnel is the only public surface).
- Same Bearer for `/mcp` and `/artifacts`.
- Tool names: `{group}__{child}__{tool}`; hub tools: `hub_*`.

## 4. Manifest (`kit.yaml`)

Copied from `kit.example.yaml`. Groups → children:

```yaml
workspace: ./workspace
bind: 127.0.0.1:3100
token_env: KIT_SHARED_TOKEN

groups:
  - id: dev
    children:
      - id: fs
        transport: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-filesystem", "./workspace/projects"]
      - id: git
        transport: stdio
        command: uvx
        args: ["mcp-server-git", "--repository", "./workspace/projects"]
      - id: python
        transport: builtin
        module: python_sandbox
      - id: shell
        transport: builtin
        module: hub_run
        enabled: false
  - id: media
    children:
      - id: montage
        transport: stdio
        enabled: false
        # command/args filled by user
```

Failed child at startup: omit its tools; hub stays up; status visible via `hub_list_children`.

## 5. Hub tools (v1)

| Tool | Role |
|---|---|
| `hub_list_children` | Tree: group → child → status → tool_count |
| `hub_workspace_list` | List under `KIT_WORKSPACE` |
| `hub_workspace_put` | Small files (base64) into workspace |
| `hub_workspace_get` | Metadata + `artifact_id` / download hint |
| `hub_run` | Optional allowlisted binaries; **default off** |

## 6. Artifacts

```http
POST /artifacts          → { id, upload_url, download_url, expires_at }
PUT  /artifacts/{id}     → body bytes
GET  /artifacts/{id}     → file
```

All require Bearer. Store under `workspace/artifacts/`. Config: max size, TTL. Tool results return `artifact_id` + tunnel URL — not multi‑MB base64 in SSE.

**v1 site:** no composer upload required; paste kit URL into Guest MCP. Later: UI cards for `artifact://` (separate AIChallenge task).

## 7. Python sandbox (`dev__python__*`)

Builtin module (not raw host `exec`):

| Control | v1 |
|---|---|
| Cwd | `workspace/sandboxes/{session_id}/` |
| Network | off by default |
| Timeout | 30s (config) |
| Packages | preinstalled / `sandbox_requirements.txt` only; no chat `pip install` |
| Isolation | subprocess minimum; docker/bwrap when available |

Tools: `exec`, `write`, `read`, `reset`. Binaries from sandbox → `/artifacts`.

Forbidden: reading kit `.env`, escaping workspace, arbitrary shell inside python tools.

## 8. Connect to AIChallenge

1. Clone kit, copy `.env.example` → `.env`, set `KIT_SHARED_TOKEN`
2. Copy `kit.example.yaml` → `kit.yaml`, enable children
3. Start hub → `cloudflared tunnel --url http://127.0.0.1:3100`
4. Site (logged in): Свой MCP → URL `https://…/mcp` + same token  
   Optional: import `packs/aichallenge-guest.example.json` (url placeholder, no secret)

## 9. Security

- Bind loopback only
- Path traversal blocked under workspace
- Secrets only in kit `.env` (gitignored); public repo has placeholders only
- Document: URL+token = control of sandboxed machine capabilities you enabled
- `hub_run` allowlist + cwd=workspace when enabled

## 10. Out of scope (v1)

- OAuth / one-click “Connect PC” without paste
- Composer → kit upload via AIChallenge API
- Shipping Godot/Blender binaries inside the kit
- Merging kit into AIChallenge monorepo

## 11. Success

Mac user: clone public kit → run `dev` profile → tunnel → Guest MCP connect → chat can `hub_list_children`, run `dev__python__exec`, and fetch an artifact URL for an output file — without opening stand `/mcp/*`.
