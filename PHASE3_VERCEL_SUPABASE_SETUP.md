# Phase 3: Vercel & Supabase Setup for Staging and Production

**Purpose**: Create staging and production versions of Vercel web projects and Supabase database projects

**Estimated Time**:
- Supabase projects: 5-10 minutes
- Vercel projects: 10-15 minutes
- Total: 20-30 minutes

---

## Current State

### What Already Exists (BETA)

✅ **Supabase**: `relay-staging` (hmqmxmxkxqdrqpdmlgtn)
- Already created with schema
- JWT secret configured
- Credentials in Railway secrets

✅ **Vercel**: `relay-beta-web`
- Already deployed to relay-beta.vercel.app
- GitHub integration configured

### What Needs to Be Created

❌ **Supabase Projects**:
- `relay-staging-db` (for staging environment)
- `relay-prod-db` (for production environment)

❌ **Vercel Projects**:
- `relay-staging-web` (for staging environment)
- `relay-prod-web` (for production environment)

---

## Part 1: Creating Supabase Projects

### Step 1: Create Staging Database Project

1. **Go to Supabase Dashboard**
   - URL: https://supabase.com/dashboard

2. **Create New Project**
   - Click "New Project" button
   - Organization: Your personal account or team
   - Project Name: `relay-staging-db`
   - Database Password: Generate strong password (save it!)
   - Region: Same as existing (us-east-1 or your preferred)
   - Click "Create new project"

3. **Wait for Project Creation**
   - Takes 2-5 minutes
   - You'll see initialization progress
   - Project URL will be generated automatically

4. **Get Project Credentials**
   - Once created, go to Settings → API
   - Copy:
     - **Project URL**: `https://[project-id].supabase.co`
     - **Anon Key**: (public/anonymous key)
     - **Service Role Key**: (secret key for backend)

5. **Save Credentials**
   - Copy to secure location (you'll need for GitHub secrets)
   - Format:
     ```
     RELAY_STAGING_SUPABASE_URL=https://[project-id].supabase.co
     RELAY_STAGING_SUPABASE_ANON_KEY=[anon-key]
     RELAY_STAGING_SUPABASE_SERVICE_ROLE_KEY=[service-role-key]
     ```

### Step 2: Create Production Database Project

Repeat the same process for production:

1. **Create New Project**
   - Project Name: `relay-prod-db`
   - Database Password: Generate new strong password
   - Region: Same as staging/beta
   - Click "Create new project"

2. **Get Project Credentials**
   - Settings → API
   - Copy:
     - **Project URL**: `https://[project-id].supabase.co`
     - **Anon Key**: (public/anonymous key)
     - **Service Role Key**: (secret key for backend)

3. **Save Credentials**
   - Format:
     ```
     RELAY_PROD_SUPABASE_URL=https://[project-id].supabase.co
     RELAY_PROD_SUPABASE_ANON_KEY=[anon-key]
     RELAY_PROD_SUPABASE_SERVICE_ROLE_KEY=[service-role-key]
     ```

### Step 3: Verify Supabase Projects

After creating both projects, verify:

```bash
# List all Supabase projects (if CLI installed)
supabase projects list

# Expected output:
# relay-beta-db     (hmqmxmxkxqdrqpdmlgtn)     Existing
# relay-staging-db  (new-project-id-1)          New
# relay-prod-db     (new-project-id-2)          New
```

---

## Part 2: Creating Vercel Projects

### Step 1: Create Staging Web Project

1. **Go to Vercel Dashboard**
   - URL: https://vercel.com/dashboard

2. **Create New Project**
   - Click "Add New..." → "Project"
   - Import repository: Select `relay` or your repo fork
   - Project Name: `relay-staging-web`
   - Framework: Next.js
   - Root Directory: `relay_ai/product/web`

3. **Configure Environment Variables**
   - Add environment variables for staging:
     ```
     NEXT_PUBLIC_SUPABASE_URL=[staging-supabase-url]
     NEXT_PUBLIC_SUPABASE_ANON_KEY=[staging-anon-key]
     NEXT_PUBLIC_API_URL=https://relay-staging-api.railway.app
     ```

4. **Connect Git**
   - Branch: `main` (or staging branch if created)
   - Auto-deploy: On every push

5. **Deploy**
   - Vercel will build and deploy automatically
   - You'll get a `.vercel.app` domain

6. **Custom Domain** (Optional)
   - Settings → Domains
   - Add `relay-staging.vercel.app` if available

7. **Get Project IDs**
   - Project Settings → General
   - Copy:
     - **Project ID**: (shown in settings)
     - **Org ID**: (from account settings)

### Step 2: Create Production Web Project

Repeat for production:

1. **Create New Project**
   - Project Name: `relay-prod-web`
   - Framework: Next.js
   - Root Directory: `relay_ai/product/web`

2. **Configure Environment Variables**
   - Add environment variables for production:
     ```
     NEXT_PUBLIC_SUPABASE_URL=[prod-supabase-url]
     NEXT_PUBLIC_SUPABASE_ANON_KEY=[prod-anon-key]
     NEXT_PUBLIC_API_URL=https://relay-prod-api.railway.app
     ```

3. **Connect Git**
   - Branch: `production` (or main if you prefer)
   - Auto-deploy: On every push

4. **Deploy**
   - Vercel will build and deploy automatically

5. **Custom Domain** (Optional)
   - Add `relay.app` or your custom domain

6. **Get Project IDs**
   - Project Settings → General
   - Copy Project ID and Org ID

---

## Part 3: Configure GitHub Secrets

Once you have all credentials, set them as GitHub secrets:

```bash
# Staging Secrets
gh secret set RELAY_STAGING_SUPABASE_URL --body "https://[staging-id].supabase.co"
gh secret set RELAY_STAGING_SUPABASE_ANON_KEY --body "[staging-anon-key]"
gh secret set RELAY_STAGING_VERCEL_TOKEN --body "[vercel-token]"
gh secret set RELAY_STAGING_VERCEL_PROJECT_ID --body "[staging-project-id]"
gh secret set RELAY_STAGING_VERCEL_ORG_ID --body "[org-id]"

# Production Secrets
gh secret set RELAY_PROD_SUPABASE_URL --body "https://[prod-id].supabase.co"
gh secret set RELAY_PROD_SUPABASE_ANON_KEY --body "[prod-anon-key]"
gh secret set RELAY_PROD_VERCEL_TOKEN --body "[vercel-token]"
gh secret set RELAY_PROD_VERCEL_PROJECT_ID --body "[prod-project-id]"
gh secret set RELAY_PROD_VERCEL_ORG_ID --body "[org-id]"
```

---

## Part 4: Setting Up Supabase Schema (One-Time)

After creating Supabase projects, you need to run migrations to set up the schema:

### Option 1: Via GitHub Actions (Automatic)

The GitHub workflows will automatically run migrations:

```bash
# For Staging
git push origin main
# GitHub Actions will:
# 1. Run migrate-db job
# 2. Create schema in relay-staging-db
# 3. Deploy API to relay-staging-api
# 4. Deploy web to relay-staging-web

# For Production
git push origin production
# Same process but for relay-prod-db
```

### Option 2: Manual Migration (If Needed)

```bash
# Run migrations locally
RELAY_STAGE=staging SQLALCHEMY_DATABASE_URL="$RELAY_STAGING_DB_URL" alembic upgrade head

# Verify
alembic current
# Should show: "[revision-hash] (head)"
```

---

## Checklist: Vercel & Supabase Setup

### Supabase Projects

- [ ] `relay-staging-db` created
  - [ ] Project URL copied: `https://[id].supabase.co`
  - [ ] Anon key copied
  - [ ] Service role key copied
  - [ ] Credentials saved securely

- [ ] `relay-prod-db` created
  - [ ] Project URL copied: `https://[id].supabase.co`
  - [ ] Anon key copied
  - [ ] Service role key copied
  - [ ] Credentials saved securely

### Vercel Projects

- [ ] `relay-staging-web` created
  - [ ] Connected to GitHub repository
  - [ ] Branch set to: `main` (or staging)
  - [ ] Environment variables configured:
    - [ ] `NEXT_PUBLIC_SUPABASE_URL` set
    - [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY` set
    - [ ] `NEXT_PUBLIC_API_URL` set to `https://relay-staging-api.railway.app`
  - [ ] Project ID copied

- [ ] `relay-prod-web` created
  - [ ] Connected to GitHub repository
  - [ ] Branch set to: `production` (or main)
  - [ ] Environment variables configured:
    - [ ] `NEXT_PUBLIC_SUPABASE_URL` set
    - [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY` set
    - [ ] `NEXT_PUBLIC_API_URL` set to `https://relay-prod-api.railway.app`
  - [ ] Project ID copied

### GitHub Secrets

- [ ] All `RELAY_STAGING_*` secrets set (5 secrets)
- [ ] All `RELAY_PROD_*` secrets set (5 secrets)
- [ ] Secrets verified: `gh secret list`

---

## Verification: Test Each Stage

### Test Staging Deployment

```bash
# Push to main to trigger staging deployment
git push origin main

# Watch deployment
# 1. Go to GitHub Actions: https://github.com/kmabbott81/djp-workflow/actions
# 2. Click on "Deploy to Staging" workflow
# 3. Watch jobs:
#    ✓ migrate-db (creates schema)
#    ✓ deploy-api (deploys to relay-staging-api)
#    ✓ deploy-web (deploys to relay-staging-web)
#    ✓ smoke-tests (verifies deployment)

# After ~10 minutes, verify:
curl https://relay-staging-api.railway.app/health
# Should return: {"status":"healthy"}

# Check web:
open https://relay-staging.vercel.app
# Should load your app
```

### Test Production Deployment

```bash
# Push to production to trigger prod deployment
git push origin production

# Watch deployment (same as staging)
# After ~10 minutes, verify:
curl https://relay-prod-api.railway.app/health

# Check web:
open https://relay.app
```

---

## Service Mapping After Setup

```
BETA (Currently Running):
├── Supabase: relay-staging (hmqmxmxkxqdrqpdmlgtn)
├── Railway: relay-beta-api
├── Vercel: relay-beta.vercel.app
└── Status: ✅ DEPLOYED

STAGING (After This Setup):
├── Supabase: relay-staging-db (new)
├── Railway: relay-staging-api
├── Vercel: relay-staging.vercel.app
└── Status: ⏳ DEPLOYING

PRODUCTION (After This Setup):
├── Supabase: relay-prod-db (new)
├── Railway: relay-prod-api
├── Vercel: relay.app
└── Status: ⏳ DEPLOYING
```

---

## Environment Variable Reference

### After All Setup Complete

```yaml
# BETA
RELAY_STAGE: beta
RELAY_BETA_SUPABASE_URL: https://hmqmxmxkxqdrqpdmlgtn.supabase.co
RELAY_BETA_SUPABASE_ANON_KEY: [key]
RELAY_BETA_API_URL: https://relay-beta-api.railway.app
RELAY_BETA_DB_URL: [database-connection]

# STAGING
RELAY_STAGE: staging
RELAY_STAGING_SUPABASE_URL: https://[staging-id].supabase.co
RELAY_STAGING_SUPABASE_ANON_KEY: [key]
RELAY_STAGING_API_URL: https://relay-staging-api.railway.app
RELAY_STAGING_DB_URL: [database-connection]

# PRODUCTION
RELAY_STAGE: prod
RELAY_PROD_SUPABASE_URL: https://[prod-id].supabase.co
RELAY_PROD_SUPABASE_ANON_KEY: [key]
RELAY_PROD_API_URL: https://relay-prod-api.railway.app
RELAY_PROD_DB_URL: [database-connection]
```

---

## Troubleshooting

### Problem: Vercel Build Fails

**Solution**:
1. Check environment variables are set correctly
2. Verify `NEXT_PUBLIC_API_URL` points to correct Railway service
3. Check Vercel build logs for specific errors
4. Common: Missing `NEXT_PUBLIC_SUPABASE_*` variables

### Problem: Supabase Schema Missing

**Solution**:
1. Manually run migrations:
   ```bash
   SQLALCHEMY_DATABASE_URL="postgresql://..." alembic upgrade head
   ```
2. Or wait for next GitHub Actions deployment
3. Verify: `alembic current`

### Problem: GitHub Actions Workflow Fails

**Solution**:
1. Check GitHub secrets are set: `gh secret list`
2. Verify secret values are correct (no extra spaces)
3. Check Railway/Vercel services exist
4. Review workflow logs for specific errors

---

## Status: Phase 3 Part C - Ready

**Completed**:
- ✅ Phase 1 & 2: Documentation and code preparation
- ✅ Phase 3 Part A: GitHub branches and workflows
- ✅ Phase 3 Part B: Railway service rename guide
- ✅ Phase 3 Part C: Vercel & Supabase setup (THIS)

**Next**:
- Execute Railway service rename
- Create Supabase projects (staging & prod)
- Create Vercel projects (staging & prod)
- Set GitHub secrets
- Test all three deployments

---

**Date**: 2025-11-02
**Phase**: 3 (Infrastructure Renaming) - Part C
**Estimated Duration**: 20-30 minutes
**Risk**: LOW (straightforward provisioning)
