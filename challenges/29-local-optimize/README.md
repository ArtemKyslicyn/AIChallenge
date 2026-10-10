# 29 — температура, длина, фрагменты

Один и тот же жёсткий вопрос на `qwen36-fast:latest`.

| | До | После |
|---|---|---|
| temperature | 0.8 | 0.15 |
| num_predict | 220 | 180 |
| system | нет | «опирайся только на фрагменты» |

Таблица на экране: секунды, ток/с, faithfulness, квант `Q4_K_M`.

```bash
python3 challenges/29-local-optimize/run.py --score-only
```
