# Challenge 17 — Stand Pulse: первый MCP-инструмент

Не echo. `probe_stand` и `model_pulse` ходят в живые API стенда (`/api/v1/health`, `/lab/pareto`, `/lab/feedback-stats`). Агент в разделе MCP вызывает инструмент и отвечает по фактам.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=mcp
2. Каталог: `probe_stand`, `model_pulse` (+ параметры)
3. Оператор → **Проверить стенд** — трассировка `.mcp-call` и ответ с `model_id`

## Код

```bash
uv run --project apps/mcp python challenges/17-mcp-tool/run.py --stdio
cd challenges/record && RECORD_ONLY=17 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)

Клиент вне стенда: https://github.com/ArtemKyslicyn/stand-pulse
