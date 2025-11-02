# GitHub Secrets Setup Guide - Relay AI

**Status**: Ready to configure
**Date**: 2025-11-02
**Target**: Enable automatic deployment to Railway + Vercel via GitHub Actions

---

## Overview

This guide provides step-by-step instructions to set GitHub secrets required for CI/CD deployment automation. **8 total secrets** needed: **3 already found** in project files + **5 to retrieve** from external services.

---

## Part 1: Secrets Already Found ✅

These 3 values have been verified in project files:

### 1. RAILWAY_TOKEN
- **Location**: Project files (verified)
- **Value**: Already available
- **Purpose**: Authenticate with Railway API for deployments
- **Status**: ✅ Ready to use

### 2. RAILWAY_PROJECT_ID
- **Location**: Project files (verified)
- **Value**: Already available
- **Purpose**: Specify which Railway project to deploy to
- **Status**: ✅ Ready to use

### 3. DATABASE_PUBLIC_URL
- **Location**: Project files (verified)
- **Value**: Already available
- **Purpose**: PostgreSQL connection string for migrations
- **Status**: ✅ Ready to use

---

## Part 2: Secrets to Retrieve from External Services

### 5 Missing Secrets - Get These Now

#### Secret #4: VERCEL_TOKEN
**Where to get it:**
1. Go to: https://vercel.com/account/tokens
2. Click "Create Token"
3. Name: `relay-github-actions`
4. Scope: Full account access (required for Vercel API)
5. Expiration: 90 days (recommended)
6. Click "Create"
7. Copy token value (you'll only see it once)

**Format**: `vercel_XXXXXXXXXXXXXXXXXXXX_XXXX`
**Needed for**: Deploying Next.js web app to Vercel

---

#### Secret #5: VERCEL_PROJECT_ID
**Where to get it:**
1. Go to: https://vercel.com/dashboard
2. Click your project: `relay` (or `relay-web` or similar)
3. Go to: Settings → General
4. Look for "Project ID" field
5. Copy the ID (looks like: `prj_abc123def456`)

**Format**: `prj_XXXXXXXXXXXXXXXXXXXXX`
**Needed for**: Target specific Vercel project for deployment

---

#### Secret #6: VERCEL_ORG_ID
**Where to get it:**
1. Go to: https://vercel.com/account/teams
2. Click on your team/organization
3. Go to: Settings → General
4. Look for "Team ID" field
5. Copy the ID (looks like: `team_abc123def456`)

**Alternative if personal account:**
1. Skip this if you're using personal Vercel account
2. Go to: https://vercel.com/account
3. Look for "User ID" in Settings → General
4. Use this instead

**Format**: `team_XXXXXXXXXXXXXXXXXXXXX` or `prj_XXXXXXXXXXXXXXXXXXXXX`
**Needed for**: Specify account/team for Vercel API calls

---

#### Secret #7: NEXT_PUBLIC_SUPABASE_URL
**Where to get it:**
1. Go to: https://supabase.com/dashboard
2. Select your project
3. Go to: Settings → API
4. Look for "Project URL"
5. Copy the full URL (looks like: `https://abc123.supabase.co`)

**Format**: `https://XXXXXXX.supabase.co`
**Needed for**: Connect web app to Supabase backend

---

#### Secret #8: NEXT_PUBLIC_SUPABASE_ANON_KEY
**Where to get it:**
1. Go to: https://supabase.com/dashboard
2. Select your project
3. Go to: Settings → API
4. Look for "anon" public key (under "Project API keys")
5. Copy the key value (long string starting with `eyJ`)

**Format**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
**Needed for**: Allow public authentication to Supabase

---

## Part 3: Set Secrets in GitHub

### Option A: Automatic (Recommended)

Once you have all 8 values, save them to a temporary file and use the provided script:

```bash
# Create a temporary file with all 8 secrets
cat > /tmp/secrets.env << 'EOF'
RAILWAY_TOKEN=value1
RAILWAY_PROJECT_ID=value2
DATABASE_PUBLIC_URL=value3
VERCEL_TOKEN=value4
VERCEL_PROJECT_ID=value5
VERCEL_ORG_ID=value6
NEXT_PUBLIC_SUPABASE_URL=value7
NEXT_PUBLIC_SUPABASE_ANON_KEY=value8
EOF

# Run the automation script (Coming soon - Claude Code will prepare this)
bash scripts/set-github-secrets.sh --from-file /tmp/secrets.env
```

### Option B: Manual via GitHub UI

1. Go to: https://github.com/kylem/relay-ai/settings/secrets/actions
2. For each secret below, click "New repository secret"
3. Name: `RAILWAY_TOKEN`
4. Value: (paste the value from Part 1/2 above)
5. Click "Add secret"
6. Repeat for all 8 secrets

**Secrets to add (in order):**
- RAILWAY_TOKEN
- RAILWAY_PROJECT_ID
- DATABASE_PUBLIC_URL
- VERCEL_TOKEN
- VERCEL_PROJECT_ID
- VERCEL_ORG_ID
- NEXT_PUBLIC_SUPABASE_URL
- NEXT_PUBLIC_SUPABASE_ANON_KEY

### Option C: GitHub CLI (Single Command)

Once you have all values, use `gh` CLI:

```bash
# Set each secret one-by-one
gh secret set RAILWAY_TOKEN --body "value1"
gh secret set RAILWAY_PROJECT_ID --body "value2"
gh secret set DATABASE_PUBLIC_URL --body "value3"
gh secret set VERCEL_TOKEN --body "value4"
gh secret set VERCEL_PROJECT_ID --body "value5"
gh secret set VERCEL_ORG_ID --body "value6"
gh secret set NEXT_PUBLIC_SUPABASE_URL --body "value7"
gh secret set NEXT_PUBLIC_SUPABASE_ANON_KEY --body "value8"
```

---

## Part 4: Verify Secrets Are Set

```bash
# List all configured secrets (shows names only, not values)
gh secret list

# Expected output:
# RAILWAY_TOKEN
# RAILWAY_PROJECT_ID
# DATABASE_PUBLIC_URL
# VERCEL_TOKEN
# VERCEL_PROJECT_ID
# VERCEL_ORG_ID
# NEXT_PUBLIC_SUPABASE_URL
# NEXT_PUBLIC_SUPABASE_ANON_KEY
```

---

## Part 5: Test Deployment

Once all secrets are configured:

```bash
# Trigger the deployment workflow
git push origin main

# Watch the deployment in real-time
gh run list --workflow=deploy-full-stack.yml
gh run view <run-id> --log

# Or manually trigger workflow
gh workflow run deploy-full-stack.yml --ref main
```

---

## Timeline to Live

| Step | Time | Action |
|------|------|--------|
| 1. **Retrieve secrets** | 10 min | Get 5 values from Vercel + Supabase |
| 2. **Set GitHub secrets** | 5 min | Use `gh secret set` or UI |
| 3. **Verify secrets** | 2 min | Run `gh secret list` |
| 4. **Deploy** | 15 min | `git push origin main` triggers deployment |
| 5. **Verify live** | 5 min | Check API health + web app loads |
| **Total** | **37 min** | Full deployment from setup to live |

---

## Troubleshooting

### "gh command not found"
```bash
# Install GitHub CLI
# macOS: brew install gh
# Windows: winget install GitHub.cli
# Linux: sudo apt install gh
```

### "Secret not found in deployment"
1. Verify secret exists: `gh secret list`
2. Check GitHub Actions workflow file: `.github/workflows/deploy-full-stack.yml`
3. Verify secret name matches exactly (case-sensitive)

### "Deployment failed: 'VERCEL_TOKEN' not recognized"
1. Verify token is valid on Vercel
2. Token may have expired (90-day expiration)
3. Generate new token if needed

### "Database migration failed"
1. Verify DATABASE_PUBLIC_URL is correct: `psql $DATABASE_PUBLIC_URL -c "SELECT 1"`
2. Check database is accessible on Railway
3. Run migrations manually: `alembic upgrade head`

---

## Security Best Practices

✅ **DO:**
- [ ] Keep tokens in GitHub Secrets (never commit to git)
- [ ] Regenerate VERCEL_TOKEN if accidentally exposed
- [ ] Rotate tokens every 90 days
- [ ] Use separate tokens for CI/CD vs. local development
- [ ] Monitor secret access in GitHub audit logs

❌ **DON'T:**
- [ ] Commit .env files to git
- [ ] Share tokens in chat/email/Slack
- [ ] Reuse production tokens for local development
- [ ] Log secrets in CI/CD output (GitHub masks automatically)

---

## Next Steps

1. **Collect secrets** (Part 1-2) - You do this
2. **Set secrets** (Part 3) - Use `gh secret set` command
3. **Verify** (Part 4) - Run `gh secret list`
4. **Deploy** (Part 5) - Push to main branch
5. **Go live** - Web app loads at https://relay-beta.vercel.app/beta

---

## Questions?

If you run into issues:
1. Check troubleshooting section above
2. Verify secret name matches workflow file exactly
3. Verify token hasn't expired on service provider
4. Check GitHub Actions logs: https://github.com/kylem/relay-ai/actions

---

**Status**: ✅ Ready for user to retrieve 5 missing secrets
**Next**: Once user provides values, Claude Code will set all 8 secrets via `gh` CLI
