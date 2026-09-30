#!/usr/bin/env bash
# Smoke load against local RAG (API embeddings / fake). No secrets printed.
set -euo pipefail

BASE="${RAG_BASE_URL:-http://127.0.0.1:18766}"
TOKEN="${RAG_SHARED_TOKEN:-}"
N="${RAG_LOAD_N:-8}"
AUTH=()
if [[ -n "$TOKEN" ]]; then
  AUTH=(-H "Authorization: Bearer ${TOKEN}")
fi

echo "RAG_LOAD base=${BASE} n=${N}"

code=$(curl -sS -o /tmp/rag-health.json -w "%{http_code}" --max-time 10 "${BASE}/health" || true)
[[ "$code" == "200" ]] || { echo "RAG_LOAD_FAIL health=${code}"; exit 1; }
echo "RAG_LOAD_OK health=200"

# Warm index (idempotent).
curl -sS -o /tmp/rag-index.json --max-time 120 "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{"strategy":"structural"}' \
  "${BASE}/v1/index" >/dev/null || true

fail=0
for i in $(seq 1 "$N"); do
  (
    c=$(curl -sS -o "/tmp/rag-search-${i}.json" -w "%{http_code}" --max-time 30 "${AUTH[@]}" \
      -H "Content-Type: application/json" \
      -d "{\"query\":\"What is Guest MCP and model_id?\",\"top_k\":4}" \
      "${BASE}/v1/search" || echo 000)
    echo "$c" >"/tmp/rag-search-${i}.code"
  ) &
done
wait

ok=0
for i in $(seq 1 "$N"); do
  c=$(cat "/tmp/rag-search-${i}.code" 2>/dev/null || echo 000)
  if [[ "$c" == "200" ]]; then
    ok=$((ok + 1))
  else
    fail=$((fail + 1))
    echo "RAG_LOAD_WARN search[$i]=${c}"
  fi
done

echo "RAG_LOAD searches_ok=${ok}/${N}"
[[ "$ok" -ge 1 ]] || { echo "RAG_LOAD_FAIL no successful searches"; exit 1; }

if command -v docker >/dev/null 2>&1; then
  cid=$(docker compose ps -q rag 2>/dev/null || true)
  if [[ -n "$cid" ]]; then
    mem=$(docker stats --no-stream --format "{{.MemUsage}}" "$cid" 2>/dev/null || echo "n/a")
    echo "RAG_LOAD mem=${mem}"
  fi
fi

echo "RAG_LOAD_OK"
