# День 23 — 10 контрольных вопросов (стендовая база)

Прогонять с галочкой **«Использовать базу»**. Ожидание: ответ опирается на docs + блок «Источники базы».

| # | Вопрос | Ожидание | Источники (примерно) |
|---|---|---|---|
| 1 | Что такое `model_id` в ответах? | Каждому ответу ассистента атрибутируется id модели (API/SSE/UI/DB) | AGENTS.md, design spec |
| 2 | Куда ходит публичный :443? | xray Reality → nginx :8443 → web :18080 | deploy-vless / README Production |
| 3 | Что такое Guest MCP? | Свой Streamable HTTP MCP посетителя, не стендовый `/mcp/*` | guest-mcp design, docs |
| 4 | Как подключить локальный kit? | Clone kit → tunnel → URL+Bearer в Подключениях | mcp-kit design / guest packs |
| 5 | Где править сценарии чата? | `configs/scenarios` YAML | architecture / CLAUDE.md |
| 6 | Что делает FakeLLM? | Тесты/демо без ключа LLM | AGENTS, .env.example notes |
| 7 | Зачем `X-Session-Token`? | Анонимная сессия чата | platform design |
| 8 | Что такое Profile «Профиль»? | Аккаунт, модели, подключения, Guest MCP | profile design |
| 9 | Можно ли `compose down` на проде? | Нет — rolling up, edge guards | deploy-vless-safe |
| 10 | Чем RAG fixed отличается от structural? | Размер vs заголовки/файлы | этот сервис / challenge 22 |

## Сравнение без RAG / с RAG

Для вопросов 1–3 и 9 зафиксировать в видео: без базы модель чаще галлюцинирует порты/имена; с базой — цитирует фрагменты и блок «Источники».
