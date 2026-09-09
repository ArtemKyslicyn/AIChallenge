# Challenge 07 — Context Memory (Артем)

Prod: `https://aichallenge.arcilite.ru` · 2026-09-08T16:04:37.292222+00:00

- Draft: `challenge-07-artem` · model: `google/gemini-2.5-flash`
- Case A store: **Артем** + **Python**
- Case B recall after restart: format `Имя:` / `Язык:` — **passed**
- Case C clear → `0` messages

## A — store

Меня зовут Артем. Запомни два факта для теста памяти: (1) моё имя — Артем; (2) любимый язык программирования — Python. Подтверди кратко оба факта.

Привет, Артем! Подтверждаю:
1. Ваше имя — Артем.
2. Ваш любимый язык программирования — Python.

## B — recall

Проверка после перезапуска. Ответь ровно двумя строками:
Имя: <только имя>
Язык: <только язык>

Имя: Артем
Язык: Python

## C — after clear

Не знаю.

UI: https://aichallenge.arcilite.ru/?shell=agents
