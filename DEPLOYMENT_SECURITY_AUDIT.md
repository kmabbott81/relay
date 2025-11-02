# DEPLOYMENT AUTOMATION SECURITY AUDIT
## Relay AI - GitHub Actions & Bash Scripts Review

**Date:** 2025-11-02
**Scope:** `.github/workflows/deploy-full-stack.yml` and `scripts/deploy-all.sh`
**Overall Security Posture:** CAUTION - Multiple Medium/High Issues Found

---

## EXECUTIVE SUMMARY

The deployment automation contains several security vulnerabilities that should be addressed before production use. The most critical issues involve:

1. **Hardcoded production URLs** exposing infrastructure details
2. **Unsafe git operations** allowing uncommitted credentials to be committed
3. **Unverified npm package installations** creating supply chain attack surface
4. **Insufficient secrets masking** in logs and outputs
5. **Missing security headers validation** for HTTPS endpoints

**Approval Status:** NOT APPROVED - Issues must be resolved before production deployment

---

## CRITICAL ISSUES (Must Fix)

### 1. CRITICAL: Unsafe Auto-Commit Pattern Leaking Secrets
**Location:** `scripts/deploy-all.sh` lines 115-118
**Severity:** CRITICAL
**Category:** Secret Management / Credential Exposure

```bash
# CHECK GIT STATUS
if [ -n "$(git status --porcelain)" ]; then
    git add -A                                    # ← DANGER: Blindly adds ALL untracked files
    git commit -m "chore: auto-commit before Railway deployment" || true
fi
git push origin main
```

**Vulnerability Details:**
- `git add -A` commits ALL untracked files, including `.env`, credentials, and API keys
- If a developer has uncommitted `.env` files (even though `.gitignore` exists), they get committed to git history
- Once pushed to GitHub, these secrets are permanent in the repository history
- Even if deleted later, secrets remain in git history and can be recovered
- `.gitignore` prevents file staging normally, but `git add -A` overrides gitignore rules

**Attack Scenario:**
1. Developer leaves `.env` file with real secrets (not staged)
2. Script runs `deploy_railway` without checking git status carefully
3. `git add -A` stages `.env` file despite gitignore
4. Secrets are committed and pushed to GitHub
5. GitHub Advanced Security flags exposed credentials
6. Attacker clones repo and extracts tokens

**Recommended Fix:**
```bash
# Better approach: Only commit tracked changes
git diff --cached --quiet  # Check if changes staged
if [ -n "$(git diff --cached --name-only)" ]; then
    git commit -m "chore: deployment changes" || true
fi

# OR safer: Don't auto-commit at all
# Require explicit manual commit before deployment
if [ -n "$(git status --porcelain)" ]; then
    log_error "Uncommitted changes detected. Please commit manually:"
    git status
    exit 1
fi
```

---

### 2. HIGH: Hardcoded Production URLs Exposing Infrastructure
**Location:**
- `deploy-full-stack.yml` lines 47, 56, 126, 132, 139
- `deploy-all.sh` lines 20-21

**Severity:** HIGH
**Category:** Information Disclosure / Infrastructure Reconnaissance

```yaml
API_URL="https://relay-production-f2a6.up.railway.app"   # Hardcoded in workflow
curl -f https://relay-production-f2a6.up.railway.app/health  # Multiple locations
```

**Vulnerability Details:**
- Production infrastructure URLs embedded in source control
- These URLs are visible in GitHub (public repository assumptions)
- Railway deployment ID (`f2a6`) exposed and could be used for reconnaissance
- `relay-beta.vercel.app` and `relay-production` naming patterns leak environment details
- Attackers can enumerate these endpoints for vulnerabilities

**Information Disclosed:**
- Platform: Railway + Vercel (specific hosting infrastructure)
- Environment: Production vs Beta (staging URLs exposed)
- Service names: "relay-production", "knowledge", "health" endpoints
- Deployment tracking IDs

**Recommended Fix:**
```yaml
# Use environment variables for all URLs
env:
  API_URL: ${{ secrets.API_PROD_URL }}
  WEB_URL: ${{ secrets.WEB_PROD_URL }}

# Use repository variables (non-secret) for public URLs that change per environment
# OR reference from deployment configuration file not committed to main repo
```

---

### 3. HIGH: Unverified Global npm Package Installation
**Location:**
- `deploy-full-stack.yml` lines 36, 102
- `deploy-all.sh` lines 36, 56, 237-238

**Severity:** HIGH
**Category:** Supply Chain Risk / Dependency Injection

```bash
npm install -g @railway/cli    # Line 36 - No version pinning
npm install -g vercel           # Line 102 - No version pinning
npm install -g @railway/cli vercel  # deploy-all.sh line 237
```

**Vulnerability Details:**
- Global npm package installs without version pinning
- No integrity checking (no `--prefer-offline --no-audit` or pinned versions)
- Vulnerable to npm registry hijacking attacks
- If attacker compromises npm package, malicious code runs with deployment credentials
- No verification of package signatures or checksums

**Attack Scenario:**
1. Attacker publishes malicious version of `@railway/cli` (e.g., version 5.9.1)
2. GitHub Actions installs latest version without pinning
3. Malicious package reads `RAILWAY_TOKEN` from environment
4. Exfiltrates credentials to attacker-controlled server
5. Attacker gains access to all Railway deployments

**Recommended Fix:**
```bash
# Pin specific versions
npm install -g @railway/cli@5.8.1 vercel@35.2.0

# Or use npm ci (clean install) with package-lock.json
npm ci -g @railway/cli vercel

# Or use Docker image with pre-installed tools (safer)
docker run -e RAILWAY_TOKEN=... railway-cli:5.8.1 railway up
```

---

## HIGH PRIORITY ISSUES (Should Fix Before Production)

### 4. HIGH: Secrets Potentially Exposed in GitHub Actions Logs
**Location:** `deploy-full-stack.yml` lines 48-51
**Severity:** HIGH
**Category:** Secret Leakage / Log Exposure

```yaml
echo "Deployed API with ID: $DEPLOYMENT_ID"
echo "API URL: $API_URL"
```

**Vulnerability Details:**
- `$DEPLOYMENT_ID` could contain sensitive information from Railway API response
- GitHub Actions logs are visible to anyone with repository read access
- While `RAILWAY_TOKEN` has built-in masking, custom outputs may not be masked
- Deployment IDs could be used for reconnaissance or targeted attacks

**Recommended Fix:**
```yaml
# Use ::add-mask:: to mask sensitive values
echo "::add-mask::$DEPLOYMENT_ID"
echo "deployment_id=$DEPLOYMENT_ID" >> $GITHUB_OUTPUT

# OR limit what's printed
echo "✓ Deployment completed" >> $GITHUB_OUTPUT
# Don't echo sensitive deployment IDs to logs
```

---

### 5. HIGH: Missing Error Handling and Output Validation
**Location:**
- `deploy-full-stack.yml` lines 46, 104-105
- `deploy-all.sh` lines 115-118

**Severity:** HIGH
**Category:** Security Misconfiguration / Failure Analysis

```bash
# No validation of jq output
DEPLOYMENT_ID=$(railway status --json 2>/dev/null | jq -r '.latestDeployment.id // "unknown"')

# If jq fails, DEPLOYMENT_ID becomes "unknown"
# If railway is not authenticated, this silently succeeds
```

**Vulnerability Details:**
- `2>/dev/null` silently discards errors
- No verification that `railway status` succeeded
- Falling back to "unknown" masks deployment failures
- Script could "succeed" even if Railway deployment failed
- Hard to debug actual deployment issues

**Recommended Fix:**
```bash
# Validate commands succeed
DEPLOYMENT_ID=$(railway status --json)
if [ $? -ne 0 ]; then
    log_error "railway status failed"
    exit 1
fi
DEPLOYMENT_ID=$(echo "$DEPLOYMENT_ID" | jq -r '.latestDeployment.id')
if [ -z "$DEPLOYMENT_ID" ] || [ "$DEPLOYMENT_ID" = "null" ]; then
    log_error "No deployment ID found in Railway response"
    exit 1
fi
```

---

### 6. HIGH: Missing HTTPS Certificate Validation
**Location:** Multiple `curl` commands
**Severity:** HIGH
**Category:** Man-in-the-Middle (MITM) Attack Surface

```bash
curl -f https://relay-production-f2a6.up.railway.app/health
curl -f https://relay-production-f2a6.up.railway.app/api/v1/knowledge/health
curl -f https://relay-beta.vercel.app/beta
```

**Current State:** These should be fine with `-f` flag, BUT:
- `-f` only checks HTTP status, not certificate validity
- No explicit `--cacert` or certificate pinning
- Vulnerable to proxy/firewall MITM attacks
- No mutual TLS (mTLS) verification

**Recommended Fix:**
```bash
# Add certificate verification (already done by default, but explicit is better)
curl -f --cacert /etc/ssl/certs/ca-certificates.crt https://relay-production-f2a6.up.railway.app/health

# OR use --cert-status for OCSP validation
curl -f --cert-status https://relay-production-f2a6.up.railway.app/health
```

---

## MEDIUM PRIORITY ISSUES (Should Fix)

### 7. MEDIUM: Missing Rollback Strategy on Deployment Failure
**Location:** `deploy-full-stack.yml` lines 53-64
**Severity:** MEDIUM
**Category:** Operational Security / Incident Response

**Vulnerability Details:**
- Health check waits 30 attempts (2.5 minutes)
- No rollback if API fails health checks
- No notification to security team if deployment fails
- Failed deployments leave system in inconsistent state
- No automated incident response

**Recommended Fix:**
```yaml
- name: Rollback on health check failure
  if: failure()
  run: |
    echo "Health check failed - triggering rollback"
    railway rollback --environment production
    # Send alert
    curl -X POST ${{ secrets.SLACK_WEBHOOK }} -d '{"text":"Deployment failed - rolled back"}'
```

---

### 8. MEDIUM: Database Migration Timing Issues
**Location:** `deploy-full-stack.yml` lines 66-72
**Severity:** MEDIUM
**Category:** Data Integrity / Race Conditions

```yaml
- name: Run database migrations
  env:
    DATABASE_URL: ${{ secrets.DATABASE_PUBLIC_URL }}
  run: |
    pip install alembic
    alembic upgrade head
```

**Vulnerability Details:**
- Migrations run AFTER API deployment
- New API code running while database schema is outdated
- No down-time window, data migration could fail
- `DATABASE_PUBLIC_URL` - "public" suffix suggests insecure exposure
- No backup before migration

**Recommended Fix:**
```yaml
# Run migrations BEFORE API deployment
# Use private database URL (not public)
# Add backup step
- name: Backup database
  run: |
    pg_dump ${{ secrets.DATABASE_PRIVATE_URL }} > backup.sql

- name: Run migrations
  run: alembic upgrade head
```

---

### 9. MEDIUM: No Verification of Deployment Identity
**Location:** `deploy-all.sh` lines 43-44
**Severity:** MEDIUM
**Category:** Authentication / Access Control

```bash
railway link  # Links to project but no verification shown
railway up --detach  # Deploys but doesn't verify to correct environment
```

**Vulnerability Details:**
- `railway link` could silently link to wrong project
- No verification that correct project is targeted
- No confirmation before pushing to production
- Attacker could redirect deployment to their own Railway project
- `--detach` runs in background with no visibility

**Recommended Fix:**
```bash
# Verify project identity
PROJECT_ID=$(railway project --json | jq -r '.id')
if [ "$PROJECT_ID" != "$EXPECTED_PROJECT_ID" ]; then
    log_error "Wrong Railway project: $PROJECT_ID"
    exit 1
fi

# Require explicit confirmation for production
if [ "$DEPLOY_MODE" == "railway" ]; then
    read -p "Deploy to production? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        exit 0
    fi
fi
```

---

### 10. MEDIUM: Insufficient Access Control on Deployment Scripts
**Location:** File permissions - `scripts/deploy-all.sh`
**Severity:** MEDIUM
**Category:** Privilege Escalation / Unauthorized Access

**Vulnerability Details:**
- Deploy script can be executed by any user with repository access
- No role-based access control (RBAC) for who can deploy
- No audit trail of who triggered deployments
- Script uses shared credentials (tokens in environment)
- No separation of duties between staging/production

**Recommended Fix:**
```bash
# Add RBAC check
ALLOWED_USERS="deploy-bot,kyle"
if ! echo "$ALLOWED_USERS" | grep -q "$USER"; then
    log_error "User $USER not authorized to deploy"
    exit 1
fi

# Use GitHub branch protection rules
# Require approval for production deployments
# Enable deployment branches restriction
```

---

## VULNERABILITY SUMMARY TABLE

| Issue | Severity | Type | File | Line(s) | Remediable |
|-------|----------|------|------|---------|-----------|
| Auto-commit leaks secrets | CRITICAL | Secrets Management | deploy-all.sh | 117-118 | Yes |
| Hardcoded URLs | HIGH | Information Disclosure | deploy-full-stack.yml | 47, 56, 126, 132, 139 | Yes |
| Unverified npm installs | HIGH | Supply Chain | deploy-full-stack.yml, deploy-all.sh | 36, 102, 237-238 | Yes |
| Secrets in logs | HIGH | Secret Leakage | deploy-full-stack.yml | 48-51 | Yes |
| Missing error handling | HIGH | Misconfiguration | deploy-full-stack.yml, deploy-all.sh | 46, 104-105 | Yes |
| Missing cert validation | HIGH | MITM Risk | Multiple curl commands | Various | Minor |
| No rollback strategy | MEDIUM | Operational | deploy-full-stack.yml | 53-64 | Yes |
| Migration timing | MEDIUM | Data Integrity | deploy-full-stack.yml | 66-72 | Yes |
| No identity verification | MEDIUM | Authentication | deploy-all.sh | 43-44 | Yes |
| No RBAC enforcement | MEDIUM | Access Control | deploy-all.sh | Various | Yes |

---

## POSITIVE SECURITY FINDINGS

### What's Working Well

1. **Secrets handled via GitHub Secrets** - `${{ secrets.RAILWAY_TOKEN }}` properly uses GitHub's encrypted secrets storage (not hardcoded)
2. **`.gitignore` configured** - `.env`, `*.key`, `*_credentials` properly excluded
3. **Health checks implemented** - API and web app health verification before considering deployment "done"
4. **Multi-stage deployment** - API deploys first, then web app, then smoke tests (proper sequencing)
5. **Shell safety** - `set -e` prevents script continuation on errors
6. **Environment separation** - Staging vs production URLs are separated
7. **Logging for debugging** - Color-coded output for troubleshooting
8. **Docker multi-stage build** - Reduces image size and excludes build tools from production image

---

## RECOMMENDATIONS

### Immediate (Before Next Deployment)

1. **Remove auto-commit pattern** - Require manual git operations
2. **Move hardcoded URLs to secrets** - Use GitHub Secrets for all infrastructure endpoints
3. **Pin npm package versions** - Specify exact versions for supply chain safety
4. **Add secret masking** - Use `::add-mask::` for sensitive deployment IDs
5. **Rename database secrets** - Change `DATABASE_PUBLIC_URL` to `DATABASE_PRIVATE_URL`

### Short-term (Sprint)

6. Implement deployment approval workflow (GitHub environment protection)
7. Add rollback mechanism on health check failure
8. Implement RBAC checks in deployment scripts
9. Add audit logging for all deployments
10. Create incident response playbook for failed deployments

### Long-term (Strategic)

11. Migrate to Infrastructure-as-Code (Terraform) with policy enforcement
12. Implement secrets rotation policy (every 90 days)
13. Deploy SIEM for deployment activity monitoring
14. Establish branch protection rules with required reviews
15. Implement deployment approval by security team for production

---

## COMPLIANCE NOTES

**GDPR:** No PII handling in deployment scripts - COMPLIANT
**PCI-DSS:** Database credentials not hard-coded - PARTIAL COMPLIANCE (needs secrets rotation)
**SOC 2:** Missing audit trail for deployment actions - NON-COMPLIANT

---

## APPROVAL DECISION

**STATUS: NOT APPROVED FOR PRODUCTION**

**Required Actions Before Approval:**
- [ ] Fix CRITICAL: Remove auto-commit pattern (deploy-all.sh)
- [ ] Fix HIGH: Externalize hardcoded URLs to secrets
- [ ] Fix HIGH: Pin npm package versions with checksums
- [ ] Fix HIGH: Add secret masking for deployment outputs
- [ ] Fix HIGH: Implement rollback strategy
- [ ] Security review of remediated code

**Approved By:** [PENDING]
**Date Approved:** [PENDING]
**Reviewer:** Security Team

---

## REFERENCES

- OWASP: https://owasp.org/Top10/
- GitHub Actions Security: https://docs.github.com/en/actions/security-guides
- Supply Chain Security: https://slsa.dev/
- Secret Management Best Practices: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
