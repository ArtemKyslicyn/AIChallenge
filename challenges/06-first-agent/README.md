# Challenge 06 — First Agent

Инкапсулированный агент: definition (инструкция + temperature + max_tokens) → `POST /api/v1/agent-workshop/run` → только `{ content, model_id }`.

Не путать с обычным чатом (Scenario/Session) и не вызывать `/llm/complete` для этого урока.

## На платформе

1. Открой https://aichallenge.arcilite.ru/?shell=agents  
   (или topbar **Агенты**)
2. Выбери пресет «Краткий редактор» или свой черновик
3. Отправь вопрос → получи ответ с бейджем `model_id`
4. Убедись, что каждый вопрос — отдельный прогон (лог без серверной истории)

### Команда / Прогон (Day 6.2)

1. Переключись на **Команда** → режим **Прогон** (или префикс `/прогон` в задаче)
2. Выбери базового агента; ось **temperature** или **модели**
3. Запусти — в ленте fan-out вариантов и **Склейщик** (если включён fan-in)
4. У каждого ответа свой `model_id`

## Код

```bash
# из корня репо
python3 challenges/06-first-agent/run.py
```

Артефакты: `results.json`, `RESULTS.md`, видео **`challenge-06.mp4`** (и `.webm`).

## Видео

```bash
cd challenges/record && npm install && npx playwright install chromium
RECORD_ONLY=06 npm run record
```

Формат сдачи: **Видео + Код**.
