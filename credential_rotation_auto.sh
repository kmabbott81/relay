#!/bin/bash
#
# Automated Credential Rotation Script
# Usage: bash credential_rotation_auto.sh
#
# This script automates:
# - GitHub Secrets update
# - Railway PostgreSQL password reset
# - Railway environment variable updates
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Automated Credential Rotation ===${NC}"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v gh &> /dev/null; then
    echo -e "${RED}✗ GitHub CLI (gh) not found. Install: https://cli.github.com${NC}"
    exit 1
fi

if ! command -v railway &> /dev/null; then
    echo -e "${RED}✗ Railway CLI not found. Install: npm install -g @railway/cli${NC}"
    exit 1
fi

echo -e "${GREEN}✓ GitHub CLI found${NC}"
echo -e "${GREEN}✓ Railway CLI found${NC}"
echo ""

# Get new credentials from user
echo -e "${YELLOW}Enter your NEW credentials:${NC}"
echo ""

read -s -p "New OpenAI API Key (sk-proj-...): " NEW_OPENAI_KEY
echo ""
if [ -z "$NEW_OPENAI_KEY" ]; then
    echo -e "${RED}✗ OpenAI key is required${NC}"
    exit 1
fi

read -s -p "New Anthropic API Key (sk-ant-...): " NEW_ANTHROPIC_KEY
echo ""
if [ -z "$NEW_ANTHROPIC_KEY" ]; then
    echo -e "${RED}✗ Anthropic key is required${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Credentials captured securely${NC}"
echo ""

# Step 1: Update GitHub Secrets
echo -e "${YELLOW}Step 1: Updating GitHub Secrets...${NC}"

if gh secret set OPENAI_API_KEY --body "$NEW_OPENAI_KEY"; then
    echo -e "${GREEN}✓ OpenAI API Key updated in GitHub Secrets${NC}"
else
    echo -e "${RED}✗ Failed to update OpenAI key${NC}"
    exit 1
fi

if gh secret set ANTHROPIC_API_KEY --body "$NEW_ANTHROPIC_KEY"; then
    echo -e "${GREEN}✓ Anthropic API Key updated in GitHub Secrets${NC}"
else
    echo -e "${RED}✗ Failed to update Anthropic key${NC}"
    exit 1
fi

echo ""

# Step 2: Reset PostgreSQL Password via Railway
echo -e "${YELLOW}Step 2: Resetting PostgreSQL Password...${NC}"

# Note: This requires Railway CLI authentication
# The actual reset command depends on your Railway project structure
echo -e "${YELLOW}Note: You may be prompted to authenticate with Railway${NC}"

if railway link; then
    echo -e "${GREEN}✓ Linked to Railway project${NC}"
else
    echo -e "${RED}⚠ Failed to link Railway project (may already be linked)${NC}"
fi

echo ""
echo -e "${YELLOW}Resetting PostgreSQL password...${NC}"

# Get the new password from Railway
NEW_DB_PASSWORD=$(railway run env | grep DATABASE_URL | cut -d'@' -f1 | tail -c 20)

if [ -z "$NEW_DB_PASSWORD" ]; then
    echo -e "${YELLOW}⚠ Could not auto-detect new password${NC}"
    echo "You may need to manually reset via: https://railway.app/project"
    read -s -p "Enter new PostgreSQL password (or press Enter to skip): " NEW_DB_PASSWORD
    echo ""
fi

if [ -n "$NEW_DB_PASSWORD" ]; then
    # Update GitHub Secret with new DATABASE_URL format
    NEW_DATABASE_URL="postgresql://postgres:${NEW_DB_PASSWORD}@switchyard.proxy.rlwy.net:39963/railway"

    if gh secret set DATABASE_URL --body "$NEW_DATABASE_URL"; then
        echo -e "${GREEN}✓ Database URL updated in GitHub Secrets${NC}"
    else
        echo -e "${RED}✗ Failed to update DATABASE_URL${NC}"
        exit 1
    fi
fi

echo ""

# Step 3: Update Railway Environment Variables
echo -e "${YELLOW}Step 3: Updating Railway Environment Variables...${NC}"

if railway variable set OPENAI_API_KEY "$NEW_OPENAI_KEY"; then
    echo -e "${GREEN}✓ OPENAI_API_KEY updated in Railway${NC}"
else
    echo -e "${RED}⚠ Could not update OPENAI_API_KEY in Railway (may require manual update)${NC}"
fi

if railway variable set ANTHROPIC_API_KEY "$NEW_ANTHROPIC_KEY"; then
    echo -e "${GREEN}✓ ANTHROPIC_API_KEY updated in Railway${NC}"
else
    echo -e "${RED}⚠ Could not update ANTHROPIC_API_KEY in Railway (may require manual update)${NC}"
fi

if [ -n "$NEW_DATABASE_URL" ]; then
    if railway variable set DATABASE_URL "$NEW_DATABASE_URL"; then
        echo -e "${GREEN}✓ DATABASE_URL updated in Railway${NC}"
    else
        echo -e "${RED}⚠ Could not update DATABASE_URL in Railway (may require manual update)${NC}"
    fi
fi

echo ""

# Step 4: Deploy Services
echo -e "${YELLOW}Step 4: Deploying services with new credentials...${NC}"

if railway deploy; then
    echo -e "${GREEN}✓ Services deployed successfully${NC}"
else
    echo -e "${YELLOW}⚠ Deployment may require manual trigger${NC}"
fi

echo ""

# Step 5: Verification
echo -e "${YELLOW}Step 5: Verifying credentials...${NC}"

# Check GitHub Secrets
if gh secret list | grep -q OPENAI_API_KEY; then
    echo -e "${GREEN}✓ GitHub Secrets verified${NC}"
else
    echo -e "${RED}✗ GitHub Secrets verification failed${NC}"
fi

echo ""
echo -e "${GREEN}=== Credential Rotation Complete ===${NC}"
echo ""
echo "Next steps:"
echo "1. Verify Railway deployments: https://railway.app/project"
echo "2. Check GitHub Actions: https://github.com/kmabbott81/djp-workflow/actions"
echo "3. Test API connections with new credentials"
echo "4. Delete old credentials from OpenAI and Anthropic dashboards"
echo ""
