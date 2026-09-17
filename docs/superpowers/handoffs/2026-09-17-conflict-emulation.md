# Handoff: Conflict Emulation Board → AIChallenge

Source: https://github.com/ArtemKyslicyn/conflict-emulation  
Integrated into AIChallenge Agent Battle (option **C**: vendor + live bridge).

## Where in AIChallenge

| What | Path |
|------|------|
| Static board | `apps/web/public/conflict/` |
| Live mapper | `apps/web/src/battle/conflictBridge.ts` |
| iframe host | `apps/web/src/components/ConflictEmulationHost.tsx` |
| UI tabs | `AgentBattle` · Civ hex / LLM board / planet / strategy / arcs |

## Bridge

Parent posts `aichallenge.conflict.live` with a patch from battle meters
(`stability`, `panic`, `tech_lead`, `means`, cabinet voices). LLM board applies
`applyLivePatch` → `viz = f(worldState)`. Planet / parchment / arcs stay cinematic
siblings (hash/`show` only).

Embed: `/conflict/index.html?embed=1#llm`

## Standalone

```bash
# from apps/web/public/conflict or original repo
python3 -m http.server 8877 --bind 127.0.0.1
```

Pages: https://artemkyslicyn.github.io/conflict-emulation/

## Practices

1. Briefing / fog of war  
2. Structured action space  
3. Secretary / schema validate  
4. Deterministic GM resolve  
5. Cascades  
6. Narrator separate  
7. Live battle → LLM board  

## Not this chat

tenant-service work stays in `/Users/arcilite/tenant-service`.
