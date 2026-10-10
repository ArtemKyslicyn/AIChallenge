# Local LLM handoff (days 26–30)

The human implements and records. This file locks the API and the screen. The longer build steps stay in `docs/superpowers/plans/2026-10-08-local-llm-source.md`. The design spec is `docs/superpowers/specs/2026-10-08-local-llm-source-design.md`.

Day 26 is already shot: `challenges/26-local-llm/challenge-26.mp4`. Do not reshoot it on the 8B tags. Graded model: `ollama/qwen36-fast:latest` on `http://100.90.210.109:11435`.

Production deploy is allowed when the human asks. No xray edits.

## Routes

Auth is the existing `X-Auth-Token`. Anonymous users get no row and no `ollama/` ids.

| Method | Path | Body / result |
|---|---|---|
| `PUT` | `/api/v1/me/llm-sources` | `name`, `base_url`, optional `api_key`. Returns `name`, `base_host`, `status`, `models`, `enabled`. Never the key or the full URL. |
| `GET` | `/api/v1/me/llm-sources` | The same object, or `null`. |
| `DELETE` | `/api/v1/me/llm-sources` | `204`. |
| `GET` | `/api/v1/llm/models` | Cloud catalog, then `ollama/<tag>` for the signed-in user. |

`PUT` canonicalizes the origin, then `GET {origin}/api/tags` with an 8 second timeout, then replaces the one row. Unreachable host: `502` and «Ollama недоступен по этому адресу.» Blocked address: `400` and «Этот адрес подключить нельзя.»

Chat, probe, workshop, and battle keep calling `container.router`. Bind the source inside the SSE generator (and around non-stream awaits), then reset it in `finally`. A pin `ollama/…` uses native `POST /api/chat` with `think: false` and a 90 second first-token budget. It does not fall through to the cloud chain. `auto` stays the cloud chain.

Day 30 reuses `max_message_chars` (8000 → 422) and adds `local_llm_requests_per_hour` (default 30) counted only for `ollama/` calls. Over the cap: `429` and «Слишком много запросов подряд. Подождите немного и напишите снова.»

## Screen

Order in Подключения: база знаний → локальная модель → свой MCP.

1. Signed out: the line «Сначала войдите.» No form.
2. Signed in, no source: title, status, one button «Подключить». Fields stay closed.
3. «Подключить» opens «Название», «Адрес Ollama», «Ключ (необязательно)». Hint under the address, exactly: `M1 http://100.90.210.109:11435. Туннель: http://127.0.0.1:21434. Этот Mac: http://127.0.0.1:11434.`
4. Empty key is valid. Never echo it.
5. Save is the 8 second tags check. The button stays enabled (`aria-busy`, ignore a second submit). This screen does not say 90 seconds.
6. Success collapses the fields. Status: «Подключено: {host}. Моделей: {n}.» No tag chips. Delete is `type="button"` with accessible name «Удалить локальную модель».
7. Errors go to a separate alert. The status live region stays mounted even when empty.
8. The id `ollama/qwen36-fast:latest` is chosen in Модели and printed on the existing chat badge. «Авто» never selects it.
9. Until the first token, the empty bubble shows that id, a seconds counter, and «Модель грузится, до 90 с.»

## What to record after the endpoints exist

1. **27.** Save the M1 URL. Collapsed line, no 90-second copy on the button. Pin the 35B id. Memory prompt. Badge matches. Lines `Имя: Артем` and `Язык: Python`.
2. **28.** Same pin. Question about public `:443` with the base off, then on. Sources footer only when it is on.
3. **29.** Same question twice. Before: temperature 0.8, long answer, no system text. After: temperature 0.15, shorter cap, «только по фрагментам». Table: seconds, tokens/s, faithfulness, quant `Q4_K_M`.
4. **30.** Local API only. Three successful pinned calls. One call over `max_message_chars` returns 422. A burst returns 429 with the rate-limit sentence. The browser never calls `:11435` itself.
