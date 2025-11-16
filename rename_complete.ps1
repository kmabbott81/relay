
# Automated post-rename script for PowerShell
Write-Host "=================================================="
Write-Host "POST-RENAME AUTOMATION"
Write-Host "=================================================="
Write-Host ""

# Update local remote
Write-Host "Updating local git remote..."
git remote set-url origin https://github.com/kmabbott81/relay.git
Write-Host "Done"
Write-Host ""

# Create feature branch
Write-Host "Creating documentation branch..."
git checkout -b docs/update-repo-name-references
Write-Host "Done"
Write-Host ""

# Update documentation files
Write-Host "Updating documentation files..."

$files = @(
    "pyproject.toml",
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        $updated = $content -replace "kmabbott81/djp-workflow", "kmabbott81/relay"
        Set-Content -Path $file -Value $updated -NoNewline
        Write-Host "Updated: $file"
    }
}

Write-Host ""

# Commit changes
Write-Host "Committing changes..."
git add -A
git commit -m "docs: Update repository name references from djp-workflow to relay"
Write-Host "Done"
Write-Host ""

# Create PR
Write-Host "Creating pull request..."
$title = "docs: Update repository name references (djp-workflow to relay)"
$body = "Repository renamed from djp-workflow to relay. Updated all documentation references."
gh pr create --title $title --body $body
Write-Host "Done"
Write-Host ""

Write-Host "=================================================="
Write-Host "AUTOMATION COMPLETE"
Write-Host "=================================================="
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Review PR at: https://github.com/kmabbott81/relay/pulls"
Write-Host "2. Merge the PR"
Write-Host "3. Delete old Vercel projects"
Write-Host "4. Add Vercel environment variables"
Write-Host ""
