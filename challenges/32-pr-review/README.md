# Day 32 — Проверить diff

**На сайте:** **Ассистент → Diff**

**Цель:** инварианты репо (секреты, compose down, слои). **Без LLM.**

## Что сделать

1. **Ассистент → Diff**
2. `python3 challenges/32-pr-review/run.py` или `./scripts/review.sh HEAD~1`
3. CI: `.github/workflows/review.yml` — секреты → fail

## Что сдать

| Артефакт | Файл |
|---|---|
| Видео UI + CLI | `challenge-32.mp4` |
| Скрипт | `run.py` |
| Чеклист | [`RESULTS.md`](RESULTS.md) |
