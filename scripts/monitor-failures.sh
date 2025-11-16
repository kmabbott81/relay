#!/bin/bash
# Monitor script to detect and report workflow failures
# Run this periodically to check for failures and escalate to Claude Code

set -e

echo "=================================================="
echo "Relay CI Failure Monitor"
echo "=================================================="
echo ""

# Check for failed workflow runs in the last 24 hours
echo "Checking for recent failed workflows..."
echo ""

FAILED_RUNS=$(gh run list \
  --branch main \
  --status failure \
  --json name,conclusion,createdAt,number,headCommit \
  --limit 20 | \
  jq -r '.[] | "\(.number) | \(.name) | \(.createdAt)"')

if [ -z "$FAILED_RUNS" ]; then
  echo "✓ No recent failed workflows found"
else
  echo "⚠️  Found failed workflows:"
  echo "$FAILED_RUNS"
fi

echo ""
echo "Checking for unresolved failure issues..."
echo ""

# Check for open failure issues
OPEN_ISSUES=$(gh issue list \
  --label failure \
  --state open \
  --json number,title,createdAt \
  --jq '.[] | "\(.number) | \(.title) | \(.createdAt)"')

if [ -z "$OPEN_ISSUES" ]; then
  echo "✓ No open failure issues"
else
  echo "⚠️  Found open failure issues:"
  echo "$OPEN_ISSUES"
  echo ""
  echo "View details at: https://github.com/kmabbott81/relay/issues?q=label:failure+state:open"
fi

echo ""
echo "=================================================="
echo "Monitor complete"
echo "=================================================="
echo ""
echo "If failures are present, share the issue numbers with Claude Code for auto-remediation."
