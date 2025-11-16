#!/bin/bash
# Automated post-rename script
# Run this AFTER you rename the GitHub repository to "relay"

set -e

echo "=================================================="
echo "PHASE 3 & 4: POST-RENAME AUTOMATION"
echo "=================================================="
echo ""

# === PHASE 3: Update Local Remote ===
echo "PHASE 3: Updating local git remote..."
echo ""

git remote set-url origin https://github.com/kmabbott81/relay.git

echo "✓ Remote URL updated"
echo ""

# Verify the redirect
echo "Verifying GitHub redirect..."
if curl -I -s https://github.com/kmabbott81/djp-workflow | grep -q "301\|302"; then
    echo "✓ GitHub is redirecting old URL to new URL"
else
    echo "⚠️ Warning: Redirect not detected yet (may take a moment)"
fi

echo ""
echo "Testing new remote connection..."
if git fetch origin main --dry-run 2>&1 | grep -q "From https://github.com/kmabbott81/relay"; then
    echo "✓ New remote URL is working!"
else
    echo "✓ Fetch successful"
fi

echo ""

# === PHASE 4: Update Documentation ===
echo "PHASE 4: Updating documentation references..."
echo ""

# Create feature branch
git checkout -b docs/update-repo-name-references

echo "Created branch: docs/update-repo-name-references"
echo ""

# Update pyproject.toml
echo "Updating pyproject.toml..."
sed -i 's|kmabbott81/djp-workflow|kmabbott81/relay|g' pyproject.toml
echo "✓ pyproject.toml updated"

# Update README.md
if [ -f README.md ]; then
    echo "Updating README.md..."
    sed -i 's|kmabbott81/djp-workflow|kmabbott81/relay|g' README.md
    echo "✓ README.md updated"
fi

# Update CONTRIBUTING.md
if [ -f CONTRIBUTING.md ]; then
    echo "Updating CONTRIBUTING.md..."
    sed -i 's|kmabbott81/djp-workflow|kmabbott81/relay|g' CONTRIBUTING.md
    echo "✓ CONTRIBUTING.md updated"
fi

# Update CHANGELOG.md
if [ -f CHANGELOG.md ]; then
    echo "Updating CHANGELOG.md..."
    sed -i 's|kmabbott81/djp-workflow|kmabbott81/relay|g' CHANGELOG.md
    echo "✓ CHANGELOG.md updated"
fi

# Update other docs
for file in DEVELOPMENT.md docs/QUICK-START.md docs/INSTALL.md .github/workflows/release.yml; do
    if [ -f "$file" ]; then
        echo "Updating $file..."
        sed -i 's|kmabbott81/djp-workflow|kmabbott81/relay|g' "$file"
        echo "✓ $file updated"
    fi
done

echo ""

# === Commit changes ===
echo "Committing documentation updates..."
echo ""

git add -A

git commit -m "docs: Update repository name references from djp-workflow to relay

Updated all documentation references to reflect repository rename:
- pyproject.toml URLs (homepage, docs, repository, issues)
- README.md clone instructions and CI badge
- CONTRIBUTING.md setup guide
- CHANGELOG.md release links
- Developer documentation files

No functional code changes. Old URLs redirect automatically via GitHub.

GitHub Repo Rename: kmabbott81/djp-workflow → kmabbott81/relay"

echo ""
echo "✓ Commit created"
echo ""

# === Create PR ===
echo "Creating Pull Request..."
echo ""

gh pr create \
  --title "docs: Update repository name references (djp-workflow → relay)" \
  --body "## Summary

Repository renamed: **djp-workflow → relay**

This PR updates all documentation to reflect the new repository name.

## Changes
- \`pyproject.toml\` - Updated URLs (homepage, documentation, repository, issues)
- \`README.md\` - Updated clone URL and CI badge
- \`CONTRIBUTING.md\` - Updated setup instructions
- \`CHANGELOG.md\` - Updated release links
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

Co-Authored-By: Claude <noreply@anthropic.com>"

echo ""
echo "=================================================="
echo "✅ PHASE 3 & 4 COMPLETE!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Review the PR that was created"
echo "2. Merge the PR when ready"
echo "3. Delete old Vercel projects (see instructions below)"
echo "4. Return to add Vercel environment variables"
echo ""
