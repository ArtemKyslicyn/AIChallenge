# 26 — локальная модель

Видео уже снято: `challenge-26.mp4`. Модель `qwen36-fast:latest` (35.5B, Q4_K_M) на M1 `http://100.90.210.109:11435`. Теги 8B на этом Mac в зачёт не идут.

Проверка без сети:

```bash
python3 challenges/26-local-llm/run.py --score-only
```

Полный прогон к Ollama: `node challenges/record/record-local-llm.mjs` из `challenges/record`. Опциональный второй адрес, когда поднят `ssh -N kalinin-gpu`: `http://127.0.0.1:21434`.
