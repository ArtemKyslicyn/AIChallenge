# Deferred features index (2026-09-03)

Status: **Phases A–C done (2026-09-03)** — Phase D (research) is the open track.
Возврат — через **мастер-план**.

## Entrypoint

**[Master plan: Observability → Prefs → Routing Loop](./2026-09-03-observability-routing-master.md)**  
Phases A–D; каждый пункт фазы = ссылка на подплан/spec.

## Подпланы и описания

| Phase | Что | Spec (описание) | Подплан |
|-------|-----|-----------------|---------|
| ✅ A / B UI | Lab observability UX | [ux-design](../specs/2026-09-03-lab-observability-ux-design.md) · [checklist](../specs/2026-09-03-lab-observability-ux-checklist.md) | [P0 UX](./2026-09-03-lab-observability-ux.md) |
| ✅ A | Model Pareto Lab | [pareto design](../specs/2026-09-03-model-pareto-lab-design.md) | [P1 Pareto](./2026-09-03-model-pareto-lab.md) |
| ✅ B | Feedback → router | [feedback design](../specs/2026-09-03-feedback-router-design.md) | [P2 Feedback](./2026-09-03-feedback-router.md) |
| ▶ D | Research ideas — **выбран D.A: FrugalGPT cascade** | — | [research fit](./2026-09-03-research-product-fit.md) (выбор сделан — писать подплан P3) |

**Что уже живёт в продукте:**

- `run_traces` + `GET /lab/pareto` + `GET /sessions/{id}/traces`
- `message_feedback` + `POST /messages/{id}/feedback` + `/lab/feedback-stats` + `/lab/preference-export`
- Мягкий штраф роутеру по доле «Не полезно» (переупорядочивание, не бан)
- Float «Модели» с вкладками Рейтинг / Оценки, строка оценки под ответом
- [Демо-скрипт](./2026-09-03-observability-demo-script.md), пройденный UX-гейт, env-доки

**Resume:**  
«Execute docs/superpowers/plans/2026-09-03-observability-routing-master.md from Phase D»
