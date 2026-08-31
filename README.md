# AIChallenge

Публичный челлендж: собрать **масштабируемую AI/чат-платформу** (backend + frontend в одной репе, Docker), с чистой архитектурой Python, безопасными секретами и стримингом ответов модели.

Репозиторий: [github.com/ArtemKyslicyn/AIChallenge](https://github.com/ArtemKyslicyn/AIChallenge)

## О чём челлендж

Сделать monorepo, в котором:

| Часть | Требование |
|--------|------------|
| Backend | Python, FastAPI, **Clean / Hexagonal** (SOLID), модульный монолит |
| Frontend | React + TypeScript (Vite SPA) |
| Infra | Docker Compose: `api` + `web` + Postgres |
| Chat UX | Анонимная сессия по ссылке, **SSE**-стриминг токенов |
| LLM | OpenAI-compatible абстракция + роутер моделей (failover при 429/quota), в т.ч. OpenRouter / DeepSeek |
| Прозрачность | У каждого ответа ассистента видно **`model_id`** (API, SSE, UI, БД) |
| Секреты | `.env` только локально; в git и в чат агентам — **никогда** |
| Домен | Код **domain-agnostic** (без patient/doctor и т.п. в именах); сценарии — конфиг |

Продуктовый смысл (например, диалог перед визитом) задаётся позже через сценарии/конфиг, не через названия модулей.

## Статус

v1 **в разработке** (ветка `feat/v1-chat-platform`). Уже есть каркас API, domain/ports, ModelRouter, Postgres/Alembic, use cases сессий/чата/probe. Compose + web — по плану.

## Документация (с чего читать)

| Документ | Зачем |
|----------|--------|
| **[Design spec](docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md)** | Утверждённая архитектура: слои, API, SSE, LLM-router, модели данных, критерии успеха |
| **[План для Claude Code](docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md)** | Пошаговая реализация (14 задач, TDD, чеклисты, DoD) |
| **[CLAUDE.md](CLAUDE.md)** | Entrypoint для Claude Code: секреты, стек, ссылка на план |
| **[AGENTS.md](AGENTS.md)** | Правила для любых агентов + индекс project skills |
| **[Индекс docs](docs/README.md)** | Карта всей документации |
| **`.env.example`** | Имена переменных окружения (без реальных значений) |

Кратко по слоям в коде (`apps/api`):

```text
domain/        → сущности и порты (без FastAPI/SQLAlchemy)
application/   → use cases
adapters/      → HTTP, Postgres, LLM, YAML-сценарии
core/          → settings, DI, logging
```

## Быстрый старт (локально, без ключа LLM)

```bash
git clone https://github.com/ArtemKyslicyn/AIChallenge.git
cd AIChallenge
cp .env.example .env
# в .env: USE_FAKE_LLM=true  (редактор, не чат агента)

cd apps/api
uv sync
uv run pytest tests/unit -v
uv run uvicorn app.main:app --reload --port 8000
```

Проверка:

```bash
curl -s http://localhost:8000/api/v1/health
# {"status":"ok"}
```

Полный стек (когда появятся Dockerfile/Compose по плану):

```bash
docker compose up --build
```

## API (v1, контракт)

Префикс: `/api/v1`. Для сессии: заголовок `X-Session-Token`.

| Method | Path | Назначение |
|--------|------|------------|
| `GET` | `/health` | Liveness |
| `POST` | `/sessions` | Создать анонимную сессию |
| `GET` | `/sessions/{id}/messages` | История (с `model_id`) |
| `POST` | `/sessions/{id}/messages` | Сообщение пользователя → **SSE** |
| `POST` | `/llm/complete` | Прямой probe к модели (без сессии) |

SSE-события: `model` → `token`* → `message_end` (или `error`). В `model` / `message_end` всегда есть фактический `model_id`.

## Секреты

1. Скопируй `.env.example` → `.env` **сам в редакторе**.
2. Не коммить `.env`, не вставляй ключи в чат Cursor/Claude Code.
3. Для демо без провайдера: `USE_FAKE_LLM=true`.
4. Имена переменных: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_CHAIN`, `DATABASE_URL`, …

Подробнее: skill `aichallenge-secrets`, правило `.cursor/rules/secrets-safety.mdc`.

## Критерии приёмки челленджа (v1)

- [ ] `docker compose up` поднимает db + api + web, health ок  
- [ ] Анонимный чат по SSE, история в Postgres  
- [ ] В UI и API виден `model_id` ответа  
- [ ] `POST /llm/complete` возвращает ответ и `model_id`  
- [ ] Смена провайдера (OpenRouter ↔ DeepSeek) — только конфиг/env  
- [ ] Нет секретов в git; в коде нет медицинских ролей в нейминге  

## Вне скоупа v1

Auth/роли, админка сценариев, Redis для роутера, голос, биллинг, микросервисы.

## Лицензия / использование

Учебный / челлендж-репозиторий. Форк и PR приветствуются после стабилизации v1.
