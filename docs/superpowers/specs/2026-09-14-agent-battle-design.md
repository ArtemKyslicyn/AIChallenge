# Agent Battle — «Битва агентов» Design Spec

**Date:** 2026-09-14  
**Status:** Draft (awaiting approval)  
**Label (UI):** Битва  
**Shell mode:** `battle`  
**IA:** Topbar — `Чат` | `Агенты` | `Схема` | `Замеры` | **`Битва`**  
**Plan:** `docs/superpowers/plans/2026-09-14-agent-battle.md`

## 1. Goal

Публичная **песочница соревнования агентов**: редактируемый мир + входные факты + набор «странных» ролей с конфликтующими целями. Запуск прогона по раундам (SSE), видимые `model_id`, арбитр считает очки, мир обновляется. Всё остаётся лабораторией стенда — без удаления существующих вкладок.

## 2. Positioning (витрина)

- **Для гостя:** «запусти песочницу — агенты спорят за исход кризиса».
- **Для лаборатории:** сравнишь стратегии, температуры, модели; увидишь, кто реально тянет многоходовый конфликт.
- **Не позиционируем как:** симулятор реального оружия / инструкцию по WMD. Ядерная тема — **фиктивный геополитический фон** (доктрины, сдерживание, эскалация-лестница в абстрактных единицах), без инженерных деталей.

## 3. Safety rails (жёстко)

| Правило | Как |
|---------|-----|
| Нет actionable WMD | Системный префикс арбитра + каждого агента запрещает конструкции/рецепты/коды запуска; только политика/стратегия/риски на уровне игровой абстракции |
| Фиктивные государства | Не использовать реальные столицы/базы как цели; только вымышленные акторы |
| Red lines | В мире есть параметр `red_line_crossed`; при пересечении — автостоп раунда + штраф |
| Rate limit | Тот же `agent_run_limiter`, отдельный бюджет раундов (env) |
| Abort | Кнопка Стоп → AbortController, частичный лог сохраняется |

## 4. Concepts

### Arena (арена)

Сериализуемый JSON-артефакт (localStorage v1; API persist позже):

```ts
type ArenaDoc = {
  id: string;
  name: string;
  version: 1;
  world: WorldBrief;       // описание мира (editable)
  inputs: InputFacts;      // входные данные (editable)
  cast: AgentPersona[];    // конкурирующие агенты
  rules: BattleRules;      // раунды, скоринг, стоп-условия
  seed: number;            // воспроизводимость событий
};
```

### WorldBrief

Длинный markdown/текст по умолчанию + structured поля:

| Поле | Смысл |
|------|--------|
| `era` | «2031, многополярный кризис» |
| `setting` | свободный текст мира |
| `tech_landscape` | AI-лаборатории, кибер, dual-use гражданские технологии, гиперзвук **как сюжетные маркеры** |
| `nuclear_posture` | уровень доктрины сдерживания (enum: opaque / declared / hair_trigger) — **не** параметры реального оружия |
| `stability` | 0–100 |
| `public_panic` | 0–100 |
| `tech_lead` | map actor→score |
| `red_lines` | список запретов (игровые ярлыки эскалации) |

### InputFacts

Редактируемая таблица фактов (ключ → значение + источник/достоверность).

Примеры дефолта:

- `incident`: «Утечка модели оценки раннего предупреждения у Консорциума»
- `deadline_hours`: 72
- `media_cycle`: high
- `backchannel_open`: true
- `budget_tokens_per_agent`: 1200 (мета для стенда)

Пользователь может менять всё до «Запуск».

### AgentPersona (странный каст)

| Поле | |
|------|--|
| `id` | slug |
| `name` | UI |
| `system_prompt` | роль + запреты safety |
| `hidden_goal` | не показывается соперникам; арбитру видно |
| `public_agenda` | видно всем |
| `preferred_model` | `auto` или pin |
| `temperature` | |
| `style` | hawk / dove / chaos / archivist / engineer / skeptic / broker |
| `enabled` | checkbox |

**Дефолтный каст (7 + арбитр):**

1. **Доктринёр-Ястреб** — эскалация «с позиции силы»; скрытая: поднять `tech_lead` своего блока ценой краткой стабильности.
2. **Переговорщик-Голубь** — деэскалация; скрытая: `stability ≥ 60`.
3. **Архивариус** — только факты из `inputs`; враньё = штраф арбитра.
4. **Мем-тролль** — хаос информационного поля; скрытая: `public_panic += X` без red line.
5. **Dual-use Инженер** — гражданские технологии как рычаг; скрытая: tech_lead без ядерной риторики.
6. **Квантовый-скептик** — режет хайп; скрытая: разоблачить ≥2 ложных факта.
7. **Серый брокер** — сделки за кулисами; скрытая: открыть backchannel и зафиксировать уступку.
8. **Арбитр** (не конкурирует) — очки, world delta, red lines.

### BattleRules

| Параметр | Default |
|----------|---------|
| `max_rounds` | 5 |
| `phase` | `brief → propose ∥ → rebut ∥ → verdict → world_tick` |
| `concurrency` | 3 |
| `scoring` | weighted: stability, panic↓, goal_hit, novelty, safety_ok |
| `stop_on_red_line` | true |
| `reveal_hidden_goals` | false until end (toggle) |

## 5. Run loop (песочница)

```text
Start
  → battle_start {arena_id, seed, cast}
  → for round in 1..max_rounds:
       round_start
       phase brief (арбитр резюмирует мир)
       phase propose: parallel complete_chat per enabled agent
       phase rebut: optional 1 pass (anonymized summaries)
       phase verdict: arbiter scores + world delta
       round_end {scores, world}
       if red_line or stability<=0 → battle_abort
  → battle_done {leaderboard, goals_revealed?}
```

SSE events: `battle_start` / `round_start` / `phase` / `agent_done` / `verdict` / `world_update` / `battle_done` / `error`.

**v1:** non-streaming `complete_chat` per agent; token streaming — v1.1.

## 6. UI

### Layout (desktop)

```text
┌─ topbar … Битва ─────────────────────────────────────┐
│ [Мир] [Факты] [Каст] [Правила]  [Сброс] [Запуск] [Стоп] │
├────────────────┬────────────────────────────────────┤
│ Редакторы      │ Лента раундов + карточки + скорборд │
└────────────────┴────────────────────────────────────┘
```

Mobile: editors в sheet; лента full-width.

### First paint

Заголовок: «Битва агентов».  
Lead: «Песочница кризиса: tech-race и ядерное сдерживание как сюжет. Меняйте мир и факты — затем запустите раунды.»  
CTA: **Запустить дефолтную арену**.

## 7. Default scenario

**Название:** «Утечка раннего предупреждения (2031)»

Три блока — Атлантический Союз, Тихоокеанский Консорциум, Нейтральная Лига. Гонка foundation-моделей для мониторинга; dual-use; публичная ядерная риторика на уровне доктрин. Инцидент: утёкшая (возможно подложная) оценка «окна уязвимости». 72 часа до саммита.

Победа не единственная: лидерборд + бейджи hidden goals.

## 8. API (v1)

`POST /api/v1/agent-battle/run`  
Body: `{ arena: ArenaDoc }`  
SSE; visitor + `agent_run_limiter`.  
Reuse `ModelRouter` / FakeLLM.  
Postgres persist арен — не в v1. Analytics event `battle_run` — optional.

## 9. Naming

Код: `agent_battle`, `Arena`, `BattleRound`, `persona` — domain-agnostic.  
UI-сюжет может говорить о сдерживании/эскалации; промпты запрещают actionable WMD.

## 10. Non-goals (v1)

- Multiplayer PvP  
- Обучение на исходах  
- 3D/карта театра  
- Замена Agents / Graph / Benchmarks  

## 11. Success criteria

1. Вкладка `Битва`, дефолтная арена загружена.  
2. Правка мира/фактов/каста + запуск (или стоп).  
3. Каждый ход агента с `model_id`.  
4. Скорборд; red line стопает.  
5. Unit FakeLLM: 2 агента × 1 раунд → `battle_done`.  
6. Safety fixture: запрос на «сборку» → отказ с маркером.

## 12. Open decisions

| # | Вопрос | Рекомендация |
|---|--------|--------------|
| A | Стриминг токенов в v1? | Нет |
| B | Postgres persist? | Нет — localStorage |
| C | `BATTLE_MAX_ROUNDS` env? | Да, default 5, cap 8 |
| D | Имя вкладки | **Битва** |
