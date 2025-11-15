# Quick Credential Rotation - Fully Automated

**Time**: ~15 minutes total | **Effort**: Minimal | **Risk**: Low

---

## Overview

This guide automates 90% of credential rotation. You provide new keys, I handle the updates.

---

## What You Do (5 minutes)

### 1. Create New OpenAI API Key

1. Go to: https://platform.openai.com/account/api-keys
2. Click "Create new secret key"
3. **Copy the key** (it appears only once)
4. Keep it in your clipboard or secure note

**Result**: You should have a key like `sk-proj-xxxxxxxxxxx...`

### 2. Create New Anthropic API Key

1. Go to: https://console.anthropic.com/account/keys
2. Click "Create Key"
3. **Copy the key**
4. Keep it in your clipboard or secure note

**Result**: You should have a key like `sk-ant-xxxxxxxxxxx...`

### 3. Reset PostgreSQL via Railway Dashboard

1. Go to: https://railway.app/project
2. Select your project (should see "relay-beta-api" or similar)
3. Find the PostgreSQL plugin
4. Click "Settings" or "Reset Password"
5. **Copy the new DATABASE_URL connection string**

**Result**: You should have: `postgresql://postgres:NEW_PASSWORD@switchyard.proxy.rlwy.net:39963/railway`

---

## What I Do (10 minutes)

### Option A: I Run the Automation Script (RECOMMENDED)

**Prerequisites**:
- GitHub CLI installed: `gh auth status` (shows you're logged in)
- Railway CLI installed: `railway --version`
- You have the 3 new values from above

**Commands to run** (I'll execute these):

```bash
cd C:\Users\kylem\openai-agents-workflows-2025.09.28-v1

# Step 1: Update GitHub Secrets
gh secret set OPENAI_API_KEY --body "YOUR_NEW_OPENAI_KEY"
gh secret set ANTHROPIC_API_KEY --body "YOUR_NEW_ANTHROPIC_KEY"
gh secret set DATABASE_URL --body "postgresql://postgres:NEW_PASSWORD@switchyard.proxy.rlwy.net:39963/railway"

# Step 2: Update Railway Environment Variables
railway variable set OPENAI_API_KEY "YOUR_NEW_OPENAI_KEY"
railway variable set ANTHROPIC_API_KEY "YOUR_NEW_ANTHROPIC_KEY"
railway variable set DATABASE_URL "postgresql://postgres:NEW_PASSWORD@switchyard.proxy.rlwy.net:39963/railway"

# Step 3: Trigger deployment
railway deploy
```

**Outcome**: All systems updated, deployment in progress

---

### Option B: Manual GitHub Update (If Railway CLI not available)

If you don't have Railway CLI, I can at least automate GitHub Secrets:

```bash
# I run this (you provide the 3 new values)
gh secret set OPENAI_API_KEY --body "YOUR_KEY"
gh secret set ANTHROPIC_API_KEY --body "YOUR_KEY"
gh secret set DATABASE_URL --body "YOUR_CONNECTION_STRING"
```

Then you manually update Railway env vars via web dashboard

---

## What Happens Next

After automation completes:

1. **GitHub Secrets**: Updated ✓
2. **Railway Environment**: Updated ✓
3. **Deployment**: Triggered ✓
4. **CI/CD**: Will use new credentials ✓

---

## Verification (5 minutes)

```bash
# Check GitHub Secrets are set
gh secret list

# Check Railway deployment status
railway status

# Verify API keys work (test via your apps)
```

---

## Summary

| Step | You | Me | Time |
|------|-----|-----|------|
| Create OpenAI key | ✓ | | 3 min |
| Create Anthropic key | ✓ | | 2 min |
| Reset PostgreSQL | ✓ | | ~5 min |
| Update GitHub Secrets | | ✓ | 2 min |
| Update Railway env | | ✓ | 3 min |
| Deploy | | ✓ | 2 min |
| Verify | (both) | | ~2 min |
| **TOTAL** | ~10 min | ~7 min | **~15 min** |

---

## Ready?

**Tell me**:
1. OpenAI API key (new)
2. Anthropic API key (new)
3. New PostgreSQL password/connection string

Then I'll run the automation for you!

---

*Generated 2025-11-15 - Credential Rotation Automation*
