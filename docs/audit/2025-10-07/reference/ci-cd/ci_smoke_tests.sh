#!/bin/bash
# CI Smoke Tests - Production validation after deployment
# Usage: BACKEND_URL=https://... ADMIN_KEY=xxx DEV_KEY=xxx bash scripts/ci_smoke_tests.sh

set -e

BACKEND_URL=${BACKEND_URL:-https://relay-production-f2a6.up.railway.app}
ADMIN_KEY=${ADMIN_KEY}
DEV_KEY=${DEV_KEY}

echo "=== CI Smoke Tests ==="
echo "Backend: $BACKEND_URL"
echo ""

# Test 1: Health check
echo "Test 1: Health check"
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "$BACKEND_URL/_stcore/health")
HEALTH_BODY=$(echo "$HEALTH_RESPONSE" | head -n -1)
HEALTH_CODE=$(echo "$HEALTH_RESPONSE" | tail -n 1)

if [ "$HEALTH_CODE" != "200" ]; then
  echo "❌ Health check failed with status $HEALTH_CODE"
  exit 1
fi

if ! echo "$HEALTH_BODY" | grep -q '"ok":true'; then
  echo "❌ Health check response missing 'ok:true'"
  echo "Response: $HEALTH_BODY"
  exit 1
fi
echo "✅ Health check passed"
echo ""

# Test 2: /actions list (with dev key)
echo "Test 2: /actions list"
LIST_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "X-API-Key: $DEV_KEY" \
  "$BACKEND_URL/actions")
LIST_BODY=$(echo "$LIST_RESPONSE" | head -n -1)
LIST_CODE=$(echo "$LIST_RESPONSE" | tail -n 1)

if [ "$LIST_CODE" != "200" ]; then
  echo "❌ /actions list failed with status $LIST_CODE"
  echo "Response: $LIST_BODY"
  exit 1
fi

if ! echo "$LIST_BODY" | grep -q '"actions"'; then
  echo "❌ /actions list response missing 'actions' field"
  echo "Response: $LIST_BODY"
  exit 1
fi
echo "✅ /actions list passed"
echo ""

# Test 3: /actions preview (with dev key)
echo "Test 3: /actions preview"
PREVIEW_PAYLOAD='{"method":"example.hello","input_schema":{"type":"object"}}'
PREVIEW_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "X-API-Key: $DEV_KEY" \
  -H "Content-Type: application/json" \
  -d "$PREVIEW_PAYLOAD" \
  "$BACKEND_URL/actions/preview")
PREVIEW_BODY=$(echo "$PREVIEW_RESPONSE" | head -n -1)
PREVIEW_CODE=$(echo "$PREVIEW_RESPONSE" | tail -n 1)

if [ "$PREVIEW_CODE" != "200" ]; then
  echo "❌ /actions preview failed with status $PREVIEW_CODE"
  echo "Response: $PREVIEW_BODY"
  exit 1
fi

if ! echo "$PREVIEW_BODY" | grep -q '"execution_token"'; then
  echo "❌ /actions preview response missing 'execution_token' field"
  echo "Response: $PREVIEW_BODY"
  exit 1
fi
echo "✅ /actions preview passed"
echo ""

# Test 4: /audit read (with admin key)
echo "Test 4: /audit read"
AUDIT_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "X-API-Key: $ADMIN_KEY" \
  "$BACKEND_URL/audit?limit=10")
AUDIT_BODY=$(echo "$AUDIT_RESPONSE" | head -n -1)
AUDIT_CODE=$(echo "$AUDIT_RESPONSE" | tail -n 1)

if [ "$AUDIT_CODE" != "200" ]; then
  echo "❌ /audit read failed with status $AUDIT_CODE"
  echo "Response: $AUDIT_BODY"
  exit 1
fi

if ! echo "$AUDIT_BODY" | grep -q '"logs"'; then
  echo "❌ /audit response missing 'logs' field"
  echo "Response: $AUDIT_BODY"
  exit 1
fi
echo "✅ /audit read passed"
echo ""

# Test 5: Security headers
echo "Test 5: Security headers"
HEADERS=$(curl -s -I "$BACKEND_URL/_stcore/health")

if ! echo "$HEADERS" | grep -qi "Strict-Transport-Security"; then
  echo "❌ Missing Strict-Transport-Security header"
  exit 1
fi

if ! echo "$HEADERS" | grep -qi "Content-Security-Policy"; then
  echo "❌ Missing Content-Security-Policy header"
  exit 1
fi

if ! echo "$HEADERS" | grep -qi "X-Content-Type-Options"; then
  echo "❌ Missing X-Content-Type-Options header"
  exit 1
fi
echo "✅ Security headers present"
echo ""

# Test 6: Rate limit headers (check for their presence in response)
echo "Test 6: Rate limit headers"
RATE_LIMIT_RESPONSE=$(curl -s -I \
  -H "X-API-Key: $DEV_KEY" \
  "$BACKEND_URL/actions")

if echo "$RATE_LIMIT_RESPONSE" | grep -qi "X-RateLimit-Limit"; then
  echo "✅ Rate limit headers present"
else
  echo "⚠️  Rate limit headers not found (may be disabled)"
fi
echo ""

echo "=== All smoke tests passed! ==="
