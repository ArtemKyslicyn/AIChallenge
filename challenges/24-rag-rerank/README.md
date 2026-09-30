# День 23 — реранкинг и фильтрация

Папка: `24-rag-rerank` (22/23 заняты индексацией и первым RAG).

## Что сделано

После vector search:

1. `top_k_pre` (по умолчанию 20)
2. порог `min_score` (filtered/full)
3. heuristic rerank: cosine + token overlap (full)
4. `top_k_post` (по умолчанию 6)
5. query rewrite в режиме `full` (filler strip + aliases)

Режимы в чате (**Ещё** при «Использовать базу»): `raw` | `filtered` | `full`.

Загрузка документов: **Ещё → Добавить в базу**, **В базу** у медиа-ряда, **Профиль → Подключения → Добавить документ**.

## Сравнение

См. `RESULTS.md`. Видео: `VIDEO.md`.
