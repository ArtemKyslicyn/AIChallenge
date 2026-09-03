# Research → product fit (parked ideas)

**Date:** 2026-09-03  
**Status:** Ideas only — not an implementation plan. Pick one spine before writing a plan.  
**Product spine already planned:** Pareto Lab + Feedback→Router + UX Models float.

## Filter (что считать «созвучным»)

Берём исследование, только если оно усиливает уже видимый продукт:

1. **выбор модели** (chain / cost / quality), или  
2. **оценку ответа** (judge / human pref), или  
3. **демо «платформа рулит моделями»** в Lab UI  

Отсекаем: RAG «потому что все так делают», multi-agent ради агентов, GPU-train на этом VPS, статьи без UI/метрики в чате.

---

## Tier A — встроить в текущий roadmap (максимум пользы)

### 1. FrugalGPT cascade + scorer ([Chen et al., 2023](https://arxiv.org/abs/2305.05176))

**Идея:** дешёвая модель → оценка «достаточно ли хорошо?» → иначе эскалация.

**Куда в продукт:** следующий шаг после Pareto + Feedback. Scorer v1 = ваш lab judge / короткий self-check; не mid-stream splice (эскалация = новый complete или pre-stream routing).

**Польза:** меньше $ и latency на простых «привет», сильнее модели на сложных; в UI Models float: «остались на cheap» vs «эскалировали».

### 2. RouteLLM ([Ong et al., 2024](https://arxiv.org/abs/2406.18665), LMSYS)

**Идея:** учить router на **preference data** (strong vs weak), порог cost/quality.

**Куда в продукт:** JSONL export из Feedback plan = датасет; v1 — порог/матрица без тяжёлого train; v2 — лёгкий classifier или готовый RouteLLM router offline → веса в chain.

**Польза:** прямая линия «наши 👍/👎 → умный роутинг», созвучно Kalinin Q/₽ ranking.

### 3. Arena / Bradley–Terry ranking ([LMSYS Chatbot Arena methodology](https://arxiv.org/abs/2403.04132) family)

**Идея:** pairwise human prefs → стабильный рейтинг моделей (BT ≈ «Elo»).

**Куда в продукт:** режим «Два рядом» уже есть → кнопка «A лучше / B лучше / ничья» → локальный leaderboard во вкладке Models рядом с Pareto.

**Польза:** Pareto = ops-метрики; Arena-tab = **человеческий** вкус. Демо выглядит как мини-LMArena для *вашего* трафика, не чужой бенчмарк сбоку.

---

## Tier B — усиление, если A уже живёт

### 4. Mixture-of-Thought consistency cascade ([Yue et al.](https://arxiv.org/abs/2310.03094) / MoT cascades)

Эскалация, когда слабая модель **несогласована** на 2–3 семплах (без отдельного trained scorer).

**Продукт:** только для probe/lab или non-stream complete; в чат-стриме дорого. Созвучно, если пометить «режим надёжности» в Lab.

### 5. Semantic cache (FrugalGPT «approximation» / GPTCache-класс)

Кэш эмбеддинга похожих вопросов → тот же ответ / skip LLM.

**Продукт:** lab presets + частые «с чем поможешь?» из выгрузки. Польза: latency/$ на демо. Риск: stale/wrong hit — нужен явный «из кэша» badge.

### 6. G-Eval / structured LLM-as-judge ([Liu et al.](https://arxiv.org/abs/2303.16634))

У вас уже judge JSON. Подтянуть **рубрики + калибровку** под scorecard, писать judge score в `RunTrace`.

**Продукт:** колонка quality в Pareto = не только success_rate, а judge_mean — сразу ближе к Kalinin QC gates.

---

## Tier C — не сейчас (сбоку относительно чат-платформы)

| Тема | Почему мимо |
|------|-------------|
| Classic RAG / vector DB | Нет корпуса знаний в продукте |
| Full RLHF / reward model train | Нет GPU story на этом хосте; export в Kalinin — ок как later |
| Speculative decoding | Нужен контроль над весами/runtime |
| Multi-agent debate ради статьи | Expert panel уже есть; ещё один слой без метрик = шум |

---

## Рекомендуемый «исследовательский сюжет» для резюме/демо

> Сначала **мерим** (Pareto + traces) → собираем **prefs** (thumbs + compare battles) → **рулим** (FrugalGPT cascade / RouteLLM threshold) → показываем **локальный Arena BT** рядом с ops-Pareto.

Одна фраза: не «прикрутили paper», а «production LLM routing loop как в FrugalGPT/RouteLLM/Arena, на своём трафике».

## Next (когда вернётесь)

Выбрать **один** Tier A follow-up и завести plan:

- `…-frugal-cascade.md` **или**  
- `…-arena-bt-leaderboard.md` **или**  
- `…-routellm-threshold.md`  

Не три сразу.
