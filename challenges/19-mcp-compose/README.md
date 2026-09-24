# Challenge 19 — пайплайн MCP: search → summarize → saveToFile

Ночной бриф стенда собирается тремя MCP-инструментами. Агент не останавливается после первого вызова: JSON `search` уходит в `summarize(payload)`, ответ — в `saveToFile(brief)`. Файл пишется в `MCP_DATA_DIR/briefs/` и в SQLite.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=mcp
2. Каталог: `search`, `summarize`, `saveToFile`
3. **Ночной бриф** — три `.mcp-call` подряд и карточка архива

## Код

```bash
uv run --project apps/mcp python challenges/19-mcp-compose/run.py --stdio
cd challenges/record && RECORD_ONLY=19 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)
