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
| LLM | OpenAI-compatible + ModelRouter (failover до 1-го токена); по умолчанию **RouterAI**, также OpenRouter / DeepSeek |
| Прозрачность | У каждого ответа ассистента видно **`model_id`** (API, SSE, UI, БД) |
| Секреты | `.env` только локально; в git и в чат агентам — **никогда** |
| Домен | Код **domain-agnostic** (без patient/doctor и т.п. в именах); сценарии — конфиг |

Продуктовый смысл (например, диалог перед визитом) задаётся позже через сценарии/конфиг, не через названия модулей.

## Статус

v1 **в `main` и на live**: API (hexagonal, ModelRouter, Postgres/Alembic), SPA с SSE и лейблом `model_id`, Docker Compose / prod, CI/CD. Провайдер по умолчанию — **RouterAI** (`routerai.ru`), цепочка моделей — env `LLM_MODEL_CHAIN`.

Дополнительно в UI: выбор модели в композере, режим **«Два рядом»** (compare через probe), шаблоны/свои правила ответа, сайдбар истории чатов (локальный кэш + `X-Visitor-Id`).

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
cp .env.example .env   # RouterAI: LLM_API_KEY или ROUTERAI_KEY + LLM_MODEL_CHAIN
docker compose up -d --build api
```

Подробнее: [docs/env-local.md](docs/env-local.md).

## Конфигурация

Только имена. Значения живут в `.env`, который в `.gitignore` и который нельзя коммитить, печатать или вставлять в чат агента.

| Переменная | Назначение |
|------------|------------|
| `DATABASE_URL` | DSN Postgres (`postgresql+asyncpg://…`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Доступы сервиса `db` |
| `LLM_BASE_URL` | OpenAI-совместимый endpoint. По умолчанию `https://routerai.ru/api/v1` |
| `LLM_API_KEY` | Ключ провайдера. Пусто ⇒ keyless / FakeLLM (или возьмётся `ROUTERAI_KEY`) |
| `ROUTERAI_KEY` | Алиас ключа RouterAI, если `LLM_API_KEY` пуст |
| `LLM_MODEL_CHAIN` | Model id через запятую (failover по порядку). Дефолт — баланс ум/цена через RouterAI |
| `LLM_EXHAUSTED_TTL_SECONDS` | Сколько пропускать модель после 429/quota |
| `USE_FAKE_LLM` | Принудительно детерминированный провайдер |
| `LLM_PROBE_ENABLED` | Гейт для `POST /api/v1/llm/complete` |
| `CORS_ALLOW_ORIGINS` | Origins через запятую; нужен только для дева без прокси |
| `MAX_MESSAGE_CHARS` / `MAX_HISTORY_MESSAGES` | Лимит сообщения и окна истории |
| `SCENARIOS_DIR` | Переопределение `configs/scenarios/` |
| `VITE_API_URL` | **Только build-time.** Пусто ⇒ относительный `/api/v1` за nginx |

Смена провайдера или модели — только конфиг: `LLM_BASE_URL` + ключ + `LLM_MODEL_CHAIN`, затем перезапуск `api`.

Дефолтная цепочка RouterAI (см. `.env.example`):

`deepseek/deepseek-v4-flash` → `qwen/qwen3-235b-a22b-2507` → `deepseek/deepseek-v3.2` → `google/gemini-2.5-flash`

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

Префикс: `/api/v1`. Для сессии: `X-Session-Token`. Для истории посетителя: `X-Visitor-Id` (UUID из `localStorage`).

| Method | Path | Назначение |
|--------|------|------------|
| `GET` | `/health` | Liveness |
| `POST` | `/sessions` | Создать анонимную сессию → `{id, access_token}` |
| `GET` | `/sessions/history` | Сводка сессий текущего visitor (title / count) |
| `GET` | `/sessions/{id}` | Метаданные (токен никогда не возвращается повторно) |
| `GET` | `/sessions/{id}/messages` | История (с `model_id`) |
| `POST` | `/sessions/{id}/messages` | Сообщение пользователя → **SSE**; опционально `{model}` |
| `GET` | `/sessions/{id}/stream?message_id=` | Повтор сохранённого ответа тем же набором событий |
| `GET` | `/llm/models` | Каталог моделей для UI (id, label, capabilities) |
| `POST` | `/llm/complete` | Probe (без записи в чат); generation: temperature / reasoning / … |
| `GET` | `/media/{id}.ext` | Сгенерированные картинка/видео (если `MEDIA_TOOLS_ENABLED`) |

SSE-события: `model` → (`tool_start` / `tool_result`)* → `token`* → `message_end` (или `error`). В `model` / `message_end` всегда есть фактический `model_id`.

Media tools (опционально): intent / OpenAI `tool_calls` → Pollinations (image) / Pixazo LTX (video). Включается `MEDIA_TOOLS_ENABLED=true`; см. `.env.example`.

## Секреты

1. Скопируй `.env.example` → `.env` **сам в редакторе**.
2. Не коммить `.env`, не вставляй ключи в чат Cursor/Claude Code.
3. Для демо без провайдера: `USE_FAKE_LLM=true` (или просто не заполняй ключ).
4. Имена переменных: `LLM_BASE_URL`, `LLM_API_KEY`, `ROUTERAI_KEY`, `LLM_MODEL_CHAIN`, `DATABASE_URL`, …

`.env` исключён из обоих build-контекстов через `.dockerignore` и не попадает в слои образа. Подробнее: skill `aichallenge-secrets`, правило `.cursor/rules/secrets-safety.mdc`.

## Критерии приёмки челленджа (v1)

- [x] `docker compose up` поднимает db + api + web, health ок  
- [x] Анонимный чат по SSE, история в Postgres  
- [x] В UI и API виден `model_id` ответа  
- [x] `POST /llm/complete` возвращает ответ и `model_id`  
- [x] Смена провайдера (RouterAI ↔ OpenRouter ↔ DeepSeek) — только конфиг/env  
- [x] Нет секретов в git; в коде нет медицинских ролей в нейминге  

## Осознанные ограничения v1

Не баги, а решения:

- **Failover только до первого токена.** Если провайдер умер после того, как текст пошёл, ответ завершается событием `error`, а частичный текст сохраняется с меткой `[прервано]`. Смена модели посреди ответа склеила бы два разных ответа.
- **`GET /sessions/{id}/stream` — повтор, а не resume.** Ответ, который ещё генерируется, отдаёт 404; живой resume требует общего буфера и вне скоупа.
- **Состояние роутера — на процесс.** Для одного контейнера этого достаточно; Redis подставляется за тот же порт.
- **Нет аутентификации.** Сессии анонимные с bearer-токеном; `user_id` зарезервирован и не используется.
- **Нет rate-limit** на создание сессий.
- **Сессия в `localStorage`.** После сброса БД id становится призраком; SPA проверяет сессию на load и при 404 создаёт новую («Новый чат» делает то же вручную).
- **Compare («Два рядом»)** идёт через `POST /llm/complete`, не пишется в Postgres; после перезагрузки страницы пары сравнения в треде нет.
- **Сайдбар истории** показывает только чаты с токеном в этом браузере; сервер обогащает title/count, чужие сессии не отдаёт.
- **Media tools** выключены по умолчанию (`MEDIA_TOOLS_ENABLED=false`). Картинки — Pollinations (ключ опционален), видео — Pixazo LTX (`PIXAZO_API_KEY`). Локальный GPU не используется.

## Вне скоупа v1

Auth/роли, админка сценариев, Redis для роутера, голос, биллинг, микросервисы, live-resume SSE.

## Production / CI/CD

- **Live (предпочтительно):** https://aichallenge.arcilite.ru/ (`:443` через Reality)  
  Если TLS на `:443` зависает с твоей сети — запасной URL: https://aichallenge.arcilite.ru:8443/  
  Health: `/api/v1/health`.
- **CD:** `.github/workflows/deploy.yml` → на сервере `scripts/deploy.sh`  
  Протокол: **rolling** recreate, **без** `compose down`, **без** рестарта xray; после деплоя проверка и `:443`, и `:8443` (см. `.cursor/rules/deploy-vless-safe.mdc`).
- **Compose prod:** `docker-compose.prod.yml` (web на `127.0.0.1:18080`, снаружи — host nginx на `:8443`, xray на `:443`)
- Секреты и `.env` только на хосте деплоя, **не** в git
- Деплой на VPS агентом — только по **явному** запросу («задеплой» и т.п.)

## Лицензия / использование

Учебный / челлендж-репозиторий. Форк и PR приветствуются после стабилизации v1.
