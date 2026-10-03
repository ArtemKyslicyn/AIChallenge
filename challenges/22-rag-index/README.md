# День 22 — индексация документов (chunking ×2 + meta)

**Папка:** `22-rag-index` (номер 21 занят live-models).  
**Артефакты:** `challenge-22.mp4` · `RESULTS.md` · `VIDEO.md`

## Требование задания

Индексация корпуса с **двумя** стратегиями чанкинга, метаданные чанков, сравнение чисел. Сервис в Docker, эмбеддинги через API (local — admin-off).

## Где смотреть

| Что | Где |
|---|---|
| Сервис | `apps/rag` · compose `rag` · loopback `:18766` |
| Стратегии | `fixed` (800/120) · `structural` (заголовки/файлы) |
| Метаданные | `source`, `title`, `section`, `chunk_id`, `strategy` |
| Цифры сравнения | `RESULTS.md` |
| UI stats | Профиль → «База знаний стенда» / вкладка База |
| Load | `./scripts/rag-load-smoke.sh` |

## Чеклист

См. `RESULTS.md`.
