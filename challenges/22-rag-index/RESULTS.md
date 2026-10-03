# День 22 — RESULTS (чеклист)

Корпус (compose): `docs/` + `README.md` + `AGENTS.md` + `CLAUDE.md` → **58** файлов.  
Прод stats: `GET /api/v1/rag/stats` → structural **761** чанков (совпадает с таблицей).  
Видео: `challenge-22.mp4` (UI: Профиль / настройки + оверлей цифр из этой таблицы).

## Сравнение стратегий

| Метрика | fixed | structural |
|---|---|---|
| chunks | **620** | **761** |
| avg chars | **770.5** | **547.6** |
| indexed_files | 58 | 58 |
| meta: source / title / section / chunk_id / strategy | yes | yes |

## Чеклист задания

| # | Требование | Доказательство | Статус |
|---|---|---|---|
| 1 | Индексация корпуса в Docker-сервисе | `apps/rag` + compose `rag`; прод `total_chunks≥761` | **PASS** |
| 2 | Две стратегии чанкинга | таблица fixed vs structural выше | **PASS** |
| 3 | Метаданные у чанков | поля в store/API hits; UI sources | **PASS** |
| 4 | Сравнение зафиксировано числами | эта таблица + видео-оверлей | **PASS** |
| 5 | API embeddings по умолчанию; local admin-off | `embedding_provider=api`, local toggle off | **PASS** |
| 6 | (Опц.) load smoke | `scripts/rag-load-smoke.sh` | code ready |

## Hit@k smoke (FakeEmbedder, mode=raw, top-3)

| Query | Top sources (score) |
|---|---|
| Guest MCP | guest-mcp / agent specs (~0.49–0.54) |
| model_id | `docs/env-local.md`, profile spec (~0.52–0.62) |
| Reality :443 | deploy / agent specs |
| Profile | profile / AGENTS |
| FakeLLM | plans / AGENTS |

Structural лучше для вопросов «по секции»; fixed — ровнее по размеру.
