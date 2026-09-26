# Challenge 16 — MCP connect + list tools

Минимальный клиент на официальном Python SDK: `initialize` → `list_tools`.
Сервер — `apps/mcp` (stdio в CI, Streamable HTTP на стенде).

Инструменты дня 16: `echo`, `time_now`, `list_stages` (плюс Stand Pulse — дни 17/18). Проверка — subset, лишние имена не ломают день 16.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=mcp
2. Статус `connected` и таблица инструментов

Публичный MCP: `https://aichallenge.arcilite.ru/mcp` (Bearer `MCP_SHARED_TOKEN`).
Контейнер слушает только `127.0.0.1:18765`. Путь `/mcp` идёт через web nginx, не через `:443`/xray.

## Код

```bash
# локальный stdio (без токена, без сети)
uv run --project apps/mcp python challenges/16-mcp-connect/run.py --stdio

# стенд (нужен MCP_SHARED_TOKEN в окружении, не в git)
uv run --project apps/mcp python challenges/16-mcp-connect/run.py --url https://aichallenge.arcilite.ru/mcp
```

```bash
cd challenges/record && RECORD_ONLY=16 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)

Вторая версия (живой выбор в чате): [`VERSION-2.md`](VERSION-2.md)
