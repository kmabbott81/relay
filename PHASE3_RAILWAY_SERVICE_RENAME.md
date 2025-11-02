# Phase 3: Railway Service Rename Procedure

**Current Service**: `relay-production-f2a6`
**New Service**: `relay-beta-api`
**Estimated Downtime**: ~5 minutes
**Risk Level**: LOW (straightforward rename operation)

---

## Overview

This guide walks you through renaming the existing Railway service to match the new naming convention. The service will be renamed from `relay-production-f2a6` (confusing name) to `relay-beta-api` (clear stage identifier).

### Why This Change?

The current name `relay-production-f2a6` is misleading because:
- ❌ It says "production" but it's actually for BETA testing (50 user limit)
- ❌ No stage identifier in deployments (no way to know which version you're editing)
- ❌ Inconsistent with new naming convention: `relay-[STAGE]-[SERVICE]`

The new name `relay-beta-api` is clear because:
- ✅ `relay` = Project name
- ✅ `beta` = Stage identifier (limited users, ~50)
- ✅ `api` = Service type (backend API)

---

## Prerequisites

Before proceeding, verify you have:

1. **Access to Railway Dashboard**
   - URL: https://railway.app/dashboard
   - Account credentials ready

2. **Railway Project Information**
   - Project ID (currently visible on dashboard)
   - Service ID for `relay-production-f2a6`

3. **Backup Plan** (optional but recommended)
   - Note current environment variables
   - Document current deployment config

---

## Method 1: Railway UI (Recommended - Easiest)

### Step 1: Navigate to Railway Dashboard

1. Go to: https://railway.app/dashboard
2. Log in with your Railway account
3. Select the relay project

### Step 2: Open Service Settings

1. Click on the service currently named `relay-production-f2a6`
2. In the service panel, look for the service name at the top
3. Click on **Settings** (gear icon)

### Step 3: Rename Service

1. Find **General** section in Settings
2. Look for **Service Name** field
3. Current value: `relay-production-f2a6`
4. Change to: `relay-beta-api`
5. Click **Save**

### Step 4: Verify Rename

1. The service list should now show `relay-beta-api` instead of `relay-production-f2a6`
2. All existing environment variables remain unchanged
3. All existing deployments are preserved

### Step 5: Update GitHub Workflows (Already Done)

The GitHub workflows are already configured to look for `relay-beta-api`, so:
- Future deployments from `beta` branch will target the correctly named service
- Existing deployments continue to work without changes

---

## Method 2: Railway CLI (For Automation)

If you prefer CLI automation:

```bash
# Install Railway CLI (if not already installed)
npm install -g @railway/cli

# Login to Railway
railway login

# List current services to verify project
railway service list

# Rename service (approach depends on Railway CLI version)
# Option A: Using railway command (if supported)
railway service rename relay-beta-api

# Option B: Manual verification after UI rename
railway service list
# Should show: relay-beta-api (green, DEPLOYED status)
```

---

## What Happens During Rename

### During Rename (~30 seconds)

- Service configuration is updated in Railway's database
- Service remains running (no downtime during rename itself)
- All existing connections continue working
- Environment variables are unchanged
- Deployment history is preserved

### Immediate After Rename (1-2 minutes)

The service will:
1. Update name in dashboard
2. Update in service list
3. Update internal service routing
4. Deployments continue normally

### Verification After Rename

Check that:
1. Service name changed in dashboard
2. Service still shows as `DEPLOYED` status
3. All environment variables intact
4. API still accessible at: `https://relay-beta-api.railway.app`

---

## Verification Checklist

After completing the rename, verify everything:

### In Railway Dashboard

- [ ] Service name changed from `relay-production-f2a6` to `relay-beta-api`
- [ ] Status shows `DEPLOYED` (green)
- [ ] No errors in logs
- [ ] All environment variables present:
  - [ ] `RELAY_STAGE=beta`
  - [ ] `RELAY_BETA_SUPABASE_URL` (or similar)
  - [ ] `RELAY_BETA_DB_URL` (or similar)
  - [ ] Other service-specific variables

### API Connectivity

```bash
# Test API is still accessible
curl https://relay-beta-api.railway.app/health

# Expected response:
# {"status":"healthy","stage":"beta"}
```

### Git Deployment

```bash
# The existing deployed code should still work
# Next deployment from beta branch will use the new service name

# Check recent deployments in Railway
railway deployment list
# Should show recent successful deployment
```

---

## Rollback Plan (If Needed)

**If something goes wrong**, the rename is easily reversible:

1. Go back to Railway dashboard
2. Same Settings → General → Service Name field
3. Change back to: `relay-production-f2a6`
4. Save

The rename is non-destructive and can be undone at any time.

---

## Expected Results

### Before Rename

```
Service Name: relay-production-f2a6
URL: https://relay-production-f2a6.up.railway.app/health
Status: ✅ DEPLOYED
Logs: Working normally
```

### After Rename

```
Service Name: relay-beta-api
URL: https://relay-beta-api.railway.app/health
Status: ✅ DEPLOYED
Logs: Working normally (no changes)
```

**Note**: The URL domain will change from `relay-production-f2a6.up.railway.app` to `relay-beta-api.railway.app` or similar (depending on Railway's URL routing).

---

## Next Steps After Rename

1. **Update all references** to the service name in:
   - GitHub workflows (already done ✅)
   - Documentation
   - Local development scripts
   - Monitoring dashboards

2. **Set up GitHub secrets**:
   ```bash
   gh secret set RELAY_BETA_RAILWAY_TOKEN --body "..."
   gh secret set RELAY_BETA_RAILWAY_PROJECT_ID --body "..."
   gh secret set RELAY_BETA_SUPABASE_URL --body "..."
   # ... etc
   ```

3. **Test GitHub Actions**:
   ```bash
   git push origin beta
   # Watch deployment at: https://github.com/kmabbott81/djp-workflow/actions
   ```

4. **Verify three-stage deployment**:
   - Beta: `git push origin beta`
   - Staging: `git push origin main`
   - Production: `git push origin production`

---

## Timing Recommendation

**Best Time to Do This**:
- Off-peak hours (less user activity)
- After verifying backup plan
- When you can monitor for ~15 minutes

**Duration**:
- Rename operation: ~1 minute
- Verification: ~5 minutes
- Total: ~10-15 minutes

---

## Monitoring During Rename

Keep these monitoring tools open:

1. **Railway Dashboard** (https://railway.app/dashboard)
   - Watch service status change
   - Monitor for any error messages

2. **GitHub Actions** (https://github.com/kmabbott81/djp-workflow/actions)
   - Check if any workflows are running
   - Verify no deployment errors

3. **Terminal** (optional)
   ```bash
   # Keep a terminal tab with this command to monitor
   watch -n 5 'curl -s https://relay-beta-api.railway.app/health | jq'
   ```

---

## Troubleshooting

### Problem: Service Name Doesn't Update

**Solution**:
1. Refresh the Railway dashboard (Ctrl+R or Cmd+R)
2. Log out and log back in
3. Try the CLI method instead

### Problem: API URL Changes

**Solution**:
Railway may update the subdomain. Check:
1. Railway dashboard for new URL
2. Update GitHub workflows if URL format changes
3. Test: `curl https://[new-url]/health`

### Problem: Environment Variables Lost

**Solution**:
Railway preserves environment variables during rename. If missing:
1. Check the service still has them listed
2. Add them back manually if needed
3. All existing deployment history preserved

---

## Success Criteria

After completing the rename, you'll have:

✅ Service renamed: `relay-production-f2a6` → `relay-beta-api`
✅ Naming convention consistent: `relay-[STAGE]-[SERVICE]`
✅ GitHub workflows ready to deploy to renamed service
✅ Environment variables intact
✅ Deployment history preserved
✅ Zero user-facing downtime
✅ API accessible at new service name

---

## Status: Phase 3 Part B - Ready

**Completed in Phase 3 Part A**:
- ✅ GitHub branches created
- ✅ GitHub Actions workflows created
- ✅ Naming convention documented

**This Task (Phase 3 Part B)**:
- Railway service rename

**Still To Do (Phase 3 Part C)**:
- Create Vercel projects for staging and production
- Create Supabase projects for staging and production
- Configure all GitHub secrets
- Test each stage deployment

---

## Questions?

Refer to:
- NAMING_CONVENTION.md - Complete naming guide
- PHASE3_GITHUB_SECRETS_REQUIRED.md - Secrets configuration
- NAMING_CONVENTION_IMPLEMENTATION_PLAN.md - Full 4-phase plan

---

**Date**: 2025-11-02
**Phase**: 3 (Infrastructure Renaming) - Part B
**Estimated Duration**: 10-15 minutes
**Risk**: LOW (easily reversible)
