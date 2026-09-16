# Challenge 11 — Модель памяти агента

Три слоя памяти, отдельные хранилища, явные записи.

| Слой | Что хранит | Где |
|------|------------|-----|
| **Краткосрочная** | Реплики текущего диалога | `agent_dialogs.messages` |
| **Рабочая** | Цель, чеклист, scratch задачи | `agent_dialogs.working_memory` (JSONB) |
| **Долговременная** | Профиль, решения, знания | `agent_long_term_memory` (по visitor) |

Запись в working / long-term — только через `POST /agent-workshop/memory/write` с явным `layer`. Краткосрочная растёт только из `run` с `persist`.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents → Один агент  
Пишите в чат: «запомни цель: …», «меня зовут …», «запомни решение: …» — или чипы в композере.

## Код / видео

```bash
python3 challenges/11-agent-memory/run.py
cd challenges/record && RECORD_ONLY=11 npm run record
```

Текст ролика: [`VIDEO.md`](VIDEO.md) · промпт: [`prompt.txt`](prompt.txt)
