# Документация AIChallenge

Карта документов репозитория. Начни с [корневого README](../README.md).

## Спеки и планы

| Файл | Описание |
|------|----------|
| [specs/2026-08-31-ai-chat-platform-design.md](superpowers/specs/2026-08-31-ai-chat-platform-design.md) | **Design spec** — целевая архитектура v1: hexagonal monorepo, API/SSE, LLM ModelRouter, Postgres, секреты, критерии успеха. Источник правды по дизайну. |
| [plans/2026-08-31-ai-chat-platform-claude-code.md](superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md) | **Implementation plan** для Claude Code: 15 задач с TDD-шагами, file map, DoD, правила секретов. Им исполняют агенты. |

## Агенты и соглашения

| Файл | Описание |
|------|----------|
| [../CLAUDE.md](../CLAUDE.md) | Entrypoint Claude Code (Anthropic-аккаунт). |
| [../AGENTS.md](../AGENTS.md) | Общие правила агентов + индекс skills. |
| [../.cursor/skills/](../.cursor/skills/) | Project skills: architecture, secrets, llm, docker, frontend, testing. |
| [../.cursor/rules/](../.cursor/rules/) | Always-on / glob rules (secrets, conventions, api, web). |

## Конфиги продукта (не секреты)

| Путь | Описание |
|------|----------|
| [../configs/scenarios/](../configs/scenarios/) | YAML-сценарии диалога (нейтральный язык). |
| [../.env.example](../.env.example) | Шаблон env: RouterAI / OpenRouter / DeepSeek (один провайдер за раз). |
| [env-local.md](env-local.md) | Локальный `.env` (gitignore): RouterAI по умолчанию, цепочка моделей, заливка на хост. |
| [../docker-compose.yml](../docker-compose.yml) | Стек `db + api + web`; работает без `.env` (keyless). |
| [../docker-compose.prod.yml](../docker-compose.prod.yml) | Prod compose (web на loopback). |
| [../.github/workflows/ci.yml](../.github/workflows/ci.yml) | CI: ruff, mypy, unit + integration, сборка фронта. |
| [../.github/workflows/deploy.yml](../.github/workflows/deploy.yml) | CD после зелёного CI / вручную (нужен явный запрос на деплой). |

## Как обновлять доки

1. Существенные архитектурные решения — сначала в **design spec**, потом в код.  
2. Порядок реализации — в **plan** (чеклисты задач).  
3. README — лицо челленджа: цели, статус, быстрый старт, ссылки сюда.
