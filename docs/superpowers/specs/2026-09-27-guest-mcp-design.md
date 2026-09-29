# Guest MCP — Design Spec

**Date:** 2026-09-27  
**Status:** Approved for implementation plan (2026-09-27)  
**Depends on:** chat platform spec `2026-08-31-ai-chat-platform-design.md`, stand MCP catalog, anonymous sessions  
**Decision locked:** Approach **A** — visitor pastes Streamable HTTP URL + Bearer; chat calls those tools. Stand Pulse unchanged.

## 1. Goal

Visitor connects **their** MCP from the computer (public HTTPS tunnel or local URL) and uses ordinary chat as the agent surface: git, files, iOS/Android device, tests — without replacing the stand MCP or days 16–21 videos.

Challenge addendum: **вариант 3** on days 16–21 (connect own kit, first successful tool from chat). Old handshake / LiveWhoToAsk stories stay.

## 2. Product analytics

### 2.1 Jobs

| Job | Who | Success |
|---|---|---|
| J1 Prove variant 3 | Challenge / video | Settings → connect → ordinary chat calls one guest tool; `model_id` on the reply |
| J2 Experiment on my machine | Visitor with a kit | Second session reconnects; ≥1 guest invoke/week |
| J3 Mobile from chat | iOS/Android kit via tunnel | First device tool (`mobile_list`, `simctl`, `adb`, …) returns without hanging chat |

Stand Pulse (вахта, рейтинг, бриф) is a **different** product. Do not mix its events with guest connect.

### 2.2 North star

**Time-to-first-guest-tool:** open Settings → Подключения → successful handshake → first `tool_result` from a guest server in ordinary chat.

Activation: `guest_mcp_connect_ok` **and** `guest_mcp_tool_ok` in the same visitor week.  
Retention: same `url_host` connected again after 7 days (name/host only — never store token in analytics).

### 2.3 Funnel (ops-console events)

Fail-open emit, same as other product events. **Never** put URL query, token, or tool args in `props`.

| Event | When | Props (safe) |
|---|---|---|
| `settings_opened` | Настройки open | `tab` |
| `guest_mcp_connect_started` | Submit Подключить | `url_host`, `has_token` |
| `guest_mcp_connect_ok` | Handshake + list tools | `url_host`, `tool_count`, `latency_ms` |
| `guest_mcp_connect_fail` | Handshake fail | `url_host`, `reason` (`timeout` \| `unauthorized` \| `ssrf` \| `unreachable` \| `bad_url`) |
| `guest_mcp_toggled` | Enable on/off | `enabled`, `url_host` |
| `guest_mcp_disconnect` | Delete | `url_host` |
| `guest_mcp_tool_started` | SSE `tool_start` guest | `tool_name`, `url_host` |
| `guest_mcp_tool_ok` | SSE `tool_result` ok | `tool_name`, `url_host`, `latency_ms` |
| `guest_mcp_tool_fail` | Tool/SSE fail | `tool_name`, `url_host`, `reason` (`timeout` \| `unreachable` \| `tool_error`) |

Funnel in admin: `settings_opened(tab=connections)` → `connect_started` → `connect_ok` → `tool_ok`.

### 2.4 Guardrails

- Handshake timeout **8s** (same budget as pulse). Guest invoke **12s**. Chat composer stays typable.
- Guest tools only when `chatMode === single`. ×2 / ×T / ×4 skip guest MCP (hint only).
- Chat **never** `POST /mcp/invoke`. Stand allowlist and pulse stay on `/mcp/*`.
- Token never in list DTO, UI live region, transcript, or analytics.

## 3. Separate kit repo (local MCP hub)

AIChallenge only speaks **URL + Bearer**. Local stdio servers (filesystem, git, Xcode, montage, …) cannot be reached from prod until they are published as Streamable HTTP.

**Public repo** (not this monorepo): [`aichallenge-mcp-kit`](https://github.com/ArtemKyslicyn/aichallenge-mcp-kit) — hierarchical **hub** + artifact HTTP + Python sandbox.

Full design: `docs/superpowers/specs/2026-09-28-mcp-kit-hub-design.md`.

Job of that repo: one process listens on `/mcp` (+ `/artifacts`) with a visitor-chosen token; `kit.yaml` attaches child MCPs in **groups** (`dev`, `media`, …). README: Cloudflare/ngrok one-liner → paste URL into Свой MCP / Настройки.

### 3.1 Children to wrap (researched; enabled via kit manifest)

| Use | Repo / package | Why |
|---|---|---|
| Files | `@modelcontextprotocol/server-filesystem` | Official read/write in a sandbox dir |
| Git | `mcp-server-git` (official) | Status, diff, commit on a local repo |
| Python sandbox | **builtin** in kit | Exec under `workspace/sandboxes/` (network off by default) |
| GitHub | `github/github-mcp-server` | PRs/issues (token on the kit, not in AIChallenge `.env`) |
| iOS + Android UI | `mobile-next/mobile-mcp` | Sim/device; has `--listen` Streamable HTTP on `/mcp` |
| iOS Xcode | `r-huijts/xcode-mcp-server`, `lapfelix/XcodeMCP` | Build / project on a Mac |
| Android diagnose | ADB-oriented MCP (`us-all/android` and similar) | logcat / dumpsys; HTTP + `MCP_HTTP_TOKEN` |
| Browser tests | `microsoft/playwright-mcp` | Web + Expo web |
| Expo / EAS | `CaullenOmdahl/expo-mcp-server` | Optional profile |
| Montage / media | user stdio MCP or allowlisted `ffmpeg` via `hub_run` | Edit locally; return via `/artifacts` |

Default kit profile **dev**: filesystem + git + python sandbox. Optional groups: **media**, **mobile**, **github**.

AIChallenge UI: link to the public kit README + Guest MCP connect / JSON pack. No clone/run UI inside the chat app.

## 4. Architecture (hexagonal, assignment layout)

Same rule as the platform spec: **domain → application → adapters**. Guest MCP does **not** reuse `settings.mcp_base_url` / `MCP_SHARED_TOKEN`.

```
apps/api/src/app/
  domain/guest_mcp.py          # GuestMcpServer, SSRF policy, ports
  application/guest_mcp.py     # connect / list / enable / disconnect
  adapters/guest_mcp_http.py   # Streamable HTTP + Bearer client
  adapters/persistence/…       # session-scoped registry (token server-side only)
  adapters/api/guest_mcp.py    # /sessions/{id}/guest-mcp
  application/chat.py          # if enabled + single → offer guest tools on SSE
```

### 4.1 Domain

- `GuestMcpServer`: `id`, `name`, `url`, `enabled`, `tool_names`, `status`, `safe_error`
- `GuestMcpRegistry` port: CRUD by `session_id`; **read DTO has no token**
- `GuestMcpClient` port: `handshake(url, token) -> tools`, `call_tool(url, token, name, args)`
- SSRF: allow `https` public hosts; `http://127.0.0.1` / `localhost` only when `GUEST_MCP_ALLOW_LOOPBACK=true` (local/dev). Block link-local, metadata IPs, non-http(s)

### 4.2 Application

- `connect_guest_mcp` — 8s handshake, persist token server-side, return list DTO
- `list_guest_mcp` / `set_guest_enabled` / `disconnect_guest_mcp`
- Chat stream: if session has enabled guests and mode is single, pass guest tools into the existing MCP-round (same `tool_start` / `tool_result`). Cap 12s. On fail, safe SSE error, do not hang

### 4.3 HTTP

| Method | Path | Auth |
|---|---|---|
| `GET` | `/sessions/{id}/guest-mcp` | session token |
| `POST` | `/sessions/{id}/guest-mcp` | body: name, url, token |
| `PATCH` | `/sessions/{id}/guest-mcp/{sid}` | `{ enabled }` |
| `DELETE` | `/sessions/{id}/guest-mcp/{sid}` | |

**Do not** add guest routes under `/mcp/*`. Stand `list_tools` / `pulse` / `invoke` stay as they are.

### 4.4 Persistence

Session-scoped. New chat starts with empty guest set. Browser may remember `{name, url}` **without token** for re-fill. Token lives only in API session store.

## 5. UI (design-lead + settings review)

Reviewed by designer-visual, interaction, density, a11y, brand; synthesized by design-lead; settings/form pass.

**Locked placement:** Настройки → third tab **«Подключения»** is the only connect/list UI. Shell MCP tab stays Stand Pulse + one link «свой сервер — в Настройках». Chat: one muted line `MCP · {name}` when a guest is connected (opens that tab). No form on empty chat, no extra mode chip.

### 5.1 Experiments we ran (and dropped)

| Idea | Verdict |
|---|---|
| Wizard on empty chat / LiveWhoToAsk | Drops — already one dashboard (`.live-who`) |
| Chip `MCP·N` on options bar | Drops — bar is full; muted hint only |
| Mount `McpCatalog` in composer | Blocker — Pulse is an ops page |
| Form on «Общие» | Drops — wrong object type (resource vs prefs) |
| Primary form on MCP tab | Drops — user asked Cursor-like **settings**; Pulse videos stay |
| Pinned stand row with fake toggle | Drops — stand is not a guest; one line + MCP-tab link |
| Invoke buttons in settings | Drops — first tool is ordinary chat SSE |

### 5.2 Tab chrome

- `SettingsTab = "global" | "session" | "connections"`
- Strip: 3 columns, single-line labels **Общие · Чат · Подключения**, `min-height: 24px`
- Panel: `max-height: min(40vh, 22rem); overflow-y: auto`
- Guest form is its **own** `<form>` above the message form (Enter must not send chat)

### 5.3 Подключения

- Lead: «Адрес с вашего компьютера. Стенд на вкладке MCP не выключается.»
- CTA «Добавить по URL» → name, `type="url"`, `type="password"` token, **Подключить**
- Collapsed rows: name/host, status, on/off, `N умений`, delete (confirm)
- One row expanded: tool chips (cap ~6 + «ещё N»), Переподключить
- Help link to kit repo
- Handshake busy is **local** to the form — never `Chat.busy`

### 5.4 Этот чат

Toggle: «Свой сервер в этом чате» (default on after connect). No URL/token here.  
Hint: «В ×2, ×T и ×4 набор не вызывается.»

### 5.5 Thread

Guest `tool_start`: «Вызываю {name} на вашем сервере…» — **not** a media job card.  
`model_id` still on the assistant bubble.

## 6. Challenge variant 3

Add the same paragraph to days 16–21 VERSION-2 (or README). **Do not** replace `challenge-16`…`20` or `версия 2` videos.

> Старые версии: handshake на вкладке MCP и карточка «Кому писать» в чате. Их не удаляем.  
> Продукт: посетитель вставляет адрес своего набора (iPhone, Android или git) в Настройках → Подключения и видит, что обычный чат умеет спрашивать уже его сервер. Не протокол — подключение и первый опыт у себя. Под ответом по-прежнему виден `model_id`.

## 7. Non-goals (v1)

- No stdio from the browser, no auto-tunnel helper in this monorepo  
- No import of Cursor `mcp.json`  
- No guest tools in compare / ×T / ×4  
- No Pulse redesign, no 7th shell tab  
- No medical/role naming  
- Kit repo is separate; AIChallenge does not vendor those servers

## 8. Testing

- Unit: SSRF, 401, timeout, list DTO has no token (Fake guest client)  
- Chat: SSE `tool_start`/`tool_result` for guest names; skip when mode ≠ single  
- Web: settings form not nested in send form; handshake does not disable textarea  
- Stand tests (`test_mcp_catalog`, `test_agent_mcp`) stay green and unchanged in intent  
- `apps/web` `npm run build`

## 9. Success

- Visitor connects a kit URL and chat calls a guest tool without opening the MCP tab  
- Stand Pulse and days 16–21 videos still make sense  
- Ops funnel shows connect → first tool without leaking secrets  
- Architecture matches the assignment: ports + use cases + HTTP adapter, Fake in tests
