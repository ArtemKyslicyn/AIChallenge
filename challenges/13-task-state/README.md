# Challenge 13 — Task State Machine

Серверный FSM задачи в Agent Workshop: этапы `planning → execution → validation → done`, шаг, ожидаемое действие, пауза/продолжить без повтора брифа.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents  
2. Полоса **Задача**: Старт / Дальше / Пауза / Продолжить / Сброс  
3. Или директивы: `задача: …`, `этап дальше`, `пауза`, `продолжи`  
4. После паузы — продолжение с текущего шага, без пересказа плана

## Код / видео

```bash
python3 challenges/13-task-state/run.py
cd challenges/record && RECORD_ONLY=13 npm run record
```

Текст: [`VIDEO.md`](VIDEO.md)
