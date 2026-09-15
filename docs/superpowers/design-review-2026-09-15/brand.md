# Brand / IA review — empty + composer (AIChallenge)

Readonly pass on current Russian copy in `Chat.tsx` empty state and `Composer.tsx` (modes, media, placeholders, hints). Brand line: **«Чат, в котором видно модель»** (header tagline in `App.tsx` — keep).

Audience: ordinary users first; lab modes available but must not speak like a bench on first paint.

---

## Verdict

Empty state now **sells the brand** in human words («видно, какая модель»). Composer still **sells the lab**: kickers «Шаблоны / Темп. / Лаб», labels `×2` / `×T` / `×4`, and mode hints with `temperature` / DeepSeek / «стратегии промпта». Newcomers learn *modes* before they feel *model transparency*.

---

### Empty state

| Now | Assessment / proposal |
|-----|------------------------|
| **Чем помочь?** | keep |
| Пишите как в чате — под каждым ответом видно, какая модель ответила. Для картинки — кнопка **Картинка** внизу. | keep — correct brand echo; no ``model_id`` |
| Primary chip «С чем ты можешь помочь?» | keep (chat-first) |
| «Нарисовать картинку» + media row | keep as peer; media CTA belongs in composer |
| **Ещё идеи** / Скрыть доп. идеи | keep |
| Видео и комикс | keep |
| Студия температуры (×T) | **Три варианта тона** (or «Разный тон ответа») — fold-only is fine; drop `×T` from the lead |
| Агенты / Схема / Замеры / Битва | keep behind fold (stand links, not first paint) |

---

### Mode chips (labels + kickers + titles)

| Chip now | Label proposal | Kicker | Title (tooltip) |
|----------|----------------|--------|-----------------|
| Чат / **Обычный** | keep **Обычный** | keep **Чат** | Один ответ · под ним видно модель |
| Шаблоны / **×2** | **Два** (or keep ×2 only if space-critical) | **Рядом** | Два ответа: без правил и с правилами |
| Темп. / **×T** | **Три тона** | **Тон** | Один текст — три ответа разной «смелости» |
| Лаб / **×4** | **4 способа** | **Способы** | Один вопрос — четыре способа спросить |

Prefer human labels on the chip; keep `×2` / `×T` / `×4` in settings, aria, or tooltips for power users — not as the only visible word on first paint.

Current titles («Студия temperature», «4 стратегии промпта») read as lab jargon — replace with the titles above.

---

### Media & placeholders

| Now | Proposal |
|-----|----------|
| Картинка / Видео | keep |
| Напишите сообщение… | keep (default) |
| Сообщение для сравнения двух ответов… | **Сообщение — сравним два ответа…** |
| Запрос для сравнения температур… | **Один текст — три ответа разным тоном…** |
| Задача для лаборатории… | **Задача: сравним четыре способа ответа…** |

---

### Hints (options bar + footer)

| Now | Proposal |
|-----|----------|
| Два ответа: без шаблона и с шаблоном | keep / fine |
| …t = … + автооценка. Размышление выкл. (иначе t не влияет на DeepSeek). | **Один запрос — три тона ответа.** DeepSeek / `t` only in Настройки |
| Четыре стратегии промпта параллельно | **Четыре способа задать один вопрос** |
| Режим «×2»: задайте правила… | **Режим «Два»: задайте правила шаблона — иначе ответы совпадут.** |
| Enter / Shift+Enter · для картинки… | keep |
| ×4 / ×T не сохраняется в истории сервера | **Этот режим не пишется в историю чата** |

---

### Brand check

| Surface | Fits brand? |
|---------|-------------|
| Header tagline | yes |
| Empty body | yes — human paraphrase of the line |
| Mode row on first paint | weak — symbols + lab kickers overshadow «видно модель» |
| Placeholders / ×T hint | weak until softened |

**One-line goal for implementers:** keep empty copy as-is; rewrite mode chip labels/kickers/titles and non-default placeholders/hints so first paint says *chat with visible model*, and lab language appears only after the user chooses a compare mode.
