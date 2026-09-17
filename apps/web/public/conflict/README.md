# Conflict Emulation Board

Integrated static front-end for LLM-bound geopolitical conflict visualization.

## Local

```bash
cd conflict-emulation
python3 -m http.server 8877 --bind 127.0.0.1
# open http://127.0.0.1:8877
```

## Live

- Repo: https://github.com/ArtemKyslicyn/conflict-emulation
- Pages: https://artemkyslicyn.github.io/conflict-emulation/

## Views

| Tab | Role |
|-----|------|
| LLM board | World-state JSON → agents → GM → cascades → globe |
| 3D planet | Cinematic orbital cities + missile rise |
| Strategy board | Rise-of-Nations-style war declaration |
| Conflict arcs | Economic–military theater arcs |
| Architecture | Pipeline + GitHub references |

## Practices applied

1. Briefing / fog of war per country agent  
2. Structured action space (no free-form effects)  
3. Secretary / schema validation  
4. Deterministic game-master resolve  
5. Cascades (oil, shipping, sanctions, escalation ladder)  
6. Narrator separate from decision agents  
7. Visualization = `f(worldState)`  

References: WarAgent, NoblerWorks/WarGames, multi-agent crisis engines, Panopticon, AI Geopolitical Arena.

## Quality

```bash
./scripts/quality-check.sh
```

## Deploy

GitHub Pages from `main` (root).
