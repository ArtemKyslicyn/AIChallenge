# Local LLM source — design

**Date:** 2026-10-08
**Status:** approved for planning
**Related:** platform design, RAG design (`2026-09-30-rag-service-design.md`), Guest MCP URL policy

## 1. Problem

Course days 26–29 need a local model that answers from this product: chat, Agent 07 memory, and the week 21–25 RAG index. The operator chain (`LLM_BASE_URL` / `LLM_MODEL_CHAIN`) stays the cloud default. A signed-in user adds their own Ollama from Profile → Подключения.

The course model is the one SkyNet already uses, not the 8B tags on this Mac.

Live catalog on the M1 (`cab-wsm-0022444`, `http://100.90.210.109:11435`, checked 2026-10-08 with curl; `/api/tags` returned 200, nothing was loaded in `/api/ps`):

| Tag | Size | Quant | Disk |
|---|---|---|---|
| `qwen36-fast:latest` | 35.5B (parent `qwen3.6:35b`) | Q4_K_M | 22.6 GB |
| `qwen3.6:35b` / `qwen3.6:35b-a3b` | 35.5B | Q4_K_M | 22.6 GB |
| `qwen38-fast:latest` | 27.3B | Q4_K_M | 17.7 GB |
| `qwen3.5:9b` / `qwen35-fast:latest` | 9.0B | Q4_K_M | 6.6 GB |
| `deepseek-coder:33b` | 33B | Q4_0 | 18.8 GB |

Graded pin: `ollama/qwen36-fast:latest`. Port is **11435**, not 11434. SkyNet (`Documents/Kalinin`, `OllamaFallbackChatClient`) already posts native `/api/chat` here with `think: false`, `temperature` 0.4, and `num_predict`. Direct `:11434` on that host refuses the connection.

`kalinin-gpu` (`100.126.31.97`) is the Windows GPU box. SkyNet bots on that machine talk to llama-server at `http://127.0.0.1:8080/v1`, model `qwen3.6-35b-a3b-local` (fast comments: `qwen3.5-9b-fast`). From this Mac the documented path is SSH host `kalinin-gpu` (port 2222) with `LocalForward 21434 → 127.0.0.1:11434`, so Ollama appears locally as `http://127.0.0.1:21434` while `ssh -N kalinin-gpu` is up. On 2026-10-08 both SSH `:2222` and direct `:8080` / `:11434` to that peer timed out, so the live runtime for the three days is the M1. The profile still accepts the tunnel URL when the box is reachable.

This Mac's Ollama (`127.0.0.1:11434`) only has `qwen3:8b` and `llama3.1:8b`. Those stay available as a loopback source. They are not the submission model. A cold 8B load was 12.9 s; a 22 GB M1 model can exceed the cloud first-token budget of 25 s, so an `ollama/` pin uses 90 s.

## 2. Decisions

1. **One enabled Ollama origin per user**, stored in Postgres. Reconnect replaces the row. The browser never calls Ollama.
2. **Catalog id** is `ollama/<upstream>`, upstream is the Ollama tag (`qwen36-fast:latest`). Cloud ids stay `vendor/model`. Persisted `model_id`, SSE, and the bubble use the catalog id.
3. **Transport is native** `POST {origin}/api/chat` with `"think": false` and `"stream": true`. The OpenAI shim `POST /v1/chat/completions` on `qwen3:8b` puts text in `message.reasoning` and leaves `content` empty until `max_tokens` is large. The existing adapter reads only `content` and treats empty as provider failure.
4. **Pin, not AUTO.** `auto` keeps walking `LLM_MODEL_CHAIN`. A local answer happens when the user pins `ollama/…`. A failed local pin does not fall through to the cloud chain.
5. **Discovery** is server-side `GET {origin}/api/tags`, timeout 8 s. Cached tag names live on the row. Chat checks the pin against that cache.
6. **Generation knobs already in the product** (`temperature`, `max_tokens`, stop, prompt template) are forwarded as Ollama `options`. `num_ctx` stays an Ollama host setting. A second quant is out of scope: `qwen36-fast` is already Q4_K_M.
7. **RAG index stays.** `apps/rag` keeps search. Generation uses whatever the router resolved, including `ollama/…`. Query embeddings of the existing stand index stay on `EMBEDDING_PROVIDER=api` (`text-embedding-3-small`). Re-embedding locally is a later plan: it invalidates the week-6 matrix.
8. **URL policy** is separate from Guest MCP, because Ollama on a LAN is HTTP:
   - `http://127.0.0.1:11434`, `localhost`, `::1`, `host.docker.internal`, and the kalinin forward `127.0.0.1:21434` when `LOCAL_LLM_ALLOW_LOOPBACK=true`
   - Tailscale CGNAT `100.64.0.0/10` when `LOCAL_LLM_ALLOW_TAILSCALE=true` (this is how the M1 at `100.90.210.109:11435` is reached)
   - other RFC1918 only when `LOCAL_LLM_ALLOW_PRIVATE=true`
   - metadata / link-local always blocked
   - stored value is `scheme://host:port` with no path
9. **Empty API key** is valid. The column is nullable and never returned.
10. **Cloud first-token timeout stays 25 s. An `ollama/` pin uses 90 s.** `think: false` still applies. SkyNet already sends that flag to the M1.

## 3. Out of scope

- Production deploy, xray, Reality, `compose down`
- Pointing `LLM_BASE_URL` at a laptop
- Multiple sources per user, `num_ctx` in the API, Q8/F16 downloads
- Local re-embed of the stand index
- Telegram bot or a new CLI app (day 27 is this web app)
- Video binaries in git

## 4. Data

Table `user_llm_sources` (Alembic `013`, revises `012`):

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `user_id` | FK `users.id` ON DELETE CASCADE, UNIQUE |
| `name` | ≤ 80, display |
| `base_url` | canonical origin |
| `api_key` | nullable, write-only |
| `enabled` | bool |
| `status` | `connected` \| `error` \| `off` |
| `safe_error` | nullable, no URL secrets |
| `models_json` | JSON array of upstream tags |
| `updated_at` | timestamptz |

## 5. Request path

```text
Profile connect → POST /api/v1/me/llm-sources
                → SSRF check → GET /api/tags → upsert row

GET /api/v1/llm/models
                → env catalog + ollama/<tag> for the signed-in user

Chat / agent / probe pin ollama/qwen36-fast:latest
                → ContextVar user id (set from the existing auth dependency)
                → RoutingLLMProvider
                     cloud model → existing OpenAICompatibleProvider
                     ollama/*    → OllamaNativeProvider (think: false)
                → TokenChunk.model_id = ollama/qwen36-fast:latest
```

`RoutingLLMProvider` is the provider inside the existing `ModelRouter`. Call sites in `chat.py`, `agent_run.py`, `battle_run.py`, and `llm_probe.py` stay on the router. Judge and cascade keep using cloud model ids; they never receive an `ollama/` pin unless an operator puts one in `JUDGE_MODEL` (unsupported, left to fail as a missing local user).

Anonymous requests have no user in the context var. An `ollama/` pin then fails with a Russian safe error and does not call the cloud.

## 6. Course mapping

| Day | Folder | What proves it |
|---|---|---|
| 26 | `challenges/26-local-llm` | curl `http://100.90.210.109:11435/api/tags` shows `qwen36-fast`, then 3 native chats to that tag. |
| 27 | `challenges/27-local-app` | Profile source = M1 `:11435`, bubble `ollama/qwen36-fast:latest`, Agent 07 lines `Имя: Артем` / `Язык: Python` |
| 28 | `challenges/28-local-rag` | Same pin, question about `:443`, base off then on. Sources footer. Embeddings may still be the API embedder. |
| 29 | `challenges/29-local-optimize` | Same 35B tag, two option sets, table of wall time, tok/s, faithfulness. Quant column is `Q4_K_M`. |

The three prompts, rising:

1. Remember name Артем and language Python. Answer with exactly two lines.
2. What is `model_id` on this stand? (day 22 question 1)
3. Where does public `:443` go, and is `docker compose down` allowed on prod? (day 22 questions 2 and 9)

Day 29 keeps the same before/after knobs (temperature 0.8 vs 0.15, short `num_predict`, stand fragments in the system prompt). The 8B run on this Mac is only a warning: small models invent the port chain. The graded run is `qwen36-fast:latest` on the M1. When `ssh -N kalinin-gpu` is up, a second profile source `http://127.0.0.1:21434` can list whatever Ollama is installed on the GPU box; the bot's llama-server on `:8080` stays on that machine and is not required for these days.

## 7. Acceptance

- `USE_FAKE_LLM=true` suite stays green. Cloud chain behavior unchanged when the pin is not `ollama/`.
- Unit test: native provider sends `think: false` and returns `content`, rewriting `model_id` to `ollama/qwen36-fast:latest`.
- Unit test: metadata IP and bare private IP are rejected; loopback passes only with the flag; `100.126.31.97` passes only with the tailscale flag.
- Connect endpoint never returns `api_key`.
- Assistant row and SSE `model` event carry `ollama/qwen36-fast:latest`.
