# ChatGPT → Claude Code → Relay: Complete Agent Guide v1.0

**Last Updated**: October 19, 2025
**Total Agents**: 22 (18 project-specific + 4 built-in)
**Mission**: Complete Relay AI Orchestrator from R0.5 (Magic Box) through R4 (Cockpit)
**Current Focus**: Sprint 61b - UI/UX build and polish

---

## 📋 Quick Reference: Agent Decision Tree

### Built-In Agents (Use First)
```
"Need to explore codebase/find files?"  → Explore (built-in, fast)
"General research/complex question?"     → general-purpose (built-in, fallback)
```

### Project-Specific Agents (Specialized)
```
"Is the code correct?"                  → code-reviewer
"Is it secure?"                         → security-reviewer
"Does it follow architecture?"          → tech-lead
"Is the UX good?"                       → ux-reviewer
"Are we building real-time streams?"    → streaming-specialist
"Is action safe to execute?"            → safe-action-detector
"Is deployment safe? PR quality?"       → repo-guardian
"Building connectors/sync?"             → data-connector-architect
"Need RAG/citations?"                   → knowledge-retrieval-architect
"Multi-tenant/permissions?"             → multi-tenancy-architect
"How do we monitor/alert?"              → observability-architect
"File sync from local?"                 → file-system-connector-specialist
"Building with Next.js?"                → next-js-architect
"Memory/summarization?"                 → memory-architect
"Performance optimization?"             → frontend-performance
"Token costs/model selection?"          → cost-optimizer
"Supabase auth patterns?"               → supabase-auth-security
"Anonymous→registered flow?"            → anonymous-sessions-architect
```

---

# 🎯 BUILT-IN AGENTS (Always Available)

## Built-In Agent 1: `general-purpose`
**Model**: Sonnet
**Best for**: Research, complex questions, multi-step tasks, code search

**When to use**:
- Questions that don't fit specialized agents
- Researching unfamiliar technology
- Searching codebases for patterns
- Understanding system design

**How ChatGPT invokes**:
```
For Claude Code, use this agent:
/claude-code-task general-purpose "Search for how we handle authentication" \
  -p "Look for all authentication patterns in src/ and lib/ directories"
```

**For Claude Code**:
- Use as fallback when no specialized agent fits
- Can orchestrate multiple tools
- Good for exploration and research tasks

---

## Built-In Agent 2: `Explore`
**Model**: Haiku
**Best for**: Fast file pattern search, codebase exploration

**When to use**:
- Finding files matching patterns
- Quick codebase structure assessment
- Locating specific implementations
- When you need "quick" or "very thorough" exploration levels

**How ChatGPT invokes**:
```
For Claude Code, use Explore agent (specify thoroughness):
/claude-code-explore src/components "Find all React components" --thoroughness quick
```

**For Claude Code**:
- Use when searching for files or code patterns
- Faster than general-purpose for specific searches
- Good for initial codebase orientation

---

## Built-In Agent 3: `statusline-setup`
**Model**: Sonnet
**Best for**: Configuring Claude Code status line display

**When to use**:
- If you need to modify Claude Code's status display
- Customizing how tasks appear in the status line

**How ChatGPT invokes**:
```
This agent is rarely needed in normal workflow
```

**For Claude Code**:
- Skip unless explicitly requested

---

## Built-In Agent 4: `output-style-setup`
**Model**: Sonnet
**Best for**: Configuring Claude Code output styling

**When to use**:
- Customizing how Claude Code displays output
- Modifying markdown rendering, colors, formatting

**How ChatGPT invokes**:
```
This agent is rarely needed in normal workflow
```

**For Claude Code**:
- Skip unless explicitly requested

---

---

# 🔧 PROJECT AGENTS (17 Specialized)

---

## Project Agent 1: `code-reviewer` ⭐
**Model**: Sonnet
**Priority**: HIGH (Quality Gate)

**Purpose**:
Validate implementation correctness, diff quality, logic, performance, testing, best practices

**Expertise**:
- Logic errors and edge cases
- Performance optimization
- Test coverage adequacy
- Code readability and maintainability
- Language-specific idioms

**When to use**:
- ✅ Before merging pull requests
- ✅ After implementing complex features
- ✅ When fixing bugs (validate the fix doesn't create new issues)
- ✅ Code quality validation
- ❌ NOT for architectural decisions (→ tech-lead)
- ❌ NOT for security (→ security-reviewer)

**ChatGPT Instructions**:
```
When user says: "Review this code" or "Is this implementation correct?"
→ Launch code-reviewer agent via Claude Code

Example prompt for Claude Code:
"Review the changes in /src/webapi.py focusing on:
1. Logic correctness in the SSE streaming implementation
2. Error handling in the authentication flow
3. Any performance regressions
4. Test coverage for new code"
```

**Claude Code Instructions (for Lead Architect)**:
- Invoke code-reviewer for all PRs before merging
- Use as quality gate before shipping features
- Focus on: correctness > perfection
- Severity levels: CRITICAL (must fix), HIGH (should fix), MEDIUM (consider), LOW (nice-to-have)

---

## Project Agent 2: `security-reviewer` ⭐
**Model**: Sonnet
**Priority**: CRITICAL

**Purpose**:
Identify vulnerabilities, injection attacks, auth/authz flaws, cryptographic issues, compliance

**Expertise**:
- OWASP Top 10 vulnerabilities
- Injection prevention
- Authentication/authorization patterns
- Cryptographic security
- Compliance (GDPR, HIPAA, SOC2, PCI-DSS)
- Secret management

**When to use**:
- ✅ All authentication/authorization code
- ✅ Before any production deployment
- ✅ When handling sensitive data
- ✅ API endpoint security validation
- ✅ Dependency vulnerability checking

**ChatGPT Instructions**:
```
When user mentions: "security", "auth", "vulnerability", "compliance"
→ Launch security-reviewer agent via Claude Code

Example prompt for Claude Code:
"Security audit of the new OAuth flow:
1. Check CSRF protection with state parameters
2. Verify JWT token validation
3. Ensure secrets not in code/logs
4. Validate SQL injection prevention
5. Check compliance with GDPR for user data"
```

**Claude Code Instructions (for Lead Architect)**:
- ALWAYS use before production deployment
- Non-negotiable for: auth code, API endpoints, data handling
- Block deployment if CRITICAL or HIGH vulnerabilities found
- Use as safety guardrail

---

## Project Agent 3: `tech-lead` ⭐
**Model**: Sonnet
**Priority**: HIGH (Architectural Gatekeeper)

**Purpose**:
Ensure architectural alignment, sprint integrity, technical standards, roadmap adherence

**Expertise**:
- Locked architectural decisions enforcement
- Sprint scope validation
- Design pattern consistency
- Technical debt tracking
- Roadmap alignment
- Cross-sprint coordination

**When to use**:
- ✅ Before starting new features (scope validation)
- ✅ Architectural design reviews
- ✅ Before changing locked decisions
- ✅ Sprint planning and boundary enforcement
- ✅ Cross-team impact assessment

**ChatGPT Instructions**:
```
When user asks: "Should we...?" or "Does this align with architecture?"
→ Launch tech-lead agent via Claude Code

Example prompt for Claude Code:
"Architectural review for Sprint 61b:
1. Validate Magic Box route fits our locked architecture
2. Check SSE streaming aligns with architecture decisions
3. Verify no scope creep beyond Sprint 61b
4. Confirm frontend (Vanilla JS) choice still optimal
5. Identify any technical debt impact"
```

**Claude Code Instructions (for Lead Architect)**:
- Use as "architecture police" - enforce locked decisions
- Reference ROADMAP.md locked architecture section
- Sprint scope: STRICT boundary enforcement
- Ask: "Does this advance sprint goal?" and "Is this scope creep?"

---

## Project Agent 4: `ux-reviewer` ⭐
**Model**: Sonnet
**Priority**: HIGH (User-Facing Quality)

**Purpose**:
Evaluate user experience, interface consistency, accessibility, telemetry, metrics

**Expertise**:
- WCAG 2.1 accessibility compliance
- User flow validation
- Interface consistency
- Telemetry/event design
- Error messaging
- Mobile responsiveness
- Performance perception

**When to use**:
- ✅ All user-facing features before shipping
- ✅ Before design handoff to frontend
- ✅ Accessibility validation
- ✅ Telemetry/metrics design
- ✅ Mobile experience validation

**ChatGPT Instructions**:
```
When user says: "How should the UI look?" or "Is this good UX?"
→ Launch ux-reviewer agent via Claude Code

Example prompt for Claude Code:
"UX review for Magic Box /magic page:
1. Validate user flow: confusion points?
2. Check accessibility: keyboard nav, screen readers
3. Review error messages: clear and actionable?
4. Telemetry: What metrics tell us if it works?
5. Mobile: Does it work on iPhone SE?"
```

**Claude Code Instructions (for Lead Architect)**:
- Invoke for all user-facing changes
- Non-negotiable for: new pages, major flows, accessibility
- Focus on: user-perceived quality
- Deliverable: UI/UX recommendations, not implementation

---

## Project Agent 5: `supabase-auth-security` ⭐
**Model**: Sonnet
**Priority**: HIGH

**Purpose**:
Design Supabase authentication systems, API key management, session architecture, RBAC, encryption

**Expertise**:
- OAuth 2.0 flows (magic links, social login)
- JWT token management and validation
- Session architecture (anonymous, authenticated, upgrades)
- Row-Level Security (RLS) policies
- API key encryption and rotation
- RBAC design and enforcement

**When to use**:
- ✅ Auth flow implementation
- ✅ Supabase configuration
- ✅ Session management patterns
- ✅ JWT token design
- ✅ RLS policy creation
- ✅ Anonymous session architecture

**ChatGPT Instructions**:
```
When user says: "Supabase", "authentication", "session"
→ Launch supabase-auth-security agent via Claude Code

Example prompt for Claude Code:
"Design anonymous→registered session upgrade:
1. How do we preserve user data during auth?
2. Session token refresh strategy?
3. RLS policy for workspace isolation?
4. Error handling for auth failures?"
```

**Claude Code Instructions (for Lead Architect)**:
- Use for all auth/session related work
- Reference Supabase locked architecture decision
- Ensure defense-in-depth (multiple security layers)
- Coordinate with: anonymous-sessions-architect, multi-tenancy-architect

---

## Project Agent 6: `streaming-specialist`
**Model**: Haiku
**Priority**: HIGH (Sprint 61a Critical Path)

**Purpose**:
Design reliable streaming, SSE systems, auto-reconnection, message deduplication, resilience

**Expertise**:
- Server-Sent Events (SSE) implementation
- Auto-reconnection with exponential backoff
- Message deduplication and ordering
- Stream buffering and compression
- Network resilience patterns
- 99%+ stream completion rates

**When to use**:
- ✅ SSE streaming implementation (Magic Box)
- ✅ Real-time message delivery
- ✅ Stream reliability optimization
- ✅ Network interruption handling
- ✅ Performance under poor network conditions

**ChatGPT Instructions**:
```
When user mentions: "streaming", "SSE", "real-time"
→ Launch streaming-specialist agent via Claude Code

Example prompt for Claude Code:
"SSE implementation for Magic Box /magic page:
1. Auto-reconnection strategy for stalled streams?
2. Message deduplication with event IDs?
3. How to detect network stalls?
4. Compression to reduce bandwidth?
5. Target 99.9% stream completion rate"
```

**Claude Code Instructions (for Lead Architect)**:
- Critical for R0.5 (Magic Box) sprint
- Invoke early in stream implementation
- Test extensively: poor networks, interruptions, mobile handoffs
- Deliverable: Production-ready SSE client with resilience

---

## Project Agent 7: `safe-action-detector`
**Model**: Haiku
**Priority**: HIGH (Sprint 61a - Magic Box)

**Purpose**:
Classify actions as safe (auto-execute), privileged (require approval), or dangerous (block)

**Expertise**:
- Intent classification algorithms
- Risk scoring methodology
- Natural language pattern matching
- Safe action vs. privileged action boundaries
- Approval workflow design
- False positive/negative minimization

**When to use**:
- ✅ Designing action safety detection
- ✅ Intent classification for AI-generated actions
- ✅ Approval workflow design
- ✅ Risk scoring for user commands

**ChatGPT Instructions**:
```
When user asks: "How do we know if an action is safe?"
→ Launch safe-action-detector agent via Claude Code

Example prompt for Claude Code:
"Design action detection for Magic Box:
1. What actions are SAFE (read, search, analyze)?
2. What actions are PRIVILEGED (write, send, delete)?
3. What actions are DANGEROUS (block immediately)?
4. Risk scoring: how confident are we?
5. False positive minimization strategy?"
```

**Claude Code Instructions (for Lead Architect)**:
- Critical for Magic Box safety guarantees
- Classify ALL user intents
- Conservative default (when uncertain, ask for approval)
- Integrate with approval workflow

---

## Project Agent 8: `repo-guardian` ⭐ NEW
**Model**: Haiku
**Priority**: HIGH (Deployment Safety)

**Purpose**:
Monitor GitHub activity and enforce deployment safety, branch hygiene, CI/test validation, and security gates for safe production deployments

**Expertise**:
- Branch protection and hygiene validation
- PR quality checks and approvals
- CI/test success verification (unit, streaming, security)
- Security gate status monitoring
- Performance budget enforcement
- Branch→environment mapping (release/* → staging, main → production)
- Pre-merge and pre-deployment validation
- Sensitive path detection (security/streaming/UI-critical areas)

**When to use**:
- ✅ Before merging to main or release/* branches
- ✅ Before deploying to Railway (production or staging)
- ✅ Validating branch protection rules
- ✅ PR safety gates before shipping
- ✅ Post-merge verification before rollout

**ChatGPT Instructions**:
```
When user says: "Ready to merge", "Deploying to production", "PR ready?"
→ Launch repo-guardian agent via Claude Code

Example prompt for Claude Code:
"Validate PR #487 targeting main before merge:
1. Required approvals from CODEOWNERS present?
2. CI tests all green (unit, streaming, security)?
3. Security scanning with no critical/high issues?
4. Branch freshness: up-to-date with target?
5. Service worker cache bump if UI changed?"
```

**Claude Code Instructions (for Lead Architect)**:
- Invoke before ANY merge to main or release/*
- Invoke before ANY Railway deployment
- Default to BLOCKED on uncertainty (fail-closed)
- Enforce branch→environment mapping strictly
- Require explicit labels for security/performance-sensitive paths
- Verify sensitive paths (src/stream/**, auth/**, src/webapi.py) have proper labels

---

## Project Agent 9: `memory-architect`
**Model**: Haiku
**Priority**: HIGH (R1 - Memory & Context)

**Purpose**:
Design memory systems, thread summarization, entity extraction, contextual recall, knowledge graphs

**Expertise**:
- Thread summarization algorithms
- Entity extraction and NER
- Vector embeddings and similarity search
- Knowledge graph construction
- Context windowing strategies
- Memory compression and temporal decay
- Privacy-preserving memory storage

**When to use**:
- ✅ Memory system architecture (R1)
- ✅ Summarization strategies
- ✅ Entity extraction design
- ✅ Recall optimization
- ✅ Knowledge graph design

**ChatGPT Instructions**:
```
When user mentions: "memory", "summarization", "context"
→ Launch memory-architect agent via Claude Code

Example prompt for Claude Code:
"Design memory system for R1:
1. When do we summarize (every N messages)?
2. What entities to extract (people, projects, dates)?
3. How to recall 'As we discussed earlier'?
4. Privacy: encrypt memories, user controls?
5. Storage efficiency: compression strategies?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare architecture early (before R1 sprint)
- Coordinate with: memory-architect for design details
- Consider: vector embeddings, temporal decay, encryption

---

## Project Agent 10: `frontend-performance`
**Model**: Haiku
**Priority**: MEDIUM-HIGH

**Purpose**:
Optimize frontend performance, achieve Core Web Vitals targets, code splitting, lazy loading

**Expertise**:
- Performance budgets and metrics
- Bundle optimization and code splitting
- Lazy loading and virtual scrolling
- Core Web Vitals optimization (LCP, FID, CLS)
- Service Workers and caching
- Memory management and leak detection
- Performance profiling and monitoring

**When to use**:
- ✅ Performance optimization (Sprint 61a has TTFV < 1.5s target)
- ✅ Core Web Vitals targets
- ✅ Bundle size management
- ✅ Lazy loading strategies
- ✅ Mobile performance

**ChatGPT Instructions**:
```
When user asks: "How fast?" or "Performance?"
→ Launch frontend-performance agent via Claude Code

Example prompt for Claude Code:
"Optimize Magic Box for TTFV < 1.5s:
1. Current performance baseline?
2. Critical path analysis
3. Code splitting opportunities?
4. Lazy loading for non-critical code?
5. Image optimization?"
```

**Claude Code Instructions (for Lead Architect)**:
- TTFV target: < 1.5s (Sprint 61a commitment)
- Use for all user-facing pages
- Measure on: Slow 3G, iPhone SE, Android mid-range
- Deliverable: Performance budget and optimization plan

---

## Project Agent 11: `cost-optimizer`
**Model**: Haiku
**Priority**: MEDIUM

**Purpose**:
Real-time token counting, cost calculation, model selection, budget optimization

**Expertise**:
- Token counting (OpenAI, Anthropic)
- Model pricing structures
- Cost accumulation and prediction
- Streaming cost updates
- Token optimization techniques
- Model comparison for cost-effectiveness

**When to use**:
- ✅ Implementing cost tracking (on UI)
- ✅ Model selection decisions
- ✅ Cost optimization opportunities
- ✅ Token budget allocation
- ✅ Pricing display to users

**ChatGPT Instructions**:
```
When user asks: "Cost?" or "How much token?"
→ Launch cost-optimizer agent via Claude Code

Example prompt for Claude Code:
"Implement cost tracking for Magic Box:
1. Show cost pill during streaming
2. Tokens per model (GPT-4o vs Claude vs Haiku)?
3. User cost budget management?
4. Cost forecasting (hourly, daily)?
5. Cost optimization recommendations?"
```

**Claude Code Instructions (for Lead Architect)**:
- Essential for transparency (cost pill always visible)
- Track real-time cost during streaming
- Recommend model selection (cost vs. quality)
- Report daily/monthly costs

---

## Project Agent 12: `data-connector-architect`
**Model**: Haiku
**Priority**: HIGH (R3 - Connectors)

**Purpose**:
Design multi-source data connectors, OAuth flows, incremental sync, conflict resolution, privacy-preserving indexing

**Expertise**:
- OAuth 2.0 and authentication flows
- API integration architecture
- Incremental sync algorithms
- Conflict resolution
- Rate limiting and backoff
- Data deduplication
- Privacy-preserving indexing
- Unified search

**When to use**:
- ✅ Connector architecture (R3)
- ✅ OAuth flow implementation
- ✅ Sync strategy design
- ✅ Conflict resolution
- ✅ Privacy-preserving indexing
- ✅ Extending to new data sources

**ChatGPT Instructions**:
```
When user mentions: "connector", "sync", "Google Drive", "Notion"
→ Launch data-connector-architect agent via Claude Code

Example prompt for Claude Code:
"Design connector for Google Drive (R3):
1. OAuth 2.0 flow for Drive/Gmail?
2. Incremental sync with minimal API calls?
3. Handle file renames, deletions, permissions?
4. Deduplication across drives?
5. Privacy: user data stays encrypted?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare early (before R3 sprint Nov 18)
- Design OAuth first (security critical)
- Plan incremental sync (minimize API costs)
- Implement privacy-by-default

---

## Project Agent 13: `knowledge-retrieval-architect` ⭐ NEW
**Model**: Haiku
**Priority**: HIGH (R2 - Files & Knowledge)

**Purpose**:
Design RAG (Retrieval-Augmented Generation) systems, citation accuracy, hallucination prevention

**Expertise**:
- Document retrieval pipelines
- Relevance ranking and reranking
- Citation tracking and verification
- Hallucination detection
- Context window optimization
- Multi-document synthesis
- Chunking strategies

**When to use**:
- ✅ RAG system architecture (R2)
- ✅ Document retrieval strategy
- ✅ Citation accuracy design
- ✅ Hallucination prevention
- ✅ Relevance ranking

**ChatGPT Instructions**:
```
When user asks: "How do we cite sources?" or "Users have documents"
→ Launch knowledge-retrieval-architect agent via Claude Code

Example prompt for Claude Code:
"Design RAG for R2 (Files & Knowledge):
1. Chunking strategy: chunk size and overlap?
2. Retrieval pipeline: BM25 + semantic?
3. Relevance ranking: how to order results?
4. Citation extraction: traceable to source passage?
5. Hallucination detection: verify claims in documents?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare before R2 sprint (Nov 11)
- Citation accuracy non-negotiable
- Design hallucination detection
- Test with real user documents

---

## Project Agent 14: `multi-tenancy-architect` ⭐ NEW
**Model**: Haiku
**Priority**: HIGH (R4 - Cockpit, team features)

**Purpose**:
Design workspace isolation, RBAC, permission boundaries, team sharing, multi-org patterns

**Expertise**:
- Workspace and data isolation
- Role-based access control (RBAC)
- Row-Level Security (RLS) policies
- Permission boundaries and inheritance
- Team sharing and guest access
- Audit logging for compliance
- Multi-organization patterns

**When to use**:
- ✅ Team sharing features (R4)
- ✅ Permission architecture
- ✅ Workspace isolation
- ✅ Multi-tenancy design
- ✅ RBAC implementation

**ChatGPT Instructions**:
```
When user says: "Teams", "sharing", "permissions", "workspace"
→ Launch multi-tenancy-architect agent via Claude Code

Example prompt for Claude Code:
"Design team sharing for R4 (Cockpit):
1. How to isolate team data (RLS policies)?
2. Role hierarchy: Owner > Admin > Member > Guest?
3. Permission inheritance for nested resources?
4. How to share thread with team member securely?
5. Audit trail: who accessed what when?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare before R4 sprint (Dec 2)
- Security critical: data isolation is non-negotiable
- Design RBAC early (complex when retrofitted)
- Coordinate with: supabase-auth-security for RLS

---

## Project Agent 15: `observability-architect` ⭐ NEW
**Model**: Haiku
**Priority**: MEDIUM-HIGH (R4 - Cockpit)

**Purpose**:
Design monitoring, alerting, dashboards, SLI/SLO/SLAs, incident response

**Expertise**:
- Metrics collection and pipeline
- Alert threshold design
- Dashboard architecture
- SLI/SLO/SLA definition
- Distributed tracing
- Incident response playbooks
- Cost analytics
- Anomaly detection

**When to use**:
- ✅ Monitoring and alerting design (R4)
- ✅ Dashboard implementation
- ✅ SLO target setting
- ✅ Cost analytics dashboard
- ✅ Incident response planning

**ChatGPT Instructions**:
```
When user asks: "How do we know if we're healthy?" or "Build cost dashboard"
→ Launch observability-architect agent via Claude Code

Example prompt for Claude Code:
"Design observability for production:
1. Golden Signals: latency, traffic, errors, saturation?
2. SLOs: availability, latency, cost targets?
3. Dashboards: ops, devs, executives, cost?
4. Alerts: when to page on-call engineer?
5. Incident response: runbooks for common issues?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare before R4 (Dec 2)
- Focus on: user-impacting metrics
- Design cost analytics dashboard
- Implement incident response playbooks

---

## Project Agent 16: `file-system-connector-specialist` ⭐ NEW
**Model**: Haiku
**Priority**: MEDIUM (R3 - Local Sync)

**Purpose**:
Design File System Access API integration, local file sync, change detection, permissions

**Expertise**:
- Chrome File System Access API
- Permission request UX
- File change detection
- Incremental sync (polling, hashing, hybrid)
- Local indexing and search
- Conflict resolution (local vs. remote)
- Error handling and resilience

**When to use**:
- ✅ Local folder sync implementation (R3)
- ✅ File change detection design
- ✅ Permission request flow
- ✅ Local indexing strategy
- ✅ Sync conflict resolution

**ChatGPT Instructions**:
```
When user mentions: "local folder", "File System API", "sync files"
→ Launch file-system-connector-specialist agent via Claude Code

Example prompt for Claude Code:
"Design local folder sync (R3):
1. Permission request UX: how to ask user?
2. Change detection: efficient polling or hash?
3. Sync strategy: incremental or full?
4. Conflict: file changed locally AND remotely?
5. Search: fast indexing of local files?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare before R3 sprint (Nov 18)
- Focus on UX (permission requests)
- Design efficient change detection
- Handle edge cases: permission denied, quota exceeded

---

## Project Agent 17: `next-js-architect` ⭐ NEW (SONNET - Quality Requirement)
**Model**: Sonnet
**Priority**: HIGH (R4 - Cockpit)

**Purpose**:
Architect Next.js full-stack applications, App Router, Server Components, data fetching strategies

**Expertise**:
- Next.js 14+ App Router architecture
- Server vs. Client Components strategy
- Server Actions and data fetching
- Streaming and Suspense
- Authentication middleware
- Performance optimization (Core Web Vitals)
- Deployment and infrastructure

**When to use**:
- ✅ Cockpit full-stack app architecture (R4)
- ✅ Next.js design decisions
- ✅ Server Component vs. Client Component
- ✅ Data fetching strategy
- ✅ Middleware and routing

**ChatGPT Instructions**:
```
When user mentions: "Next.js", "Cockpit", "full app"
→ Launch next-js-architect agent via Claude Code

Example prompt for Claude Code:
"Design Cockpit app structure (R4):
1. App Router structure for multi-tenant?
2. Server Components for data fetching?
3. Middleware for auth and workspace routing?
4. Data fetching: Server Components, API routes, Server Actions?
5. Streaming for faster page loads?"
```

**Claude Code Instructions (for Lead Architect)**:
- Prepare early (before R4 sprint Dec 2)
- Use Sonnet for architectural complexity
- Design for: multi-tenancy, type safety, performance
- Deliverable: Architecture document, folder structure, patterns

---

## Project Agent 18: `anonymous-sessions-architect` ⭐ NEW
**Model**: Haiku
**Priority**: MEDIUM-HIGH (R0.5 - Magic Box, but core to conversion)

**Purpose**:
Design anonymous session flows, session upgrade patterns, quota management, onboarding

**Expertise**:
- Anonymous session lifecycle
- Session upgrade architecture (anon → registered)
- Data preservation during signup
- Quota and rate limiting
- Conversion funnel optimization
- Conflict resolution (duplicate accounts)
- Session storage strategies

**When to use**:
- ✅ Anonymous session design (R0.5 Magic Box)
- ✅ Signup flow design
- ✅ Quota management
- ✅ Data preservation during auth
- ✅ Conversion optimization

**ChatGPT Instructions**:
```
When user says: "Anonymous users", "session limits", "signup flow"
→ Launch anonymous-sessions-architect agent via Claude Code

Example prompt for Claude Code:
"Design anonymous sessions for Magic Box:
1. Session limits: 20 msgs/hour, 100 total, 5MB, 7 days?
2. Upgrade flow: how to preserve data when signing up?
3. OAuth signup: merge or keep separate?
4. Quota enforcement: clear error messages?
5. Conversion: at what point do we ask to sign up?"
```

**Claude Code Instructions (for Lead Architect)**:
- Critical for R0.5 launch
- Design low-friction entry (no signup required)
- Implement quota enforcement with warnings
- Focus on: smooth anonymous → registered transition
- Coordinate with: supabase-auth-security for upgrade flow

---

---

## 🗺️ Agent Deployment by Release

### R0.5: Magic Box (Oct 21-28) - CURRENT
**Primary Agents**:
- streaming-specialist (SSE implementation)
- safe-action-detector (action detection)
- cost-optimizer (cost tracking)
- anonymous-sessions-architect (quotas, session limits)
- frontend-performance (TTFV < 1.5s)
- ux-reviewer (user flow validation)

**Support Agents**:
- supabase-auth-security (anonymous sessions)
- code-reviewer (quality gate)
- security-reviewer (auth validation)
- tech-lead (scope enforcement)

---

### R1: Memory & Context (Nov 4-11)
**Primary Agents**:
- memory-architect (summarization, entity extraction)
- observability-architect (memory quality metrics)

**Support Agents**:
- code-reviewer, ux-reviewer, tech-lead

---

### R2: Files & Knowledge (Nov 11-18)
**Primary Agents**:
- knowledge-retrieval-architect (RAG, citations)
- frontend-performance (search UX)

**Support Agents**:
- observability-architect (search metrics), ux-reviewer, code-reviewer

---

### R3: Connectors (Nov 18-25)
**Primary Agents**:
- data-connector-architect (OAuth, sync, search)
- file-system-connector-specialist (local sync)

**Support Agents**:
- security-reviewer, cost-optimizer, observability-architect

---

### R4: Cockpit (Dec 2+)
**Primary Agents**:
- next-js-architect (full-stack app)
- multi-tenancy-architect (team sharing, RBAC)
- observability-architect (monitoring, cost dashboard)

**Support Agents**:
- supabase-auth-security, ux-reviewer, code-reviewer, tech-lead

---

---

# 🎓 INSTRUCTIONS FOR CHATGPT

## How to Use This Guide

1. **Read this document and save to memory**:
   - Understand the 21 agents available
   - Remember which agents are for which tasks
   - Reference this when Claude Code needs specific expertise

2. **When Claude Code reports a problem or decision point**:
   - Use the Quick Reference decision tree at the top
   - Identify which agent would help
   - In your response to Claude Code, include: `/claude-code-task [agent-name] "[task description]"`

3. **Remember context across conversations**:
   - Relay mission: Complete app from Magic Box through Cockpit
   - Current focus: R0.5 Magic Box (Sprint 61b - UI/UX polish)
   - Locked architecture: See ROADMAP.md
   - Team: Claude Code is lead architect, you are coordination layer

---

## Example: How to Invoke an Agent from Claude Code

When you have Claude Code do work and you want specialized agent input:

```
Claude Code has implemented the SSE streaming but reports "stalled connections on mobile."

→ You recognize this as a streaming-specialist problem
→ In your response, include for Claude Code:

"For the mobile stall issue, consult the streaming-specialist agent on
resilience strategies for poor networks. This likely requires:
- Heartbeat/keep-alive implementation
- Stall detection with automatic reconnection
- Testing on real throttled networks (Slow 3G)"
```

---

## Starting Prompt for Sprint 61b

**Use this prompt to launch Sprint 61b focus on UI/UX:**

```
Claude Code, I've updated the agent guide with 6 new specialists.
You now have 21 agents available to complete the Relay mission.

IMMEDIATE PRIORITY: Sprint 61b - UI/UX Polish & Refinement
(Builds on Sprint 61a Magic Box implementation)

Focus Areas:
1. User Experience Polish
   - Refine /magic page UX (streaming, cost pill, action buttons)
   - Smooth anonymous → registered flow
   - Error messaging clarity
   → Primary: ux-reviewer

2. Performance Tuning
   - Measure TTFV on target devices (iPhone SE, mid-range Android)
   - Optimize bundle size and code splitting
   - Test on Slow 3G and 4G networks
   → Primary: frontend-performance

3. Streaming Reliability
   - Test SSE reconnection on poor networks
   - Verify 99.9% stream completion rate
   - Mobile network handoff handling
   → Primary: streaming-specialist

4. Quality Assurance
   - Code review of new UI components
   - Security validation of action detection
   - Architectural alignment check
   → Primary: code-reviewer, security-reviewer, tech-lead

Next Steps:
1. Launch ux-reviewer for /magic page UX assessment
2. Run frontend-performance profile on current implementation
3. Validate streaming-specialist checklist for reliability
4. Execute code-reviewer + security-reviewer gates

Deadline: Oct 21-28, 2025 (end of Sprint 61b)
Launch with: "Start with ux-reviewer assessment of /magic page"
```

---

## Key Agent Coordination Patterns

### Pattern 1: Feature Implementation (Start → Complete)
```
1. tech-lead: Scope check (is this in sprint scope?)
2. ux-reviewer: Design review (is UX good?)
3. (code-reviewer during implementation)
4. security-reviewer: Security check (before merge)
5. (code-reviewer final check)
6. tech-lead: Architecture alignment (before shipping)
```

### Pattern 2: Production Deployment
```
1. code-reviewer: Implementation quality
2. security-reviewer: Vulnerability scan
3. tech-lead: Architecture check
4. observability-architect: Monitoring ready?
5. frontend-performance: Performance acceptable?
6. Deploy with confidence
```

### Pattern 3: Complex Feature (Multi-Release)
```
R0: tech-lead scope check
    → ux-reviewer design validation
    → code-reviewer implementation
    → security-reviewer auth/data flows

R1+: data-connector-architect (connectors)
     → memory-architect (summarization)
     → knowledge-retrieval-architect (citations)
     → multi-tenancy-architect (team sharing)
     → next-js-architect (cockpit)
```

---

## When to Use Each Agent

### Always Use (Non-Negotiable)
- **Before production**: security-reviewer (ALWAYS)
- **Before merge**: code-reviewer (quality gate)
- **Architectural decisions**: tech-lead (scope/alignment)
- **User-facing features**: ux-reviewer (UX quality)

### Use Proactively (Quality Improvement)
- **Performance issues**: frontend-performance
- **Real-time features**: streaming-specialist
- **Auth/session work**: supabase-auth-security
- **Cost concerns**: cost-optimizer
- **New connectors**: data-connector-architect

### Use for Preparation (Before Sprint)
- **Memory system** (R1): memory-architect + knowledge-retrieval-architect
- **Cockpit** (R4): next-js-architect + multi-tenancy-architect + observability-architect
- **Connectors** (R3): data-connector-architect + file-system-connector-specialist

---

## Remember These Key Facts

1. **Current Release**: R0.5 (Magic Box) - Sprint 61b
2. **Locked Decisions** (Don't change without RFC):
   - Auth: Supabase
   - Embedding: text-embedding-3-small
   - Frontend: Vanilla JS (Magic), Next.js (Cockpit)
   - Stream: SSE
3. **Quality Targets**:
   - TTFV: < 1.5s
   - Stream completion: > 99.9%
   - Citation accuracy: > 95%
   - Anonymous → Registered conversion: > 20%
4. **Agent Models**:
   - Sonnet: Complex architectural/security decisions
   - Haiku: Pattern-based, specialized guidance
5. **Coordination**: You orchestrate agents, Claude Code executes

---

**Document Version**: 1.0
**Last Updated**: October 18, 2025
**Next Review**: After Sprint 61b (Oct 21-28)
