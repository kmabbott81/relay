# Vercel Deployment - Environment Variables Setup

## Why It's Failing

Your Vercel deployment is failing because the Next.js web app requires 3 environment variables that haven't been set in Vercel's project settings.

## Required Environment Variables

Add these to **Vercel Project Settings > Environment Variables**:

### 1. NEXT_PUBLIC_SUPABASE_URL
**Value**: Your Supabase project URL
- Go to: https://app.supabase.com
- Select your project (relay or similar)
- Find the project URL in Settings > API
- Copy the full URL (example: `https://xxxxx.supabase.co`)

### 2. NEXT_PUBLIC_SUPABASE_ANON_KEY
**Value**: Your Supabase anon key
- Same location as above (Settings > API)
- Copy the `anon` public key (starts with `eyJ...`)

### 3. NEXT_PUBLIC_API_URL
**Value**: Your backend API URL
- Should be: `https://relay-beta-api.railway.app`
- OR if you have production: `https://relay-prod-api.railway.app`

## How to Add to Vercel

1. Go to: https://vercel.com/dashboard
2. Select your project (relay-studio-one)
3. Click **Settings** (top menu)
4. Click **Environment Variables** (left sidebar)
5. For each variable:
   - **Name**: Enter the variable name exactly as above
   - **Value**: Paste the value from your Supabase project
   - **Environment**: Select `Production` (or all environments if needed)
   - Click **Save**

## Expected Values

Replace with YOUR actual values:

```
NEXT_PUBLIC_SUPABASE_URL=https://hmqmxmxkxqdrqpdmlgtn.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
NEXT_PUBLIC_API_URL=https://relay-beta-api.railway.app
```

## After Adding Environment Variables

1. Redeploy in Vercel:
   - Go to **Deployments** tab
   - Find the latest failed deployment
   - Click **Redeploy**

OR

2. Push new code to trigger auto-deploy:
   ```bash
   git commit --allow-empty -m "trigger: Redeploy with Vercel env vars"
   git push
   ```

## Verify It Works

After redeployment:
1. Go to: https://relay-studio-one.vercel.app
2. Navigate to `/beta`
3. You should be able to enter email and login

## Files That Use These Variables

- `relay_ai/product/web/app/beta/page.tsx` - Uses all 3 variables
- `relay_ai/product/web/app/layout.tsx` - May reference in headers

---

**Status**: Follow these steps and Vercel deployment should succeed ✅
