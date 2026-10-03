# День 25 — RESULTS (чеклист)

Видео (короткий демо-проход): `challenge-25.mp4`  
Полная приёмка длинных сценариев: `run.py` + `SCENARIOS.md`  
Прод: `?shell=rag`, индекс ~766 chunks, sources работают.

## Чеклист задания

| # | Требование | Доказательство | Статус |
|---|---|---|---|
| 1 | Мини-чат (веб) | вкладка **База** / `RagMemoryChat.tsx` | **PASS** |
| 2 | История диалога | persist workshop dialog; log растёт | **PASS** |
| 3 | RAG на каждый вопрос | `use_rag` always-on в UI send | **PASS** |
| 4 | Ответ с учётом базы | grounded ответы + «нет в базе» честно | **PASS** |
| 5 | Источники **всегда** | UI details; API `rag_sources` | **PASS** |
| 6 | Цель задачи | полоса «Цель» + `WorkingMemory.goal` / TaskState | **PASS** |
| 7 | Уточнения зафиксированы | facts panel (`context_mode=facts`) | **PASS** |
| 8 | Ограничения/термины | invariants (:443 / Guest MCP≠/mcp) | **PASS** |
| 9 | Сценарий A 10–15 ходов | `run.py --scenario a --limit 12` → **12/12** sources | **PASS** |
| 10 | Сценарий B 10–15 ходов | `run.py --scenario b --limit 12` → **12/12** sources | **PASS** |
| 11 | Цель не теряется mid-dialog | turn 8 в обоих прогонах повторяет goal | **PASS** |

## Live прогон (prod)

```text
DONE turns=12 with_sources=12   # scenario A
DONE turns=12 with_sources=12   # scenario B
```

Повтор:

```bash
python3 challenges/25-rag-memory/run.py --scenario a --limit 12
python3 challenges/25-rag-memory/run.py --scenario b --limit 12
```

## Видео vs полный прогон

| | Видео | `run.py` |
|---|---|---|
| Длина | ~4 вопроса, цель/источники крупно | 12+12 ходов |
| Роль | показать UI shell | доказать устойчивость |

## Probe

`rag_retrieval`: hits_pre=20 → hits_post=6; при healed matrix query в пространстве `fake-hash`.
