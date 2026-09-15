# Interaction review — «want an image» (2026-09-15, current code)

Readonly pass over `Composer.tsx`, `Chat.tsx` (empty chips / seeds), `media_tools.py`, `MediaJobCard.tsx`.

Product constraints: ordinary chat default; keep ×2 / ×T / ×4 / media / settings (reorganize, don’t delete).

---

## 1. Journey: «I want an image»

| Step | What happens | Failure risk |
|------|----------------|--------------|
| 1. Empty chat | Headline «Чем помочь?»; copy points to **Картинка**; primary chip = chat («С чем ты можешь помочь?»); «Нарисовать картинку» is secondary; media row + «Ещё идеи» | Low — hierarchy matches “ordinary default” |
| 2a. Chip / media suggestion | `setSeed({ text, chatMode: "single" })` → Composer seeds text + mode | OK |
| 2b. Composer **Картинка** | `applyMediaDraft("image")` → `setChatMode("single")` + `Нарисуй ` (rewrites video / bare `сделай` prefixes) | OK |
| 2c. Free-type while in ×2 / ×T / ×4 | On submit: `looksLikeMediaIntent` → force `chatMode: "single"` + send via `sendSingle` | **Partial** — regex ≠ backend (see bugs) |
| 3. Send | Only `sendSingle` runs SSE + media tools; compare/lab/temp_studio never emit `tool_*` | OK if mode is single (forced or not) |
| 4. Backend | Soft gate `maybe_needs_media_tools` → model tools and/or `detect_media_intent` (`_IMAGE_HINT` etc.) → `tool_start` / `tool_result` | Soft words alone may probe but not hard-intent |
| 5. Waiting | Dock: compact `MediaJobCard` while `activeMediaJob.phase === "running"`; turn card for running/error (non-comic); status line | Dock drops error (dock = running only); turn keeps error |
| 6. Done | Markdown / comic panels in thread; mode left on single after force | OK |

**Paths that succeed:** empty media chips, **Картинка**, free-type with client-matched verbs (`нарисуй`, `хочу картинку`, `комикс`, `сделай короткое видео`, bare `сгенерируй…`), or already in **Обычный** with backend-matching phrasing.

**Paths that still fail:** media-like wording that backend understands but client does **not** force single while ×2/×T/×4 is selected (e.g. «Сделай картинку…», English `draw` / `generate an image`).

---

## 2. Bugs (severity)

**High**  
*(none remaining on the classic “mode trap for `нарисуй…`” — that path is fixed.)*

**Medium**
1. **Client vs backend intent asymmetry** — `looksLikeMediaIntent` misses phrases `_IMAGE_HINT` accepts (`сделай картинку/рисунок`, `generate/draw … image`), so multi-mode free-type still goes to probe text, not generation. Conversely, bare `сгенерируй…` / substring `комикс` forces single even when the user meant lab/compare text — silent mode steal.
2. **No feedback when mode is auto-forced** — `submit()` flips to single without a one-line status/hint; user in ×4 may think lab ran.

**Low**
3. **Media tip only in `single`** — footer «для картинки: Картинка / нарисуй…» hidden in ×2/×T/×4; disclosure still relies on button or lucky phrasing.
4. **Soft / casual phrasing** — «картинку кота» / soft `_SOFT_MEDIA` without verb: gate may open, hard `detect_media_intent` may not; model must emit tools.
5. **Error dock** — floating dock shows only `running`; errors live on the turn card + status. Fine if user looks at the thread; easy to miss if they stare at the composer.
6. **Duplicate empty media affordances** — secondary «Нарисовать картинку» + `MEDIA_SUGGESTIONS` row still overlap (noise, not a hard fail). Primary chat chip is correct.
7. **`MediaJobCard`** — clear running/done/error copy + elapsed; no retry/dismiss control (passive). Acceptable for v1.

---

## 3. Minimal fixes (impact order)

1. **Align `looksLikeMediaIntent` with `detect_media_intent`** — include `сделай … (картинк|изображен|рисунок)`, English image/video verbs used on the API; narrow bare `сгенерируй` so it only forces when followed by media nouns (or mirror `_IMAGE_HINT` / `_VIDEO_HINT` / `_COMIC_HINT`).
2. **One-line feedback on force** — e.g. status or composer hint: «Медиа → обычный чат» when `forceSingle` fires (keeps features; clarifies switch).
3. **Optional:** show the media tip (or «Картинка переключит на обычный») whenever mode ≠ single, not only in single.
4. **Optional:** on media `tool_result` error, keep dock visible briefly or until dismiss so composer-focused users see failure without scrolling.

---

## 4. Cross-check: media → single

| Entry | Forces `single`? |
|-------|------------------|
| `applyMediaDraft` (`setChatMode("single")`) | **Yes** |
| Empty «Нарисовать картинку» seed | **Yes** (`chatMode: "single"`) |
| `MEDIA_SUGGESTIONS` / `MORE_MEDIA_SUGGESTIONS` seeds | **Yes** |
| Chat suggestion chips (non-×T) | **Yes** (`single`) |
| Free-type submit + `looksLikeMediaIntent` | **Yes** (client regex) |
| Free-type media-like text **outside** that regex while ×2/×T/×4 | **No** → never hits media tools |
| Default prefs | `defaultChatMode: "single"` (user can change globally) |

**Verdict:** Composer **Картинка**, Chat media/empty seeds, and media-like submit (client regex) all force single and reach `sendSingle`. Remaining gap is **regex parity** with `media_tools.detect_media_intent`, not missing `setChatMode("single")` on the designed CTAs.
