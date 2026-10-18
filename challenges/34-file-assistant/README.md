# Day 34 — Файловый ассистент

**Где на сайте:** **Ассистенты → Файлы**

Через `aichallenge-mcp-kit` builtin `project_files` (read/search/write/diff) в `workspace/projects`.

## Сценарии (≥2)

1. **Найти usages:** goal «найди все места с GuestMcp» → `dev__files__search`
2. **Сгенерировать README/ADR:** goal «создай README для demo/» → `write` + показать diff
