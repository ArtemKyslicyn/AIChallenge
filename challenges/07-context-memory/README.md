# Challenge 07 — Context Memory

История диалога в **Postgres** (`agent_dialogs`). После reload агент помнит факты.

Явные кейсы теста:
- **A** — сохранить: имя **Артем**, язык **Python**
- **B** — после перезапуска ответить строками `Имя:` / `Язык:`
- **C** — «Очистить лог» → история пустая

## Код / видео

```bash
python3 challenges/07-context-memory/run.py
cd challenges/record && RECORD_ONLY=07 npm run record
```

Артефакты: `results.json`, `RESULTS.md`, `challenge-07.mp4`.
