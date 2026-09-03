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
| escalated_badge | эскалировали |
| escalated_hint | Дешёвая модель не справилась — ответила модель посильнее |
| escalation_rate | Эскалации: {n} из {total} ({percent}%) |

## Heuristic gate

- [x] H1 Visibility — loading/empty/error/pending visible
- [x] H2 Language — no raw JSON in primary UI
- [x] H3 Control — Escape, change vote, close float
- [x] H4 Consistency — float-dock + table styles match Lab/Debug
- [x] H5 Prevention — no feedback mid-stream
- [x] H6 Recognition — column `title` hints + formula details
- [x] H7 Efficiency — 24h/7d switch
- [x] H8 Aesthetic — one job per tab; no chart clutter
- [x] H9 Recovery — Retry works
- [x] H10 Help — empty states tell next action
- [x] Mobile ~390px — thumbs ≥44px; dock clear of send
- [x] `prefers-reduced-motion` — no jarring scale

**Block merge if any unchecked after Task 7.**

## Гейт пройден 2026-09-03 — на чём именно

Пять специализированных ревьюеров прогнали живой стенд (throwaway Postgres + FakeLLM API +
Vite dev, наполненный прогонами и оценками) через Playwright: скриншоты на 1280×900 и 390×844,
`elementFromPoint` вместо «на глаз», чтение `document.activeElement` вместо чтения исходников,
замеры контраста по формуле WCAG.

Два пункта изначально **не отмечались** и блокировали мерж:

- **H4** — панель прыгала 344↔287px при переключении вкладок, а `.models-float-fab` на ≤480px
  становилась полосой во всю ширину, пока Debug оставался пилюлей.
- **Mobile ~390px** — док лежал поверх композера: `elementFromPoint` на поле ввода и на кнопке
  отправки возвращал `BUTTON.models-float-fab`. Отправить сообщение с телефона было нельзя.

Корневая причина второго оказалась старше этой фичи: три захардкоженных `bottom` (88/96/72px)
против реальной высоты композера 177px на десктопе и 244px на телефоне, плюс невидимая
полноширинная обёртка Debug, перехватывавшая тапы по «Настройкам». Третья панель не создала
баг, а обнажила его. Починено публикацией реальной высоты композера в `--composer-h`.

После правок все четыре цели композера (textarea, отправка, «Настройки», чип режима)
резолвятся сами в себя на 390 и 1280, в режимах ×1 и ×4, с открытой панелью и без.

Разобранные, но **не подтвердившиеся** находки:

- «Контраст неактивной вкладки 3.59:1» — не воспроизвёлся. Три независимых замера дают 5.69:1;
  у аудитора, судя по всему, парсер прочитал сериализацию `color-mix` как 0–255. Токен оставлен
  как был: менять принятый цвет без причины — ровно то, что запрещает D14 §1.

Остались follow-up'ами (severity ≤2, записаны осознанно): «Оценки» в режимах ×2/×4 не
показывают strip, хотя пустое состояние на него ссылается; повторный клик по уже нажатой
оценке переотправляет её вместо отмены; порядок Tab внутри панели идёт вкладки → контент,
а окно и «Свернуть» достаются только Shift+Tab.

Дописано 2026-09-03 при добавлении бейджа каскада: на 390px футер последнего ответа с
бейджем «эскалировали» частично уезжает под FAB «Модели» (👎 перекрыт на ~38px).
`elementFromPoint` на обеих кнопках возвращает сами кнопки, и ровно так же сегодня ведёт
себя длинный `model_id` — это свойство дока над тредом, а не бейджа.

## Заметки к строкам

- `feedback_wait` удалён: strip не показывается во время стрима вовсе, поэтому подсказка
  «дождитесь» не рендерится нигде. Отсутствие контрола — и есть выполнение H5.
- `a11y_*` — доступные имена, не видимый текст. Нужны, потому что три плавающие панели
  должны представляться скринридеру одинаково.
- `col_down_rate` заменяет английский `down%` в русской шапке таблицы.
- `escalated_*` и `escalation_rate` — каскад FrugalGPT (спека `2026-09-03-frugal-cascade-design.md`).
  Бейдж ставится **только** на `cascade_stage === "escalated"`: на дешёвом пути отсутствие бейджа
  и есть «обошлись дешёвой моделью», а лишний бейдж на каждом ответе обесценил бы оба.
  `escalation_rate` — одна строка под таблицей Рейтинга, не отдельная секция.
- `title_feedback` отличается от `tab_feedback`: заголовок панели не должен дословно повторять
  ярлык вкладки в 8px над ним.
