# Lab observability — UX ship checklist & microcopy

**Status:** Deferred template — tick during UX plan Task 7.  
**Spec:** `2026-09-03-lab-observability-ux-design.md`

## Microcopy (RU) — do not invent variants in PRs

| Key | String |
|-----|--------|
| fab_models | Модели |
| tab_ranking | Рейтинг |
| tab_feedback | Оценки |
| title_ranking | Рейтинг моделей |
| window_24h | 24 часа |
| window_7d | 7 дней |
| col_model | Модель |
| col_n | N |
| col_ok | Успех |
| col_p50 | p50, с |
| col_cost | Cost |
| col_score | Score |
| hint_n | Сколько раз модель завершила ответ в окне |
| hint_ok | Доля успешных ответов |
| hint_p50 | Медиана времени ответа |
| hint_cost | Относительная стоимость (proxy) |
| hint_score | Успех / время / cost — выше лучше |
| formula_summary | Score = успех ÷ время_ответа ÷ cost. Нужен баланс качества, скорости и цены. |
| empty_ranking | Пока нет замеров. Отправьте пару сообщений в чат. |
| err_ranking | Не удалось загрузить рейтинг |
| retry | Повторить |
| sorted_by | Сортировка: Score ↓ |
| feedback_up | Полезно |
| feedback_down | Не полезно |
| feedback_thanks | Спасибо |
| feedback_err | Не удалось сохранить оценку |
| empty_feedback | Оценок пока нет — нажмите «Полезно» / «Не полезно» под ответом. |
| penalized_chip | Ниже в очереди |
| title_feedback | Оценки моделей |
| col_down_rate | Доля 👎 |
| formula_details | Как считается Score |
| sorted_by_feedback | Сортировка: доля 👎 ↓ |
| err_feedback | Не удалось загрузить оценки |
| feedback_group | Оценка ответа |
| a11y_window | Период |
| a11y_tabs | Разделы |
| a11y_collapse_models | Свернуть панель «Модели» |
| a11y_collapse_results | Свернуть результаты лаборатории |
| a11y_collapse_debug | Свернуть журнал отладки |
| penalized_hint | Из‑за частых «Не полезно» модель временно реже выбирается автоматически |

## Heuristic gate

- [ ] H1 Visibility — loading/empty/error/pending visible
- [ ] H2 Language — no raw JSON in primary UI
- [ ] H3 Control — Escape, change vote, close float
- [ ] H4 Consistency — float-dock + table styles match Lab/Debug
- [ ] H5 Prevention — no feedback mid-stream
- [ ] H6 Recognition — column `title` hints + formula details
- [ ] H7 Efficiency — 24h/7d switch
- [ ] H8 Aesthetic — one job per tab; no chart clutter
- [ ] H9 Recovery — Retry works
- [ ] H10 Help — empty states tell next action
- [ ] Mobile ~390px — thumbs ≥44px; dock clear of send
- [ ] `prefers-reduced-motion` — no jarring scale

**Block merge if any unchecked after Task 7.**

## Заметки к строкам

- `feedback_wait` удалён: strip не показывается во время стрима вовсе, поэтому подсказка
  «дождитесь» не рендерится нигде. Отсутствие контрола — и есть выполнение H5.
- `a11y_*` — доступные имена, не видимый текст. Нужны, потому что три плавающие панели
  должны представляться скринридеру одинаково.
- `col_down_rate` заменяет английский `down%` в русской шапке таблицы.
- `title_feedback` отличается от `tab_feedback`: заголовок панели не должен дословно повторять
  ярлык вкладки в 8px над ним.
