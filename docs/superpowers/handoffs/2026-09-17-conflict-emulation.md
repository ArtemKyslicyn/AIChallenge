# Handoff: Conflict Emulation Board → AIChallenge

Source: https://github.com/ArtemKyslicyn/conflict-emulation  
Integrated into AIChallenge Agent Battle (option **C**: vendor + live bridge).

## Root cause (2026-09-17 fix)

Live `postMessage` fired on iframe `onLoad` **before** the LLM-board fragment
script registered `applyLivePatch` → patches dropped. Host also unmounted on
Civ tab, so the bridge went cold mid-battle.

## Fix (WarAgent / multi-agent-simulation-engine practice)

1. Shared **world bus** (`worldBus.ts`): localStorage + BroadcastChannel checkpoint
2. Host always mounted (dormant on Civ); stable iframe URL (no hash reload)
3. Host queues patches; iframe buffers `pendingLive` until board ready
4. Board signals `aichallenge.conflict.ready` after init; parent flushes

## Where

| What | Path |
|------|------|
| Static board | `apps/web/public/conflict/` |
| Mapper | `apps/web/src/battle/conflictBridge.ts` |
| World bus | `apps/web/src/battle/worldBus.ts` |
| iframe host | `apps/web/src/components/ConflictEmulationHost.tsx` |

## Bridge protocol

- Parent → iframe: `aichallenge.conflict.live` `{ patch }`
- Parent → iframe: `aichallenge.conflict.show` `{ view }`
- Parent → iframe: `aichallenge.conflict.ping`
- Iframe → parent: `aichallenge.conflict.ready`

## References

- WarAgent (Country / Secretary / Board) — arXiv:2311.17227
- RomanTsisyk/multi-agent-simulation-engine — GM + cascading world state + static viz
