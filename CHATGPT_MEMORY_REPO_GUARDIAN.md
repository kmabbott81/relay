# ChatGPT Memory: When to Deploy repo-guardian Agent

**Created**: October 19, 2025
**Agent**: repo-guardian
**Purpose**: Deployment safety gatekeeper

---

## 🎯 DEPLOYMENT TRIGGERS FOR repo-guardian

### Primary Triggers (Always Use)

1. **User says "ready to merge"**
   - Code: `I'm ready to merge PR #XXX to main/release/*`
   - Action: Immediately invoke repo-guardian
   - Reason: Final safety gate before shipping

2. **User is deploying to Railway**
   - Code: `Deploying to production/staging`
   - Code: `Railway deployment initiated`
   - Action: Invoke repo-guardian for pre-deployment validation
   - Reason: Prevent unsafe deployments

3. **User opens PR targeting protected branches**
   - Code: `Opened PR to main or release/*`
   - Action: Check if repo-guardian validation is needed
   - Reason: Establish merge safety criteria early

4. **User asks "Is this PR ready?"**
   - Code: `Can I merge this?`, `Is it safe to ship?`
   - Action: Invoke repo-guardian for comprehensive validation
   - Reason: Comprehensive quality and safety check

---

## 📋 VALIDATION CHECKLIST repo-guardian Performs

When you invoke repo-guardian, it validates:

```
PRE-MERGE VALIDATION (ALL required)
├─ Reviews: Required approvals from CODEOWNERS present
├─ CI Status: All tests green (unit + streaming + security)
├─ Security: Scanning completed, no critical/high vulnerabilities
├─ Required Files: Docs/config updated when applicable
├─ Service Worker: Cache version bumped if UI/SW changed
├─ Performance: Bundle sizes within budget (or perf-approved label)
├─ Branch Freshness: Up-to-date with target branch

PRE-DEPLOYMENT VALIDATION (Railway)
├─ Branch→Environment: Correct mapping (main→prod, release/*→staging)
├─ Merge State: Confirmed merged (not deploying from unmerged PR)
├─ Build Artifacts: Fresh and successful
├─ Final Gate: Commit authors, reviewers, timing (flag anomalies)
└─ Re-run Pre-Merge: On the merge commit SHA

SENSITIVE PATHS (fail-closed if touched)
├─ src/stream/** → requires "security-approved" label
├─ auth/** → requires "security-approved" label
├─ src/webapi.py → requires "security-approved" label
├─ static/magic/sw.js → requires "perf-approved" label
└─ static/magic/** → requires "perf-approved" label
```

---

## 🔴 BLOCKER CONDITIONS (repo-guardian Returns BLOCKED)

Know when repo-guardian will block:

1. **Missing approvals** from CODEOWNERS
2. **CI tests failing** (any category)
3. **Security scanning** not run OR found critical/high issues
4. **Sensitive path touched** without corresponding label
5. **Performance budget exceeded** without perf-approved
6. **Branch stale** relative to target (not rebased)
7. **Branch name non-conforming** (not release/* or from main)
8. **Service worker** modified without cache version bump
9. **Uncertainty/missing info** → default BLOCKED (fail-closed)

---

## 🟢 APPROVAL CONDITIONS (repo-guardian Returns APPROVED)

repo-guardian approves when:

- ✅ All required approvals obtained
- ✅ All CI tests passing
- ✅ Security scanning complete + no critical/high
- ✅ Branch freshness OK
- ✅ Sensitive paths have required labels (or untouched)
- ✅ Performance within budget (or labeled perf-approved)
- ✅ Service worker cache bumped (if applicable)
- ✅ All required files updated
- ✅ No suspicious commit/author patterns

---

## 💡 HOW TO INVOKE repo-guardian

### From ChatGPT to Claude Code

```
For Claude Code, invoke repo-guardian agent:
"Validate PR #487 targeting main before merge:
1. Check required approvals from CODEOWNERS
2. Verify all CI tests are green
3. Confirm security scanning completed
4. Check if sensitive paths touched (need labels?)
5. Verify service worker cache bump
6. Final decision: APPROVED or BLOCKED?"
```

### Example Scenarios

**Scenario 1: PR Ready to Merge**
```
User: "I've finished the SSE streaming feature in PR #492. Can we merge to main?"
You: "I'll have repo-guardian validate this before merge"
→ Invoke repo-guardian for comprehensive validation
```

**Scenario 2: Production Deployment**
```
User: "Main is ready, deploying to production via Railway now"
You: "Let me run final deployment safety checks with repo-guardian"
→ Invoke repo-guardian for pre-deployment validation
```

**Scenario 3: Release Branch to Staging**
```
User: "Merging release/v2.3.1 to staging for QA"
You: "I'll validate this merge with repo-guardian first"
→ Invoke repo-guardian for release→staging validation
```

---

## ⚠️ CRITICAL REMINDERS

1. **Never bypass repo-guardian** - It's the deployment safety gatekeeper
2. **Fail-closed by default** - If uncertain, repo-guardian returns BLOCKED
3. **Require exact info** - repo-guardian will ask for PR links, CI URLs, specific labels
4. **Labels are critical** - Sensitive path changes MUST have appropriate labels
5. **Service worker is strict** - ANY UI/SW changes require CACHE_VERSION bump
6. **Branch hygiene enforced** - Branch names and targets are validated strictly

---

## 🚀 WHEN NOT TO INVOKE repo-guardian

❌ During development (not yet ready to merge)
❌ For feature branches (not targeting protected branches)
❌ For local testing/exploration
❌ For code review feedback (use code-reviewer instead)
❌ For UX feedback (use ux-reviewer instead)

✅ ONLY when:
- Ready to merge to main/release/*
- About to deploy to Railway
- Need final safety validation before shipping

---

## 📊 Decision Flow

```
User wants to MERGE or DEPLOY?
  ├─ YES → Invoke repo-guardian
  │  ├─ APPROVED → Safe to proceed
  │  └─ BLOCKED → Fix issues, re-run repo-guardian
  └─ NO → Continue development, don't invoke yet
```

---

**Remember**: repo-guardian is the gatekeeper. When in doubt, invoke it.
**Default**: BLOCKED (safer to block and verify, than ship and regret)
