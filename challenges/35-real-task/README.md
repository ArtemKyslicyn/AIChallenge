# Day 35 — Подготовить changelog

**На сайте:** **Ассистент → Changelog**

**Цель:** инвариант-ревью → AI changelog; на экране `model_id`.

**Модель:** по умолчанию локальная (`ollama/…` если подключена); в селекторе можно облако / Авто. API: `POST /api/v1/assistants/real-task` с `model` + `local_llm_scope`. Для сдачи — бейдж `ollama/…`.

## Что сделать

1. Подключи Local LLM
2. **Ассистент → Changelog** — проверь селектор модели
3. **Подготовить changelog**
4. Показать `model_id` + текст

## Что сдать

| Артефакт | Файл |
|---|---|
| Видео | `challenge-35.mp4` |
| Чеклист | [`RESULTS.md`](RESULTS.md) |
