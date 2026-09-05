# Comic Generator — Design Spec

**Date:** 2026-09-04  
**Status:** Implemented (v1)  
**Depends on:** chat SSE, media tools (`MEDIA_TOOLS_ENABLED`), Pollinations image adapter, media store  
**Approach:** single chat tool `generate_comic` + server-side storyboard + **one Pollinations image per panel** (Flux follows single scenes better than multi-panel pages) + HTML dialogue overlays (not baked into the image)

## Goal

User writes a free-form request in normal chat («нарисуй комикс…»): idea and/or dialogue. The model (via tool) plans a short comic; Pollinations draws **text-free** panel art; the UI writes **real HTML/CSS dialogue** as bubbles and/or captions on top of panels. Panels stream in one-by-one after a text storyboard.

## Non-goals (v1)

- Separate chat mode or `/comic` page
- Img2img / face reference / LoRA
- Per-panel regenerate button (candidate for v1.1)
- Video / animated panels
- Dedicated `comics` Postgres table
- PDF/PNG export of the full strip
- Baking speech text into the image model

## Locked decisions

| Topic | Choice |
|-------|--------|
| Entry | Chat tool + keyword fallback (same pattern as image/video) |
| Input | Flexible: preserve user dialogue when present; invent when absent |
| Panel count | Model chooses **3–6**, hard max **6** |
| On-image text | Forbidden in prompts; UI overlay only |
| Overlay | Short dialogue → bubble; long / narrative → caption (or both) |
| Consistency | Style bible + character sheet + shared `seed`; sheet repeated in every panel prompt |
| Progress | Text storyboard tokens first → `comic_start` skeleton → **N** panel images via SSE |
| Architecture | Approach 1: one tool `generate_comic`; server owns storyboard JSON + Pollinations per panel |
| Rate limit | Do **not** start a comic if remaining image budget &lt; **panel count** |
| Parallelism | Sequential panels in v1 (simpler rate limits + clearer SSE) |
| Layout | Default **`per_panel`**. `single_page` kept as experimental (Flux often ignores multi-grid prompts) |
| Failures | After `generate_comic` attempt (ok or fail), **do not** fall through to free chat that invents fake `comic+json` |

## Flow

```text
user message
  → tool probe / intent → generate_comic({ brief })
  → LLM storyboard JSON (low temperature, schema)
  → stream human-readable storyboard as token events
  → comic_start { comic_id, title, panel_count, characters }
  → for each panel (sequential):
        build image prompt (style + looks + visual + "no text/letters/bubbles")
        Pollinations → MediaStore
        comic_panel { … overlay fields, image_url | error }
  → comic_end { ok_count, fail_count }
  → tool_result
  → message_end (persist storyboard + panel URLs in message content)
```

## Storyboard contract

Server-validated JSON (clamp/reject outside 3–6 panels):

```json
{
  "title": "string",
  "style": "clean comic illustration, consistent characters, …",
  "seed": 12345,
  "characters": [
    { "id": "a", "name": "Кот", "look": "orange tabby, blue scarf" }
  ],
  "panels": [
    {
      "index": 1,
      "visual": "wide shot, metro platform, …",
      "speaker": "a",
      "dialogue": "Эй, робот!",
      "caption": null,
      "text_mode": "bubble"
    }
  ]
}
```

- `text_mode`: `bubble` | `caption` | `both`
- Image prompt always appends: no text, no letters, no watermarks, no speech bubbles
- Character `look` lines from the sheet are concatenated into every panel prompt

## Domain / application

- Tool name: `generate_comic` (alongside `generate_image` / `generate_video` in media tool schemas)
- Keyword fallback: комикс / comic strip / «нарисуй комикс» (and light English equivalents)
- Use-case lives in `application` (e.g. `comic.py` + hooks from `chat.py` media loop); Pollinations via existing `MediaGenerator` port
- No new DB entity in v1: persist a structured comic block inside the assistant message `content` (JSON fence or agreed marker) so history can rehydrate the strip
- `model_id` required on the turn (storyboard LLM attribution), same as other assistant replies
- Analytics: `comic_generated` with `panel_count`, `ok_count`, `fail_count`, `model_id`; failed panels still count toward image attempts where applicable

## SSE

| Event | Payload (essential) |
|-------|---------------------|
| `comic_start` | `comic_id`, `title`, `panel_count`, `characters[]` |
| `comic_panel` | `comic_id`, `index`, `status` (`ok`\|`error`), `image_url?`, `speaker?`, `dialogue?`, `caption?`, `text_mode`, `error?` |
| `comic_end` | `comic_id`, `ok_count`, `fail_count` |

Wire order: `tool_start` → (`model`) → storyboard `token`s → `comic_start` → N× `comic_panel` → `comic_end` → `tool_result` → `message_end`.

`tool_result` for comics does not rely on a single `media_url`; panels are the source of truth.

## UI

- `ComicStrip` in the assistant turn: responsive grid (3 row / 4 → 2×2 / 5–6 → two columns)
- On `comic_start`: N skeletons
- On `comic_panel`: art + HTML bubble and/or bottom caption; on error show dialogue text anyway
- Storyboard text remains normal markdown/tokens above the strip
- Empty-state chip suggesting a comic brief (near existing media chips)
- History: parse persisted comic block → same `ComicStrip` without live SSE

## Errors

| Case | Behavior |
|------|----------|
| Storyboard LLM / invalid JSON | One schema retry; then tool error, no images |
| Single panel Pollinations failure | That panel `error`; others continue; tool ok if ≥1 panel ok |
| Image rate limit before start | Do not start; clear user-facing error |
| Client abort | Persist partial tokens + panels received so far (same SSE abort policy as chat) |

## Limits / flags

- Gated by existing `MEDIA_TOOLS_ENABLED`
- Each panel consumes one unit of `MEDIA_IMAGE_LIMIT_PER_HOUR`
- Max 6 panels; typically one `generate_comic` per user message (cap tool rounds consistent with media loop)

## Testing

- Intent → `generate_comic`
- Storyboard clamp 3–6; prompt builder forbids on-image text; `text_mode` heuristics
- Fake media generator: yields `comic_start` / panels / `comic_end`
- SSE frame mapping for new events
- Web: history parser + strip render (skeleton → filled)

## Success criteria (v1)

1. «Нарисуй комикс: …» in single chat produces storyboard text then 3–6 panels  
2. Dialogue is selectable HTML, not glyphs in the PNG  
3. Reload restores the strip from message content  
4. Resolved `model_id` visible on the turn  
5. Ops/analytics can count `comic_generated`

## Implementation notes

- Prefer FakeLLM + Fake media in unit tests; no real Pollinations in CI  
- Domain-agnostic naming only (no product/medical role names in defaults)  
- After this spec is reviewed, write a task-by-task plan under `docs/superpowers/plans/`
