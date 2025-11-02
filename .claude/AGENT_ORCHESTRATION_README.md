# 🤖 Claude Code Agent Orchestration - START HERE

**READ THIS AT THE START OF EVERY SESSION**

---

## What This Is

This directory contains the **Agent Orchestration Protocol (AOP)** - a decision tree that automatically routes tasks to the right specialized agents BEFORE implementing anything.

**Location of source of truth**:
```
C:\Users\kylem\openai-agents-workflows-2025.09.28-v1\AGENT_ORCHESTRATION_PROTOCOL.md
```

---

## Why This Exists

**Problem**: On Nov 2, user asked "Can you set GitHub secrets?" and I:
1. ✗ Asked for 8 secret values
2. ✗ User had to tell me to check history
3. ✗ Found 3 values were already in `.env` files

**Root cause**: No proactive decision tree to trigger `project-historian` automatically

**Solution**: This protocol ensures every task routes through the right agents FIRST

---

## The Decision Tree (5 Seconds)

```
User task → Classify it ↓
  ├─ "Add new feature" → Project Historian FIRST
  ├─ "Set up/config"   → Project Historian FIRST
  ├─ Code written      → Code Reviewer FIRST
  ├─ Secrets/auth      → Security Reviewer FIRST
  ├─ Deploy/infra      → Agent Deployment Monitor FIRST
  ├─ Performance       → Frontend Performance FIRST
  └─ Architecture      → Tech Lead FIRST
→ Wait for findings
→ THEN implement
```

---

## Mandatory Checklist (BEFORE ANY WORK)

- [ ] Read `AGENT_ORCHESTRATION_PROTOCOL.md` (in project root)
- [ ] Classify user's task type
- [ ] Identify primary agent(s) needed
- [ ] Execute agents in order
- [ ] Synthesize findings
- [ ] Report to user
- [ ] THEN proceed with implementation

---

## Real-World Examples

### Example 1: "Set GitHub secrets automatically"
```
✗ WRONG:
  1. Ask user for values
  2. User: "Check project files first"
  3. Search and find values

✓ RIGHT (using AOP):
  1. Classify: "Setting up config"
  2. Trigger: project-historian
  3. project-historian: "Found 3/8 values already"
  4. Ask user for only 5 missing values
  5. Set secrets
```

### Example 2: "Deploy web app to Vercel"
```
✓ RIGHT (using AOP):
  1. Classify: "Infrastructure/deployment"
  2. Trigger: agent-deployment-monitor
  3. agent-deployment-monitor: "Check code first"
  4. Trigger: code-reviewer
  5. code-reviewer: "Code ready ✓"
  6. Trigger: security-reviewer
  7. security-reviewer: "Secrets safe ✓"
  8. Trigger: observability-architect
  9. observability-architect: "Monitoring configured ✓"
  10. Deploy
```

### Example 3: "Fix the database migration"
```
✓ RIGHT (using AOP):
  1. Classify: "Code correctness"
  2. Trigger: code-reviewer
  3. code-reviewer: "Race condition detected"
  4. Fix implementation
  5. Trigger: agent-deployment-monitor
  6. agent-deployment-monitor: "Deploy when ready"
```

---

## Agent Mapping

| Classification | Agent | Why | Quick Check |
|---|---|---|---|
| "Add feature", "implement", "create" | `project-historian` | Prevent duplicate work | "Was this done before?" |
| Code changes | `code-reviewer` | Catch bugs, performance | "Is this correct?" |
| Secrets, auth, compliance | `security-reviewer` | Prevent breaches | "Is this secure?" |
| Architecture decisions | `tech-lead` | Maintain consistency | "Does this align?" |
| Deployment, infrastructure | `agent-deployment-monitor` | Verify readiness | "Are we ready?" |
| Web performance | `frontend-performance` | Meet targets | "Will this be fast?" |
| Metrics, monitoring | `observability-architect` | Visibility | "Can we observe it?" |

---

## How to Use This Protocol

### Session Start Ritual

```bash
# 1. At the START of every session:
#    Read: C:\Users\kylem\openai-agents-workflows-2025.09.28-v1\AGENT_ORCHESTRATION_PROTOCOL.md

# 2. When user asks for something:
#    Classify their task into one of the categories above

# 3. Route to appropriate agent(s)
#    Execute in order (primary first, then secondary if needed)

# 4. Wait for agent findings

# 5. Synthesize and report findings

# 6. THEN implement per findings
```

### When to Re-Check

- [ ] User changes direction mid-task
- [ ] New requirements added
- [ ] Scope expands
- [ ] Different risk domain discovered

---

## Key Principles

### 1. Always Check History First
- Before implementing → Ask project-historian
- Before setting config → Ask project-historian
- Before deploying → Ask agent-deployment-monitor
- **Never restart work that's been done before**

### 2. Security is Non-Negotiable
- Before ANY secrets handling → Trigger security-reviewer
- Before ANY deployment → Trigger security-reviewer
- No exceptions

### 3. Coordination Matters
- Multi-agent scenarios need orchestration
- Some agents are dependent (security-reviewer depends on code-reviewer)
- Execute in logical order

### 4. This Is The Source of Truth
- This protocol overrides default behavior
- If unsure which agent → Check `AGENT_ORCHESTRATION_PROTOCOL.md`
- If protocol unclear → Ask for clarification

---

## Failure Cases (What Went Wrong Nov 2)

### Failure: No Proactive History Check
```
Task: Set GitHub secrets
Classification: Setting up config
Expected: Trigger project-historian FIRST
Actual: Asked user for values immediately
Result: User had to tell me to check history
Fix: Now mandatory in AOP
```

### How to Avoid
```
✓ Always think: "Has this been done before?"
✓ Always think: "Are there related files with partial data?"
✓ Always route to project-historian for ANY setup/config task
```

---

## Updates

**Last Updated**: 2025-11-02
**Version**: 1.0
**Source of Truth**: `AGENT_ORCHESTRATION_PROTOCOL.md` in project root

Changes to the protocol should be:
1. Documented in main file
2. Committed to git
3. Reviewed by Tech Lead
4. Communicated to all agents

---

## Quick Link

**Main Protocol**: [AGENT_ORCHESTRATION_PROTOCOL.md](../AGENT_ORCHESTRATION_PROTOCOL.md)

---

## For Claude Code Sessions

**START OF SESSION CHECKLIST**:
```
□ Read this file (you're reading it now ✓)
□ Read the full protocol (AGENT_ORCHESTRATION_PROTOCOL.md)
□ Acknowledge: "I will route all tasks through appropriate agents"
□ Ready to classify user tasks
```

**ON EVERY USER REQUEST**:
```
□ Pause before implementation
□ Classify task type
□ Check which agent(s) to trigger
□ Execute agents
□ Wait for findings
□ THEN implement per findings
```

---

**Agent Orchestration Status**: ✅ **ACTIVE**

This is now the operative decision tree for all Claude Code work in this project.

**No agent shall be left behind. No duplicate work shall be done.**
