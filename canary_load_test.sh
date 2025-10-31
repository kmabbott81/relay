#!/usr/bin/env bash
set -euo pipefail

API_ROOT="https://relay-production-f2a6.up.railway.app"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTDIR="artifacts/canary_${STAMP}"
mkdir -p "$OUTDIR"

get_token() {
  curl -sS -X POST "$API_ROOT/api/v1/anon_session" \
    -H "Content-Type: application/json" -d '{}' 2>/dev/null | grep -o '"token":"[^"]*"' | cut -d'"' -f4
}

echo "[T0] Creating 5 anon tokens..."
TOKENS=()
for i in {1..5}; do
  t="$(get_token)"
  if [[ -z "$t" ]]; then echo "Token fetch failed"; exit 1; fi
  TOKENS+=("$t")
  echo "  Token $i: ${t:0:20}..."
done
printf "%s\n" "${TOKENS[@]}" > "$OUTDIR/tokens.txt"

measure() {
  local token="$1"
  local i="$2"
  # Measure HTTP code and TTFB (time to first byte)
  curl -sS -o /dev/null \
    -w '%{http_code} %{time_starttransfer}\n' \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -X POST "$API_ROOT/api/v1/stream" \
    -d '{"message":"canary test '"$i"'","model":"gpt-4o-mini"}' 2>/dev/null || echo "000 0"
}

echo "[RUN] 500 requests over 5 users (staggered)…"
> "$OUTDIR/raw_results.tsv"
req_count=0
for i in $(seq 1 500); do
  u=$(( (i-1) % 5 ))
  measure "${TOKENS[$u]}" "$i" >> "$OUTDIR/raw_results.tsv" &
  req_count=$((req_count + 1))

  # Throttle to avoid rate limiting: 5 parallel per token + periodic sleeps
  if (( req_count % 25 == 0 )); then
    wait  # Wait for batch to complete
    echo "  [Progress] Completed $req_count requests..."
    sleep 1  # Brief pause between batches
  fi
done
wait
echo "  [Complete] All 500 requests submitted and processed"

# Convert seconds to ms
awk '{printf "%s %.3f\n", $1, $2*1000}' "$OUTDIR/raw_results.tsv" > "$OUTDIR/results_ms.tsv"

# Success count (2xx)
succ=$(awk '$1 ~ /^2/ {c++} END{print c+0}' "$OUTDIR/results_ms.tsv")
total=$(wc -l < "$OUTDIR/results_ms.tsv")
ratio=$(awk "BEGIN{printf \"%.4f\", $succ/$total}")

# p95 TTFB (as proxy for TTFV)
p95=$(awk '{print $2}' "$OUTDIR/results_ms.tsv" | sort -n | awk '{a[NR]=$1} END{idx=int(0.95*NR); if(idx<1) idx=1; print a[idx]}')

echo "total=$total success=$succ ratio=$ratio p95_ms=$p95"

# Guardrails
pass=1
echo "{" > "$OUTDIR/verdict.json"
echo "  \"total\": $total," >> "$OUTDIR/verdict.json"
echo "  \"success\": $succ," >> "$OUTDIR/verdict.json"
echo "  \"ratio\": $ratio," >> "$OUTDIR/verdict.json"
echo "  \"p95_ms\": $p95," >> "$OUTDIR/verdict.json"

ratio_numeric=$(awk "BEGIN{print ($succ/$total)}")
if (( $(echo "$ratio_numeric < 0.996" | awk '{if($1 < 0.996) print 1; else print 0}') )); then
  echo "GATE FAIL: Success ratio $ratio_numeric < 0.996 (99.6%)"
  pass=0
fi

p95_numeric=$(echo "$p95" | awk '{print int($1)}')
if (( p95_numeric > 1500 )); then
  echo "GATE FAIL: p95 TTFV $p95 ms > 1500ms"
  pass=0
fi

if [[ $pass -eq 1 ]]; then
  echo "  \"pass\": true" >> "$OUTDIR/verdict.json"
  echo "✅ CANARY PASSED"
else
  echo "  \"pass\": false" >> "$OUTDIR/verdict.json"
  echo "❌ CANARY FAILED"
fi

echo "}" >> "$OUTDIR/verdict.json"

cat > "$OUTDIR/summary.txt" <<EOF
Canary Load Test Results
========================
Total Requests: $total
Successful (2xx): $succ
Success Ratio: $ratio (target: >= 0.996 = 99.6%)
p95 TTFV (ms): $p95 (target: <= 1500ms)
Status: $([ $pass -eq 1 ] && echo "PASS ✅" || echo "FAIL ❌")
EOF

cat "$OUTDIR/summary.txt"
exit $pass
