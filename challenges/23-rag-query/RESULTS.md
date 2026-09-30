# Challenge 23 — RAG ask results

## Modes

| Mode | How | Result |
|---|---|---|
| Without RAG | checkbox off | general answer, no sources footer |
| With RAG | «Использовать базу» | context injected + `rag_sources` SSE |

## Sample pair (fill after demo)

**Q:** Куда ходит публичный :443?

- Without: _paste_  
- With: _paste_ + sources listed  

## Load / capacity

API embeddings default — `rag-load-smoke` should pass on the VPS. Local embeddings stay admin-off unless explicitly enabled.
