# Challenge 20 — оркестрация MCP

Агент **Разбор смены** ходит по логическим серверам `watch` → `models` → `brief`: `watch_brief`, `model_pulse`, затем `search → summarize → saveToFile`. Старый каталог дней 16–19 не вырезан.

Продуктовая вторая версия (живой выбор в чате): [`VERSION-2.md`](VERSION-2.md)

## На платформе

1. https://aichallenge.arcilite.ru/?shell=mcp
2. Плитки серверов watch / models / brief
3. **Разбор смены** — пять вызовов с `data-server`

```bash
cd challenges/record && RECORD_ONLY=20 npm run record
```
