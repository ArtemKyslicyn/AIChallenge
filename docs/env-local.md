# Локальные секреты (не в git)

Рабочий файл: **`.env`** в корне репо.

- Уже в `.gitignore` (и `.cursorignore`) — не попадёт в коммит и не должен читаться агентом.
- Шаблон без секретов: `.env.example` (в git).

## Заполнить ключ

1. Открой `.env`
2. Для DeepSeek раскомментируй и вставь:

```env
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=сюда_ключ
LLM_MODEL_CHAIN=deepseek-chat,deepseek-reasoner
USE_FAKE_LLM=false
```

(Блок OpenRouter выше в файле закомментируй или перезапиши теми же переменными — активен один провайдер.)

## Безопасно на сервер

```bash
# с Mac, из корня репо
scp -i ~/.ssh/SSH_KEY .env DEPLOY_HOST:APP_DIR/.env
ssh DEPLOY_HOST 'chmod 600 APP_DIR/.env && cd APP_DIR && docker compose -f docker-compose.prod.yml up -d --force-recreate api'
```

Не вставляй ключи в чат Cursor/Claude и не коммить `.env`.
