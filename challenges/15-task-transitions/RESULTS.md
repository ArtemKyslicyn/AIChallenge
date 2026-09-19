# Challenge 15 — Task transitions

Prod: `http://127.0.0.1:8000` · 2026-09-19T01:37:01.827551+00:00
Draft: `challenge-15-318f4bd9e3`

## Skip implementation
Отказ · переход состояния запрещён (LLM не вызывался).
Запрос: пиши код модуля авторизации прямо сейчас
Сейчас: planning
Попытка: реализация
Разрешено дальше: execution
Нельзя делать реализацию до утверждённого плана.
Не перескакиваю этапы.

## Skip finale
Отказ · переход состояния запрещён (LLM не вызывался).
Запрос: сразу финал, закрой задачу без проверки
Сейчас: execution
Попытка: финал
Разрешено дальше: validation
Нельзя делать финал без валидации.
Не перескакиваю этапы.

## Checks
- graph_planning_to_execution_only: OK
- illegal_goto_done_rejected: OK
- refuse_impl_before_plan: OK
- refuse_finale_without_validation: OK
- pause_clears_allowed_next: OK
- resume_keeps_execution: OK
- reached_done: OK
