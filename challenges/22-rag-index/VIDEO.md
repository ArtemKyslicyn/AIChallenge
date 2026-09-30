# Challenge 22 — видео (индексация / дни 21)

Сайт после деплоя: https://aichallenge.arcilite.ru/  
Не показывать `RAG_SHARED_TOKEN` / ключи LLM. Не затирать чужие `challenge-*.mp4`.

## Сценарий (~2–3 мин)

1. **Профиль → Подключения** — блок «База знаний стенда»: видны чанки / стратегия / embed.
2. Крупно: индикатор в чате ещё выкл (или открыть «Ещё» без галочки).
3. **Терминал** (loopback на сервере или локально):  
   `curl …/v1/stats` → затем `POST /v1/index` `{"strategy":"fixed"}` → снова stats.  
   Показать числа чанков / avg.
4. То же для `{"strategy":"structural"}` — сравнить на экране (два stats или RESULTS.md).
5. Коротко пролистать `apps/rag` / `RESULTS.md`: две стратегии + метаданные (`source`, `title`, `section`, `chunk_id`).
6. (Опционально) `./scripts/rag-load-smoke.sh` — `RAG_LOAD_OK`.

## Кадр-итог

Таблица fixed vs structural из `challenges/22-rag-index/RESULTS.md`.
