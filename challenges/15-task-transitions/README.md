# Challenge 15 — Controlled task transitions

Явный граф этапов `planning → execution → validation → done`. Ассистент не перепрыгивает: реализация только после плана, финал только после валидации. Недопустимый `goto` и skip-intent — отказ без LLM (`model_id=task-fsm`). Пауза держит этап.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents
2. Полоса **Задача**: текущий этап, пунктир — разрешённый переход, зачёркнутый — запрещённый скачок
3. Клик по `done` из `planning` → отказ
4. Чат: `пиши код …` на planning → отказ; `сразу финал` на execution → отказ
5. Пауза → работа запрещена; **Продолжить** — тот же этап

## Код / видео

```bash
python3 challenges/15-task-transitions/run.py
cd challenges/record && RECORD_ONLY=15 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)
