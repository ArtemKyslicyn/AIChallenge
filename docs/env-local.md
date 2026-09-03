# Локальные секреты (не в git)

Рабочий файл: **`.env`** в корне репо.

- Уже в `.gitignore` (и `.cursorignore`) — не попадёт в коммит и не должен читаться агентом.
- Шаблон без секретов: `.env.example` (в git).

## Заполнить ключ (рекомендуемый prod: free-first)

Цель: стабильность ≥90% при минимуме оплаты — OpenRouter `:free` → дешёвые платные OR → RouterAI.

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=сюда_ключ_openrouter
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=openrouter/free,nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4-31b-it:free,google/gemini-2.5-flash,deepseek/deepseek-chat
ROUTERAI_KEY=сюда_ключ_routerai
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=deepseek/deepseek-v4-flash,mistralai/mistral-nemo
LLM_MAX_ATTEMPTS=4
LLM_FIRST_TOKEN_TIMEOUT_SECONDS=18
LLM_EXHAUSTED_TTL_SECONDS=180
USE_FAKE_LLM=false
```

### Цепочка (free → cheap → RA)

| Порядок | Tier | Model | Зачем |
|--------:|------|-------|--------|
| 1–3 | OR primary | `openrouter/free`, nemotron-super:free, gemma:free | \$0 |
| 4–5 | OR primary | `gemini-2.5-flash`, `deepseek-chat` | дешёвый paid, добирает до ≥90% |
| 6–7 | RA fallback | `deepseek-v4-flash`, `mistral-nemo` | якорь стабильности |

Каталог free: [openrouter.ai/collections/free-models](https://openrouter.ai/collections/free-models). RouterAI: [routerai.ru](https://routerai.ru).

При `429` / quota / 404 / timeout роутер уходит на следующий id **до первого токена**.

### Дешёвая альтернатива только RouterAI

```env
LLM_BASE_URL=https://routerai.ru/api/v1
ROUTERAI_KEY=...
LLM_HTTP_PROXY=
LLM_MODEL_CHAIN=mistralai/mistral-nemo,meta-llama/llama-3.1-8b-instruct,deepseek/deepseek-v4-flash
```

Другие варианты — см. `.env.example`.

### Рекомендуемый prod: OpenRouter free-first + RouterAI fallback

Primary — free и дешёвые платные через proxy. Fallback — RouterAI flash/nemo.

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=...
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=openrouter/free,nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4-31b-it:free,google/gemini-2.5-flash,deepseek/deepseek-chat
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=deepseek/deepseek-v4-flash,mistralai/mistral-nemo
ROUTERAI_KEY=...
```

### OpenRouter как primary (если с VPS 403 — нужен proxy)

На проде настроен `llm-proxy` в Docker → sing-box mixed на хосте. Проверено: OpenRouter **200** через прокси (без 403).

1. Ключ: [openrouter.ai/keys](https://openrouter.ai/keys) → `OPENROUTER_API_KEY` в `.env`
2. На VPS после деплоя: `sudo bash scripts/llm-proxy-firewall.sh` (iptables для docker bridge)
3. Переключение в `.env`:

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=ключ_openrouter
LLM_API_KEY=
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3-super-120b-a12b:free,nvidia/nemotron-3.5-lightning:free,minimax/minimax-m3:free,thinkingmachines/inkling:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,z-ai/glm-5.2:free,minimax/minimax-m2.7:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,poolside/laguna-s-2.1:free,cohere/north-mini-code:free,inclusionai/ling-3.0-flash-fin:free,openrouter/free,liquid/lfm-2.5-2.6b:free,google/gemini-2.5-flash,deepseek/deepseek-chat,openai/gpt-4o-mini
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=mistralai/mistral-nemo,meta-llama/llama-3.1-8b-instruct,deepseek/deepseek-v4-flash
ROUTERAI_KEY=...   # fallback: дешёвые RouterAI после OpenRouter
```

4. `docker compose -f docker-compose.prod.yml up -d api --force-recreate`

## На хост деплоя

Скопируй `.env` на сервер **вне git** (scp/sftp/панель — как удобно), выставь права `600`, пересоздай контейнер `api` через `docker compose -f docker-compose.prod.yml`. Конкретные host/path/SSH-ключи в публичных доках не храним.

После смены только `LLM_*` достаточно `docker compose -f docker-compose.prod.yml up -d api --force-recreate` — **не** сноси volume Postgres (иначе браузерные сессии станут «призраками»).

Для полного редеплоя кода на сервере: `scripts/deploy.sh` (не вызывает `compose down`). Браузер: **https://aichallenge.arcilite.ru:8443/** — если обычный `:443` зависает на TLS с твоей сети.

Media tools (картинки/видео в чате): в `.env` на сервере `MEDIA_TOOLS_ENABLED=true`, опционально `POLLINATIONS_API_KEY`, для видео `PIXAZO_API_KEY`. Затем recreate `api`.

Не вставляй ключи в чат Cursor/Claude и не коммить `.env`.

## Наблюдаемость и оценки (имена переменных)

Каждый завершённый ответ пишет `RunTrace`; вкладка «Модели → Рейтинг» строит по ним таблицу,
вкладка «Оценки» — по 👍/👎 под ответами. Значения ниже — дефолты, ключей здесь нет.

| Переменная | Что делает |
|------------|------------|
| `RUN_TRACE_ENABLED` | писать ли трейсы. `false` останавливает сбор, но уже собранное остаётся видимым |
| `MODEL_COST_PROXY_JSON` | JSON `{"model-id": 0.2}` — относительная цена модели для колонки Cost и Score. Пусто = без цены |
| `FEEDBACK_DOWN_RATE_THRESHOLD` | доля «Не полезно», с которой модель уезжает в конец авто-цепочки (0.6) |
| `FEEDBACK_MIN_VOTES` | минимум голосов, до которого штраф не применяется (5) |
| `FEEDBACK_PENALTY_TTL_SECONDS` | окно голосов; оно же само снимает штраф, когда старые голоса выпали (86400) |
| `FEEDBACK_PENALTY_REFRESH_SECONDS` | как часто процесс перечитывает агрегаты (60) |
| `FEEDBACK_EXPORT_ENABLED` | включает `GET /lab/preference-export`; выключено — ручка отвечает 404 |
| `FEEDBACK_EXPORT_INCLUDE_CONTENT` | класть ли текст промпта и ответа в выгрузку. По умолчанию нет |

Штраф — это **переупорядочивание, а не бан**: оштрафованная модель уходит в конец цепочки, но
остаётся в ней, а явный пин модели в композере всегда пробуется первым. Правило «переключаться
только до первого токена» это не меняет.

Выгрузка предпочтений выключена по умолчанию потому, что каждая строка ссылается на конкретное
сообщение. Включать её стоит на время выгрузки датасета, а не постоянно.
