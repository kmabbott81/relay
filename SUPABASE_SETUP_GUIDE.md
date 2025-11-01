# Supabase Configuration Guide for R2 Phase 3

## Quick Start (5-10 minutes)

You need **two credentials** from Supabase:
1. **SUPABASE_PROJECT_ID** — Project identifier (e.g., `relay` or `abc123xyz`)
2. **SUPABASE_JWT_SECRET** — Signing secret for JWT tokens (64-character hex string)

---

## Option A: Create New Supabase Project (Recommended)

### Step 1: Create Project
1. Go to [supabase.com/dashboard](https://supabase.com/dashboard)
2. Sign in or create account
3. Click **"New Project"**
4. Fill in:
   - **Project name**: `relay-staging` (or similar)
   - **Database password**: Generate strong password (auto-generated OK)
   - **Region**: Select closest to your infrastructure (e.g., US-East-1)
5. Click **"Create new project"** (takes ~2 min)

### Step 2: Get Credentials
Once project is created:

1. **Find Project ID:**
   - Settings → General
   - Copy **Project ID** (shown under project name, e.g., `abcdefghijklmnop`)
   - OR use any identifier you prefer (e.g., `relay`)

2. **Find JWT Secret:**
   - Settings → API
   - Under **Project API keys**, find **JWT Secret**
   - Copy the secret (long hex string, ~256 characters)
   - ⚠️ **Keep this secret!** Treat like password.

### Step 3: Add to Railway
In Railway dashboard for your staging project:

```
Environment Variables:
  SUPABASE_PROJECT_ID=relay-staging
  SUPABASE_JWT_SECRET=<paste the 256-char secret>
```

---

## Option B: Use Existing Supabase Project

If you already have a Supabase project:

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard)
2. Select your project
3. Settings → API
4. Copy:
   - **Project ID**: Settings → General
   - **JWT Secret**: Settings → API → "JWT Secret"
5. Add to Railway (same as Step 3 above)

---

## Option C: Retrieve from Supabase CLI (If Already Configured)

If you have Supabase CLI installed:

```bash
supabase projects list
supabase secrets list --project-ref <PROJECT_REF>
```

---

## What You'll Get

Once configured, you can generate Supabase-signed JWTs with:

```python
import jwt

payload = {
    "sub": "user_123",
    "user_id": "user_123",
    "aud": "authenticated",
    "iat": 1234567890,
    "exp": 1234567890 + 604800,  # 7 days
}

token = jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")
# token = "eyJhbGc..."
```

---

## Verification

Once Railway env vars are set, verify by visiting:
```
https://relay-production-f2a6.up.railway.app/ready
```

Response should show:
```json
{
  "ready": true,
  "checks": {
    "database": "ok",
    "redis": "ok",
    "jwt": "configured"
  }
}
```

---

## Timeline

- **Create Supabase project**: 2 min
- **Get credentials**: 1 min
- **Add to Railway**: 1 min
- **Restart deployment**: 1 min (automatic on push)
- **Total**: ~5 minutes

---

## Need Help?

Common issues:

**Issue: "JWT_SECRET not found"**
- Verify: Settings → API → JWT Secret (should be visible)
- Regenerate if needed: Click refresh icon next to JWT Secret

**Issue: "Project not created"**
- Check email for verification link
- Project creation can take up to 5 minutes

**Issue: "Railway deployment failed"**
- Verify env var values have no extra spaces
- Check Railway logs: Deployments → [latest] → Logs
