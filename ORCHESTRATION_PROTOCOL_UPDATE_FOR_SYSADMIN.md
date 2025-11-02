# Agent Orchestration Protocol - Infrastructure Audit Enhancement

**Date**: 2025-11-02
**Issue**: Project-historian agent missed existing Supabase project (hmqmxmxkxqdrqpdmlgtn) because it only searched project files, not external services
**Root Cause**: Agent orchestration protocol lacks **multi-source infrastructure discovery** mechanism
**Solution**: Add explicit infrastructure audit trigger with comprehensive service checks

---

## Problem Statement

On 2025-11-02, the project-historian agent reported "No existing Supabase project found" when in reality:
- ✅ Supabase project `relay-staging` (ID: hmqmxmxkxqdrqpdmlgtn) exists
- ✅ Project URL and JWT key stored in Railway secrets
- ✅ User manually added these ~2 weeks ago per instructions
- ❌ Agent never checked Railway secrets, GitHub Secrets, or other external services

**Impact**:
- Wasted time recommending creating a new project
- Failed to identify that database schema may already be initialized
- Demonstrated the orchestration protocol doesn't enforce comprehensive infrastructure audit

**Fix Required**: Update agent-deployment-monitor's ORCHESTRATION_TRIGGER_MECHANISM to include mandatory multi-source infrastructure discovery.

---

## What to Add to Agent-Deployment-Monitor File

### Addition 1: New Trigger Rule - Infrastructure Discovery

**Location**: `.claude/agents/agent-deployment-monitor.md`

**Section**: ORCHESTRATION_TRIGGER_MECHANISM → Add after existing trigger rules:

```markdown
### 8️⃣ **TRIGGER: Multi-Source Infrastructure Discovery**

**WHEN**:
- [ ] User mentions "setup" OR "config" OR "deploy"
- [ ] User asks about environment status or configuration
- [ ] ANY new task related to infrastructure, deployments, or external services
- [ ] Project-historian is about to recommend creating NEW infrastructure

**PRIMARY RESPONSIBILITY**: Agent-deployment-monitor (uses project-historian + data-connector-architect)

**MANDATORY CHECKS** (Must verify ALL sources before implementing):

#### A. Railway Services & Secrets
```bash
# Check connected services
railway service list

# Check environment variables (all services)
railway variables              # Prometheus
railway variables --service relay-grafana
railway variables --service relay-postgres (if exists)
railway variables --service relay-api (or main relay service)

# Report findings:
- Which services exist?
- What environment variables are set?
- What secrets/credentials are stored?
- What database connections exist?
- What domains/URLs are active?
```

#### B. GitHub Repository
```bash
# Check for secrets (names only, not values)
gh secret list

# Check for existing workflows
gh workflow list

# Check recent commits for infrastructure changes
git log --oneline --all --grep="supabase\|vercel\|railway\|docker" | head -20

# Check branches for infrastructure work
git branch -a | grep -i "infra\|deploy\|setup"

# Report findings:
- What GitHub secrets exist?
- What CI/CD workflows are configured?
- Any recent infrastructure commits?
```

#### C. Supabase (If project uses Supabase)
```bash
# User must provide Supabase credentials or project ID
# Check: Does user have supabase CLI installed?
supabase projects list

# If using CLI:
supabase db list
supabase storage list

# OR: Ask user to confirm in Supabase dashboard:
# - Go to: https://supabase.com/dashboard
# - List your projects
# - Report any that match pattern: relay-*, staging*, production*
```

#### D. Vercel (If project uses Vercel)
```bash
# Check deployed projects
vercel projects

# List deployments
vercel deployments

# Check environment variables (if deployed)
vercel env ls

# Report findings:
- What Vercel projects exist?
- What domains are configured?
- What environment variables are set?
- What are latest deployment statuses?
```

#### E. Docker (If using containers)
```bash
# Check local images
docker images | grep -i relay

# Check running containers
docker ps -a | grep -i relay

# Check docker-compose
docker-compose ps (if using docker-compose)

# Report findings:
- What Docker images exist?
- What containers are running?
- What ports are exposed?
```

#### F. Git Repository Analysis
```bash
# Search for all infrastructure references
grep -r "supabase\|vercel\|railway\|docker\|postgres\|redis" \
  --include="*.md" \
  --include="*.env*" \
  --include="*.yaml" \
  --include="*.yml" \
  --include="*.json" \
  . | head -50

# Search commit history
git log --all -p --grep="infrastructure\|setup\|config" | head -100

# Report findings:
- What infrastructure is documented?
- What credentials/configs are in git history?
- Any TODO or FIXME items related to infrastructure?
```

#### G. Local Environment Files (Carefully!)
```bash
# Check what .env* files exist (DON'T read contents without permission)
ls -la .env* 2>/dev/null

# Report findings:
- What environment files exist?
- Are they in .gitignore?
- When were they last modified?
```

**ACTION TAKEN**:

After comprehensive check, report findings as structured table:

| Service | Status | Details | Credentials Location |
|---------|--------|---------|----------------------|
| Railway | Active | Services: api, prometheus, grafana | Railway dashboard |
| Supabase | Active | Project ID: hmqmxmxkxqdrqpdmlgtn | Railway secrets + Supabase dashboard |
| Vercel | [Pending] | [Details] | Vercel dashboard + GitHub secrets |
| GitHub | Active | Secrets: [count], Workflows: [count] | GitHub repo settings |
| Docker | [Status] | [Details] | Local machine |
| Git | Active | [Recent commits] | Git history |

**DECISION LOGIC**:

```
IF any infrastructure found:
  ✅ Report ALL found infrastructure BEFORE recommending new setup
  ✅ Ask user: "Use existing OR create new?"
  ✅ If using existing: Extract credentials and update deployment plan
  ✅ If creating new: Proceed with new infrastructure recommendations

IF no infrastructure found:
  ✅ Proceed with fresh setup recommendations
  ✅ Document what was created and where credentials are stored
```

**FAILURE MODES**:

- ⚠️ If user lacks CLI tool (railway, vercel, gh): Fall back to manual verification
- ⚠️ If credentials not in expected locations: Ask user directly "Where are your [service] credentials?"
- ⚠️ If infrastructure partially configured: Flag as "INCOMPLETE" and ask user for clarification
```

---

### Addition 2: Updated Decision Tree

**Location**: Same file, ORCHESTRATION_DECISION_TREE section

**Update the classification logic to include:**

```markdown
### UPDATED CLASSIFICATION → TRIGGER MAPPING

When user task involves ANY of these keywords:
- "setup" / "configure" / "deploy"
- "staging" / "beta" / "production"
- "supabase" / "vercel" / "railway" / "docker"
- "secrets" / "credentials" / "environment"
- "infrastructure" / "architecture"

**PRIMARY TRIGGER**: agent-deployment-monitor
**REASON**: Must audit all infrastructure BEFORE recommending changes

**agent-deployment-monitor MUST then**:
1. Run comprehensive infrastructure discovery (see Addition 1)
2. Route findings to project-historian for duplication analysis
3. Route findings to security-reviewer for credential safety check
4. Report all findings to user BEFORE proceeding with implementation
```

---

### Addition 3: Infrastructure Registry Template

**Location**: New section in agent-deployment-monitor.md

**Purpose**: Maintains authoritative record of all infrastructure

```markdown
### INFRASTRUCTURE REGISTRY (Maintained by agent-deployment-monitor)

**Last Updated**: [Auto-update on each deployment audit]

#### Services Currently Active

| Service | Type | Location | Status | Credentials | Last Verified |
|---------|------|----------|--------|-------------|----------------|
| Railway | Container | [URL] | Active | Railway secrets | 2025-11-02 |
| Supabase | Database | hmqmxmxkxqdrqpdmlgtn | Active | Railway secrets | 2025-11-02 |
| Vercel | Frontend | [Pending] | TBD | GitHub secrets | [TBD] |
| PostgreSQL | Database | Railway | Active | DATABASE_URL | 2025-11-02 |
| Redis | Cache | Railway | [TBD] | [TBD] | [TBD] |
| GitHub | Source | github.com/kylem/relay-ai | Active | GitHub secrets | 2025-11-02 |
| Docker | Container | [TBD] | [TBD] | [TBD] | [TBD] |

#### Credentials Storage Map

| Credential | Location | Owner | Rotated | Next Rotation |
|-----------|----------|-------|---------|----------------|
| RAILWAY_TOKEN | Railway env | kylem | [Date] | [Date + 90d] |
| SUPABASE_JWT_SECRET | Railway env | kylem | [Date] | [Date + 90d] |
| VERCEL_TOKEN | GitHub secrets | kylem | [TBD] | [TBD] |
| GITHUB_TOKEN | [TBD] | [TBD] | [TBD] | [TBD] |
| DATABASE_PUBLIC_URL | Railway env | kylem | [Never rotated] | Review needed |

#### Environment Map

```
BETA (Current):
  Frontend: relay-beta.vercel.app (Vercel)
  Backend: relay-production-f2a6.up.railway.app (Railway)
  Database: Supabase relay-staging (hmqmxmxkxqdrqpdmlgtn)

PRODUCTION (Future):
  Frontend: relay.ai (Vercel - TBD)
  Backend: api.relay.ai (Railway - TBD)
  Database: Supabase relay-production (TBD)
```
```

---

## Implementation Instructions for System Admin

### Step 1: Update agent-deployment-monitor.md

Add the following sections to `.claude/agents/agent-deployment-monitor.md`:

1. **New Trigger Rule #8**: Multi-Source Infrastructure Discovery (from Addition 1 above)
2. **Updated Decision Tree**: Add infrastructure discovery as PRIMARY TRIGGER (from Addition 2 above)
3. **Infrastructure Registry**: Add template for tracking services (from Addition 3 above)
4. **Commit message**: "feat: Add multi-source infrastructure discovery to orchestration protocol"

### Step 2: Add Infrastructure Audit Tool Documentation

Create new file: `.claude/INFRASTRUCTURE_AUDIT_CHECKLIST.md` with:
- Step-by-step commands for each service
- How to run without permissions errors
- Where credentials are stored
- What to do when infrastructure is found vs. not found

### Step 3: Update Project Historian Instructions

In `.claude/agents/project-historian.md`, add:

```markdown
### MULTI-SOURCE SEARCH REQUIREMENT

When searching for existing infrastructure/configuration:

**MUST search in:**
- ✅ Project files (.env, git, markdown, code)
- ✅ Git commit history
- ✅ Project documentation
- ✅ **NEW**: Ask agent-deployment-monitor to check Railway/Vercel/GitHub/Docker
- ✅ **NEW**: Ask user if unsure about external services

**BEFORE concluding**: "No existing infrastructure found"
- Always coordinate with agent-deployment-monitor
- Never recommend creating NEW infrastructure without confirming it doesn't exist externally
```

---

## What This Solves

### Before (Current Broken State)
```
User: "I need to set up Supabase"
  ↓
project-historian: "Searching project files..."
  ↓
project-historian: "No Supabase found. Recommend creating new."
  ↓
User: "But I already created it and stored credentials in Railway!"
  ↓
Wasted effort ❌
```

### After (Fixed State)
```
User: "I need to set up Supabase"
  ↓
agent-deployment-monitor: "Checking all infrastructure sources..."
  ↓
agent-deployment-monitor: "Found Supabase project (hmqmxmxkxqdrqpdmlgtn) in Railway secrets"
  ↓
agent-deployment-monitor: "Found database schema status: [checking...]"
  ↓
agent-deployment-monitor: "Use existing OR create new?"
  ↓
User: "Use existing"
  ↓
Seamless continuation ✅
```

---

## Services Covered

This update ensures checking:

✅ **Compute/Hosting**:
- Railway (API, background jobs, databases)
- Vercel (web app)
- Docker (local development)

✅ **Data/Storage**:
- Supabase (auth, database, file storage)
- PostgreSQL (via Railway or standalone)
- Redis (caching, sessions)

✅ **Source Control**:
- GitHub (repo, secrets, workflows)
- Git (commit history, branches)

✅ **Credentials**:
- Railway environment variables
- GitHub Secrets
- Vercel environment variables
- Local .env files

✅ **Infrastructure Definition**:
- docker-compose.yml
- vercel.json
- railway.json
- GitHub Actions workflows

✅ **Future Services** (scalable design):
- AWS / GCP / Azure (when added)
- CDN / Cloudflare (when added)
- Monitoring / DataDog / New Relic (when added)
- CI/CD tools beyond GitHub (when added)

---

## Testing the Fix

After system admin updates agent-deployment-monitor.md:

**Test 1: Existing Infrastructure Discovery**
```
User prompt: "Set up Supabase for beta deployment"
Expected: Agent-deployment-monitor finds hmqmxmxkxqdrqpdmlgtn
Result: ✅ or ❌
```

**Test 2: New Infrastructure Recommendation**
```
User prompt: "Set up Docker for local development"
Expected: Agent checks, finds no Docker, recommends setup
Result: ✅ or ❌
```

**Test 3: Multi-Service Audit**
```
User prompt: "Prepare for beta launch"
Expected: Agent audits Railway, Supabase, Vercel, GitHub, Git
Result: ✅ or ❌
```

---

## Future Enhancements (Post-Implementation)

Once this is working:

1. **Automated Infrastructure State Reporting**
   - Monthly audit of all services
   - Email report of infrastructure status
   - Credential rotation reminders

2. **Infrastructure Change Tracking**
   - Log all infrastructure changes
   - Audit trail of who configured what
   - Drift detection (if infrastructure changes outside of Claude)

3. **Credential Rotation Automation**
   - Alert when credentials are 60+ days old
   - Automated rotation prompts
   - Tracking of rotation history

4. **Disaster Recovery**
   - Document backup/restore procedures
   - Verify backups exist
   - Test recovery process quarterly

---

## Summary for System Admin

**What to add to agent-deployment-monitor.md**:

1. New trigger rule #8: Multi-Source Infrastructure Discovery
2. Updated decision tree to prioritize infrastructure audit
3. Infrastructure registry template
4. Detailed command checklist for each service

**Why**:
- Prevents recommending duplicate infrastructure
- Ensures all credential sources are discovered
- Maintains authoritative infrastructure record
- Scales to future services automatically

**Testing**:
- User: "Set up Supabase"
- Agent: "Found existing project hmqmxmxkxqdrqpdmlgtn in Railway"
- User: ✅ Problem solved

---

## Commit Message Template

```
feat: Add multi-source infrastructure discovery to agent-deployment-monitor

- Add new trigger rule #8: Infrastructure Discovery
- Checks Railway, GitHub, Supabase, Vercel, Docker, Git
- Runs BEFORE project-historian recommends new infrastructure
- Prevents duplicate setup recommendations

Resolves: Gap where project-historian missed Supabase in Railway secrets
Tested: Manual verification of infrastructure audit commands
Fixes: https://github.com/[repo]/issues/[issue-number]

Files:
- .claude/agents/agent-deployment-monitor.md (added sections 1-3)
- .claude/INFRASTRUCTURE_AUDIT_CHECKLIST.md (new file)
- .claude/agents/project-historian.md (updated multi-source guidance)
```

---

**Prepared by**: Claude Code
**For**: System Admin / Infrastructure Lead
**Implementation Time**: ~30 minutes
**Risk Level**: LOW (documentation only, no code changes)
**Testing Required**: YES (manual test of 3 scenarios above)
