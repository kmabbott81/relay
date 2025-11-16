# Deleting Vercel Projects

## Projects to Delete

After the GitHub rename, delete these orphaned/duplicate Vercel projects:

1. **djp-workflow** (old name, tied to renamed repo)
2. **relay-prod-web** (duplicate/unused production project)

Keep: **relay-beta-web** (your active project)

---

## How to Delete a Vercel Project

### Method 1: Via Vercel Web Dashboard (Recommended)

**Step 1: Go to Project Settings**
1. Go to: https://vercel.com/dashboard
2. Click on the project you want to delete (e.g., `djp-workflow`)
3. Click **Settings** (top menu bar)

**Step 2: Find Delete Option**
4. Scroll down to the bottom of the Settings page
5. Look for **"Danger Zone"** section (usually red background)
6. Find the button that says **"Delete"** or **"Delete Project"**

**Step 3: Confirm Deletion**
7. Click the Delete button
8. A modal will appear asking to confirm
9. **Type the project name** to confirm (this is a safety check)
10. Click **"Delete Project"** to confirm

**Step 4: Wait for Confirmation**
- Page will show "Project deleted successfully"
- Project disappears from your dashboard

**Time Required:** ~1 minute per project

---

### Method 2: Via Vercel CLI (If Installed)

If you have Vercel CLI installed:

```bash
# List all your projects
vercel projects list

# Delete a specific project
vercel remove <project-name> --confirm

# Example:
vercel remove djp-workflow --confirm
vercel remove relay-prod-web --confirm
```

---

## Step-by-Step Screenshots Guide

### Finding the Delete Button

**Location of "Danger Zone" Section:**
- Settings page → Scroll all the way down
- Look for red text or red background section
- Should see "Delete" option

**If you don't see it:**
1. Make sure you're on the correct project
2. Make sure you have project admin permissions
3. Click directly on the project name first, then Settings

---

## Deletion Sequence

**Recommended order:**
1. Delete `djp-workflow` first
2. Delete `relay-prod-web` second
3. Keep `relay-beta-web` (your active project)

**Why this order?**
- Less likely to accidentally delete the wrong project
- Vercel UI is freshest when you start

---

## What Happens After Deletion

✅ **Deleted immediately:**
- Project removed from dashboard
- Domain no longer resolves
- Deployment history removed
- Environment variables deleted
- GitHub integration disconnected

⚠️ **Note:**
- Can NOT be undone easily
- Project name becomes available for reuse
- Old URLs will show 404

---

## Verification

After deletion, verify by:

1. **Check Dashboard:**
   - Go to: https://vercel.com/dashboard
   - Confirm deleted projects no longer appear

2. **Verify Domains:**
   ```bash
   # These should now return 404 or DNS error
   curl https://djp-workflow.vercel.app
   curl https://relay-prod-web.vercel.app

   # This should still work
   curl https://relay-studio-one.vercel.app
   ```

---

## If You Accidentally Delete the Wrong Project

**Immediate Actions:**
1. Contact Vercel Support: https://vercel.com/support
2. Mention: "Accidentally deleted project X, please recover if possible"
3. Provide: Project ID, deletion timestamp, team name

**Recovery Window:** Usually 30 days

---

## After Deleting, Return Here

Once you've deleted the Vercel projects:

1. **Add Environment Variables to relay-beta-web:**
   - See: `VERCEL_DEPLOYMENT_FIX.md`
   - Add 3 variables:
     - `NEXT_PUBLIC_SUPABASE_URL`
     - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
     - `NEXT_PUBLIC_API_URL`

2. **Redeploy:**
   - Go to Deployments tab
   - Click "Redeploy" on latest build
   - Or push a new commit to trigger auto-deploy

---

## Quick Reference

| Project | Action | Keep/Delete |
|---------|--------|------------|
| relay-beta-web | Keep | ✅ Keep (active) |
| relay-prod-web | Delete | ❌ Delete (orphaned) |
| djp-workflow | Delete | ❌ Delete (old name) |

---

**Status:** Follow this guide to clean up old projects
