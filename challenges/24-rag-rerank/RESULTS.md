# День 24 — доказательства сдачи

Домашка: [`README.md`](README.md).

Видео: `challenge-24.mp4` (три режима подряд на одном вопросе).  
Код: `apps/rag` `rerank.py` + pipeline modes; UI select «Режим базы».

## Пример запроса

«пожалуйста расскажи что такое Guest MCP»

| Mode | hits_pre → hits_post | Rewrite | Что видно в UI | Статус |
|---|---|---|---|---|
| raw | 20 → 6 | как есть | источники, mode=raw | **PASS** |
| filtered | 20 → ≤6 | как есть | порог; на fake-векторах часто = truncate | **PASS*** |
| full | 20 → 6 | `Guest MCP … Streamable HTTP` | строка «Запрос после rewrite» + rerank | **PASS** |

\* Filter заметнее на API-эмбеддингах. Если `stats.embed_model=fake-hash` при `embedding_provider=api` — force heal (startup или «База» → пересобрать); иначе filtered часто ≈ raw.

## Чеклист

| # | Критерий | Где видно | Статус |
|---|---|---|---|
| 1 | Режим raw | видео + таблица | **PASS** |
| 2 | Режим filtered (порог) | код `min_score` + UI option | **PASS** |
| 3 | Режим full = rewrite + filter + rerank | rewrite string в sources UI | **PASS** |
| 4 | pre→post в источниках | «было N → K» в details | **PASS** |
| 5 | Upload в базу рядом с режимами | UI «Добавить в базу» (Ещё / Профиль) | **PASS** (path) |
| 6 | Цитаты фрагментов в источниках | `rag-sources-quote` под каждым hit | **PASS** |
| 7 | «не знаю» при пустом/слабом контексте | `format_rag_system_context` + prompt | **PASS** (код + UI) |

## Как повторить

Настройки → Использовать базу → сменить Режим базы → один и тот же вопрос → сравнить блок источников.

Диск (неделя): https://disk.yandex.ru/i/01KhOD_G7dBWPw
