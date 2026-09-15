# Challenge 11 — Agent Memory

Prod: `https://aichallenge.arcilite.ru` · 2026-09-15T21:51:14.021533+00:00

## Слои до пробы
- short_term: 2 реплик
- working.goal: Показать три слоя памяти в ответе агента
- long_term.profile: {'name': 'Артём'}

## Ответ с памятью
- Имя: Артём / Цель: Показать три слоя памяти в ответе агента

## После clear dialog (working сброшен, long-term жив)
- Имя: Артём  
Цель: Нет рабочей цели.

## Checks
- name_in_with: OK
- goal_in_with: OK
- name_survives_clear: OK
- working_cleared: OK
