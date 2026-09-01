# Локальные секреты (не в git)

Рабочий файл: **`.env`** в корне репо.

- Уже в `.gitignore` (и `.cursorignore`) — не попадёт в коммит и не должен читаться агентом.
- Шаблон без секретов: `.env.example` (в git).

## Заполнить ключ (RouterAI — по умолчанию)

1. Открой `.env`
2. Выставь:

```env
LLM_BASE_URL=https://routerai.ru/api/v1
LLM_API_KEY=сюда_ключ_routerai
# или только ROUTERAI_KEY=... — API подхватит, если LLM_API_KEY пуст
ROUTERAI_KEY=
LLM_MODEL_CHAIN=deepseek/deepseek-v4-flash,qwen/qwen3-235b-a22b-2507,deepseek/deepseek-v3.2,google/gemini-2.5-flash
USE_FAKE_LLM=false
```

### Цепочка по умолчанию (баланс ум / цена)

| Порядок | Model id | Зачем |
|--------:|----------|--------|
| 1 | `deepseek/deepseek-v4-flash` | основной, дёшево и заметно умнее tiny-моделей |
| 2 | `qwen/qwen3-235b-a22b-2507` | крупный MoE, failover |
| 3 | `deepseek/deepseek-v3.2` | стабильный mid-tier |
| 4 | `google/gemini-2.5-flash` | сильный запасной |

Каталог и цены: [routerai.ru](https://routerai.ru). Бесплатных chat-моделей у RouterAI нет — только pay-as-you-go в ₽.

При `429` / quota / payment-required роутер уходит на следующий id **до первого токена**.

### Дешёвая альтернатива (если нужен минимум ₽)

```env
LLM_MODEL_CHAIN=mistralai/mistral-nemo,meta-llama/llama-3.1-8b-instruct,deepseek/deepseek-v4-flash
```

Другие провайдеры (один за раз): OpenRouter `:free` (через sing-box на VPS) или прямой DeepSeek — см. `.env.example`.

### OpenRouter free через sing-box (если с VPS 403)

На проде настроен `llm-proxy` в Docker → sing-box mixed на хосте. Проверено: OpenRouter **200** через прокси (без 403).

1. Ключ: [openrouter.ai/keys](https://openrouter.ai/keys) → `OPENROUTER_API_KEY` в `.env`
2. На VPS после деплоя: `sudo bash scripts/llm-proxy-firewall.sh` (iptables для docker bridge)
3. Переключение в `.env`:

```env
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=ключ_openrouter
LLM_API_KEY=
LLM_HTTP_PROXY=http://llm-proxy:11081
LLM_MODEL_CHAIN=nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3-super-120b-a12b:free,nvidia/nemotron-3.5-lightning:free,minimax/minimax-m3:free,thinkingmachines/inkling:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,z-ai/glm-5.2:free,minimax/minimax-m2.7:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,poolside/laguna-s-2.1:free,cohere/north-mini-code:free,inclusionai/ling-3.0-flash-fin:free,openrouter/free,liquid/lfm-2.5-2.6b:free
LLM_FALLBACK_BASE_URL=https://routerai.ru/api/v1
LLM_FALLBACK_MODEL_CHAIN=deepseek/deepseek-v4-flash,qwen/qwen3-235b-a22b-2507,deepseek/deepseek-v3.2,google/gemini-2.5-flash
ROUTERAI_KEY=...   # fallback tier после исчерпания всех :free
```

4. `docker compose -f docker-compose.prod.yml up -d api --force-recreate`

## На хост деплоя

Скопируй `.env` на сервер **вне git** (scp/sftp/панель — как удобно), выставь права `600`, пересоздай контейнер `api` через `docker compose -f docker-compose.prod.yml`. Конкретные host/path/SSH-ключи в публичных доках не храним.

После смены только `LLM_*` достаточно `docker compose -f docker-compose.prod.yml up -d api --force-recreate` — **не** сноси volume Postgres (иначе браузерные сессии станут «призраками»).

Не вставляй ключи в чат Cursor/Claude и не коммить `.env`.
