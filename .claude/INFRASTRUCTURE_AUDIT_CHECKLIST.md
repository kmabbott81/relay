# Infrastructure Audit Checklist

**Purpose**: Comprehensive audit of all external services and infrastructure before recommending new setups
**Owner**: agent-deployment-monitor
**Last Updated**: 2025-11-02

---

## Quick Reference

Use this checklist when user mentions: "setup", "config", "deploy", "staging", "production", "supabase", "vercel", "railway", "docker", "secrets", "credentials", "environment", "infrastructure"

**Expected Time**: 15-20 minutes for complete audit
**Risk Level**: LOW (read-only queries only)

---

## 1. Railway Services & Secrets Audit

### Check What Services Exist

```bash
railway service list
```

**Expected Output Example**:
```
NAME               STATUS    CREATED      UPDATED
api                DEPLOYED  2 days ago   5 hours ago
prometheus         RUNNING   10 days ago  10 days ago
grafana            RUNNING   10 days ago  10 days ago
```

**Record**:
- [ ] Which services are active?
- [ ] When were they last updated?
- [ ] Are there any failed or stuck services?

### Check Environment Variables for Each Service

```bash
# Main service (usually api or relay)
railway variables

# Specific service
railway variables --service relay-grafana
railway variables --service relay-postgres   # if exists
railway variables --service relay-api         # or main relay service
```

**Record**:
- [ ] What environment variables are set in each service?
- [ ] Are SUPABASE_URL, DATABASE_URL, API_KEY variables present?
- [ ] Are all required credentials configured?

### Report Railway Findings

| Item | Status | Details |
|------|--------|---------|
| Services Active | ✅/❌ | [Count and names] |
| Environment Vars | ✅/❌ | [Confirmed set] |
| Database Connection | ✅/❌ | [DATABASE_URL present?] |
| API Keys | ✅/❌ | [External service keys present?] |

---

## 2. GitHub Repository Audit

### Check for Stored Secrets

```bash
gh secret list
```

**Expected Output Example**:
```
Name                   Updated
RAILWAY_TOKEN         2025-10-15T14:30:00Z
SUPABASE_KEY          2025-10-20T09:15:00Z
VERCEL_TOKEN          2025-11-01T10:45:00Z
```

**Record**:
- [ ] What secrets are stored in GitHub?
- [ ] When were they last updated?
- [ ] Are any secrets stale (> 90 days old)?

### Check for CI/CD Workflows

```bash
gh workflow list
```

**Expected Output Example**:
```
NAME               STATE      CREATED
deploy.yml         active     2 weeks ago
test.yml           active     3 weeks ago
lint.yml           active     1 month ago
```

**Record**:
- [ ] What automated workflows exist?
- [ ] Are deployment pipelines configured?
- [ ] Any workflows disabled or failing?

### Check Git History for Infrastructure Changes

```bash
git log --oneline --all --grep="supabase\|vercel\|railway\|docker" | head -20
```

**Expected Output Example**:
```
a1b2c3d - feat: Add Supabase integration to relay service
e4f5g6h - chore: Update Railway deployment config
i7j8k9l - fix: Configure Vercel environment variables
```

**Record**:
- [ ] Recent infrastructure setup commits?
- [ ] Any incomplete or reverted infrastructure changes?
- [ ] When was infrastructure last modified?

### Check for Infrastructure Branches

```bash
git branch -a | grep -i "infra\|deploy\|setup"
```

**Expected Output Example**:
```
infrastructure/supabase-setup
infrastructure/vercel-deployment
infrastructure/database-migration
```

**Record**:
- [ ] Any infrastructure work branches?
- [ ] Should these be merged or archived?

### Report GitHub Findings

| Item | Status | Details |
|------|--------|---------|
| Secrets Count | ✅ | [Number and names] |
| Workflows | ✅ | [List of active workflows] |
| Recent Changes | ✅ | [Infrastructure commits] |
| WIP Branches | ✅/❌ | [Infrastructure branches] |

---

## 3. Supabase Audit

### Option A: CLI-Based Check (Requires Supabase CLI)

```bash
# Verify supabase CLI is installed
supabase --version

# If installed, list projects
supabase projects list
```

**Expected Output Example**:
```
ID                      NAME              REGION
hmqmxmxkxqdrqpdmlgtn   relay-staging     us-east-1
xyz123                  relay-test        us-east-1
```

**Record**:
- [ ] What Supabase projects exist?
- [ ] Which ones match our project naming (relay-*, staging*, production*)?
- [ ] What region are they in?

### Option B: Manual Dashboard Check

If CLI not available:

1. Go to: https://supabase.com/dashboard
2. Log in with your account
3. List all projects
4. Look for projects matching: `relay-*`, `staging*`, `production*`

**Record**:
- [ ] Project ID (if found)
- [ ] Project name
- [ ] Current status
- [ ] URL (dashboard link)

### Check Database & Storage (if CLI access confirmed)

```bash
supabase db list
supabase storage list
```

### Report Supabase Findings

| Item | Status | Details |
|------|--------|---------|
| Projects Found | ✅/❌ | [Project IDs and names] |
| Database Status | ✅/❌ | [Schemas, tables count] |
| Storage Buckets | ✅/❌ | [Bucket names] |
| Credentials Location | ✅ | [Railway secrets / GitHub secrets] |

---

## 4. Vercel Deployment Audit

### Check Deployed Projects

```bash
# Verify vercel CLI installed
vercel --version

# List projects
vercel projects
```

**Expected Output Example**:
```
relay-beta         https://relay-beta.vercel.app
relay-production   https://relay.ai (not yet deployed)
```

**Record**:
- [ ] What Vercel projects exist?
- [ ] What domains are configured?
- [ ] Production vs staging deployments?

### List Recent Deployments

```bash
vercel deployments
```

**Expected Output Example**:
```
AGE     URL                                STATE
5h      https://relay-v123.vercel.app    READY
2d      https://relay-v122.vercel.app    READY
```

**Record**:
- [ ] Latest deployment status?
- [ ] How many successful deployments?
- [ ] Any failed deployments to investigate?

### Check Environment Variables

```bash
vercel env ls
```

**Record**:
- [ ] What environment variables are configured?
- [ ] Are API keys and secrets set?

### Report Vercel Findings

| Item | Status | Details |
|------|--------|---------|
| Projects | ✅/❌ | [Project names and URLs] |
| Latest Deploy | ✅ | [Status and timestamp] |
| Environment Vars | ✅ | [Configured variables] |
| Credentials | ✅ | [GitHub secrets / Vercel dashboard] |

---

## 5. Docker Infrastructure Audit

### Check Local Docker Images

```bash
docker images | grep -i relay
```

**Expected Output Example**:
```
relay-api           latest   a1b2c3d4   2 days ago   500MB
relay-frontend      latest   e4f5g6h7   1 week ago   200MB
```

**Record**:
- [ ] What Docker images exist locally?
- [ ] When were they built?
- [ ] Are they current or outdated?

### Check Running Containers

```bash
docker ps -a | grep -i relay
```

**Expected Output Example**:
```
CONTAINER ID    IMAGE          NAMES        STATUS
abc123def456    relay-api      relay-api-1  Up 2 days
ghi789jkl012    relay-frontend relay-web    Exited (0) 5 days ago
```

**Record**:
- [ ] What containers are currently running?
- [ ] Which ones are stopped (exited)?
- [ ] How long have they been running?

### Check Docker Compose (if using)

```bash
docker-compose ps
```

**Record**:
- [ ] Any docker-compose services defined?
- [ ] Service health status?

### Report Docker Findings

| Item | Status | Details |
|------|--------|---------|
| Images | ✅/❌ | [Count and names] |
| Running Containers | ✅/❌ | [Status] |
| Docker Compose | ✅/❌ | [If used, service list] |

---

## 6. Git Repository Analysis

### Search for All Infrastructure References

```bash
grep -r "supabase\|vercel\|railway\|docker\|postgres\|redis" \
  --include="*.md" \
  --include="*.env*" \
  --include="*.yaml" \
  --include="*.yml" \
  --include="*.json" \
  . | head -50
```

**Record**:
- [ ] Infrastructure references found?
- [ ] In documentation, config, or code?
- [ ] Are they current or outdated?

### Search Commit History for Infrastructure

```bash
git log --all -p --grep="infrastructure\|setup\|config" | head -100
```

**Record**:
- [ ] Infrastructure setup documented in commits?
- [ ] Any migration or configuration changes?
- [ ] Timestamps for these changes?

### Look for TODOs Related to Infrastructure

```bash
grep -r "TODO\|FIXME" . --include="*.md" --include="*.js" --include="*.ts" | grep -i "infra\|setup\|deploy"
```

**Record**:
- [ ] Outstanding infrastructure TODOs?
- [ ] Any partially configured services?

### Report Git Analysis Findings

| Item | Status | Details |
|------|--------|---------|
| Documented Infrastructure | ✅ | [What's documented] |
| Setup Commits | ✅ | [When set up] |
| Outstanding TODOs | ✅/❌ | [List of items] |

---

## 7. Local Environment Files Audit

### Check What Environment Files Exist

```bash
ls -la .env* 2>/dev/null
```

**Expected Output Example**:
```
.env.local
.env.production
.env.example
```

**⚠️ IMPORTANT**: DO NOT read file contents without explicit permission

**Record**:
- [ ] What .env files exist?
- [ ] Are they in .gitignore? (Should be ✅)
- [ ] Last modified dates?

### Verify .gitignore Configuration

```bash
grep ".env" .gitignore
```

**Record**:
- [ ] Environment files properly ignored?
- [ ] No secrets accidentally committed?

### Report Local Environment Findings

| Item | Status | Details |
|------|--------|---------|
| Env Files | ✅ | [Names of files] |
| .gitignore Protected | ✅ | [Confirmed] |
| Modification Date | ✅ | [When last updated] |

---

## Summary Report Template

After running all audits, fill out this summary:

### Infrastructure Discovery Summary

**Audit Date**: [Date]
**Auditor**: [Agent/Human]

#### Services Found

| Service | Found? | Details | Credentials Location |
|---------|--------|---------|----------------------|
| Railway | ✅/❌ | [Services list] | Railway dashboard |
| Supabase | ✅/❌ | [Project IDs] | Railway secrets / Supabase |
| Vercel | ✅/❌ | [Deployments] | GitHub secrets / Vercel |
| GitHub | ✅/❌ | [Secrets count] | GitHub repo settings |
| Docker | ✅/❌ | [Images/containers] | Local machine |
| Git | ✅ | [Recent commits] | Git history |

#### Next Steps

- [ ] If infrastructure found: **Ask user: "Use existing OR create new?"**
- [ ] If existing: Extract credentials and update deployment plan
- [ ] If not found: Proceed with fresh setup recommendations
- [ ] Document what was created and where credentials are stored

#### Confidence Level

- 🟢 **HIGH**: All services checked, all tools available
- 🟡 **MEDIUM**: Some services checked, some tools unavailable
- 🔴 **LOW**: Limited access, manual verification needed

**Confidence**: [HIGH/MEDIUM/LOW]

---

## Troubleshooting

### CLI Tool Not Installed

**Railway not available**:
```bash
# Install: npm install -g railway
# Or: https://railway.app/docs/guides/cli
```

**Vercel not available**:
```bash
# Install: npm install -g vercel
# Or: https://vercel.com/docs/cli
```

**GitHub CLI not available**:
```bash
# Install: brew install gh (macOS)
# Or: https://github.com/cli/cli
```

**Supabase not available**:
```bash
# Install: npm install -g supabase
# Or: https://supabase.com/docs/guides/cli
```

### Permission Errors

- ⚠️ If lacking credentials for Railway/Vercel/Supabase: Ask user to provide them
- ⚠️ If no GitHub access: Fall back to manual git command checking
- ⚠️ If Docker daemon not running: `docker ps` will fail gracefully

### Incomplete Infrastructure

If infrastructure is partially configured:
1. Flag as "INCOMPLETE"
2. Ask user: "What's the current status of [service]?"
3. Document findings
4. Proceed with caution

---

## References

- Railway: https://railway.app/docs
- Supabase: https://supabase.com/docs
- Vercel: https://vercel.com/docs
- GitHub CLI: https://cli.github.com
- Docker: https://docs.docker.com/get-started/

**Source of Truth**: `.claude/agents/agent-deployment-monitor.md` (Trigger Rule #8)
