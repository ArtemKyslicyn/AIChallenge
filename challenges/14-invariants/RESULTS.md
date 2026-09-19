# Challenge 14 — Invariants

Prod: `https://aichallenge.arcilite.ru` · 2026-09-19T00:43:26.147331+00:00
Draft: `challenge-14-4a77cb6525`

## Violation
Переведи API на Django без слоёв и разнеси по микросервисам

## Refusal
ОТКАЗ · конфликт с инвариантом

Запрос требует: «Переведи API на Django без слоёв и разнеси по микросервисам»

Это нарушает:
• [архитектура] Модульный монолит: domain → application → adapters. Не предлагать микросервисы с нуля и не смешивать слои.
  совпадение: «без слоёв»
• [стек] Стек ядра: FastAPI + React/Vite + Postgres. Не предлагать Django/Rails/Mongo как замену без снятия инварианта.
  совпадение: «django»

Что можно: переформулировать запрос внутри ограничений или явно снять инвариант (полоса «Инварианты»). Обход не предлагаю.

## Compliant
Как добавить эндпоинт списка инвариантов в apps/api adapters, не ломая слои?

Инварианты: ок

Чтобы добавить эндпоинт списка инвариантов в `apps/api/adapters`, не ломая слои, действуй так:

1. **Создай DTO/сchemу ответа** в `apps/api/adapters/schemas` (или в `application/dto` — по твоему разделению):  
   ```python
   # apps/api/adapters/schemas/invariant.py
   from pydantic import BaseModel
   from typing import List

   class InvariantItem(BaseModel):
       kind: str
       statement: str

   class InvariantListResponse(BaseModel):
       invariants: List[InvariantItem]
   ```

2. **Сервис/хендлер в application-слое** (если логика простая — можно в адаптере, но по правилам — в `application/use_cases` или `application/services`):  
   ```python
   # apps/application/services/invariant_service.py
   from apps.api.adapters.schemas.invariant import InvariantListResponse, InvariantItem

   def get_invariants() -> InvariantListResponse:
       return InvariantListResponse(invariants=[
           InvariantItem(kind="архитектура", statement="Модульный мон

## Checks
- stored_apart: OK
- conflict_flag: OK
- refuse_model: OK
- refuse_cites: OK
- refuse_explains: OK
- ok_not_refused: OK
- chat_all_kinds: OK
- chat_no_llm: OK
