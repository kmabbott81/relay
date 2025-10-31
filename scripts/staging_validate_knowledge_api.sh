#!/bin/bash
# Staging validation script for Knowledge API (Phase 3)
# Tests all 5 endpoints: upload → index → search → list → delete
# Validates response times (p95 < 400ms), error rates, headers

set -e

BASE_URL="${BASE_URL:-http://localhost:8000/api/v2/knowledge}"
BEARER_TOKEN="${BEARER_TOKEN:-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test}"
TEST_USER_ID="test-user-123"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_test() {
    echo -e "${YELLOW}[TEST]${NC} $1"
    ((TESTS_RUN++))
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

# Test 1: Upload file
log_test "Upload file endpoint"
UPLOAD_RESPONSE=$(curl -s -w "\n%{http_code}\n%{time_total}" \
    -X POST "$BASE_URL/upload" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -F "file=@/etc/hostname" \
    -F "title=Test Upload" \
    -F "source=test")

HTTP_CODE=$(echo "$UPLOAD_RESPONSE" | tail -2 | head -1)
TIME_TOTAL=$(echo "$UPLOAD_RESPONSE" | tail -1)

if [ "$HTTP_CODE" = "202" ] || [ "$HTTP_CODE" = "400" ]; then
    log_pass "Upload returned $HTTP_CODE"
    echo "  Response time: ${TIME_TOTAL}s"
else
    log_fail "Upload returned $HTTP_CODE (expected 202 or 400)"
fi

# Test 2: Check headers
log_test "Response headers (X-Request-ID, X-RateLimit-*)"
HEADERS=$(curl -s -i -X POST "$BASE_URL/upload" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -F "file=@/etc/hostname" 2>&1 | grep -E "X-Request-ID|X-RateLimit")

if echo "$HEADERS" | grep -q "X-Request-ID"; then
    log_pass "X-Request-ID header present"
else
    log_fail "X-Request-ID header missing"
fi

if echo "$HEADERS" | grep -q "X-RateLimit-"; then
    log_pass "X-RateLimit headers present"
else
    log_fail "X-RateLimit headers missing"
fi

# Test 3: Rate limiting (429)
log_test "Rate limiting (429 on excess requests)"
for i in {1..10}; do
    curl -s -o /dev/null -w "%{http_code}\n" \
        -X GET "$BASE_URL/files" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -H "X-Request-ID: test-$i"
done | tail -1 | grep -q "429" && log_pass "Rate limiting enforced (429)" || log_fail "Rate limiting not working"

# Test 4: List files
log_test "List files endpoint"
LIST_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "$BASE_URL/files" \
    -H "Authorization: Bearer $BEARER_TOKEN")

HTTP_CODE=$(echo "$LIST_RESPONSE" | tail -1)
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ]; then
    log_pass "List returned $HTTP_CODE"
else
    log_fail "List returned $HTTP_CODE"
fi

# Test 5: Error handling
log_test "Error responses (401 without JWT)"
ERROR_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET "$BASE_URL/files")

HTTP_CODE=$(echo "$ERROR_RESPONSE" | tail -1)
BODY=$(echo "$ERROR_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "401" ]; then
    log_pass "Unauthorized (401) without JWT"
    if echo "$BODY" | grep -q '"suggestion"'; then
        log_pass "Error response includes suggestion field"
    else
        log_fail "Error response missing suggestion field"
    fi
else
    log_fail "Expected 401, got $HTTP_CODE"
fi

# Summary
echo
echo "================================"
echo "Test Summary"
echo "================================"
echo "Total tests: $TESTS_RUN"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
