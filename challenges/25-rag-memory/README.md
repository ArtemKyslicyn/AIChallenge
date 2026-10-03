# Challenge 25 — мини-чат: RAG + источники + память задачи

Production-like shell: `?shell=rag` / вкладка **База**.

## Что внутри

| Слой | Откуда |
|---|---|
| История диалога | `agent_dialogs` (workshop persist) |
| Always-on RAG | `use_rag` на `/agent-workshop/run` → sidecar `apps/rag` |
| Источники | `rag_sources` в ответе run; UI блок под каждым ответом |
| Цель / этап | `WorkingMemory.goal` + `TaskState` |
| Уточнения | sticky `facts` (`context_mode=facts`) |
| Ограничения | `invariants` |

## Сценарии

Два длинных прогона (10–15 ходов): `SCENARIOS.md`.  
Проверка: цель не теряется, у ответов есть источники.

## Видео

Скрипт: `VIDEO.md`. Запись: `RECORD_ONLY=25 node challenges/record/record.mjs`.
