# День 21 (сдача) — индексация документов

Папка: `22-rag-index` (номер 21 занят live-models).

## Что сделано

- Сервис [`apps/rag`](../../apps/rag): chunking **fixed** + **structural**, эмбеддинги API/fake (+ local optional), SQLite + numpy vectors, метаданные `source/title/section/chunk_id/strategy`.
- Compose service `rag` на `127.0.0.1:18766`, corpus: `docs/`, README, AGENTS, CLAUDE.
- Сравнение стратегий: `RESULTS.md`.
- Load smoke: `scripts/rag-load-smoke.sh`.

## Видео

Снять: индекс → stats → два strategy reindex → сравнение в RESULTS → (опционально) load smoke.
Не затирать чужие `challenge-*.mp4`.
