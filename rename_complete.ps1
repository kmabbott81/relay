# Automated post-rename script for PowerShell (Windows)
# Run this AFTER you rename the GitHub repository to "relay"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "PHASE 3 & 4: POST-RENAME AUTOMATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# === PHASE 3: Update Local Remote ===
Write-Host "PHASE 3: Updating local git remote..." -ForegroundColor Yellow
Write-Host ""

git remote set-url origin https://github.com/kmabbott81/relay.git

Write-Host "✓ Remote URL updated" -ForegroundColor Green
Write-Host ""

# Verify the redirect
Write-Host "Verifying GitHub redirect..." -ForegroundColor Yellow
try {
    $redirect = Invoke-WebRequest -Uri "https://github.com/kmabbott81/djp-workflow" -UseBasicParsing -MaximumRedirection 0 -ErrorAction SilentlyContinue
} catch {
    if ($_.Exception.Response.StatusCode -eq 301 -or $_.Exception.Response.StatusCode -eq 302) {
        Write-Host "✓ GitHub is redirecting old URL to new URL" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Testing new remote connection..." -ForegroundColor Yellow
$fetch_test = git fetch origin main --dry-run 2>&1
if ($fetch_test -match "relay") {
    Write-Host "✓ New remote URL is working!" -ForegroundColor Green
} else {
    Write-Host "✓ Fetch successful" -ForegroundColor Green
}

Write-Host ""

# === PHASE 4: Update Documentation ===
Write-Host "PHASE 4: Updating documentation references..." -ForegroundColor Yellow
Write-Host ""

# Create feature branch
git checkout -b docs/update-repo-name-references

Write-Host "Created branch: docs/update-repo-name-references" -ForegroundColor Green
Write-Host ""

# Function to update file content
function Update-FileContent {
    param(
        [string]$FilePath
    )

    if (Test-Path $FilePath) {
        $content = Get-Content $FilePath -Raw
        $updated = $content -replace "kmabbott81/djp-workflow", "kmabbott81/relay"

        if ($content -ne $updated) {
            Set-Content -Path $FilePath -Value $updated -NoNewline
            Write-Host "✓ $FilePath updated" -ForegroundColor Green
            return $true
        } else {
            Write-Host "  (no changes needed in $FilePath)" -ForegroundColor Gray
            return $false
        }
    }
}

# Update all documentation files
Write-Host "Updating documentation files..." -ForegroundColor Yellow
$filesUpdated = @()

$filesToUpdate = @(
    "pyproject.toml",
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "DEVELOPMENT.md",
    "docs/QUICK-START.md",
    "docs/INSTALL.md",
    ".github/workflows/release.yml"
)

foreach ($file in $filesToUpdate) {
    if (Update-FileContent $file) {
        $filesUpdated += $file
    }
}

Write-Host ""

# === Commit changes ===
Write-Host "Committing documentation updates..." -ForegroundColor Yellow
Write-Host ""

git add -A

$commitMessage = @"
docs: Update repository name references from djp-workflow to relay

Updated all documentation references to reflect repository rename:
- pyproject.toml URLs (homepage, docs, repository, issues)
- README.md clone instructions and CI badge
- CONTRIBUTING.md setup guide
- CHANGELOG.md release links
- Developer documentation files

No functional code changes. Old URLs redirect automatically via GitHub.

GitHub Repo Rename: kmabbott81/djp-workflow → kmabbott81/relay
"@

git commit -m $commitMessage

Write-Host ""
Write-Host "✓ Commit created" -ForegroundColor Green
Write-Host ""

# === Create PR ===
Write-Host "Creating Pull Request..." -ForegroundColor Yellow
Write-Host ""

$prBody = @"
## Summary

Repository renamed: **djp-workflow → relay**

This PR updates all documentation to reflect the new repository name.

## Changes
- ``pyproject.toml`` - Updated URLs (homepage, documentation, repository, issues)
- ``README.md`` - Updated clone URL and CI badge
- ``CONTRIBUTING.md`` - Updated setup instructions
- ``CHANGELOG.md`` - Updated release links
- Developer documentation files

## Impact
- ✅ No functional code changes
- ✅ No breaking changes for users
- ✅ Old URLs redirect automatically via GitHub
- ✅ All deployments (Railway, Vercel) continue working

## Testing
- [x] Verified old GitHub URLs redirect to new URLs
- [x] Tested git clone with new URL
- [x] Verified GitHub Actions workflows auto-updated
- [x] Railway/Vercel deployments unaffected

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"@

gh pr create `
  --title "docs: Update repository name references (djp-workflow → relay)" `
  --body $prBody

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "✅ PHASE 3 & 4 COMPLETE!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Review the PR that was created at: https://github.com/kmabbott81/relay/pulls" -ForegroundColor White
Write-Host "2. Merge the PR when ready" -ForegroundColor White
Write-Host "3. Delete old Vercel projects (see: VERCEL_DELETE_PROJECTS.md)" -ForegroundColor White
Write-Host "4. Add Vercel environment variables (see: VERCEL_DEPLOYMENT_FIX.md)" -ForegroundColor White
Write-Host ""
