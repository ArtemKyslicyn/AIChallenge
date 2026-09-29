# User Profile panel — product UI/UX design

**Date:** 2026-09-29  
**Status:** implemented (v1 UI + auth APIs); user tests pending moderated run  
**Surface:** `apps/web` — topbar Profile overlay (not a new shell mode)  
**Related:** Guest MCP (`2026-09-27-guest-mcp-design.md`), kit hub (`2026-09-28-mcp-kit-hub-design.md`), platform design § auth post-v1  
**Follow-ups:** `2026-09-29-user-profile-architecture.md`, `2026-09-29-user-profile-user-tests.md`

## 0. Design-lead lock (2026-09-29)

Reviewed by designer-visual, interaction, density, a11y, brand; synthesized by design-lead.

**Ship as:** calm right drawer ~460px; sticky title **Профиль**; **grouped** left rail (10 destinations, not 10 equal pills); existing CSS tokens (no AuthPanel indigo).

**Composer:** remove «Свой MCP» chip + settings tabs **Подключения** and **Общие**; globals only in Profile; one link **«Подключения и модели — в профиле»**.

**Rail groups + locked labels**

| Group | Label | `?profile=` |
|---|---|---|
| Аккаунт | Аккаунт | `account` |
| | Безопасность | `security` |
| По умолчанию | Модели | `models` |
| | Как отвечать | `answers` |
| | По умолчанию | `chat` |
| Подключения | Подключения | `connections` |
| | Состояние | `stand` |
| На устройстве | Предпочтения | `personalization` |
| | На этом устройстве | `device` |
| | О продукте | `about` |

**Modes:** **Обычный** / **Два рядом**.  
**Logout:** **Выйти** only in Аккаунт; **Выйти на этом устройстве** in Безопасность.  
**Stand:** one status sentence + refresh + CTA closes Profile → MCP shell.  
**Connections:** GuestMcp list-first density mode.  
**a11y blockers:** dialog + focus trap + Esc nested; password labels; clear-history `alertdialog` (local only).  
**Auth:** shared state; after login stay in Profile and jump to intended section.

### A11y acceptance (from designer-a11y)

| Topic | Minimum |
|---|---|
| Overlay | `role="dialog"` + `aria-modal="true"` + trap + restore focus to topbar trigger + `inert` backdrop |
| Esc | Innermost first (confirm → mobile detail → profile); stopPropagation vs shell |
| Passwords | Visible labels; `autocomplete` current/new; `role="alert"` on errors; no paste block |
| Section nav | `nav` + `aria-current` **or** vertical tablist; gated = soft-gate, not dead clicks |
| Mobile | Visible **Назад**; Esc = back then close; focus restore both ways |
| Confirms | Clear history = `alertdialog`; focus cancel by default |
| Motion | `prefers-reduced-motion: reduce` → instant show/hide |
| Favorites | Accessible names + `aria-pressed`; not icon-only |

**Anonymous first paint (density):** show full rail only when signed in; anonymous = **Аккаунт** + one line «После входа — модели, ответы, подключения» (do not paint nine locked stubs).  
**Density note:** design-lead kept 10 destinations in **grouped** rail; if rail still wraps in implementation, prefer merge to 5 (`Аккаунт` · `Модели` · `Ответы` · `Подключения` · `Ещё`) without cutting features.

## 1. Problem

Account exists (login/register) but has no home. Generation defaults and Guest MCP live in the composer; stand pulse lives only on the MCP shell tab; personalization lives in Agents. Users cannot change password or display name. Product needs one **Профиль** for identity, security, defaults, connections, and a compact stand glance.

## 2. Decision

**Approach 1:** Full-height overlay / drawer from topbar account control.  
Not a sixth shell tab. Composer keeps **per-chat overrides** only.

**v1 models:** favorites + default from stand catalog (no BYOK keys).  
**Later:** BYOK LLM endpoints, server-synced prefs, email reset, analytics consent, data export, revoke-all tokens.

## 3. Information architecture

Left nav (or stacked anchors on narrow viewports):

| Id | Section | v1 content |
|---|---|---|
| `account` | Аккаунт | email (RO), display name (edit), logout |
| `security` | Безопасность | change password; logout this device |
| `models` | Модели | ★ favorites; default model for new chats; link to Models float ranking |
| `answers` | Ответы | language, temperature, reasoning, response template + custom rules |
| `chat` | Чат по умолчанию | default mode single/compare; Guest MCP on for new chats |
| `connections` | Подключения | embed `GuestMcpPanel`; kit README link |
| `stand` | Стенд | compact health/severity + one incident; refresh; CTA open MCP shell |
| `personalization` | Персонализация | active preference profile + lens; link to Agents for full CRUD |
| `device` | Данные на устройстве | visitor ≠ account copy; clear **local** chat history (confirm) |
| `about` | О продукте | kit link, model_id always attributed, short guest-MCP note |

Anonymous: panel opens on **Аккаунт** with login/register; other sections gated or show “войдите”.

## 4. UX rules (product)

1. **One job per section** — no card collage, no stat strips in the first paint of the panel.
2. **Composer slims down:** remove «Свой MCP» chip and settings tab **Подключения**; add one text-link «Глобальное — в профиле».
3. **Settings in composer** = session overrides only (mode, model, MCP toggle, template for *this* chat).
4. **Stand:** compact status only; full Pulse stays on shell **MCP** (ops board ≠ account home).
5. **Security:** current → new → confirm password; no “forgot password” until mailer exists.
6. **Favorites / defaults:** persist client-side keyed by `user:<id>` in v1; sync later.
7. **a11y:** focus trap in overlay, Esc closes, labelled sections, password fields with visible labels (not placeholder-only).
8. **Brand:** panel title **Профиль** is the hero of the overlay; section titles secondary. Domain-agnostic copy.

## 5. Entry points

| From | Action |
|---|---|
| Topbar | Click email / «Профиль» (logged in) or «Войти» (opens panel on account) |
| Composer | Link «Подключения и модели — в профиле» |
| MCP shell | Optional muted line: «Краткий статус — в профиле» (do not remove Pulse) |
| Deep link | `?profile=connections` / `?profile=models` (optional v1 if cheap) |

## 6. Visual / interaction sketch

- Desktop: ~420–480px right drawer or centered sheet max ~720px with left rail ~160px.
- Mobile: full-screen sheet; section list → detail (one level).
- Motion: 2 intentional — open/close overlay; section cross-fade or instant swap (prefer instant for density).
- Avoid purple-on-white / cream-serif / broadsheet defaults; follow existing chat CSS variables.

## 7. Out of scope v1

BYOK LLM, server prefs sync, email verify/reset, analytics consent UI, NDJSON user export, theme/density system, sound on SSE complete, moving full `McpCatalog` into Profile.
