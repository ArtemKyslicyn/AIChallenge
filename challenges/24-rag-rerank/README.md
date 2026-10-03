# День 24 — rewrite / filter / rerank

**Папка:** `24-rag-rerank` (22=индекс, 23=ask).  
**Артефакты:** `challenge-24.mp4` · `RESULTS.md` · `VIDEO.md`

## Требование задания

После vector search: retrieve шире → фильтр по similarity → (опц.) rerank → top_k. Режимы сравнимы. Query rewrite в «умном» режиме. Источники показывают pre→post.

## Режимы (чат → Настройки → «Использовать базу»)

| Mode | Rewrite | min_score | Rerank |
|---|---|---|---|
| `raw` | нет | нет | truncate |
| `filtered` | нет | да | нет |
| `full` | да | да | heuristic overlap |

Defaults: `top_k_pre=20`, `top_k_post=6`, `min_score=0.18`.

## Чеклист

См. `RESULTS.md`.
