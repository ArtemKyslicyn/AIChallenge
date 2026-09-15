# Visual review — empty state & composer (AIChallenge)

Readonly pass on current code (post prior fixes): `Chat.tsx` empty state, `Composer.tsx` modes/media, `MediaJobCard.tsx`, and related rules in `index.css` (`.empty*`, `.chip*`, `.composer*`, `.mode-chip*`, `.media-job*`).

**Constraints honored:** ordinary chat default; ×2 / ×T / ×4 stay always visible (do not re-hide behind «Режим»); keep **Картинка**; no feature removal. Prefer minimal visual-weight diffs.

---

## Top 5 findings

### 1. Major — Composer options bar still outweighs the textarea on first paint

Always-visible modes are correct for product, but `.composer-options-bar` still reads as a control strip first: **Модель** + decorative **«Режим»** + four stacked mode chips + **Картинка/Видео** + **Настройки** (plus lab preset / sample when ×4). The textarea sits below that band inside the same shell, so calm “chat first” is undercut by chrome density—not by missing features.

**Hints (minimal diffs):**
- `Composer.tsx` → `.composer-options-bar` (drop the visible `aria-hidden` **«Режим»** label; kickers + `aria-label` already name modes)
- `index.css` → `.composer-options-bar` / `.composer-mode-toggle`: treat modes as one segmented control (shared border / tighter internal gap) so the eye reads **one** mode group, then media, then settings
- Do **not** collapse ×2/×T/×4 behind «Режим»

---

### 2. Major — Idle ×2/×T/×4 still share equal footprint with «Обычный»

Quieter idle styles help (`.mode-chip-stack:not(.mode-chip-default):not([aria-pressed="true"])` at `opacity: 0.72`), but four `.mode-chip-stack` cells keep the same `min-width: 3.25rem` and two-line kicker+label height. Physical mass still competes with the default; product rule is “available, must not dominate.”

**Hints:**
- `index.css` → `.mode-chip-stack`, `.mode-chip-kicker`, `.mode-chip-label`
- Prefer reducing **height/mass** over hiding: e.g. default stays stack or slightly taller; idle lab modes single-line `×2` / `×T` / `×4` with title/aria for full names—or smaller min-width / less padding for non-default only
- Keep pressed accents; keep all four visible

---

### 3. Major — Pressed ×4 looks like pressed «Обычный» (fill), not like a distinct lab mode

`.mode-chip-temp[aria-pressed="true"]` correctly uses orange fill (`#ea580c`). `.mode-chip-lab[aria-pressed="true"]` uses the **same accent / accent-soft recipe** as `.mode-chip-default[aria-pressed="true"]`; only the kicker goes teal (`#0d9488`). Active lab vs ordinary chat is hard to tell at a glance—hierarchy fails when ×4 is selected.

**Hints:**
- `index.css` → `.mode-chip-lab[aria-pressed="true"]` (~1680) and `.mode-chip-lab[aria-pressed="true"] .mode-chip-kicker` (~1100)
- Mirror the ×T pattern: teal border/fill for pressed lab (token or reuse the existing `#0d9488` mixes), keep default on accent blue
- Minimal: change lab pressed background/border only; leave markup alone

---

### 4. Minor — Empty state still double-loads media next to a chat-primary row

`chip-primary` correctly sits on the first chat suggestion («С чем ты можешь помочь?»). Good fix. Residual clutter: first row also includes **«Нарисовать картинку»**, then a full `.suggestions-media` row with a long media chip, before «Ещё идеи». Ordinary-chat default is clearer than before, but first paint still has **two** media CTAs besides composer **Картинка**.

**Hints:**
- `Chat.tsx` empty → `.suggestions` / `.suggestions-media` / `.chip-media`
- Prefer one empty media entry (either the short «Нарисовать картинку» **or** the media row), and keep the durable affordance on composer **Картинка**
- Leave video/comic under «Ещё идеи» (already good progressive disclosure)

---

### 5. Minor — Micro-type and off-token polish (kickers, weights, comic job tint)

`.mode-chip-kicker` at **9px** (10px ≤720px) is below a comfortable UI caption size; `font-weight: 650` on labels/titles is non-standard. `.media-job--image` / `--video` have running tints; **comic** has no `.media-job--comic.media-job--running` rule and inherits generic accent-soft. Hardcoded `#ea580c` / `#0d9488` work but sit outside `:root` tokens.

**Hints:**
- `index.css` → `.mode-chip-kicker` (prefer ≥11px or drop kickers on narrow once labels are clear)
- `index.css` → `.media-job--comic.media-job--running` (distinct quiet tint, parallel to image/video)
- Optional: map orange/teal to semantic vars later; not a blocker for this pass

---

## What works (keep)

- Always-visible ×2 / ×T / ×4 + label **«Обычный»**; idle non-default opacity quieting is the right direction.
- Empty **chat-first** primary chip; lab / video / stands behind «Ещё идеи».
- Composer **Картинка** (weight 600, accent-soft) vs quieter **Видео** (`--quiet`); media group separated by `border-left` on `.composer-media-actions`.
- Textarea remains the primary input surface; hint line still points to «Картинка» in single mode.
- `MediaJobCard` + `.media-job-dock` (compact running) is a clear, non-modal progress signal above the composer.
- Empty copy naming **Картинка** + model attribution under replies aligns with product rules.

---

## Checklist verified

| Item | Result |
|------|--------|
| Empty composition calm vs lab-dashboard | Improved — chat primary + collapsed «Ещё идеи»; residual dual media chips |
| Brand on first paint | Relies on topbar `.brand` (out of scope files); empty is product-neutral «Чем помочь?» |
| Default = ordinary chat visually | Yes for empty primary + pressed `.mode-chip-default`; ×4 pressed fill still confusable with default |
| ×2/×T/×4 available, not dominating | Available yes; quieter idle yes; equal stack footprint still competes |
| Image gen obvious, textarea not buried | Yes — **Картинка**, empty media chip(s), hint |
| Mode vs media separation | Better — media `radius-md` + left rule; still one wrap row |
| Typography (empty h2 / body / chips) | Empty OK (24px / muted body); mode kickers still tiny |
| Spacing / 8pt in empty + composer | Mostly tokens; stack padding / kicker gaps still ad-hoc |
| Color / 60-30-10 on these surfaces | Accent for default + media; ×T orange OK; ×4 fill not teal |
| Dark tokens for these selectors | Inherited via CSS vars; hardcoded orange/teal should still read |
| Media job running hierarchy | Image/video tinted; comic undifferentiated |

### Could not verify without a browser

- Wrap/overflow of `.composer-options-bar` at ~360–720px and measured `--composer-h` vs float dock
- Live contrast of 9px muted kickers + `opacity: 0.72` idle chips on light/dark
- Perceived “dashboard vs chat” with real topbar + float FABs
- Motion on `.chip:hover` `translateY` under `prefers-reduced-motion`
- Whether pressed ×4 vs «Обычный» is actually confused in a real session (code suggests yes)
