#!/bin/bash
###############################################################################
# reorganize.sh — Idempotent repo reorganization for relay-ai structure
#
# USAGE:
#   ./scripts/reorganize.sh --dry-run    # Default: show plan, don't execute
#   ./scripts/reorganize.sh --execute    # Actually move files
#   ./scripts/reorganize.sh --rollback   # Restore from backup
#
# SAFETY:
#   - Creates pre-reorg tag before changes
#   - Backs up moved files to ./_backup_moved/
#   - Dry-run mode by default
#   - Prints undo instructions
#   - Requires explicit --execute flag
#
###############################################################################

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${REPO_ROOT}/_backup_moved_${TIMESTAMP}"
DRY_RUN=${DRY_RUN:-true}
EXECUTE_MODE="${1:-}"

# Trap for error handling
trap 'echo "❌ Error: reorganization failed" && exit 1' ERR

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
  echo "ℹ️  $*"
}

log_success() {
  echo "✓ $*"
}

log_warn() {
  echo "⚠️  $*"
}

log_error() {
  echo "❌ $*"
}

# Dry-run mode: print what would be done
run_cmd() {
  local cmd="$*"
  if [ "$DRY_RUN" = true ]; then
    echo "  [DRY-RUN] $cmd"
  else
    echo "  [EXECUTE] $cmd"
    eval "$cmd"
  fi
}

# ============================================================================
# Mode Selection
# ============================================================================

case "${EXECUTE_MODE}" in
  "--execute")
    DRY_RUN=false
    log_warn "🚀 EXECUTE MODE ENABLED - Files will be moved!"
    ;;
  "--rollback")
    log_info "Rolling back to pre-reorg-${TIMESTAMP}..."
    cd "$REPO_ROOT"
    git checkout pre-reorg-${TIMESTAMP}
    log_success "Rolled back to pre-reorg-${TIMESTAMP}"
    exit 0
    ;;
  "--dry-run"|"")
    # Default: dry-run mode
    DRY_RUN=true
    if [ -z "$EXECUTE_MODE" ]; then
      log_info "🔍 DRY-RUN MODE (default) - Use --execute to apply changes"
    else
      log_info "🔍 DRY-RUN MODE - Use --execute to apply changes"
    fi
    ;;
  *)
    log_error "Unknown mode: $EXECUTE_MODE"
    echo "Usage: $0 [--dry-run|--execute|--rollback]"
    exit 1
    ;;
esac

# ============================================================================
# Verification
# ============================================================================

log_info "🔍 Preflight checks..."

# Check git state
if ! git -C "$REPO_ROOT" status --porcelain | grep -q "^??"; then
  log_info "No untracked files (good)"
else
  log_warn "Untracked files detected. They will be preserved."
fi

# Verify preexisting tag
if git -C "$REPO_ROOT" rev-parse "pre-reorg-$(date +%Y%m%d)" > /dev/null 2>&1; then
  log_success "Pre-reorg tag exists: pre-reorg-$(date +%Y%m%d)"
else
  log_error "Pre-reorg tag NOT found. Run preflight first:"
  echo "  git tag pre-reorg-\$(date +%Y%m%d)"
  exit 1
fi

# ============================================================================
# Move Plan (Displayed Before Any Changes)
# ============================================================================

log_info "📋 Move Plan:"
echo ""
echo "OLD PATH                          | NEW PATH"
echo "==================================|=================================="

# Define moves
declare -A MOVES=(
  ["src/knowledge"]="relay-ai/platform/api/knowledge"
  ["src/stream"]="relay-ai/platform/api/stream"
  ["src/memory"]="relay-ai/platform/security/memory"
  ["tests"]="relay-ai/platform/tests"
)

# Also handle artifacts
ARTIFACTS=$(find "$REPO_ROOT/artifacts" -maxdepth 1 -name "r2_canary_*" -type d 2>/dev/null | head -5)
for artifact in $ARTIFACTS; do
  artifact_name=$(basename "$artifact")
  MOVES["artifacts/$artifact_name"]="relay-ai/evidence/canaries/$artifact_name"
done

# Also handle GATE_SUMMARY.md
MOVES["GATE_SUMMARY.md"]="relay-ai/evidence/compliance/GATE_SUMMARY.md"

# Display table
for old_path in "${!MOVES[@]}"; do
  new_path="${MOVES[$old_path]}"
  printf "%-33s | %s\n" "$old_path" "$new_path"
done

echo ""

# ============================================================================
# Verify Paths Exist
# ============================================================================

log_info "🔎 Verifying paths..."

missing=0
for old_path in "${!MOVES[@]}"; do
  if [ ! -e "$REPO_ROOT/$old_path" ]; then
    log_warn "NOT FOUND: $old_path"
    ((missing++))
  else
    log_success "Found: $old_path"
  fi
done

if [ $missing -gt 0 ]; then
  log_error "❌ $missing path(s) not found. Cannot proceed."
  exit 1
fi

echo ""

# ============================================================================
# Execute Moves (or Show Plan)
# ============================================================================

log_info "Preparing backup..."

if [ "$DRY_RUN" = true ]; then
  log_info "📌 DRY-RUN MODE - No files will be moved"
else
  log_info "📦 Creating backup directory: $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
fi

echo ""
log_info "🚀 Starting moves..."
echo ""

moved_count=0
for old_path in "${!MOVES[@]}"; do
  new_path="${MOVES[$old_path]}"

  if [ -e "$REPO_ROOT/$old_path" ]; then
    if [ "$DRY_RUN" = true ]; then
      log_info "Would move: $old_path → $new_path"
    else
      log_info "Moving: $old_path → $new_path"

      # Create parent directory if needed
      mkdir -p "$(dirname "$REPO_ROOT/$new_path")"

      # Move via git if it's a tracked file
      if git -C "$REPO_ROOT" ls-files "$old_path" > /dev/null 2>&1; then
        run_cmd "cd '$REPO_ROOT' && git mv '$old_path' '$new_path'"
      else
        # Otherwise copy and remove
        run_cmd "cp -r '$REPO_ROOT/$old_path' '$REPO_ROOT/$new_path'"
        run_cmd "rm -rf '$REPO_ROOT/$old_path'"
      fi

      # Backup original
      run_cmd "cp -r '$REPO_ROOT/$new_path' '$BACKUP_DIR/$(basename $old_path)_backup'"

      ((moved_count++))
    fi
  fi
done

echo ""

# ============================================================================
# Commit Changes
# ============================================================================

if [ "$DRY_RUN" = false ]; then
  log_info "📝 Committing changes..."
  cd "$REPO_ROOT"

  if git status --porcelain | grep -q "^[AM]"; then
    git add relay-ai/
    git commit -m "chore: product-first repo skeleton + strategy docs (no code moves)"
    log_success "Committed reorganization"
  else
    log_info "No changes to commit"
  fi
fi

echo ""

# ============================================================================
# Summary & Undo Instructions
# ============================================================================

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                     REORGANIZATION SUMMARY                        ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

if [ "$DRY_RUN" = true ]; then
  log_info "Mode: DRY-RUN (no files changed)"
  echo ""
  echo "To execute the actual move, run:"
  echo "  bash scripts/reorganize.sh --execute"
  echo ""
else
  log_success "Mode: EXECUTE ($moved_count files moved)"
  echo ""
  log_success "Backup created: $BACKUP_DIR"
  echo ""
fi

echo "UNDO INSTRUCTIONS:"
echo "  git checkout pre-reorg-$(date +%Y%m%d)"
echo ""

echo "NEXT STEPS:"
if [ "$DRY_RUN" = true ]; then
  echo "  1. Review the move plan above"
  echo "  2. Run: bash scripts/reorganize.sh --execute"
  echo "  3. Verify: git status && pytest tests/"
else
  echo "  1. Verify: git status"
  echo "  2. Run tests: pytest tests/ relay_ai/platform/tests/"
  echo "  3. Commit: git push origin feat/reorg-product-first"
fi

echo ""
log_success "Done!"
