# Lab Observability UI/UX — Design Spec

**Date:** 2026-09-03  
**Status:** Deferred (plan ready; implement **with or just before** Pareto + Feedback UI tasks)  
**Covers:** Model Pareto Lab + Feedback → Router surfaces  
**Specs:** `2026-09-03-model-pareto-lab-design.md`, `2026-09-03-feedback-router-design.md`  
**Frontend skill:** `.cursor/skills/aichallenge-frontend/SKILL.md`  
**Eval method:** Nielsen heuristics (`.claude/skills/ux-heuristics`)

## 1. Product intent (UX)

Две аудитории, один визуальный язык:

| Persona | Job | Surface |
|---------|-----|---------|
| **Автор / демо** | Показать, что платформа **мерит и рулит** моделями | Lab → вкладка «Модели» (Pareto + feedback) |
| **Обычный чат** | Быстро сказать «ответ ок / не ок», не утонуть в метриках | Thumbs под assistant bubble |

Не цель: отдельный «data science dashboard» на весь экран, Grafana-look, фиолетовый AI-glow.

## 2. Information architecture

```
Chat shell (existing)
├── Assistant Turn
│   ├── content + model_id label (existing)
│   ├── media / tools (existing)
│   └── Feedback strip (new) — only after message_end
└── float-dock (existing mutex Debug ↔ Results)
    └── Lab Insights float (new OR extend LabResults / Debug)
        ├── Tab: Рейтинг      ← Pareto table
        ├── Tab: Оценки       ← feedback by model
        └── Tab optional: Этот чат ← session traces
```

**Decision (locked for v1 UX):**  
Не плодить третий FAB рядом с Debug/Results. Добавить **вкладки внутрь** существующего Lab results float **или** одну новую FAB «Модели» в том же `float-dock`, подчиняющуюся тому же mutex (открыта только одна панель). Предпочтение: **одна FAB «Модели»** — иначе Results перегрузится judge-таблицей.

Mutex: Debug | Results | Models — максимум одна развёрнута.

## 3. Chat: feedback strip

### Placement
- Под текстом assistant, **над** нижней границей пузыря / в `Turn` footer рядом с `model_id`
- Не перекрывать media player

### Controls
- Две кнопки-иконки + доступный текст: «Полезно» / «Не полезно» (`aria-pressed`)
- После выбора: выбранная остаётся pressed; повторный клик **переключает** (last write wins на API)
- Пока идёт стрим: strip **скрыт** или disabled с `title="Дождитесь конца ответа"`

### Microcopy (RU, domain-agnostic)
- Helpful: «Полезно»
- Not: «Не полезно»
- Toast/inline: «Спасибо» (1.2s) — без «обучаем модель» (не обещать RLHF)
- Error: «Не удалось сохранить оценку»

### States
| State | UI |
|-------|-----|
| idle | обе кнопки ghost |
| pending | disabled + subtle opacity |
| up/down | pressed style на выбранной |
| error | краткий текст, кнопки снова active |

### Mobile
- Hit target ≥ 44×44 CSS px
- Не вызывать zoom; не открывать клавиатуру

## 4. Lab: Models float — «Рейтинг»

### Hierarchy (one job)
1. Заголовок: «Рейтинг моделей»
2. Одна строка контекста: окно «за 24 ч» (select: 24h / 7д)
3. Таблица (не scatter в v1 — denser и читаемее в float)

### Columns (recognition > recall)
| Col | Label | Hint (title) |
|-----|-------|----------------|
| model | Модель | resolved `model_id` |
| n | N | число завершённых прогонов |
| ok% | Успех | доля status=ok |
| p50 | p50, с | медиана total_ms / 1000 |
| cost | $/proxy | относительная стоимость |
| score | Score | формула в `<details>` |

### Empty / loading / error
- Loading: skeleton 3 rows (не spinner на весь chat)
- Empty: «Пока нет замеров. Отправьте пару сообщений в чат.»
- Error: «Не удалось загрузить рейтинг» + Retry

### Progressive disclosure
- `<details>Как считается Score</details>` — формула из spec, человеческим языком
- Row click / expand → last attempts for **current session** only (не глобальный drill-down в v1)

### Sorting
- Default: score desc
- Clickable headers optional v1.1; в v1 достаточно default

## 5. Lab: tab «Оценки»

- Таблица: модель | 👍 | 👎 | down%
- Badge на моделях с активным penalty: «временно ниже в очереди» (если API отдаст `penalized: true`)
- Не пугать «бан»; тон: система подстраивает порядок

## 6. Visual language (consistency)

Reuse tokens from `index.css`:
- `.lab-results-table`, `.float-dock`, `.ghost-button`, `.debug-float-*`
- Accent: существующий meta accent (не новый purple)
- Density: как LabResults — compact table, `max-height` + scroll внутри float
- Width: same as `.lab-results-float` / `.debug-float`

Motion: 1) float open 150–200ms ease; 2) feedback pressed scale 0.96; 3) skeleton shimmer optional mild. No confetti.

## 7. Accessibility

- FAB `aria-expanded`, `aria-controls`
- Escape closes float → focus back to FAB (как DebugFloat)
- Thumbs: `aria-label`, `aria-pressed`
- Tables: `<th scope="col">`, caption or `aria-labelledby`
- Contrast: score/warning text on float background ≥ WCAG AA
- Prefers-reduced-motion: skip scale/shimmer

## 8. Heuristic acceptance (ship gate)

Before merge UI, score each (0–4 Nielsen severity; **block if any ≥3 open**):

1. Visibility of status — loading/empty/error/pending feedback  
2. Real-world language — no raw JSON in primary UI  
3. User control — Escape, mutex, change vote  
4. Consistency — float-dock patterns  
5. Error prevention — no feedback mid-stream  
6. Recognition — column hints, formula details  
7. Flexibility — window 24h/7d for power users  
8. Aesthetic — one job per tab, no chart junk  
9. Error recovery — Retry  
10. Help — short formula + empty CTA  

## 9. Out of scope UI

- Full-screen analytics
- Scatterplot / D3 (optional later)
- Per-visitor public profiles
- Inline editing of cost proxy
- Explaining VPN/proxy to end users
