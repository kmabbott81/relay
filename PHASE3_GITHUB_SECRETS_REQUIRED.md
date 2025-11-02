# Phase 3: GitHub Secrets Configuration Required

**Status**: GitHub workflows created and ready
**Files Created**:
- `.github/workflows/deploy-beta.yml`
- `.github/workflows/deploy-staging.yml`
- `.github/workflows/deploy-prod.yml`

---

## Workflow Deployment Strategy

| Branch | Workflow | Trigger | Target |
|--------|----------|---------|--------|
| `beta` | `deploy-beta.yml` | Push to beta branch | `relay-beta-api` (Railway) |
| `main` | `deploy-staging.yml` | Push to main branch | `relay-staging-api` (Railway) |
| `production` | `deploy-prod.yml` | Push to production branch | `relay-prod-api` (Railway) |

---

## Required GitHub Secrets

All secrets must be set in repository settings: **Settings → Secrets and variables → Actions**

### For BETA Deployment

| Secret Name | Source | Purpose |
|---|---|---|
| `RELAY_BETA_RAILWAY_TOKEN` | Railway account settings | Authenticate with Railway CLI |
| `RELAY_BETA_RAILWAY_PROJECT_ID` | Railway project settings | Target Railway project for beta |
| `RELAY_BETA_SUPABASE_URL` | Supabase dashboard (API keys) | Backend: Supabase project URL |
| `RELAY_BETA_SUPABASE_ANON_KEY` | Supabase dashboard (API keys) | Backend: Supabase anonymous key |
| `RELAY_BETA_DB_URL` | Railway environment variables | Database connection string |
| `RELAY_BETA_VERCEL_TOKEN` | Vercel account settings | Authenticate with Vercel CLI |
| `RELAY_BETA_VERCEL_PROJECT_ID` | Vercel project settings | Target Vercel project for beta |
| `RELAY_BETA_VERCEL_ORG_ID` | Vercel team settings | Vercel organization/account ID |

### For STAGING Deployment

| Secret Name | Source | Purpose |
|---|---|---|
| `RELAY_STAGING_RAILWAY_TOKEN` | Railway account settings | Authenticate with Railway CLI |
| `RELAY_STAGING_RAILWAY_PROJECT_ID` | Railway project settings | Target Railway project for staging |
| `RELAY_STAGING_SUPABASE_URL` | Supabase dashboard (API keys) | Backend: Supabase project URL |
| `RELAY_STAGING_SUPABASE_ANON_KEY` | Supabase dashboard (API keys) | Backend: Supabase anonymous key |
| `RELAY_STAGING_DB_URL` | Railway environment variables | Database connection string |
| `RELAY_STAGING_VERCEL_TOKEN` | Vercel account settings | Authenticate with Vercel CLI |
| `RELAY_STAGING_VERCEL_PROJECT_ID` | Vercel project settings | Target Vercel project for staging |
| `RELAY_STAGING_VERCEL_ORG_ID` | Vercel team settings | Vercel organization/account ID |

### For PRODUCTION Deployment

| Secret Name | Source | Purpose |
|---|---|---|
| `RELAY_PROD_RAILWAY_TOKEN` | Railway account settings | Authenticate with Railway CLI |
| `RELAY_PROD_RAILWAY_PROJECT_ID` | Railway project settings | Target Railway project for production |
| `RELAY_PROD_SUPABASE_URL` | Supabase dashboard (API keys) | Backend: Supabase project URL |
| `RELAY_PROD_SUPABASE_ANON_KEY` | Supabase dashboard (API keys) | Backend: Supabase anonymous key |
| `RELAY_PROD_DB_URL` | Railway environment variables | Database connection string |
| `RELAY_PROD_VERCEL_TOKEN` | Vercel account settings | Authenticate with Vercel CLI |
| `RELAY_PROD_VERCEL_PROJECT_ID` | Vercel project settings | Target Vercel project for production |
| `RELAY_PROD_VERCEL_ORG_ID` | Vercel team settings | Vercel organization/account ID |

---

## Setting Secrets via GitHub CLI

```bash
# Set Beta secrets
gh secret set RELAY_BETA_RAILWAY_TOKEN --body "$(cat .railway-token)"
gh secret set RELAY_BETA_RAILWAY_PROJECT_ID --body "your-beta-project-id"
gh secret set RELAY_BETA_SUPABASE_URL --body "https://[beta-id].supabase.co"
gh secret set RELAY_BETA_SUPABASE_ANON_KEY --body "eyJ..."
gh secret set RELAY_BETA_DB_URL --body "postgresql://..."
gh secret set RELAY_BETA_VERCEL_TOKEN --body "your-vercel-token"
gh secret set RELAY_BETA_VERCEL_PROJECT_ID --body "your-beta-project-id"
gh secret set RELAY_BETA_VERCEL_ORG_ID --body "your-org-id"

# Set Staging secrets
gh secret set RELAY_STAGING_RAILWAY_TOKEN --body "$(cat .railway-token)"
# ... etc

# Set Production secrets
gh secret set RELAY_PROD_RAILWAY_TOKEN --body "$(cat .railway-token)"
# ... etc
```

---

## Current Infrastructure Status

### What Already Exists (BETA)

✅ **Supabase Project**: `relay-staging` (ID: `hmqmxmxkxqdrqpdmlgtn`)
- Already created and configured
- Already has JWT secret configured
- Located in Railway secrets

✅ **Railway Service**: `relay-production-f2a6`
- Already deployed and running
- Will be renamed to `relay-beta-api` in next step
- Currently has environment variables set

✅ **Vercel Project**: `relay-beta-web`
- Already deployed to `relay-beta.vercel.app`

### What Needs to Be Created (STAGING & PROD)

❌ **Supabase Projects**:
- `relay-staging-db` (new project needed)
- `relay-prod-db` (new project needed)

❌ **Railway Services**:
- `relay-staging-api` (new service needed)
- `relay-prod-api` (new service needed)

❌ **Vercel Projects**:
- `relay-staging-web` (new project needed)
- `relay-prod-web` (new project needed)

---

## Next Steps

### Step 1: Railway Service Rename (5-10 minutes, ~5 min downtime)

Current: `relay-production-f2a6`
New: `relay-beta-api`

**Via Railway UI**:
1. Go to: https://railway.app/dashboard
2. Select `relay-production-f2a6`
3. Settings → General → Service name
4. Change to `relay-beta-api`
5. Save changes

**Verification**:
```bash
railway service list
# Should show: relay-beta-api (instead of relay-production-f2a6)
```

### Step 2: Update GitHub Secrets for Beta

Use the `gh secret set` commands above for all `RELAY_BETA_*` secrets.

### Step 3: Create Staging Infrastructure

**Supabase**:
1. Go to https://supabase.com/dashboard
2. Create new project named `relay-staging-db`
3. Get URL and anon key
4. Add to GitHub secrets as `RELAY_STAGING_SUPABASE_*`

**Railway** (if needed for staging):
1. Create new Railway service named `relay-staging-api`
2. Connect your repository

**Vercel**:
1. Go to https://vercel.com/dashboard
2. Create new project named `relay-staging-web`
3. Connect to `relay_ai/product/web` directory

### Step 4: Create Production Infrastructure

Same as staging, but for `relay-prod-*` services.

### Step 5: Test Each Deployment

```bash
# Test Beta deployment
git push origin beta
# Watch: https://github.com/kmabbott81/djp-workflow/actions

# Test Staging deployment
git push origin main
# Watch: https://github.com/kmabbott81/djp-workflow/actions

# Test Production deployment (after staging is verified)
git push origin production
# Watch: https://github.com/kmabbott81/djp-workflow/actions
```

---

## Workflow Behavior

### Beta Workflow (`deploy-beta.yml`)

**Triggered by**: `git push origin beta`

**Jobs (in order)**:
1. `migrate-db` - Run Alembic migrations
2. `deploy-api` - Deploy to `relay-beta-api` on Railway
3. `deploy-web` - Deploy to `relay-beta-web` on Vercel
4. `smoke-tests` - Health check API

**Environment Variables in Workflow**:
```yaml
RELAY_STAGE: beta
RELAY_BETA_SUPABASE_URL: ${{ secrets.RELAY_BETA_SUPABASE_URL }}
RELAY_BETA_SUPABASE_ANON_KEY: ${{ secrets.RELAY_BETA_SUPABASE_ANON_KEY }}
RELAY_BETA_API_URL: https://relay-beta-api.railway.app
RELAY_BETA_DB_URL: ${{ secrets.RELAY_BETA_DB_URL }}
```

### Staging Workflow (`deploy-staging.yml`)

**Triggered by**: `git push origin main`

**Jobs (in order)**:
1. `migrate-db` - Run Alembic migrations
2. `deploy-api` - Deploy to `relay-staging-api` on Railway
3. `deploy-web` - Deploy to `relay-staging-web` on Vercel
4. `smoke-tests` - Health check API

**Environment Variables in Workflow**:
```yaml
RELAY_STAGE: staging
RELAY_STAGING_SUPABASE_URL: ${{ secrets.RELAY_STAGING_SUPABASE_URL }}
RELAY_STAGING_SUPABASE_ANON_KEY: ${{ secrets.RELAY_STAGING_SUPABASE_ANON_KEY }}
RELAY_STAGING_API_URL: https://relay-staging-api.railway.app
RELAY_STAGING_DB_URL: ${{ secrets.RELAY_STAGING_DB_URL }}
```

### Production Workflow (`deploy-prod.yml`)

**Triggered by**: `git push origin production`

**Jobs (in order)**:
1. `pre-deployment-checks` - Verify production readiness
2. `migrate-db` - Run Alembic migrations
3. `deploy-api` - Deploy to `relay-prod-api` on Railway
4. `deploy-web` - Deploy to `relay-prod-web` on Vercel
5. `smoke-tests` - Health check API
6. `notify-deployment` - Send success notification

**Environment Variables in Workflow**:
```yaml
RELAY_STAGE: prod
RELAY_PROD_SUPABASE_URL: ${{ secrets.RELAY_PROD_SUPABASE_URL }}
RELAY_PROD_SUPABASE_ANON_KEY: ${{ secrets.RELAY_PROD_SUPABASE_ANON_KEY }}
RELAY_PROD_API_URL: https://relay-prod-api.railway.app
RELAY_PROD_DB_URL: ${{ secrets.RELAY_PROD_DB_URL }}
```

---

## Branch Merging Strategy

```
Workflow:
┌─────────────┐
│   beta      │ ← Limited testing (Beta users)
│   branch    │   Deploys to relay-beta-api
└──────┬──────┘
       │
       │ (PR + Test)
       ↓
┌─────────────┐
│   main      │ ← Internal QA (Staging)
│   branch    │   Deploys to relay-staging-api
└──────┬──────┘
       │
       │ (PR + Full Test)
       ↓
┌─────────────┐
│ production  │ ← General Availability (Prod)
│   branch    │   Deploys to relay-prod-api
└─────────────┘
```

**Recommended Flow**:
1. Develop on feature branch
2. PR to `beta` → Merge when ready
3. Auto-deploy to `relay-beta-api`
4. Test beta deployment (5-10 minutes)
5. PR from `beta` to `main` → Merge when verified
6. Auto-deploy to `relay-staging-api`
7. Full internal QA (1-2 days)
8. PR from `main` to `production` → Merge when approved
9. Auto-deploy to `relay-prod-api`
10. Production live ✅

---

## Verification Checklist

Before proceeding, verify:

- [ ] Beta branch created and pushed to origin
- [ ] Main branch exists (already exists)
- [ ] Production branch created and pushed to origin
- [ ] `deploy-beta.yml` workflow file created
- [ ] `deploy-staging.yml` workflow file created
- [ ] `deploy-prod.yml` workflow file created
- [ ] All workflows visible in GitHub Actions
- [ ] No merge conflicts when branches created

---

## Status: Phase 3 - Part A Complete ✅

**Completed**:
- ✅ GitHub branches created (beta, production)
- ✅ GitHub workflows created (deploy-*.yml)
- ✅ Stage-specific environment variables documented

**Still To Do (Phase 3 - Part B)**:
- Railway service rename: `relay-production-f2a6` → `relay-beta-api`
- Create Vercel projects for staging and production
- Create Supabase projects for staging and production
- Configure all GitHub secrets
- Test each stage deployment

---

**Date**: 2025-11-02
**Phase**: 3 (Infrastructure Renaming) - Part A
**Status**: Ready for Railway service rename
