# Relay Naming Convention Reference

**Purpose**: Eliminate ambiguity about which stage/environment each resource belongs to.

**Status**: ✅ Active (Phase 1 Complete - Documentation)

---

## Core Patterns

### Service Naming Pattern

```
relay-[STAGE]-[SERVICE]
```

**Components**:
- `relay` - Project identifier (always "relay")
- `[STAGE]` - Deployment stage (beta, staging, prod)
- `[SERVICE]` - Service type (api, db, web, worker, etc.)

**Examples**:
```
relay-beta-api        # API deployed to beta environment
relay-staging-db      # Database for staging environment
relay-prod-web        # Frontend deployed to production
```

### Environment Variable Pattern

```
RELAY_[STAGE]_[SERVICE]_[VARIABLE]
```

**Components**:
- `RELAY` - Project prefix (always "RELAY")
- `[STAGE]` - Stage in uppercase (BETA, STAGING, PROD)
- `[SERVICE]` - Service identifier (SUPABASE, API, DB, etc.)
- `[VARIABLE]` - Specific variable (URL, KEY, TOKEN, etc.)

**Examples**:
```
RELAY_BETA_SUPABASE_URL          # Beta Supabase URL
RELAY_STAGING_API_TOKEN          # Staging API token
RELAY_PROD_DB_PASSWORD           # Production database password
RELAY_BETA_VERCEL_TOKEN          # Beta Vercel deployment token
```

---

## Complete Service Mapping

| Service | Beta | Staging | Production |
|---------|------|---------|------------|
| **Supabase Project** | relay-beta-db | relay-staging-db | relay-prod-db |
| **Railway Service** | relay-beta-api | relay-staging-api | relay-prod-api |
| **Vercel Project** | relay-beta-web | relay-staging-web | relay-prod-web |
| **Git Branch** | beta | main | production |
| **Database** | relay-beta-db | relay-staging-db | relay-prod-db |
| **API URL** | relay-beta-api.railway.app | relay-staging-api.railway.app | relay-prod-api.railway.app |
| **Web URL** | relay-beta.vercel.app | relay-staging.vercel.app | relay.app |

---

## Environment Variables by Stage

### BETA Environment

```bash
RELAY_STAGE=beta
RELAY_BETA_SUPABASE_URL=https://hmqmxmxkxqdrqpdmlgtn.supabase.co
RELAY_BETA_SUPABASE_ANON_KEY=eyJ...
RELAY_BETA_API_URL=https://relay-beta-api.railway.app
RELAY_BETA_DB_URL=postgresql://...
RELAY_BETA_VERCEL_TOKEN=...
```

### STAGING Environment

```bash
RELAY_STAGE=staging
RELAY_STAGING_SUPABASE_URL=https://[staging-project-id].supabase.co
RELAY_STAGING_SUPABASE_ANON_KEY=eyJ...
RELAY_STAGING_API_URL=https://relay-staging-api.railway.app
RELAY_STAGING_DB_URL=postgresql://...
RELAY_STAGING_VERCEL_TOKEN=...
```

### PRODUCTION Environment

```bash
RELAY_STAGE=prod
RELAY_PROD_SUPABASE_URL=https://[prod-project-id].supabase.co
RELAY_PROD_SUPABASE_ANON_KEY=eyJ...
RELAY_PROD_API_URL=https://relay-prod-api.railway.app
RELAY_PROD_DB_URL=postgresql://...
RELAY_PROD_VERCEL_TOKEN=...
```

---

## Git Branch Strategy

| Branch | Deploys To | Stage | Purpose |
|--------|-----------|-------|---------|
| `beta` | `relay-beta-api` | BETA | Beta testing (limited users) |
| `main` | `relay-staging-api` | STAGING | Internal QA and testing |
| `production` | `relay-prod-api` | PROD | General availability (GA) |

---

## Implementation Checklist

### ✅ Phase 1: Documentation & Planning (COMPLETE)
- [x] Tech-lead designed naming convention
- [x] Created NAMING_CONVENTION_IMPLEMENTATION_PLAN.md
- [x] Created this NAMING_CONVENTION.md reference
- [x] Documented all service mappings
- [x] Documented all environment variable patterns

### ⏳ Phase 2: Code Preparation (NEXT)
- [ ] Create `relay_ai/config/stage.py` - Stage detection & config loader
- [ ] Update startup checks to verify RELAY_STAGE is valid
- [ ] Update `.env.beta`, `.env.staging`, `.env.prod` files
- [ ] Update `.gitignore` to handle environment files

### ⏳ Phase 3: Infrastructure Renaming (THIS WEEK)
- [ ] Rename Railway service `relay-production-f2a6` → `relay-beta-api`
- [ ] Create GitHub branches: `beta`, `production`
- [ ] Create GitHub Environments: `beta`, `staging`, `prod`
- [ ] Move secrets to GitHub Environments
- [ ] Create Vercel projects: `relay-staging-web`, `relay-prod-web`
- [ ] Update GitHub Actions workflows for stage-specific deployments

### ⏳ Phase 4: Testing & Validation (NEXT WEEK)
- [ ] Test BETA environment - verify relay-beta-api connections
- [ ] Test STAGING environment - verify relay-staging-api connections
- [ ] Test PROD environment - verify relay-prod-api connections
- [ ] Verify cross-stage isolation (no data leakage)
- [ ] Verify logs show correct stage identifiers

---

## Quick Reference for Developers

### When you see a service name, ask:

**"What stage is this resource for?"**

```
relay-beta-api              → BETA (limited users, ~50)
relay-staging-db            → STAGING (internal testing)
relay-prod-web              → PROD (general availability)
```

### When you see an environment variable, ask:

**"What stage does this variable apply to?"**

```
RELAY_BETA_SUPABASE_URL     → BETA
RELAY_STAGING_API_TOKEN     → STAGING
RELAY_PROD_DB_PASSWORD      → PROD
```

### When deploying, verify:

1. **Service name** matches intended stage
2. **Environment variables** use correct stage prefix
3. **Git branch** matches deployment target
4. **Secrets** are stored in correct location

---

## Troubleshooting

### Problem: "Which database is this connecting to?"

**Solution**: Look at the environment variable prefix:
```
RELAY_BETA_DB_URL      → Beta database
RELAY_STAGING_DB_URL   → Staging database
RELAY_PROD_DB_URL      → Production database
```

### Problem: "I deployed to the wrong stage"

**Solution**: Check service name and git branch:
```
# If you see relay-beta-api deployed
# But you pushed to the production branch...
# Your workflow is using wrong stage in deployment step
```

### Problem: "Which Supabase project are we using?"

**Solution**: Check the URL variable:
```
RELAY_BETA_SUPABASE_URL
→ Check Railway secrets for the URL
→ Extract project ID from the URL
→ Verify it matches relay-beta-db naming
```

---

## Future-Proofing

This naming convention scales to support:
- ✅ Additional stages (canary, pre-prod, etc.)
- ✅ Multi-region deployments (relay-beta-api-us-west)
- ✅ Additional services (relay-beta-worker, relay-beta-cache)
- ✅ External integrations (relay-beta-github-token, relay-beta-stripe-key)

Simply apply the pattern: `relay-[STAGE]-[SERVICE]` and `RELAY_[STAGE]_[SERVICE]_[VAR]`

---

## Questions?

See full implementation plan: `NAMING_CONVENTION_IMPLEMENTATION_PLAN.md`

---

**Last Updated**: 2025-11-02
**Status**: Phase 1 Complete - Ready for Phase 2 (Code Preparation)
**Next**: Begin Phase 2 - Create relay_ai/config/stage.py config loader
