# Challenge 14 — Invariants

Prod: `https://aichallenge.arcilite.ru` · 2026-09-17T16:26:55.502743+00:00
Draft: `challenge-14-4d3003c925`

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

Добавляем эндпоинт в adapters, не нарушая слоёв:

**1. Определение (domain)**
В `apps/domain/` создаём интерфейс (protocol/abstract):
```python
# apps/domain/ports/invariant_list.py
from abc import ABC, abstractmethod
from typing import List

class InvariantListProvider(ABC):
    @abstractmethod
    def list_invariants(self) -> List[dict]:
        ...
```

**2. Реализация (application)**
В `apps/application/` — use-case, принимает порт:
```python
# apps/application/usecases/list_invariants.py
from typing import List
from apps.domain.ports.invariant_list import InvariantListProvider

class ListInvariants:
    def __init__(self, provider: InvariantListProvider):
        self.provider = provider

    def execute(self) -> List[dict]:
        return self.provider.list_invariants()
```

**3. Адаптер (adapters)**
В `apps/api/adapters/` — HTTP-эндпоинт, инжектит use-case:
```python
# apps/api/adapters/invariant_routes.py
from fastapi import APIRouter
from apps

## Checks
- stored_apart: OK
- conflict_flag: OK
- refuse_model: OK
- refuse_cites: OK
- refuse_explains: OK
- ok_not_refused: OK
