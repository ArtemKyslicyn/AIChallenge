# Challenge 06 — First Agent

Инкапсулированный агент: definition → `POST /api/v1/agent-workshop/run` → `{ content, model_id }`.

Демо-каст: **Алкаш · Аристотель · Программист** обсуждают теорию струн на мощной модели
(`google/gemini-2.5-flash`), во всех режимах: один / параллельно / цепочка / обсуждение / прогон.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents
2. Пресеты или «+ Пустой» → собери трёх персонажей
3. **Один агент** → вопрос про теорию струн
4. **Команда** → Параллельно, Цепочка, Обсуждение, Прогон

## Код / видео

```bash
python3 challenges/06-first-agent/run.py
cd challenges/record && RECORD_ONLY=06 npm run record
```

Артефакты: `results.json`, `RESULTS.md`, `challenge-06.mp4`.
