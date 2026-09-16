# Challenges (Days 4–12)

Автопрогон заданий челленджа через **prod** API платформы AIChallenge.

| Папка | День | UI на платформе |
|-------|------|-----------------|
| [`04-temperature/`](04-temperature/) | Температура 0 / 0.7 / 1.2 | Режим **×T** |
| [`05-model-tiers/`](05-model-tiers/) | Слабая / средняя / сильная | **Модели → Студия** |
| [`06-first-agent/`](06-first-agent/) | Первый агент + команда | Topbar **Агенты** |
| [`07-context-memory/`](07-context-memory/) | Память диалога | **Агенты** → reload |
| [`08-tokens/`](08-tokens/) | Токены / обрезка контекста | **Агенты** → лимит + метр |
| [`09-compression/`](09-compression/) | Сжатие истории (LLM summary) | **Агенты** → Контекст: Сжатие |
| [`10-context-strategies/`](10-context-strategies/) | Sliding / Facts / Branching | **Агенты** → selector + ветки |
| [`11-agent-memory/`](11-agent-memory/) | 3 слоя памяти (short/working/LTM) | **Агенты** → Память · 3 слоя |
| [`12-personalization/`](12-personalization/) | Prefs + ExpertLens + Auth | **Войти** + Профиль / Призма |

## Прогон (prod)

```bash
python3 challenges/12-personalization/run.py
```

## Видео UI

```bash
cd challenges/record && RECORD_ONLY=12 npm run record
```

Текст ролика дня 12: [`12-personalization/VIDEO.md`](12-personalization/VIDEO.md)
