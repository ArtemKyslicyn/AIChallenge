# Design lead synthesis — 2026-09-15 (round 2)

Scope: empty state + composer after always-visible modes restored. Sources: fresh `visual.md`, `interaction.md`, `density.md`, `a11y.md`, `brand.md`.

**Hard product constraints:** do not re-hide ×2/×T/×4 behind «Режим»; keep Картинка and all features; ordinary chat remains default.

---

## 1. Consensus vs conflicts

### Consensus (ship this round)

| Theme | Who | Action |
|-------|-----|--------|
| Client media intent ≠ backend hard hints | interaction (medium) | Align `looksLikeMediaIntent` with `_IMAGE_HINT` / `_VIDEO_HINT` / `_COMIC_HINT` |
| Silent force-to-single | interaction | One-line hint «Медиа → обычный чат» |
| Drop visible «Режим» label | visual, density | Group `aria-label` is enough |
| Pressed ×4 fills like default blue | visual | Teal pressed fill (mirror ×T orange) |
| Idle ×2/×T/×4 still heavy | visual, density | CSS-only quieter footprint (opacity, min-width, padding) |
| Duplicate empty media row | visual, density, interaction | Remove `MEDIA_SUGGESTIONS` row; keep peer «Нарисовать» + composer Картинка |
| Human mode copy via title/aria | brand (resolved) | Keep visible ×2/×T/×4; soften titles, aria, placeholders, hints |
| Small a11y leftovers | a11y | Textarea `:focus-visible`; model label cleanup; touch mins; media `setError`; kicker ≥11px |

### Conflicts (resolved)

| Conflict | Proposal | Lead decision |
|----------|----------|---------------|
| Collapse ×2/×T/×4 behind «Режим» | density critical | **Reject** — product + visual |
| Rename chips to Два / Три тона / 4 способа | brand | **Reject visible rename** — tooltips/aria/hints only |
| Drop «Нарисовать» empty chip | density inventory | **Keep** as peer; drop long media-row duplicate only |

### Parked

- Settings as overlay / float FAB quieting / topbar overflow (density majors beyond this pass)
- Thread padding vs sticky composer + media dock (a11y medium #3 — needs more layout work)
- Soft `_SOFT_MEDIA` alone without hard verb (API + model tools)

---

## 2. Implementation plan (done)

1. **`Composer.tsx` — intent parity** — `looksLikeMediaIntent` mirrors backend hard regexes (`сделай картинку`, `хочу картинку`, English image/video verbs, narrowed bare `сгенерируй` to media nouns).
2. **`Composer.tsx` — force hint** — transient `role="status"` line when free-type forces Обычный.
3. **`Composer.tsx` — chrome** — remove visible «Режим»; human `title` / `aria-label`; softer placeholders/hints; media tip when mode ≠ single; model `htmlFor`/`id` (drop duplicate `aria-label`).
4. **`Chat.tsx` — density** — remove duplicate `.suggestions-media` / `MEDIA_SUGGESTIONS`; keep «Нарисовать картинку»; empty-more lead «Три варианта тона».
5. **`Chat.tsx` — a11y** — media `tool_result` error also `setError` (assertive alert path).
6. **`index.css` — visual / a11y** — teal pressed `.mode-chip-lab`; quieter idle stacks; segmented mode group; kicker 11px; textarea `:focus-visible`; touch `min-height: 24px`; comic running tint.

---

## 3. Cross-check gate

| Check | Result |
|-------|--------|
| Default chatMode = single / «Обычный» | Pass — prefs unchanged |
| Media path forces single | Pass — `applyMediaDraft`, empty seeds, submit intent (backend-aligned) |
| ×2 / ×T / ×4 one click, always visible | Pass — not re-hidden |
| Картинка kept | Pass |
| `npm run build` in `apps/web` | **Pass** (`tsc -b && vite build`, 2026-09-15 round 2) |

---

## 4. Files touched

- `apps/web/src/components/Composer.tsx`
- `apps/web/src/components/Chat.tsx`
- `apps/web/src/index.css`
- `docs/superpowers/design-review-2026-09-15/lead.md` (this file)
