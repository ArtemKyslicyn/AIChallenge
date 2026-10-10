# Challenges (Days 4–30)

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
| [`21-rag-index/`](21-rag-index/) | **21** Индексация · fixed vs structural | **Профиль / rag** | **RESULTS** · video |
| [`22-rag-query/`](22-rag-query/) | **22** Первый RAG ask ± база | **Чат · Настройки** | **RESULTS** · QUESTIONS · video |
| [`23-rag-rerank/`](23-rag-rerank/) | **23** Реранк raw / filtered / full | **Чат · Режим базы** | **RESULTS** · video |
| [`24-rag-citations/`](24-rag-citations/) | **24** Цитаты · источники · «не знаю» | **Чат · база** | **RESULTS** · video |
| [`25-rag-memory/`](25-rag-memory/) | **25** Мини-чат RAG + память | **База** `?shell=rag` | **RESULTS** · SCENARIOS · run · video |
| [`26-local-llm/`](26-local-llm/) | **26** Локальная 35B, три вопроса | **Чат** | **RESULTS** · video · run |
| [`27-local-app/`](27-local-app/) | **27** Подключение и пин в профиле | **Профиль · Чат** | README · video |
| [`28-local-rag/`](28-local-rag/) | **28** Тот же пин, база выкл / вкл | **Чат · База** | README · video |
| [`29-local-optimize/`](29-local-optimize/) | **29** Температура и фрагменты | **Чат** | README · run · video |
| [`30-local-service/`](30-local-service/) | **30** Свой HTTP, лимит, длина | **Профиль · Чат** | README · video |
| [`live-models/`](live-models/) | (опц.) Живой выбор модели | **Чат** | video |

## Неделя 21–25 (RAG по домашке курса)

Текст домашек одной таблицей: [`WEEK-RAG.md`](WEEK-RAG.md).  
План пересъёмки 21–25: [`WEEK-RAG-SHOOT.md`](WEEK-RAG-SHOOT.md).  
В папке дня: **README** = что сделать · **RESULTS** = PASS · **VIDEO** = кадры.

```bash
cd challenges/record && RECORD_ONLY=21,22,23,24,25 npm run record
python3 challenges/25-rag-memory/run.py --scenario a --limit 12
python3 challenges/25-rag-memory/run.py --scenario b --limit 12
```
