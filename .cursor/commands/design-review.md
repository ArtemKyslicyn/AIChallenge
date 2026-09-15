# Design review (5 designers + lead)

Run a parallel design review of AIChallenge chat UX, then synthesize.

## Steps

1. Launch **in parallel** (Task tool) these project subagents:
   - `designer-visual`
   - `designer-interaction`
   - `designer-density`
   - `designer-a11y`
   - `designer-brand`
   Each gets the same brief: review `apps/web/src/components/Chat.tsx`, `Composer.tsx`, related CSS; ordinary chat default; image path must be clear; do not remove features.

2. After all five return, launch `design-lead` with their reports pasted in.

3. Run `scripts/check-design-agents.sh` to verify agent files are present.

4. Implement only what design-lead marks as consensus blockers/majors, then rebuild web.

## Invoke

Type `/design-review` or ask: «запусти design-review».
