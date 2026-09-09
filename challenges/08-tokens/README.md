# Challenge 08 — Token Meter

Подсчёт токенов агента (`~len/4`): запрос / история / ответ / всего + `cost_proxy`.
При переполнении `context_limit` — обрезка старой истории и баннер в UI.

## На платформе

1. https://aichallenge.arcilite.ru/?shell=agents → **Один агент**
2. Короткий вопрос → смотри блок **Токены** под ответом
3. Несколько реплик подряд → рост `История` / `Всего`
4. Поле **Лимит контекста** = `120` → длинная история → баннер «История обрезана»

## Код / видео

```bash
python3 challenges/08-tokens/run.py
cd challenges/record && RECORD_ONLY=08 npm run record
```

Артефакты: `results.json`, `RESULTS.md`, `challenge-08.mp4`.
