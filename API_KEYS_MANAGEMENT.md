# API Keys Management Guide - Complete Reference

**Purpose**: Centralized guide for managing all API credentials across Relay

---

## Current API Integrations

### 🔴 EXPOSED - MUST ROTATE NOW
These were exposed and require immediate rotation:

| API | Service | Status | Action |
|-----|---------|--------|--------|
| OpenAI | AI/GPT | ✗ EXPOSED | Rotate immediately |
| Anthropic | Claude AI | ✗ EXPOSED | Rotate immediately |
| PostgreSQL | Database | ✗ EXPOSED | Reset password immediately |

**Estimated rotation time**: ~15 minutes with automation

---

### 🟢 OPTIONAL - SET UP WHEN READY
These are not currently exposed, but available for setup:

| API | Service | Purpose | Status | Setup Time |
|-----|---------|---------|--------|------------|
| Google OAuth | Authentication | Sign-in with Google | Not set up | ~10 min |
| Microsoft OAuth | Authentication | Sign-in with Microsoft/Office 365 | Not set up | ~10 min |
| Slack | Integrations | Send messages, read channels | Not set up | ~10 min |
| Notion | Integrations | Read/write Notion databases | Not set up | ~10 min |
| Gmail | Integrations | Send emails, read inbox | OAuth (via Google) | Included |
| SMTP | Email | Generic email sending | Not set up | ~5 min |
| Azure/AWS S3 | Cloud Storage | File uploads/downloads | Not set up | ~15 min |

---

## Where to Store API Keys (Secure Approach)

### Option 1: GitHub Secrets + Railway Environment (RECOMMENDED)

**Workflow**:
1. Generate new key on provider dashboard
2. Store in GitHub Secrets (encrypted by GitHub)
3. Reference in CI/CD workflows as `${{ secrets.SECRET_NAME }}`
4. Also store in Railway environment variables for runtime access

**Advantages**:
- ✅ Encrypted by default
- ✅ Audit trail of who accessed
- ✅ Automatic secret scanning (prevents leaks)
- ✅ Scoped by environment (different keys for beta/prod)
- ✅ No local .env storage needed

**How to use**:
```bash
# GitHub Secrets (accessed via CLI or web)
gh secret set OPENAI_API_KEY --body "sk-proj-..."

# GitHub Actions uses:
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

# Railway environment variables (for runtime)
railway variable set OPENAI_API_KEY "sk-proj-..."
```

---

### Option 2: Local Development Only (.env)

**Workflow**:
1. Keep `.env` locally for development
2. NEVER commit to git (protected by .gitignore)
3. Use GitHub Secrets for CI/CD and production

**Advantages**:
- ✅ Works offline for local testing
- ✅ Simple to update during development

**Disadvantages**:
- ❌ Risk if someone forgets .gitignore
- ❌ No audit trail
- ❌ Team sharing is difficult

**How to use**:
```bash
# Local development only
OPENAI_API_KEY=sk-proj-... (in .env, never committed)

# Your Python/Node code reads:
api_key = os.getenv("OPENAI_API_KEY")
```

---

### Option 3: Enterprise Secret Management (Future)

When you scale to production:
- **AWS Secrets Manager**
- **HashiCorp Vault**
- **1Password Vault** (team shared)

---

## Complete API Keys Configuration

### 1. OpenAI API

**Setup**:
1. Go to: https://platform.openai.com/account/api-keys
2. Create new secret key
3. Copy key (format: `sk-proj-...`)
4. Store in GitHub Secrets: `OPENAI_API_KEY`
5. Store in Railway: `OPENAI_API_KEY`

**Configuration in .env.example**:
```env
OPENAI_API_KEY=                     # Add your key here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
OPENAI_MAX_TOKENS=2000
OPENAI_TEMPERATURE=0.7
```

**Current Exposed Key**:
- Format: `sk-proj-SU63rUTIzWYWATWNORy470xikejKFc_...`
- **Status**: MUST DELETE from OpenAI dashboard after rotation

---

### 2. Anthropic API

**Setup**:
1. Go to: https://console.anthropic.com/account/keys
2. Create new key
3. Copy key (format: `sk-ant-...`)
4. Store in GitHub Secrets: `ANTHROPIC_API_KEY`
5. Store in Railway: `ANTHROPIC_API_KEY`

**Configuration in .env.example**:
```env
ANTHROPIC_API_KEY=                  # Add your key here
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

**Current Exposed Key**:
- Format: `sk-ant-api03--94_Q5OOqmdlRcxzB16mn8E-...`
- **Status**: MUST DELETE from Anthropic dashboard after rotation

---

### 3. Database Credentials

**PostgreSQL Connection**:
```env
DATABASE_URL=postgresql://user:password@host:port/database
```

**Current Exposed Connection**:
- Format: `postgresql://postgres:dw33GA0E7c%21E8%21imSJJW%5Exrz@switchyard.proxy.rlwy.net:39963/railway`
- **Status**: MUST RESET password in Railway after rotation

---

### 4. Google OAuth (Optional)

**Setup**:
1. Go to: https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client ID
3. Set redirect URI to: `YOUR_DOMAIN/auth/callback/google`
4. Copy Client ID and Client Secret

**Configuration in .env**:
```env
GOOGLE_CLIENT_ID=                   # Your client ID
GOOGLE_CLIENT_SECRET=               # Your client secret
GOOGLE_REFRESH_TOKEN=               # Generated after first auth
PROVIDER_GOOGLE_ENABLED=false       # Set to true when ready
```

**Keys needed**:
- GitHub Secrets: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Railway: Same as above
- Refresh token: Generated automatically

---

### 5. Microsoft OAuth (Optional)

**Setup**:
1. Go to: https://portal.azure.com/#blade/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/RegisteredApps
2. Create new app registration
3. Copy Client ID
4. Create client secret (copy immediately)
5. Set redirect URI to: `YOUR_DOMAIN/auth/callback/microsoft`

**Configuration in .env**:
```env
MS_CLIENT_ID=                       # Your app ID
MS_CLIENT_SECRET=                   # Your app secret
MS_TENANT_ID=common                 # or specific tenant ID
PROVIDER_MICROSOFT_ENABLED=false    # Set to true when ready
```

**Keys needed**:
- GitHub Secrets: `MS_CLIENT_ID`, `MS_CLIENT_SECRET`
- Railway: Same as above

---

### 6. Slack API (Optional)

**Setup**:
1. Go to: https://api.slack.com/apps
2. Create new app
3. Create bot token
4. Copy Bot Token (format: `xoxb-...`)

**Configuration in .env**:
```env
SLACK_BOT_TOKEN=                    # Your bot token
SLACK_DEFAULT_CHANNEL_ID=           # Default channel for messages
```

**Keys needed**:
- GitHub Secrets: `SLACK_BOT_TOKEN`
- Railway: Same

---

### 7. Notion API (Optional)

**Setup**:
1. Go to: https://www.notion.so/my-integrations
2. Create new integration
3. Copy Internal Integration Token

**Configuration in .env**:
```env
NOTION_API_TOKEN=                   # Your integration token
NOTION_API_BASE=https://api.notion.com/v1
NOTION_VERSION=2022-06-28
```

**Keys needed**:
- GitHub Secrets: `NOTION_API_TOKEN`
- Railway: Same

---

### 8. Other Optional APIs

**SMTP** (Email):
```env
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
```

**AWS S3** (Cloud Storage):
```env
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
```

**Webhook Integration**:
```env
WEBHOOK_URL=https://webhook.site/your-test-id
```

---

## Current Status: Exposed Credentials

### EXPOSED NOW (In Local .env)
```
✗ OPENAI_API_KEY=sk-proj-SU63rUTIzWYWATWNORy470xikejKFc_...
✗ ANTHROPIC_API_KEY=sk-ant-api03--94_Q5OOqmdlRcxzB16mn8E_...
✗ DATABASE_URL=postgresql://postgres:dw33GA0E7c%21E8%21imSJJW%5Exrz@switchyard.proxy.rlwy.net:39963/railway
```

### NOT EXPOSED (Already not in local .env)
```
✓ GOOGLE_CLIENT_ID - Not set
✓ GOOGLE_CLIENT_SECRET - Not set
✓ MS_CLIENT_ID - Not set
✓ MS_CLIENT_SECRET - Not set
✓ SLACK_BOT_TOKEN - Not set
✓ NOTION_API_TOKEN - Not set
```

---

## Secure Storage Recommendations

### Immediate (Today)
- ✅ Rotate OpenAI, Anthropic, PostgreSQL (exposed)
- ✅ Store in GitHub Secrets + Railway
- ✅ Delete old credentials from provider dashboards

### Development
- ✅ Use .env locally (NEVER committed)
- ✅ Copy from GitHub Secrets when needed
- ✅ Or regenerate test keys for local testing

### Production
- ✅ All secrets in GitHub Secrets
- ✅ All secrets in Railway environment
- ✅ Rotate every 90 days
- ✅ Use AWS Secrets Manager for enterprise

---

## How to Add New API

When adding a new API (e.g., Notion, Slack, etc.):

1. **Get the key** from provider dashboard
2. **Store securely**:
   ```bash
   # In GitHub Secrets
   gh secret set MY_NEW_API_KEY --body "actual_key_value"

   # In Railway
   railway variable set MY_NEW_API_KEY "actual_key_value"

   # Locally (development only)
   echo "MY_NEW_API_KEY=actual_key_value" >> .env
   ```
3. **Reference in code**:
   ```python
   key = os.getenv("MY_NEW_API_KEY")
   ```
4. **Update .env.example** (without real values):
   ```env
   #MY_NEW_API_KEY=              # Placeholder
   ```

---

## Rotation Schedule

**Recommended Rotation Frequency**:
- **OpenAI API key**: Every 90 days
- **Anthropic API key**: Every 90 days
- **Database passwords**: Every 90 days
- **OAuth Client Secrets**: Every 90 days
- **Bot Tokens** (Slack, etc.): Every 90 days

**Calendar Reminders**:
- Q1: January 1, 2026
- Q2: April 1, 2026
- Q3: July 1, 2026
- Q4: October 1, 2026

---

## Troubleshooting

### "API Key not found" errors
```python
# Check if environment variable is set
import os
key = os.getenv("OPENAI_API_KEY")
if not key:
    raise ValueError("OPENAI_API_KEY not set")
```

### GitHub Secrets not working in Actions
- Verify secret name exactly matches workflow: `${{ secrets.SECRET_NAME }}`
- Re-run workflow after updating secret
- Check Actions permissions

### Railway environment variables not updating
- Use Railway CLI: `railway variable set KEY value`
- Or update via dashboard and redeploy
- Check Railway logs for errors

---

## Files for Reference

- `.env.example` - All available configuration options
- `CREDENTIAL_ROTATION_PLAN.md` - Detailed rotation procedures
- `SECURITY_REMEDIATION_EXECUTION_GUIDE.md` - Automated rotation
- `QUICK_CREDENTIAL_ROTATION.md` - Fast path (15 minutes)

---

## Next Steps

1. **TODAY**: Rotate exposed credentials (15 minutes)
2. **OPTIONAL**: Set up Google OAuth (10 minutes)
3. **OPTIONAL**: Set up Microsoft OAuth (10 minutes)
4. **OPTIONAL**: Set up Slack/Notion integrations (10 minutes each)
5. **FUTURE**: Implement AWS Secrets Manager for enterprise

---

**Generated**: 2025-11-15
**Status**: Production-Ready Guide
