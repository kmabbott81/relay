# Credential Rotation & Remediation Plan
**Status**: URGENT - EXECUTE IMMEDIATELY | **Date**: 2025-11-15 | **Severity**: CRITICAL

---

## Overview

This document provides step-by-step instructions to remediate the critical security issue identified in the repository audit: exposed credentials in local `.env` file.

**Time Estimate**: 1-2 hours | **Risk Level**: HIGH (credentials actively exposed)

---

## Exposed Credentials (MUST ROTATE IMMEDIATELY)

| Service | Type | Location | Status |
|---------|------|----------|--------|
| **OpenAI** | API Key | `.env` - OPENAI_API_KEY | EXPOSED - ROTATE NOW |
| **Anthropic** | API Key | `.env` - ANTHROPIC_API_KEY | EXPOSED - ROTATE NOW |
| **PostgreSQL** | Database | `.env` - DATABASE_URL | EXPOSED - RESET NOW |
| **Google** | API Key | `.env.example` - GOOGLE_API_KEY | Placeholder (OK) |
| **AWS** | Credentials | `.env.example` - AWS_* | Placeholder (OK) |

---

## Step 1: Immediate Containment (5 minutes)

### 1.1 Verify Credentials in .env
```bash
# Check what credentials are currently in .env
cat ".env" | grep -E "OPENAI|ANTHROPIC|DATABASE_URL"
```

### 1.2 Create Backup (Before Deletion)
```bash
# Save a copy for reference during rotation
cp .env .env.backup.2025-11-15
# Mark as sensitive
# DO NOT commit this file
```

### 1.3 Audit Recent API Usage
```bash
# Check OpenAI API usage logs at: https://platform.openai.com/account/billing/overview
# Check Anthropic API usage at: https://console.anthropic.com/account/usage
# Look for suspicious activity in the past 24 hours
# Note: Replace API keys first, then investigate anomalies
```

---

## Step 2: Rotate OpenAI API Key (10 minutes)

### 2.1 Generate New OpenAI API Key
1. Go to: https://platform.openai.com/account/api-keys
2. Click "Create new secret key"
3. Copy the new key (you won't be able to see it again)
4. **Save temporarily**: Write to `.env.new` or secure note

### 2.2 Update in GitHub Secrets
1. Go to: https://github.com/YOUR_REPO_OWNER/YOUR_REPO_NAME/settings/secrets/actions
2. Click "New repository secret"
3. **Name**: `OPENAI_API_KEY`
4. **Value**: Paste the new API key
5. Click "Add secret"

### 2.3 Invalidate Old Key
1. Return to: https://platform.openai.com/account/api-keys
2. Find the old key (starting with `sk-proj-SU63rUTIzWYWATWNORy470xikejKFc_`)
3. Click delete icon next to it
4. Confirm deletion

### 2.4 Verify New Key Works
```bash
# Test with a simple API call
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_NEW_KEY" \
  -H "User-Agent: OpenAI-Curl-CLI"
```

---

## Step 3: Rotate Anthropic API Key (10 minutes)

### 3.1 Generate New Anthropic API Key
1. Go to: https://console.anthropic.com/account/keys
2. Click "Create Key"
3. Copy the new key
4. **Save temporarily**: Write to `.env.new` or secure note

### 3.2 Update in GitHub Secrets
1. Go to: https://github.com/YOUR_REPO_OWNER/YOUR_REPO_NAME/settings/secrets/actions
2. Click "New repository secret"
3. **Name**: `ANTHROPIC_API_KEY`
4. **Value**: Paste the new API key
5. Click "Add secret"

### 3.3 Invalidate Old Key
1. Return to: https://console.anthropic.com/account/keys
2. Find the old key (starting with `sk-ant-api03--94_Q5OOqmdlRcxzB16mn8E-`)
3. Click delete/revoke
4. Confirm deletion

### 3.4 Verify New Key Works
```bash
# Test with a simple API call (requires curl + JSON)
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: YOUR_NEW_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model": "claude-3-sonnet-20240229", "max_tokens": 10, "messages": [{"role": "user", "content": "test"}]}'
```

---

## Step 4: Reset PostgreSQL Credentials (15 minutes)

### 4.1 Identify PostgreSQL Connection Details

From current `.env`:
```
DATABASE_URL=postgresql://postgres:dw33GA0E7c%21E8%21imSJJW%5Exrz@switchyard.proxy.rlwy.net:39963/railway
```

Decoded components:
- **User**: postgres
- **Password**: dw33GA0E7c!E8!imSJJW^xrz (URL-encoded)
- **Host**: switchyard.proxy.rlwy.net
- **Port**: 39963
- **Database**: railway

### 4.2 Connect to Reset Password

**Option A: Via Railway Dashboard** (Recommended)
1. Go to: https://railway.app/project
2. Select the project with the exposed database
3. Go to: PostgreSQL plugin settings
4. Click "Reset password"
5. Railway will generate a new password
6. Copy the new connection string

**Option B: Via psql Command** (If you have local access)
```bash
# Connect with current credentials
PGPASSWORD="dw33GA0E7c!E8!imSJJW^xrz" psql \
  -h switchyard.proxy.rlwy.net \
  -p 39963 \
  -U postgres \
  -d railway

# In psql prompt, reset password
ALTER USER postgres WITH PASSWORD 'NEW_STRONG_PASSWORD_HERE';
\q
```

### 4.3 Update in GitHub Secrets
1. Go to: https://github.com/YOUR_REPO_OWNER/YOUR_REPO_NAME/settings/secrets/actions
2. Click "New repository secret"
3. **Name**: `DATABASE_URL`
4. **Value**: `postgresql://postgres:NEW_PASSWORD@switchyard.proxy.rlwy.net:39963/railway`
5. Click "Add secret"

### 4.4 Update in Railway Environment Variables
1. Go to: https://railway.app/project/YOUR_PROJECT
2. Go to Environment tab
3. Set: `DATABASE_URL` with new connection string
4. Deploy

### 4.5 Verify Connection
```bash
# Test new connection (if psql installed)
psql "postgresql://postgres:NEW_PASSWORD@switchyard.proxy.rlwy.net:39963/railway" -c "SELECT version();"
```

---

## Step 5: Clean Local .env File (5 minutes)

### 5.1 Create Clean .env from .env.example
```bash
# Copy the template
cp ".env.example" ".env"

# The file should now contain only placeholders:
# RELAY_STAGE=beta
# OPENAI_API_KEY=PASTE-YOUR-KEY-HERE
# etc.
```

### 5.2 Verify No Real Credentials
```bash
# Verify no real keys remain
cat ".env" | grep -E "sk-proj|sk-ant|@switchyard"
# Should return nothing

# Double-check backup file is safely stored
ls -l ".env.backup.2025-11-15"
```

### 5.3 Secure the Backup
```bash
# IMPORTANT: Backup file contains old credentials
# Either:
# 1. Delete it completely
rm ".env.backup.2025-11-15"

# OR 2. Encrypt it and store securely
# gpg -c .env.backup.2025-11-15
# rm .env.backup.2025-11-15
# Store .env.backup.2025-11-15.gpg in secure location
```

### 5.4 Verify .env is in .gitignore
```bash
# Check that .env is protected
grep -E "^\.env$" ".gitignore"
# Should output: .env

# If not present, add it
echo ".env" >> ".gitignore"
```

---

## Step 6: Update CI/CD Workflows (10 minutes)

### 6.1 Verify GitHub Actions Use Secrets
Check your workflow files for:
- `.github/workflows/ci.yml`
- `.github/workflows/deploy-beta.yml`
- `.github/workflows/deploy-prod.yml`

They should reference secrets like:
```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

NOT:
```yaml
# WRONG - Don't do this
env:
  OPENAI_API_KEY: sk-proj-... # NEVER hardcode
```

### 6.2 Update Railway Environment Variables
1. Go to: https://railway.app/project/YOUR_PROJECT
2. For each service (API, Web, Worker):
   - Set `OPENAI_API_KEY` to secret reference (or paste new key)
   - Set `ANTHROPIC_API_KEY` to secret reference (or paste new key)
   - Set `DATABASE_URL` to new connection string
3. Deploy each service

---

## Step 7: Audit & Verification (15 minutes)

### 7.1 Verify No Credentials in Git History
```bash
# Search for old API key patterns in git history
git log -p --all -S "sk-proj-SU63rUTIzWYWATWNORy470xikejKFc" -- . 2>/dev/null | wc -l
# Should return: 0

git log -p --all -S "sk-ant-api03--94_Q5OOqmdlRcxzB16mn8E" -- . 2>/dev/null | wc -l
# Should return: 0

git log -p --all -S "dw33GA0E7c%21E8%21imSJJW%5Exrz" -- . 2>/dev/null | wc -l
# Should return: 0
```

### 7.2 Install git-secrets (Future Prevention)
```bash
# Install git-secrets tool
# On macOS:
brew install git-secrets

# On Linux:
git clone https://github.com/awslabs/git-secrets.git
cd git-secrets
make install

# Configure for this repo
cd /path/to/repo
git secrets --install
git secrets --register-aws

# Add custom pattern for API keys
git secrets --add 'sk-proj-[A-Za-z0-9_-]{30,}'
git secrets --add 'sk-ant-[a-zA-Z0-9_-]{30,}'

# Scan existing repo (optional)
git secrets --scan
```

### 7.3 Check API Usage Logs
1. **OpenAI**: https://platform.openai.com/account/billing/overview
   - Look for usage spikes after rotation
   - Note any unusual requests
2. **Anthropic**: https://console.anthropic.com/account/usage
   - Check for unexpected usage
3. **PostgreSQL**: Check Railway logs for connection attempts
   - Look for failed auth after password reset

### 7.4 Verify Deployment Still Works
```bash
# Push a test commit to trigger CI/CD
git commit --allow-empty -m "test: verify credentials rotation"
git push origin main

# Monitor GitHub Actions: https://github.com/YOUR_REPO/actions
# Verify CI/CD pipeline passes with new credentials
```

---

## Step 8: Documentation & Handoff (5 minutes)

### 8.1 Update README
Add credentials section to your `README.md`:
```markdown
## Security: Local Development

Never commit `.env` with real credentials:
- `.env` is gitignored and contains local secrets only
- Real credentials are in GitHub Secrets and Railway environment
- Use `.env.example` as a template for local setup

### Setting up Local Development
1. Copy `.env.example` to `.env`
2. Get API keys from GitHub Actions variables (for CI) or create new test keys
3. Never commit `.env` - it's only for local testing
```

### 8.2 Document Rotation Procedure
Create a file: `docs/CREDENTIAL_ROTATION.md`
```markdown
# Credential Rotation Procedure

This process should be followed every 90 days or immediately if leaked.

See: CREDENTIAL_ROTATION_PLAN.md (in repo root) for complete steps
```

### 8.3 Set Calendar Reminders
- Quarterly: OpenAI API key rotation
- Quarterly: Anthropic API key rotation
- Quarterly: Database password rotation
- Monthly: Audit git history for credential patterns

---

## Step 9: Recovery Checklist

Before considering remediation complete, verify:

### Pre-Remediation
- [ ] Identified all exposed credentials (3 found)
- [ ] Backed up .env to secure location
- [ ] Checked API usage logs for anomalies
- [ ] Noted any suspicious activity for investigation

### Rotation Complete
- [ ] OpenAI API key rotated ✓
- [ ] Anthropic API key rotated ✓
- [ ] PostgreSQL password reset ✓
- [ ] GitHub Secrets updated with new values
- [ ] Railway environment variables updated
- [ ] Old credentials invalidated/deleted
- [ ] New credentials tested and verified working

### Local Cleanup
- [ ] Local .env contains only placeholders
- [ ] Old .env.backup either deleted or encrypted
- [ ] .env in .gitignore confirmed
- [ ] No remaining credentials in local directory

### Verification
- [ ] git log scan finds no old credential patterns
- [ ] GitHub Actions tests pass with new credentials
- [ ] Railway deployments successful
- [ ] API calls working with new keys
- [ ] Database connections working with new password

### Future Prevention
- [ ] git-secrets installed and configured
- [ ] Pre-commit hooks enabled
- [ ] Team trained on secret management
- [ ] Rotation schedule documented
- [ ] Calendar reminders set (90-day cycle)

---

## Troubleshooting

### GitHub Secrets Not Working in CI
**Problem**: Pipeline fails even after setting GitHub Secrets
**Solution**:
1. Verify secret name matches exactly in workflow file
2. Redeploy/re-run workflow
3. Check workflow syntax: `${{ secrets.SECRET_NAME }}`
4. Clear GitHub Actions cache if using

### PostgreSQL Connection Still Fails
**Problem**: New password not working
**Solution**:
1. Verify Railway confirmed password reset
2. Check connection string format (URL encoding)
3. Test with new password directly via psql
4. Check for network/firewall issues to switchyard.proxy.rlwy.net
5. Contact Railway support if reset failed

### API Keys Not Working in Local Testing
**Problem**: New keys not accepting requests
**Solution**:
1. Wait 30 seconds for propagation
2. Test API key directly in provider's dashboard
3. Check API endpoint URL is correct
4. Verify key has correct permissions/scopes
5. Check rate limiting hasn't been triggered

### git-secrets Already Committed Old Credentials
**Problem**: Old credentials in git history before git-secrets installed
**Solution**:
1. This is a more complex issue (BFG Repo-Cleaner)
2. Contact security team for git history remediation
3. This may require force-push and coordination

---

## Post-Remediation Audit

After completing all steps, re-run security audit:

```bash
# Run the comprehensive audit (after credentials rotated)
# This will verify:
# - No credentials in .env
# - No credentials in git history
# - GitHub Secrets configured
# - Deployments working with new credentials
```

Expected result: [APPROVED] ✓

---

## Contact & Escalation

If any step fails:
1. **OpenAI Issues**: Support@openai.com or https://help.openai.com
2. **Anthropic Issues**: support@anthropic.com
3. **Railway Issues**: https://railway.app/support
4. **GitHub Issues**: https://github.community
5. **Security Team**: [Your security contact]

---

## Timeline Summary

| Step | Task | Est. Time | Status |
|------|------|-----------|--------|
| 1 | Containment | 5 min | TODO |
| 2 | OpenAI rotation | 10 min | TODO |
| 3 | Anthropic rotation | 10 min | TODO |
| 4 | PostgreSQL reset | 15 min | TODO |
| 5 | Clean .env | 5 min | TODO |
| 6 | Update CI/CD | 10 min | TODO |
| 7 | Audit & verify | 15 min | TODO |
| 8 | Documentation | 5 min | TODO |
| 9 | Final verification | 5 min | TODO |
| | **TOTAL** | **80 min** | PENDING |

---

**EXECUTE THIS PLAN IMMEDIATELY TO RESOLVE CRITICAL SECURITY ISSUE**

Generated: 2025-11-15 by Relay Deployment Gatekeeper (Claude Code)
