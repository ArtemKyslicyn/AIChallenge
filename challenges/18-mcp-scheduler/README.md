# Challenge 18 — периодическая сводка Stand Pulse

`schedule_digest` пишет задание в SQLite, сразу снимает первую сводку и дальше крутит её в HTTP-процессе MCP. Агент ставит расписание из приложения; `latest_digest` отдаёт агрегат: health + рейтинг + модели на внимании.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=mcp
2. **Сводка каждые 60 с** — агент вызывает `schedule_digest`
3. Карточка сводки и список заданий

## Код

```bash
uv run --project apps/mcp python challenges/18-mcp-scheduler/run.py --stdio
cd challenges/record && RECORD_ONLY=18 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)

Клиент: https://github.com/ArtemKyslicyn/stand-pulse (`pulse schedule`, `pulse digest`).
