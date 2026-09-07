# Challenges (Days 4–6)

Автопрогон заданий челленджа через **prod** API платформы AIChallenge.

| Папка | День | UI на платформе |
|-------|------|-----------------|
| [`04-temperature/`](04-temperature/) | Температура 0 / 0.7 / 1.2 | Режим **×T** |
| [`05-model-tiers/`](05-model-tiers/) | Слабая / средняя / сильная | **Модели → Студия** |
| [`06-first-agent/`](06-first-agent/) | Первый агент (definition → run) | Topbar **Агенты** / `?shell=agents` |

## Прогон (prod)

```bash
# из корня репо
python3 challenges/04-temperature/run.py
python3 challenges/05-model-tiers/run.py
python3 challenges/06-first-agent/run.py
```

По умолчанию `BASE_URL=https://aichallenge.arcilite.ru`. Результаты: `results.json` + `RESULTS.md` в каждой папке.

## Видео UI

```bash
cd challenges/record
npm install
npx playwright install chromium
npm run record
# или только день 6:
RECORD_ONLY=06 npm run record
```

Пишет `challenge-04|05|06.webm` / `.mp4` (нужен `ffmpeg`).

Формат сдачи: **Видео + Код** (этот каталог + ролики).
