## Density audit — Chat first paint + sticky composer

Fresh readonly review of current code: `App.tsx` topbar, `Composer.tsx` / `ComposerSettings.tsx`, `Chat.tsx` empty + float-dock, related CSS (`index.css`).

**Constraint (product):** ×2 / ×T / ×4 stay on the default composer surface — do **not** collapse them behind a single «Режим» / «Ещё режимы» toggle (users rejected that). Quieter idle styling and inventory cuts elsewhere are OK.

---

### What’s already better on density

- Idle mode chips (×2 / ×T / ×4 when not pressed) use lower opacity / lighter kickers — default «Обычный» reads as the path.
- «Видео» is quieter than «Картинка» (`composer-media-btn--quiet`).
- Empty default is thinner than earlier piles: 2 text chips + «Нарисовать картинку» + 1 media chip; video / comic / ×T / stand links sit under «Ещё идеи».
- Float mutex + `--composer-h` lift for the dock still hold; «Результаты» only after a lab payload.

---

### Severity-ranked issues

**Critical — options bar still one wrap-bag**  
`composer-options-bar` always lays out: model picker + «Режим» label + 4 stacked mode chips + Картинка/Видео + «Настройки». On tablet/phone this wraps to 2–3 rows above the textarea before any ×T/×4 contextual row or settings sheet. `--composer-h` correctly lifts `.float-dock`, but the sticky band eats thread viewport — worst with settings open + narrow width.

**Major — empty still teaches media twice (and once more in chrome)**  
Default empty: copy points to bottom «Картинка»; chips include «Нарисовать картинку» plus a separate media-row chip (“Сгенерируй картинку…”) that is the same job. Composer also has «Картинка». Three entry points for one action on first paint.

**Major — «Настройки» grows the sticky surface instead of overlaying**  
Toggle expands `ComposerSettings` inline inside sticky `composer-wrap` (z-index 50): global/session tabs, default mode (duplicates chips), language, templates, temp, reasoning, context, control chips. One tap opens a second control plane that shrinks the message list; FABs climb with measured height but compete for the same corner.

**Major — always-on float FABs vs send corner**  
Dock always mounts «Отладка» + «Модели» above the sticky composer (Results only post-lab — good). Fixed right stack sits in the send / options-wrap zone on phone; mutex helps, but two power-tool FABs are density tax on every idle chat.

**Minor — dual “mode” taxonomies still share the word**  
Topbar: Чат / Агенты / Схема / Замеры / Битва. Composer: Обычный / ×2 / ×T / ×4, labeled «Режим». Different jobs (stand section vs reply strategy), same mental slot. Hierarchy is clearer with quieter idle chips, but the label collision remains.

**Minor — chrome count before first keystroke**  
Rough always-visible interactive chrome in chat: История + 5 shell tabs + model + 4 modes + 2 media + Настройки + send + 2 FABs ≈ **17**, plus empty chips / «Ещё идеи». Keyboard hint under composer adds another muted line.

**Minor — topbar strip doesn’t condense enough**  
≤860px only shortens shell-btn padding; all five stand tabs stay. Brand + tagline (hidden ≤640px) + История still press horizontally on phone.

---

### Proposed default-surface inventory

Keep reply modes **visible** (constraint). Prefer quieter idle / fewer duplicates over collapsing modes.

| Must-have (visible, no tap) | Why |
|---|---|
| Brand + status dot | Product identity |
| История (chat only) | Session continuity |
| Shell: **Чат** active; other sections reachable | Stand navigation |
| Model picker (or clear «Авто» / Общие) | `model_id` promise |
| Mode chips: **Обычный** + ×2 + ×T + ×4 (idle quieter OK) | Users need 0-tap mode switch |
| Textarea + send/stop | Core job |
| **Картинка** | Emphasized media CTA |

| Secondary (1 tap → panel/menu; ≤2 to action) | Entry |
|---|---|
| Агенты / Схема / Замеры / Битва | Keep topbar **or** overflow «Разделы» on narrow — not empty-state deep-links |
| Видео | Keep quieter sibling **or** demote under media «Ещё» if bar still wraps |
| Templates, language, temp, reasoning, session context | «Настройки» — prefer sheet/popover over sticky growth |
| Lab preset / «Пример» / ×T temp triple | Appear only when that mode is active (already mostly true) |
| Empty: 1 primary text chip + optional 1 secondary; drop duplicate image chip | Composer «Картинка» covers media start |
| Отладка, Модели | Float dock; consider quieter idle FABs or show Debug after error/activity |
| Результаты | Post-lab only (keep) |

**Do not:** hide ×2 / ×T / ×4 behind one «Режим» control.

---

### ≤2-tap reachability map (proposed)

| Feature | Path |
|---|---|
| Send message | 0 — always |
| Pin model | 0 — select |
| Switch ×2 / ×T / ×4 | 0 — chip on bar |
| Image draft | 0 — Картинка |
| Video draft | 0 — quieter Видео **or** 1 — media › Видео if demoted |
| Lab preset / t values | 0 once mode active (contextual bar) |
| Settings (temp, rules…) | 1 — Настройки |
| Stand sections | 1 — topbar tab |
| Models ranking / studio | 1 — FAB Модели › tab |
| Debug log | 1 — FAB Отладка |
| Lab results | 1 — FAB after run **or** lab turn CTA |
| Extra empty ideas | 1 — «Ещё идеи» |

---

### First-paint target (recommendation)

**Keep visible:** brand, История, shell (Chat + peers), model, all four mode chips (idle quieter), input/send, Картинка.  

**Quieter / trim (not hide modes):** deepen idle demotion for ×2/×T/×4 vs Обычный; quiet or demote Видео if wrap persists; drop empty’s duplicate image chip; keep video/comic/×T/stand under «Ещё»; prefer settings as overlay; optional quieter Debug FAB until needed.  

**One job per band:** topbar = stand place; composer chrome = this reply (modes stay here); empty = start chatting (not a second media tutorial); dock = observe/debug.

No code edits — inventory for design-lead synthesis.
