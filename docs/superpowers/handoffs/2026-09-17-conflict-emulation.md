# Handoff: live battle theater (not iframe demo)

GitHub `conflict-emulation` visuals were vendored as static HTML and never
received Agent Battle SSE state (postMessage race + cinematic siblings).

**Now:** React `BattleLiveTheater` reads the same world snapshot as Civ hex:
stability / panic / tech_lead / means / cabinet / accumulated orders+arcs.

| View | Source |
|------|--------|
| Civ hex | `BattleCivMap` live |
| LLM board / planet / strategy / arcs | `BattleLiveTheater` live |

Static `/conflict/` pages remain as archive only — battle UI does not iframe them.
