# Challenges (Days 4–25)

Автопрогон и видео-сдачи AIChallenge.  
**Правило:** номер папки = номер дня сдачи (кроме оговорок внутри README).

| Папка | День / тема | Где на сайте | Артефакты приёмки |
|-------|-------------|--------------|-------------------|
| [`04-temperature/`](04-temperature/) | Температура 0 / 0.7 / 1.2 | **×T** | video · run |
| [`05-model-tiers/`](05-model-tiers/) | Слабая / средняя / сильная | **Модели → Студия** | video |
| [`06-first-agent/`](06-first-agent/) | Первый агент + команда | **Агенты** | video |
| [`07-context-memory/`](07-context-memory/) | Память диалога | **Агенты** | video |
| [`08-tokens/`](08-tokens/) | Токены / обрезка | **Агенты** | video |
| [`09-compression/`](09-compression/) | Сжатие истории | **Агенты** | video |
| [`10-context-strategies/`](10-context-strategies/) | Sliding / Facts / Branch | **Агенты** | video |
| [`11-agent-memory/`](11-agent-memory/) | 3 слоя памяти | **Агенты** | video |
| [`12-personalization/`](12-personalization/) | Prefs + lens + auth | **Профиль** | video |
| [`13-task-state/`](13-task-state/) | Task FSM | **Агенты** | video · run |
| [`14-invariants/`](14-invariants/) | Инварианты | **Агенты** | video · run |
| [`15-task-transitions/`](15-task-transitions/) | Граф переходов | **Агенты** | video · run |
| [`16-mcp-connect/`](16-mcp-connect/) | MCP connect | **MCP** | video · run |
| [`17-mcp-tool/`](17-mcp-tool/) … [`20-mcp-orchestration/`](20-mcp-orchestration/) | MCP tools / jobs / pipe | **MCP** | video |
| [`21-live-models/`](21-live-models/) | Живой выбор модели в чате | **Чат** | **RESULTS** · video |
| [`22-rag-index/`](22-rag-index/) | Индекс · fixed vs structural | **Профиль / rag** | **RESULTS** · video |
| [`23-rag-query/`](23-rag-query/) | Ask ± база · источники | **Чат · Настройки** | **RESULTS** · QUESTIONS · video |
| [`24-rag-rerank/`](24-rag-rerank/) | raw / filtered / full | **Чат · Режим базы** | **RESULTS** · video |
| [`25-rag-memory/`](25-rag-memory/) | Мини-чат RAG + память задачи | **База** `?shell=rag` | **RESULTS** · SCENARIOS · run · video |

## Как принимать дни 21–25

В каждой папке `RESULTS.md` — таблица **Требование → доказательство → PASS**.  
Видео = короткий UI-демо; длинные прогоны (день 25) — `run.py`.

```bash
# видео
cd challenges/record && RECORD_ONLY=21,22,23,24,25 npm run record

# день 25 — два сценария по 12 ходов
python3 challenges/25-rag-memory/run.py --scenario a --limit 12
python3 challenges/25-rag-memory/run.py --scenario b --limit 12
```
