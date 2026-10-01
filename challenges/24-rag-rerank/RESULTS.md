# Challenge 24 — filter / rewrite comparison

Defaults: `top_k_pre=20`, `top_k_post=6`, `min_score=0.18`.

| Mode | Rewrite | Threshold | Rerank |
|---|---|---|---|
| raw | no | no | no (truncate) |
| filtered | no | yes | no |
| full | yes | yes | heuristic overlap |

## Example query

«пожалуйста расскажи что такое Guest MCP»

Measured on compose-equivalent corpus (FakeEmbedder; API embeds shift absolute scores):

| Mode | hits_pre → hits_post | notes |
|---|---|---|
| raw | 20 → 6 | top scores ≈ 0.58…0.45; filler query kept as-is |
| filtered | 20 → 6 | all 20 ≥ 0.18 on fake vectors → same truncate; drops noise when API scores are wider |
| full | 20 → 6 | rewrite → `Guest MCP … Streamable HTTP`; rerank boosts title/section overlap (top ≈ 0.65) |

## Demo path

1. Ещё → Использовать базу → режим raw → вопрос → источники (pre→post).
2. Тот же вопрос в filtered, затем full — сравнить dropped / rewrite строку.
3. Добавить документ через «Добавить в базу» в Ещё.
