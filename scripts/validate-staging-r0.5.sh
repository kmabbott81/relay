#!/bin/bash

# R0.5 Security Hotfix - Staging Validation Script
# Runs 8 curl tests against staging environment
# Usage: ./validate-staging-r0.5.sh <staging-host>
# Example: ./validate-staging-r0.5.sh https://staging-relay-xxx.railway.app

set -e

HOST="${1:-https://staging-relay.railway.app}"
echo "🚀 R0.5 Security Hotfix Staging Validation"
echo "==========================================="
echo "Host: $HOST"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

test_case() {
    local num=$1
    local desc=$2
    local expected=$3
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test $num: $desc"
    echo "Expected: $expected"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

# =========================================================================
# Test 1: Auth Required (No Token → 401)
# =========================================================================

test_case 1 "Auth Required (no token = 401)" "HTTP 401"

response=$(curl -s -o /dev/null -w "%{http_code}" "$HOST/api/v1/stream?message=ping")
if [ "$response" = "401" ]; then
    pass "Unauthenticated request returns 401"
else
    fail "Expected 401, got $response"
fi

# =========================================================================
# Test 2: Get Anonymous Session Token
# =========================================================================

test_case 2 "Get Anonymous Session Token" "Valid JWT token"

token_response=$(curl -s -X POST "$HOST/api/v1/anon_session")
TOKEN=$(echo "$token_response" | jq -r '.token' 2>/dev/null || echo "")

if [ -n "$TOKEN" ] && [ ${#TOKEN} -gt 50 ]; then
    pass "Got valid JWT token (${#TOKEN} chars)"
    echo "Token preview: ${TOKEN:0:50}..."
else
    fail "Failed to get token or invalid format"
    exit 1
fi

# =========================================================================
# Test 3: Happy-Path SSE Streaming
# =========================================================================

test_case 3 "Happy-Path SSE Streaming" "event: message_chunk and id: fields"

stream_output=$(curl -s -N "$HOST/api/v1/stream?message=hello&stream_id=$(uuidgen)" \
    -H "Authorization: Bearer $TOKEN" 2>/dev/null | head -n 20)

if echo "$stream_output" | grep -q "event:"; then
    pass "SSE stream received with event fields"
    echo "Sample: $(echo "$stream_output" | head -3 | tr '\n' ' ')"
else
    fail "No SSE events received or malformed response"
fi

# =========================================================================
# Test 4: Quotas (20/hour → 21st fails with 429)
# =========================================================================

test_case 4 "Anonymous Quotas (20/hour)" "21st message returns 429"

echo "Sending 21 requests (limit is 20/hour)..."
last_code=""
for i in {1..21}; do
    last_code=$(curl -s -o /dev/null -w "%{http_code}" \
        "$HOST/api/v1/stream?message=test_msg_$i&stream_id=$(uuidgen)" \
        -H "Authorization: Bearer $TOKEN")
    echo -n "."
done
echo ""

if [ "$last_code" = "429" ]; then
    pass "21st message returns 429 (quota exceeded)"
else
    fail "Expected 429, got $last_code"
fi

# =========================================================================
# Test 5: Rate Limits (30/30s per user → 31st fails with 429)
# =========================================================================

test_case 5 "Rate Limits (30/30s per user)" "31st concurrent request returns 429"

echo "Sending 31 concurrent requests (limit is 30/30s)..."

# Create a new token for clean rate limit bucket
token_response=$(curl -s -X POST "$HOST/api/v1/anon_session")
TOKEN_NEW=$(echo "$token_response" | jq -r '.token' 2>/dev/null)

# Send 31 requests in parallel
codes=()
for i in {1..31}; do
    (curl -s -o /dev/null -w "%{http_code}" \
        "$HOST/api/v1/stream?message=burst_$i&stream_id=$(uuidgen)" \
        -H "Authorization: Bearer $TOKEN_NEW") &
done

# Collect results
for job in $(jobs -p); do
    code=$(wait $job; echo $?)
    codes+=($code)
done

# Count 429s
count_429=0
for code in "${codes[@]}"; do
    if [ "$code" = "429" ]; then
        ((count_429++))
    fi
done

if [ "$count_429" -gt 0 ]; then
    pass "Got $count_429 rate limit (429) responses in burst"
else
    fail "Expected at least one 429, got 0"
fi

# =========================================================================
# Test 6: Input Validation (Message > 8192 chars = 422/413)
# =========================================================================

test_case 6 "Input Validation (message too long)" "HTTP 422 or 413"

# Create 9000-char message
msg=$(python3 -c "print('x' * 9000)")

response=$(curl -s -X POST "$HOST/api/v1/stream" \
    -H "Authorization: Bearer $TOKEN_NEW" \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"$msg\", \"model\": \"gpt-4o-mini\"}" \
    -o /dev/null -w "%{http_code}")

if [ "$response" = "422" ] || [ "$response" = "413" ]; then
    pass "Oversized message returns $response (validation enforced)"
else
    fail "Expected 422 or 413, got $response"
fi

# =========================================================================
# Test 7: Model Whitelist Validation
# =========================================================================

test_case 7 "Model Whitelist (invalid model = 422)" "HTTP 422"

response=$(curl -s -X POST "$HOST/api/v1/stream" \
    -H "Authorization: Bearer $TOKEN_NEW" \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"test\", \"model\": \"invalid_model_xyz\"}" \
    -o /dev/null -w "%{http_code}")

if [ "$response" = "422" ]; then
    pass "Invalid model returns 422 (whitelist enforced)"
else
    fail "Expected 422, got $response"
fi

# =========================================================================
# Test 8: Retry-After Header on Rate Limit
# =========================================================================

test_case 8 "Rate Limit Headers (Retry-After present)" "Retry-After: <seconds>"

# Create fresh token
token_response=$(curl -s -X POST "$HOST/api/v1/anon_session")
TOKEN_RL=$(echo "$token_response" | jq -r '.token' 2>/dev/null)

# Burst to trigger rate limit
for i in {1..31}; do
    curl -s -o /dev/null "$HOST/api/v1/stream?message=rl_test&stream_id=$(uuidgen)" \
        -H "Authorization: Bearer $TOKEN_RL" &
done
wait

# Check for Retry-After header
response_header=$(curl -s -i "$HOST/api/v1/stream?message=test&stream_id=$(uuidgen)" \
    -H "Authorization: Bearer $TOKEN_RL" 2>&1 | grep -i "retry-after" || echo "")

if [ -n "$response_header" ]; then
    pass "Rate limit returns Retry-After header: $response_header"
else
    fail "Retry-After header not found in rate-limited response"
fi

# =========================================================================
# Summary
# =========================================================================

echo ""
echo "==========================================="
echo -e "📊 Validation Summary"
echo "==========================================="
echo -e "Passed: ${GREEN}$PASS${NC}/8"
echo -e "Failed: ${RED}$FAIL${NC}/8"

if [ $FAIL -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All validations passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Merge release/r0.5-hotfix → main"
    echo "2. Deploy to production"
    echo "3. Run same validations against prod"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Some validations failed. Review logs above.${NC}"
    exit 1
fi
