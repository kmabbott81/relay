# Relay Naming Convention Implementation Plan

**Date**: 2025-11-02
**Status**: Ready to implement
**Goal**: Establish unambiguous stage identification across ALL services
**Baseline**: Keep existing infrastructure, add naming tags

---

## Current State vs. New Convention

### Supabase

| Current | New Name | Stage | Status |
|---------|----------|-------|--------|
| `relay-staging` (hmqmxmxkxqdrqpdmlgtn) | `relay-beta-db` | BETA | RENAME (or keep & tag) |
| (none) | `relay-staging-db` | STAGING | CREATE |
| (none) | `relay-prod-db` | PROD | CREATE (placeholder) |

**Action**: Keep existing Supabase project BUT refer to it as `relay-beta-db` in all documentation and configs

---

### Railway

| Current | New Name | Stage | Status |
|---------|----------|-------|--------|
| `relay-production-f2a6` | `relay-beta-api` | BETA | RENAME |
| (implied) | `relay-staging-api` | STAGING | CREATE |
| (implied) | `relay-prod-api` | PROD | CREATE (placeholder) |

**Action**: Rename `relay-production-f2a6` to `relay-beta-api` in Railway dashboard

---

### GitHub

| Current | New Name | Stage | Status |
|---------|----------|-------|--------|
| `main` branch | `main` (deploys to staging) | STAGING | NO CHANGE |
| (none) | `beta` branch | BETA | CREATE |
| (none) | `production` branch | PROD | CREATE |

**Action**:
- Create `beta` branch (deploys to `relay-beta-api`)
- Create `production` branch (deploys to `relay-prod-api`)
- Update `main` to deploy to `relay-staging-api`

---

### Environment Variables

| Current Pattern | New Pattern | Stage |
|-----------------|-------------|-------|
| `DATABASE_URL` | `RELAY_BETA_DB_URL` | BETA |
| `SUPABASE_URL` | `RELAY_BETA_SUPABASE_URL` | BETA |
| (none) | `RELAY_STAGING_DB_URL` | STAGING |
| (none) | `RELAY_STAGING_SUPABASE_URL` | STAGING |
| (none) | `RELAY_PROD_DB_URL` | PROD |
| (none) | `RELAY_PROD_SUPABASE_URL` | PROD |

**Action**: Rename all env vars to follow `RELAY_[STAGE]_[SERVICE]_[VAR]` pattern

---

### Git Branches & Workflows

| Current | New | Stage | Deploys To |
|---------|-----|-------|------------|
| `main` | `main` | STAGING | `relay-staging-api` |
| (none) | `beta` | BETA | `relay-beta-api` |
| (none) | `production` | PROD | `relay-prod-api` |

**Workflows**:
- `.github/workflows/deploy-beta.yml` - triggered by `beta` branch
- `.github/workflows/deploy-staging.yml` - triggered by `main` branch
- `.github/workflows/deploy-prod.yml` - triggered by `production` branch

---

### Docker

| Current | New | Stage |
|---------|-----|-------|
| `relay-api:latest` | `relay-beta-api:latest` | BETA |
| (none) | `relay-staging-api:latest` | STAGING |
| (none) | `relay-prod-api:latest` | PROD |

**Action**: Update docker build/tag commands to include stage

---

### Vercel

| Current | New | Stage | URL |
|---------|-----|-------|-----|
| `relay-beta.vercel.app` | `relay-beta-web` | BETA | `relay-beta.vercel.app` |
| (none) | `relay-staging-web` | STAGING | `relay-staging.vercel.app` |
| (none) | `relay-prod-web` | PROD | `relay.app` |

**Action**: Create `relay-staging-web` and `relay-prod-web` projects

---

## Implementation Steps (In Order)

### Phase 1: Documentation & Planning (TODAY)

- [x] Tech-lead designed naming convention
- [ ] **You review & approve this plan**
- [ ] Create NAMING_CONVENTION.md in project root (reference document)
- [ ] Create quick reference card (print & post)

---

### Phase 2: Code Preparation (TOMORROW)

**Step 1: Create config loader**

Create file: `relay_ai/config/stage.py` (or `.js` if using Node)

```python
import os
from enum import Enum

class Stage(Enum):
    BETA = "beta"
    STAGING = "staging"
    PROD = "prod"

def get_stage():
    """Get current deployment stage"""
    stage = os.getenv("RELAY_STAGE", "beta")

    if stage not in [s.value for s in Stage]:
        raise ValueError(f"Invalid RELAY_STAGE: {stage}")

    return Stage(stage)

def is_beta():
    return get_stage() == Stage.BETA

def is_staging():
    return get_stage() == Stage.STAGING

def is_production():
    return get_stage() == Stage.PROD

def get_config():
    """Load stage-specific configuration"""
    stage = get_stage()

    if stage == Stage.BETA:
        return {
            'stage': 'beta',
            'supabase_url': os.getenv('RELAY_BETA_SUPABASE_URL'),
            'supabase_key': os.getenv('RELAY_BETA_SUPABASE_ANON_KEY'),
            'api_url': os.getenv('RELAY_BETA_API_URL', 'https://relay-beta-api.railway.app'),
            'db_url': os.getenv('RELAY_BETA_DB_URL'),
        }
    elif stage == Stage.STAGING:
        return {
            'stage': 'staging',
            'supabase_url': os.getenv('RELAY_STAGING_SUPABASE_URL'),
            'supabase_key': os.getenv('RELAY_STAGING_SUPABASE_ANON_KEY'),
            'api_url': os.getenv('RELAY_STAGING_API_URL'),
            'db_url': os.getenv('RELAY_STAGING_DB_URL'),
        }
    else:  # PROD
        return {
            'stage': 'prod',
            'supabase_url': os.getenv('RELAY_PROD_SUPABASE_URL'),
            'supabase_key': os.getenv('RELAY_PROD_SUPABASE_ANON_KEY'),
            'api_url': os.getenv('RELAY_PROD_API_URL'),
            'db_url': os.getenv('RELAY_PROD_DB_URL'),
        }
```

**Step 2: Update startup checks**

Update `relay_ai/platform/security/startup_checks.py`:

```python
from relay_ai.config.stage import get_stage, is_production

def validate_environment():
    stage = get_stage()
    print(f"✓ Running in {stage.value} mode")

    if is_production():
        # Production requires strict validation
        if not os.getenv('RELAY_PROD_JWT_SECRET'):
            raise RuntimeError("RELAY_PROD_JWT_SECRET not set")
        # ... more strict checks

    return True
```

**Step 3: Update .env files**

Rename and update:

```bash
# Rename
mv .env .env.beta

# Create new files
cp .env.beta .env.staging
cp .env.beta .env.prod

# Update .env.beta
RELAY_STAGE=beta
RELAY_BETA_SUPABASE_URL=https://hmqmxmxkxqdrqpdmlgtn.supabase.co
RELAY_BETA_SUPABASE_ANON_KEY=eyJ...
RELAY_BETA_API_URL=https://relay-beta-api.railway.app
RELAY_BETA_DB_URL=postgresql://...

# Create .env.staging
RELAY_STAGE=staging
RELAY_STAGING_SUPABASE_URL=...
RELAY_STAGING_SUPABASE_ANON_KEY=...
RELAY_STAGING_API_URL=...
RELAY_STAGING_DB_URL=...

# Create .env.prod
RELAY_STAGE=prod
RELAY_PROD_SUPABASE_URL=...
RELAY_PROD_SUPABASE_ANON_KEY=...
RELAY_PROD_API_URL=...
RELAY_PROD_DB_URL=...
```

Update `.gitignore`:
```
.env
.env.local
.env.*.local  # Allow .env.beta, .env.staging, .env.prod in repo if desired
```

---

### Phase 3: Infrastructure Renaming (THIS WEEK)

**Step 1: GitHub (non-destructive, can be done immediately)**

```bash
# Create new branches
git checkout -b beta
git push -u origin beta

git checkout -b production
git push -u origin production

# Create GitHub Environments (via UI or gh CLI)
gh repo create-environment beta
gh repo create-environment staging
gh repo create-environment prod

# Move secrets to environments (via UI)
# GitHub Settings → Environments → [stage] → Add secrets
# RELAY_BETA_SUPABASE_URL=...
# RELAY_BETA_SUPABASE_ANON_KEY=...
# etc.
```

**Step 2: Railway (requires service rename - brief downtime ~5 min)**

```bash
# Option 1: Via Railway UI (easiest)
# 1. Go to relay-production-f2a6 service
# 2. Settings → General → Name
# 3. Change to "relay-beta-api"
# 4. Update environment variables:
#    - RELAY_STAGE=beta
#    - RELAY_BETA_SUPABASE_URL=...
#    - RELAY_BETA_SUPABASE_ANON_KEY=...
#    - RELAY_BETA_API_URL=https://relay-beta-api.railway.app
#    - RELAY_BETA_DB_URL=...

# Option 2: Via Railway CLI
railway service rename relay-beta-api
railway variables --set "RELAY_STAGE=beta"
railway variables --set "RELAY_BETA_SUPABASE_URL=https://hmqmxmxkxqdrqpdmlgtn.supabase.co"
# ... etc
```

**Step 3: Vercel (non-destructive, add new projects)**

```bash
# Create new projects
vercel projects add relay-staging-web
vercel projects add relay-prod-web

# Configure environments in Vercel dashboard
# For relay-beta-web:
#   RELAY_STAGE=beta
#   RELAY_BETA_SUPABASE_URL=...
#   RELAY_BETA_API_URL=https://relay-beta-api.railway.app

# For relay-staging-web:
#   RELAY_STAGE=staging
#   RELAY_STAGING_SUPABASE_URL=...
#   RELAY_STAGING_API_URL=...

# Connect git branches (via Vercel UI)
# beta branch → relay-beta-web
# main branch → relay-staging-web (current)
# production branch → relay-prod-web
```

**Step 4: Create GitHub Actions workflows**

Files to create:
- `.github/workflows/deploy-beta.yml` (triggered by `beta` branch)
- `.github/workflows/deploy-staging.yml` (triggered by `main` branch)
- `.github/workflows/deploy-prod.yml` (triggered by `production` branch)

Each should use stage-specific secrets:
```yaml
# .github/workflows/deploy-beta.yml
name: Deploy to Beta

on:
  push:
    branches: [beta]

env:
  RELAY_STAGE: beta

jobs:
  deploy:
    uses: ./.github/workflows/deploy-template.yml
    with:
      stage: beta
      railway_token: ${{ secrets.RELAY_BETA_RAILWAY_TOKEN }}
      vercel_token: ${{ secrets.RELAY_BETA_VERCEL_TOKEN }}
```

---

### Phase 4: Testing & Validation (NEXT WEEK)

**Step 1: Test each environment**

```bash
# Test Beta
RELAY_STAGE=beta python -m uvicorn relay_ai.platform.api.mvp:app
# Should load RELAY_BETA_* variables

# Test Staging
RELAY_STAGE=staging python -m uvicorn relay_ai.platform.api.mvp:app
# Should load RELAY_STAGING_* variables

# Test Production
RELAY_STAGE=prod python -m uvicorn relay_ai.platform.api.mvp:app
# Should load RELAY_PROD_* variables
```

**Step 2: Verify isolation**

```bash
# Verify each stage connects to correct database
curl http://localhost:8000/health
# Should show: {"stage": "beta", "database": "relay-beta-db"}

# Verify logs show correct stage
# Should see: [RELAY_BETA] Starting server...
```

**Step 3: Deploy to each stage**

```bash
# Beta deployment
git checkout beta
git merge main  # Get latest code
git push origin beta  # Triggers deploy-beta.yml

# Staging deployment (current workflow)
git checkout main
git push origin main  # Triggers deploy-staging.yml (rename from current)

# Production deployment
git checkout production
git merge main  # Get latest code
git push origin production  # Triggers deploy-prod.yml (new)
```

---

## Naming Convention Quick Reference

### Pattern
```
relay-[STAGE]-[SERVICE]
↑     ↑     ↑    ↑
|     |     |    └─ service name (api, db, web, worker)
|     |     └────── hyphen separator
|     └──────────── stage identifier (beta, staging, prod)
└───────────────── project name (always "relay")

Examples:
relay-beta-api
relay-staging-db
relay-prod-web
```

### Environment Variables
```
RELAY_[STAGE]_[SERVICE]_[VARIABLE]
↑     ↑     ↑  ↑       ↑
|     |     |  |       └─ specific variable (URL, KEY, TOKEN)
|     |     |  └────────── service name
|     |     └───────────── underscore separator
|     └──────────────────── stage (BETA, STAGING, PROD)
└─────────────────────────── project name

Examples:
RELAY_BETA_SUPABASE_URL
RELAY_STAGING_API_TOKEN
RELAY_PROD_DB_PASSWORD
RELAY_STAGE=beta
```

### Branches
```
main          → deploys to relay-staging-api (internal testing)
beta          → deploys to relay-beta-api (limited users, 50 user limit)
production    → deploys to relay-prod-api (general availability, GA)
```

---

## Complete Mapping Table

| Service | Beta | Staging | Prod |
|---------|------|---------|------|
| **Supabase Project** | relay-beta-db (hmqmxmxkxqdrqpdmlgtn) | relay-staging-db | relay-prod-db |
| **Railway Service** | relay-beta-api | relay-staging-api | relay-prod-api |
| **Vercel Project** | relay-beta-web | relay-staging-web | relay-prod-web |
| **Git Branch** | beta | main | production |
| **GitHub Environment** | beta | staging | prod |
| **Domain** | beta.relay.app | staging.relay.app | relay.app |
| **Stage Var** | RELAY_STAGE=beta | RELAY_STAGE=staging | RELAY_STAGE=prod |
| **DB Connection** | RELAY_BETA_DB_URL | RELAY_STAGING_DB_URL | RELAY_PROD_DB_URL |
| **Supabase Var** | RELAY_BETA_SUPABASE_URL | RELAY_STAGING_SUPABASE_URL | RELAY_PROD_SUPABASE_URL |
| **API URL** | RELAY_BETA_API_URL | RELAY_STAGING_API_URL | RELAY_PROD_API_URL |
| **User Limit** | 50 | Unlimited | Unlimited |
| **Query Limit** | 100/day | Unlimited | Per subscription |
| **Purpose** | Beta testing | Internal QA | General availability |

---

## Validation Checklist

After implementation, verify:

### Service Names ✓
- [ ] Railway dashboard shows "relay-beta-api"
- [ ] Railway dashboard shows "relay-staging-api" (create new)
- [ ] Supabase shows projects with "-db" suffix
- [ ] Vercel shows projects with "-web" suffix
- [ ] GitHub shows beta, main, production branches

### Environment Variables ✓
- [ ] All vars follow `RELAY_[STAGE]_*` pattern
- [ ] `.env.beta` has only RELAY_BETA_* vars
- [ ] `.env.staging` has only RELAY_STAGING_* vars
- [ ] `.env.prod` has only RELAY_PROD_* vars
- [ ] Each file has `RELAY_STAGE=[beta|staging|prod]`

### Deployments ✓
- [ ] Pushing to `beta` deploys to `relay-beta-api`
- [ ] Pushing to `main` deploys to `relay-staging-api`
- [ ] Pushing to `production` deploys to `relay-prod-api`
- [ ] Each deployment uses correct environment variables
- [ ] Logs show correct stage: `[RELAY_BETA]`, `[RELAY_STAGING]`, `[RELAY_PROD]`

### Isolation ✓
- [ ] Beta API connects only to relay-beta-db
- [ ] Staging API connects only to relay-staging-db
- [ ] No cross-stage data leakage
- [ ] Stage detection works on startup

---

## Summary for You

✅ **You are correct to want unambiguous naming**

This plan gives you exactly that:
- **Never again wonder** which stage you're editing
- **Every service tagged** with its stage (relay-[STAGE]-[SERVICE])
- **Environment variables crystal clear** (RELAY_[STAGE]_[VAR])
- **Branches and workflows aligned** (beta→relay-beta-api, main→relay-staging-api)

The implementation is **low-risk**:
1. Code changes are purely additive (new config loader)
2. GitHub/Vercel changes are non-destructive
3. Railway rename is the only "scary" step (5 min downtime, trivial to revert)
4. You keep all existing infrastructure, just tag it

---

**Ready to implement?** Let me know and I can:
1. Create the NAMING_CONVENTION.md reference document
2. Generate the config loader code
3. Create the GitHub Actions workflow templates
4. Document step-by-step Railway rename procedure
5. Create deployment scripts that use stage-specific vars

All with zero ambiguity. ✅
