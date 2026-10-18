# Структура проекта AIChallenge

Краткий справочник для онбординга и режима **Ассистенты → Справка**.

## Monorepo

| Путь | Роль |
|------|------|
| `apps/api` | FastAPI: чат, SSE, сессии, Guest MCP, local LLM |
| `apps/web` | Vite + React: чат и вкладки стенда |
| `apps/rag` | Индекс и поиск по корпусу (Qdrant) |
| `apps/mcp` | Встроенный MCP стенда (дежурство / tools) |
| `challenges/` | Дни курса: README · RESULTS · VIDEO |
| `docs/` | Живая документация (handbook) |
| `docs/superpowers/` | Планы и спеки (история, не handbook) |
| `scripts/` | Deploy-safe checks, review, утилиты |

Слои API: `domain` → `application` → `adapters`. Из `domain` нельзя импортировать `adapters`.

## Порты (локально / прод)

- Локально: API и web через Docker Compose (см. README).
- Прод: публичный `:443` → xray Reality → nginx `:8443` → web `127.0.0.1:18080`.
- Не вешать продукт на `:443` / `:8443`. Не делать `docker compose down` при обычном деплое.

Подробнее: `docs/stand-edge-ports.md`, `AGENTS.md`.

## Инварианты ответов

- Каждый ответ ассистента несёт разрешённый `model_id` (API, SSE, UI, БД).
- Имена в коде и дефолтных сценариях — domain-agnostic (без patient/doctor).
- Секреты только в `.env` (gitignored); в чат и корпус не класть.
- CI без ключей провайдера: `USE_FAKE_LLM=true`.

## Связанные продукты

- **Agent07** — macOS local-first agentic IDE (канбан, файлы, локальные модели).
- **aichallenge-mcp-kit** — локальный MCP-хаб: туннель → «Свой MCP» на стенде.
