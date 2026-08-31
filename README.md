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

v1 **собран** на ветке `feat/v1-chat-platform`: API (domain/ports, use cases, ModelRouter, Postgres/Alembic), SPA с SSE и лейблом модели, Docker Compose `db + api + web`, unit- и интеграционные тесты, CI.

## Документация (с чего читать)

| Документ | Зачем |
|----------|--------|
| **[Design spec](docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md)** | Утверждённая архитектура: слои, API, SSE, LLM-router, модели данных, критерии успеха |
| **[План для Claude Code](docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md)** | Пошаговая реализация (15 задач, TDD, чеклисты, DoD) |
| **[CLAUDE.md](CLAUDE.md)** | Entrypoint для Claude Code: секреты, стек, ссылка на план |
| **[AGENTS.md](AGENTS.md)** | Правила для любых агентов + индекс project skills |
| **[Индекс docs](docs/README.md)** | Карта всей документации |
| **`.env.example`** | Имена переменных (без секретов) |
| **[Локальный `.env`](docs/env-local.md)** | Куда вставлять ключи и как `scp` на VPS (файл в gitignore) |


Кратко по слоям в коде (`apps/api`):

```text
domain/        → сущности и порты (без FastAPI/SQLAlchemy)
application/   → use cases
adapters/      → HTTP, Postgres, LLM, YAML-сценарии
core/          → settings, DI, logging
```

Правило слоёв проверяется тестом `tests/unit/test_layering.py`, который разбирает граф импортов, а не ревью.

## Быстрый старт

```bash
git clone https://github.com/ArtemKyslicyn/AIChallenge.git
cd AIChallenge
docker compose up --build -d
open http://localhost:8080
```

Работает **без какой-либо настройки**: если ключа провайдера нет, API падает обратно на `FakeLLMProvider`, и чат, стриминг и лейбл модели можно потрогать офлайн.

| Сервис | URL | Что там |
|--------|-----|---------|
| `web` | http://localhost:8080 | nginx отдаёт SPA и проксирует `/api` |
| `api` | http://localhost:8000 | FastAPI: `/api/v1/health`, `/docs` |
| `db` | `localhost:5432` | Postgres 16, открыт для интеграционных тестов |

С реальным провайдером — создай `.env` **в редакторе** и перезапусти:

```bash
cp .env.example .env   # заполни LLM_API_KEY и LLM_MODEL_CHAIN
docker compose up -d --build api
```

## Конфигурация

Только имена. Значения живут в `.env`, который в `.gitignore` и который нельзя коммитить, печатать или вставлять в чат агента.

| Переменная | Назначение |
|------------|------------|
| `DATABASE_URL` | DSN Postgres (`postgresql+asyncpg://…`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Доступы сервиса `db` |
| `LLM_BASE_URL` | OpenAI-совместимый endpoint (OpenRouter, DeepSeek, …) |
| `LLM_API_KEY` | Ключ провайдера. Пусто ⇒ keyless-режим |
| `LLM_MODEL_CHAIN` | Список model id через запятую, по порядку |
| `LLM_EXHAUSTED_TTL_SECONDS` | Сколько пропускать модель после 429/quota |
| `USE_FAKE_LLM` | Принудительно детерминированный провайдер |
| `LLM_PROBE_ENABLED` | Гейт для `POST /api/v1/llm/complete` |
| `CORS_ALLOW_ORIGINS` | Origins через запятую; нужен только для дева без прокси |
| `MAX_MESSAGE_CHARS` / `MAX_HISTORY_MESSAGES` | Лимит сообщения и окна истории |
| `SCENARIOS_DIR` | Переопределение `configs/scenarios/` |
| `VITE_API_URL` | **Только build-time.** Пусто ⇒ относительный `/api/v1` за nginx |

Смена провайдера — это конфиг, а не код: переставь `LLM_BASE_URL` и `LLM_MODEL_CHAIN` и перезапусти.

## Разработка без Docker

```bash
docker compose up -d db                 # только Postgres

cd apps/api
uv sync
uv run alembic upgrade head
USE_FAKE_LLM=true uv run uvicorn app.main:app --reload --port 8000

cd ../web && npm install && npm run dev  # http://localhost:5173
```

Dev-сервер Vite проксирует `/api` на `:8000`, поэтому CORS не нужен. Если браузер ходит в API напрямую — поставь `CORS_ALLOW_ORIGINS=http://localhost:5173`: middleware подключается только когда список непустой.

## Тесты

```bash
cd apps/api
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/unit -q

docker compose up -d db
RUN_INTEGRATION=1 USE_FAKE_LLM=true \
  DATABASE_URL=postgresql+asyncpg://aichallenge:changeme@localhost:5432/aichallenge \
  uv run pytest tests/integration -q
```

Ключ провайдера не нужен нигде. Интеграционный набор накатывает схему через Alembic и чистит таблицы между тестами. CI (`.github/workflows/ci.yml`) гоняет ровно эту цепочку плюс сборку фронта.

## API (v1, контракт)

Префикс: `/api/v1`. Для сессии: заголовок `X-Session-Token`.

| Method | Path | Назначение |
|--------|------|------------|
| `GET` | `/health` | Liveness |
| `POST` | `/sessions` | Создать анонимную сессию → `{id, access_token}` |
| `GET` | `/sessions/{id}` | Метаданные (токен никогда не возвращается повторно) |
| `GET` | `/sessions/{id}/messages` | История (с `model_id`) |
| `POST` | `/sessions/{id}/messages` | Сообщение пользователя → **SSE** |
| `GET` | `/sessions/{id}/stream?message_id=` | Повтор сохранённого ответа тем же набором событий |
| `POST` | `/llm/complete` | Прямой probe к модели (без сессии) |

SSE-события: `model` → `token`* → `message_end` (или `error`). В `model` / `message_end` всегда есть фактический `model_id`.

## Секреты

1. Скопируй `.env.example` → `.env` **сам в редакторе**.
2. Не коммить `.env`, не вставляй ключи в чат Cursor/Claude Code.
3. Для демо без провайдера: `USE_FAKE_LLM=true` (или просто не заполняй ключ).
4. Имена переменных: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_CHAIN`, `DATABASE_URL`, …

`.env` исключён из обоих build-контекстов через `.dockerignore` и не попадает в слои образа. Подробнее: skill `aichallenge-secrets`, правило `.cursor/rules/secrets-safety.mdc`.

## Критерии приёмки челленджа (v1)

- [x] `docker compose up` поднимает db + api + web, health ок  
- [x] Анонимный чат по SSE, история в Postgres  
- [x] В UI и API виден `model_id` ответа  
- [x] `POST /llm/complete` возвращает ответ и `model_id`  
- [x] Смена провайдера (OpenRouter ↔ DeepSeek) — только конфиг/env  
- [x] Нет секретов в git; в коде нет медицинских ролей в нейминге  

## Осознанные ограничения v1

Не баги, а решения:

- **Failover только до первого токена.** Если провайдер умер после того, как текст пошёл, ответ завершается событием `error`, а частичный текст сохраняется с меткой `[interrupted]`. Смена модели посреди ответа склеила бы два разных ответа.
- **`GET /sessions/{id}/stream` — повтор, а не resume.** Ответ, который ещё генерируется, отдаёт 404; живой resume требует общего буфера и вне скоупа.
- **Состояние роутера — на процесс.** Для одного контейнера этого достаточно; Redis подставляется за тот же порт.
- **Нет аутентификации.** Сессии анонимные с bearer-токеном; `user_id` зарезервирован и не используется.
- **Нет rate-limit** на создание сессий.

## Вне скоупа v1

Auth/роли, админка сценариев, Redis для роутера, голос, биллинг, микросервисы.

## Production / CI/CD

- **Live:** http://aichallenge.arcilite.ru/ · http://aichallenge.arcilite.ru/
- **CI:** `.github/workflows/ci.yml` — lint, mypy, unit + integration (FakeLLM), web build
- **CD:** `.github/workflows/deploy.yml` — после зелёного CI на `main` (или вручную) деплой через GitHub Secrets
- **Compose prod:** `docker-compose.prod.yml`
- Секреты и `.env` только на хосте деплоя, **не** в git

## Лицензия / использование

Учебный / челлендж-репозиторий. Форк и PR приветствуются после стабилизации v1.
