# Challenge 24 — filter / rewrite comparison

Defaults: `top_k_pre=20`, `top_k_post=6`, `min_score=0.18`.

| Mode | Rewrite | Threshold | Rerank |
|---|---|---|---|
| raw | no | no | no (truncate) |
| filtered | no | yes | no |
| full | yes | yes | heuristic overlap |

## Example query

«пожалуйста расскажи что такое Guest MCP»

| Mode | hits_pre → hits_post | notes |
|---|---|---|
| raw | 20 → 6 | may include weak scores |
| filtered | 20 → ≤6 | drops below min_score |
| full | rewrite expands Guest MCP; rerank prefers title/section hits |

Fill live numbers after `POST /v1/search` with each mode on prod/local.

## Demo path

1. Ещё → Использовать базу → режим raw → вопрос → источники (pre→post).
2. Тот же вопрос в filtered, затем full — сравнить dropped / rewrite строку.
3. Добавить документ через «Добавить в базу» в Ещё.
