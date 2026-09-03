# Deferred features index (2026-09-03)

Status: **Phases A–D done (2026-09-03).** Открыт только Tier B из research-заметки (D.3).
Возврат — через **мастер-план**.

> 🔖 **Возврат после паузы:** [Точка возврата 2026-09-03](./2026-09-03-RESUME.md) —
> где именно остановились, что уже сделано и как поднять стенд.

## Entrypoint

**[Master plan: Observability → Prefs → Routing Loop](./2026-09-03-observability-routing-master.md)**  
Phases A–D; каждый пункт фазы = ссылка на подплан/spec.

## Подпланы и описания

| Phase | Что | Spec (описание) | Подплан |
|-------|-----|-----------------|---------|
| ✅ A / B UI | Lab observability UX | [ux-design](../specs/2026-09-03-lab-observability-ux-design.md) · [checklist](../specs/2026-09-03-lab-observability-ux-checklist.md) | [P0 UX](./2026-09-03-lab-observability-ux.md) |
| ✅ A | Model Pareto Lab | [pareto design](../specs/2026-09-03-model-pareto-lab-design.md) | [P1 Pareto](./2026-09-03-model-pareto-lab.md) |
| ✅ B | Feedback → router | [feedback design](../specs/2026-09-03-feedback-router-design.md) | [P2 Feedback](./2026-09-03-feedback-router.md) |
| ✅ D | FrugalGPT cascade | [cascade design](../specs/2026-09-03-frugal-cascade-design.md) | [P3 Cascade](./2026-09-03-frugal-cascade.md) |
| ▶ D.3 | Tier B: MoT / semantic cache / G-Eval → колонка quality | — | [research fit](./2026-09-03-research-product-fit.md) |

**Что уже живёт в продукте:**

- `run_traces` + `GET /lab/pareto` + `GET /sessions/{id}/traces`
- `message_feedback` + `POST /messages/{id}/feedback` + `/lab/feedback-stats` + `/lab/preference-export`
- Мягкий штраф роутеру по доле «Не полезно» (переупорядочивание, не бан)
- Float «Модели» с вкладками Рейтинг / Оценки, строка оценки под ответом
- Каскад дешёвая → сильная модель с бейджем «эскалировали» и долей эскалаций в Рейтинге
- [Демо-скрипт](./2026-09-03-observability-demo-script.md), пройденный UX-гейт, env-доки

**Resume:**  
«Execute docs/superpowers/plans/2026-09-03-observability-routing-master.md from Phase D.3 (Tier B) — либо считать трек закрытым»
