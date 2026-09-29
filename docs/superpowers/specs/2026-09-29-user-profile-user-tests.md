# User Profile — user test plan (moderated)

**Goal:** Validate Profile IA before/after implementation.  
**Spec:** `2026-09-29-user-profile-design.md`  
**Participants:** 5–8 people familiar with chat products; mix logged-in vs first-time.  
**Environment:** staging or local with FakeLLM; one admin account for Guest MCP; kit optional.

## Protocol

- Task-based, think-aloud, ~25–35 min  
- Facilitator does not tip section names unless stuck >60s  
- Record: success / assist / fail; quotes; SUS optional at end  

## Tasks

| # | Task | Success looks like |
|---|---|---|
| T1 | «Найди, где твой аккаунт и имя» | Opens **Профиль** → **Аккаунт**; edits **Отображаемое имя** |
| T2 | «Смени пароль» | **Безопасность**; success status; understands device logout if token rotates |
| T3 | «Поставь модель по умолчанию и в избранное» | **Модели**; new chat uses default |
| T4 | «Ответы по-английски по умолчанию» | **Как отвечать** |
| T5 | «Новый чат — Два рядом» | **По умолчанию**; modes labelled **Обычный** / **Два рядом** |
| T6 | «Подключи свой MCP» (admin) | Finds **Подключения** via profile / composer link (no chip) |
| T7 | «Где краткий статус? Открой вахту MCP» | **Состояние** → CTA opens MCP shell |
| T8 | «Включи стиль ответа» | **Предпочтения** or Agents link |
| T9 | «Почисти историю только здесь» | **На этом устройстве** + confirm; no belief that server wiped |
| T10 | (Anonymous) Войти через профиль | Soft-gate; after login stays in Profile |
| T11 | Override только для этого чата | Composer settings session-only; finds «Подключения и модели — в профиле» |

## Heuristic probes (facilitator)

- First paint of Profile: can they name what the panel is for in one sentence?  
- Do they look for MCP under shell tab vs Profile?  
- Password errors readable?  
- Mobile (if device): can they switch sections without feeling lost?  

## Exit criteria (ship)

- ≥80% T1–T4, T9–T10 success without assist  
- T5–T8: no blocker confusion (assist OK for admin gate / Agents link)  
- Zero participants permanently lose ability to send chat after Profile flows  
- Design-lead blockers from review addressed before unmoderated follow-up  

## After tests

File notes under `docs/superpowers/plans/` or challenge folder if recording a demo; update spec § status to `validated` / list copy changes.
