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
LLM_MODEL_CHAIN=mistralai/mistral-nemo,meta-llama/llama-3.1-8b-instruct,inclusionai/ling-3.0-flash,openai/gpt-oss-20b,deepseek/deepseek-v4-flash
USE_FAKE_LLM=false
```

Цепочка — самые дешёвые `text→text` из каталога RouterAI (бесплатных chat-моделей у них нет). При 429/quota роутер уходит на следующий id.

Альтернативы (один провайдер за раз): OpenRouter `:free` или DeepSeek — см. комментарии в `.env.example`.

## На хост деплоя

Скопируй `.env` на сервер **вне git** (scp/sftp/панель — как удобно), выставь права `600`, пересоздай контейнер `api` через `docker compose -f docker-compose.prod.yml`. Конкретные host/path/SSH-ключи в публичных доках не храним.

Не вставляй ключи в чат Cursor/Claude и не коммить `.env`.
