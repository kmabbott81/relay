# Agent Orchestration Protocol (AOP)
**Version**: 1.0
**Last Updated**: 2025-11-02
**Status**: ACTIVE - CHECK THIS ON EVERY PROMPT
**Responsibility**: Agent Deployment Monitor + Project Historian

---

## PURPOSE

This document defines the **automatic decision tree** that should trigger specialized agents **BEFORE executing any task**. The goal is to prevent duplicate work, security issues, and architectural violations.

**This file must be consulted at the START of every prompt.**

---

## ORCHESTRATION DECISION TREE

### 📋 DECISION FLOW

```
START → Read this file to check task type
  ↓
CLASSIFY task:
  - Implementing new features?     → Route to Project Historian FIRST
  - Setting up/adding config?      → Route to Project Historian FIRST
  - Code quality/correctness?      → Route to Code Reviewer
  - Security implications?         → Route to Security Reviewer
  - Infrastructure/deployment?     → Route to Agent Deployment Monitor
  - Performance concerns?          → Route to Frontend Performance
  - Architecture alignment?        → Route to Tech Lead
  - Multiple concerns?             → Route to PRIMARY agent, then secondary
  ↓
EXECUTE primary agent
  ↓
Based on findings → EXECUTE secondary agents if needed
  ↓
PROCEED with implementation/changes
```

---

## DETAILED TRIGGER RULES

### 1️⃣ **TRIGGER: Project Historian**

**WHEN**:
- [ ] User asks to "add a new feature"
- [ ] User asks to "implement" something not yet done
- [ ] User asks to "set up" or "configure" something new
- [ ] User asks to "create" a new file/component/system
- [ ] Changes to infrastructure/architecture files
- [ ] New environment variables or secrets needed
- [ ] Database schema changes or migrations
- [ ] New deployment scripts or CI/CD changes
- [ ] Organizing files or restructuring codebase
- [ ] **EXAMPLE**: "Can you set GitHub secrets automatically?"
  - ✅ **BEFORE** running `gh secret set`, check: "Have we already done this?"

**WHAT TO CHECK**:
1. Has this exact feature been attempted before?
2. Does a similar implementation exist that we should extend?
3. Are there historical PRs or commits related to this?
4. Did a previous agent already solve a similar problem?
5. What was the outcome last time?
6. Are there environment files already with these values?

**ACTION**:
- If feature already done: REPORT findings, skip implementation
- If feature partially done: EXTEND existing work, don't restart
- If feature new: PROCEED with confidence, document in history

**EXCEPTIONS**: None. Always check first.

---

### 2️⃣ **TRIGGER: Code Reviewer**

**WHEN**:
- [ ] After writing significant code (>50 lines)
- [ ] Before committing code to main
- [ ] User asks "is this code correct?"
- [ ] User asks to "review" or "validate" code
- [ ] Logic errors suspected
- [ ] Performance optimization needed
- [ ] Refactoring proposed
- [ ] Test coverage changes
- [ ] **EXAMPLE**: "Fix the database migration sequence"
  - ✅ Review the changes for logic errors, race conditions, side effects

**WHAT TO CHECK**:
1. Implementation correctness (logic, flow control)
2. Error handling (all paths covered?)
3. Performance implications
4. Code readability and maintainability
5. Test coverage adequacy
6. Compliance with existing patterns
7. Edge cases handled?

**ACTION**:
- If issues found: Report with specific line numbers, suggest fixes
- If approved: Clear for commit
- If concerns: Block until addressed

---

### 3️⃣ **TRIGGER: Security Reviewer**

**WHEN**:
- [ ] Any secrets/credentials mentioned
- [ ] Authentication or authorization changes
- [ ] User asks to "set" or "configure" secrets
- [ ] New environment variables with sensitive values
- [ ] API keys, tokens, passwords involved
- [ ] Access control rules changed
- [ ] User data handling modified
- [ ] Encryption/decryption logic touched
- [ ] **EXAMPLE**: "Can you set GitHub secrets?"
  - ✅ Review: Are secrets being handled safely? No accidental logging?

**WHAT TO CHECK**:
1. Secrets never committed to git
2. Tokens not logged or exposed
3. No hardcoded credentials
4. Encryption keys properly managed
5. Access controls properly validated
6. Input sanitization present (if accepting user input)
7. Compliance requirements met (SOC2, GDPR, etc.)

**ACTION**:
- If vulnerabilities found: Block and suggest fixes
- If approved: Clear for deployment
- If uncertain: Escalate to security team

---

### 4️⃣ **TRIGGER: Agent Deployment Monitor**

**WHEN**:
- [ ] About to deploy to production
- [ ] GitHub Actions workflow changes
- [ ] Railway/Vercel configuration modified
- [ ] Docker or container configuration changed
- [ ] Database migrations need to run
- [ ] CI/CD pipeline changes
- [ ] User asks to "deploy" something
- [ ] User asks "can you automate deployment?"
- [ ] **EXAMPLE**: "Can you set GitHub secrets automatically?"
  - ✅ After setup, verify: Did agents deploy successfully?

**WHAT TO CHECK**:
1. All agents registered and deployed
2. No blocking dependencies
3. Deployment order correct (migrations before API)
4. Rollback strategy defined
5. Smoke tests passing
6. Monitoring in place
7. Notification channels active

**ACTION**:
- If deployment blocks detected: Report and resolve
- If all clear: Monitor deployment in real-time
- If failure: Trigger automatic rollback

---

### 5️⃣ **TRIGGER: Tech Lead**

**WHEN**:
- [ ] Architectural decisions needed
- [ ] Design patterns questioned
- [ ] System alignment concerns
- [ ] Large refactoring proposed
- [ ] Multi-system impact changes
- [ ] Locked architectural decisions at risk
- [ ] Sprint scope boundaries questioned
- [ ] Cross-team coordination needed
- [ ] **EXAMPLE**: "Should we use this approach?"
  - ✅ Review: Does this align with our locked architecture?

**WHAT TO CHECK**:
1. Aligns with locked architectural decisions
2. Maintains system consistency
3. Follows established patterns
4. No scope creep vs. locked roadmap
5. Risk assessment for large changes
6. Team coordination implications

**ACTION**:
- If misaligned: Reject and suggest alternative
- If aligned: Clear for implementation
- If unclear: Request clarification

---

### 6️⃣ **TRIGGER: Frontend Performance**

**WHEN**:
- [ ] Frontend code changes
- [ ] Performance targets mentioned
- [ ] Web app deployment
- [ ] Core Web Vitals optimization
- [ ] Bundle size concerns
- [ ] User-facing latency mentioned
- [ ] **EXAMPLE**: "Deploy web app to Vercel"
  - ✅ Review: Will this meet performance targets?

**WHAT TO CHECK**:
1. Bundle size within limits
2. Core Web Vitals targets met (LCP, FID, CLS)
3. Code splitting optimized
4. Images and assets optimized
5. Load time acceptable

**ACTION**:
- If targets missed: Suggest optimizations
- If targets met: Clear for deployment

---

### 7️⃣ **TRIGGER: Observability Architect**

**WHEN**:
- [ ] New metrics needed
- [ ] Monitoring/alerting questions
- [ ] SLO/SLA definition
- [ ] Incident response planning
- [ ] Dashboard creation
- [ ] Alert rule configuration
- [ ] **EXAMPLE**: "How do we know deployments succeeded?"
  - ✅ Design: What metrics, thresholds, alerts needed?

**WHAT TO CHECK**:
1. Metrics defined and actionable
2. Alert thresholds appropriate
3. SLO/SLA targets realistic
4. Incident response plan defined
5. Dashboards provide visibility

**ACTION**:
- If gaps found: Define metrics and alerts
- If complete: Clear for implementation

---

## MULTI-TRIGGER SCENARIOS

### When Multiple Agents Needed

**Example 1: "Implement new feature with secure config"**
```
1. Project Historian: "Was this done before?"
2. Code Reviewer: "Is the code correct?"
3. Security Reviewer: "Is config secure?"
4. Tech Lead: "Does this align with architecture?"
→ THEN implement
```

**Example 2: "Deploy to production"**
```
1. Code Reviewer: "Is code ready?"
2. Security Reviewer: "Are secrets safe?"
3. Agent Deployment Monitor: "Are all systems ready?"
4. Observability Architect: "Can we monitor it?"
→ THEN deploy
```

**Example 3: "Set up GitHub secrets"**
```
1. Project Historian: "Do we already have these values?" ← THIS STEP
2. Security Reviewer: "Are we handling tokens safely?"
3. Agent Deployment Monitor: "Will this unblock deployment?"
→ THEN set secrets
```

---

## EXECUTION PROTOCOL

### On Every Claude Code Session

**At START, BEFORE any implementation:**

1. ✅ Read this file (AGENT_ORCHESTRATION_PROTOCOL.md)
2. ✅ Classify the user's task
3. ✅ Trigger appropriate primary agent(s)
4. ✅ Wait for findings
5. ✅ Trigger secondary agents if needed
6. ✅ Synthesize findings
7. ✅ THEN proceed with implementation

### Within Each Task

**Before writing code:**
- [ ] Code Reviewer → any new code? ✅ Review first
- [ ] Security Reviewer → secrets/auth? ✅ Review first
- [ ] Tech Lead → architectural impact? ✅ Review first

**Before deploying:**
- [ ] Agent Deployment Monitor → all systems ready? ✅ Check first
- [ ] Observability Architect → can we monitor it? ✅ Check first

**Before setting config/secrets:**
- [ ] Project Historian → do we already have this? ✅ Check first

---

## REAL-WORLD EXAMPLE: What Went Wrong (Nov 2)

**Task**: "Can you set GitHub secrets automatically?"

**What I DID**:
```
1. Check if gh CLI available ✓
2. Ask user for secret values ✓
3. (USER had to tell me to check history)
4. Project Historian searches ✓
5. FOUND 3 values already provided ✓
```

**What I SHOULD have done**:
```
1. Read AGENT_ORCHESTRATION_PROTOCOL.md
2. Classify: "Setting up new config"
3. TRIGGER: Project Historian (rule: "Setting up/adding config")
4. Project Historian reports: "Found 3/8 values in .env, .env.canary"
5. Ask user for ONLY the 5 missing values
6. Set secrets
```

**Gap**: I didn't proactively trigger Project Historian because I lacked explicit decision logic.

**Fix**: This document now IS that logic.

---

## FOR AI ASSISTANTS: MANDATORY CHECKLIST

On EVERY new session or prompt, verify:

- [ ] Read AGENT_ORCHESTRATION_PROTOCOL.md
- [ ] Classified task type correctly
- [ ] Routed to appropriate agent(s)
- [ ] Agents executed in correct order
- [ ] Findings synthesized before proceeding
- [ ] No duplicate work risk

**Failure to follow**: Risks duplicate work, security issues, architectural misalignment, wasted effort.

---

## AGENT REGISTRY

| Agent | Primary Trigger | Secondary Triggers | Owner |
|-------|-----------------|-------------------|-------|
| **Project Historian** | New features, setup, config | All implementation tasks | continuity-sentinel |
| **Code Reviewer** | Code changes >50 lines | Implementation, security | code-quality-enforcer |
| **Security Reviewer** | Secrets, auth, compliance | All config, deployment | security-enforcer |
| **Tech Lead** | Architecture decisions | Major changes, refactoring | architecture-enforcer |
| **Agent Deployment Monitor** | Deployment tasks | Any infrastructure change | continuity-monitor |
| **Observability Architect** | Monitoring/alerting | Deployment, production readiness | observability-monitor |
| **Frontend Performance** | Web app changes | Deployment, optimization | performance-enforcer |
| **Code Quality Enforcer** | Code correctness | Implementation, testing | quality-enforcer |

---

## UPDATES & MAINTENANCE

**When to update this file**:
- New agent type created
- New trigger scenario discovered
- Existing rules too strict/loose
- Lessons learned from incidents

**How to update**:
1. Document the scenario
2. Define new trigger rule
3. Update AGENT_REGISTRY
4. Commit with explanation
5. Reference in agent prompt

**Last reviewed**: 2025-11-02
**Next review**: After every major incident or new agent added

---

## SIGN-OFF

**Protocol Status**: ✅ **ACTIVE**

This protocol is the source of truth for agent orchestration. It should be consulted on every prompt.

**If you're reading this in a Claude Code session**: You should have automatically consulted this file. If not, request it be added to the session context.

---

**Protocol Owner**: Agent Deployment Monitor
**Enforcer**: Project Historian + Continuity Sentinel
**Audit**: Tech Lead (monthly review)
