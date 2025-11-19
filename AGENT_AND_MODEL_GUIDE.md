# Relay AI – Agent & Model Invocation Guide (Persistent Reference)

This document defines the manual model-selection protocol and the required agent-engagement rules for all Claude Code sessions working on the Relay AI Orchestrator.

It MUST be reviewed at the beginning of every Claude Code session.

---

## 1. Manual Model Escalation Rules

Relay uses manual model selection. Claude must NEVER auto-escalate models.

### 🎯 Default Model (use unless told otherwise)
- **claude-3.5-haiku**  
  Fast, cheap, ideal for routine diffs, plumbing, light reviews.

### 🚀 Strong Model (use when deeper reasoning required)
- **claude-3.5-sonnet-20241022**  
  Use for:
  - Infrastructure changes  
  - SSE, telemetry, concurrency  
  - Security reviews  
  - Migration sequencing  
  - Anything touching auth, secrets, tokens  

### 🛡 Ultra Model (ONLY with explicit instruction)
- **claude-3-opus-20240307**  
  Use ONLY when:
  - Architecture direction debates
  - Multi-system reasoning
  - High-risk migrations or irreversible design decisions

### 🤖 OpenAI Models (manual selection only)

| Logical Key      | Provider Model ID      | Purpose |
|------------------|-------------------------|---------|
| `gpt-fast`       | `gpt-4o-mini`           | Fast OpenAI mode |
| `gpt-balanced`   | `gpt-4o`                | Default balanced |
| `gpt-ultra`      | `gpt-5.1`               | Heavy reasoning |
| `claude-fast`    | `claude-3.5-haiku`      | Anthropic fast |
| `claude-strong`  | `claude-3.5-sonnet`     | Anthropic strong |
| `claude-ultra`   | `claude-3-opus`         | Anthropic ultra |

Always call the **logical key**; Relay resolves the provider model ID.

---

## 2. Agent Engagement Rules – All 25 Agents

Relay has **25 specialized agents**. Each has ONE specific trigger and use case. Engage BEFORE writing code.

---

### 🔄 **CORE CODE QUALITY (4 agents)**

#### 🔧 **code-reviewer**
**Trigger:** Any code diff, refactor, rewrite, or new module
**Specific Use Case:** Reviews implementation correctness, logic errors, performance issues, readability, maintainability against project standards
**Question It Answers:** "Is this code correct and maintainable?"

#### 🛡 **security-reviewer**
**Trigger:** Error handlers, logging, auth, secrets, migrations, request validation, model resolution
**Specific Use Case:** Identifies injection attacks, permission flaws, input sanitization gaps, cryptographic issues, compliance violations
**Question It Answers:** "Could this code leak secrets, allow injection, or bypass auth?"

#### 🎓 **tech-lead**
**Trigger:** Architecture decisions, cross-module design, sprint sequencing, coordinating multiple agents
**Specific Use Case:** Ensures consistency with locked architectural decisions, prevents scope creep, validates sprint alignment, technical strategy
**Question It Answers:** "Does this align with our architecture and long-term roadmap?"

#### 📊 **ux-reviewer**
**Trigger:** UI endpoints, SSE behavior, stream reconnection, user flows, telemetry
**Specific Use Case:** Evaluates usability, accessibility compliance, data-driven metrics collection, user experience consistency
**Question It Answers:** "Is this user experience intuitive and properly instrumented?"

---

### 🏗 **INFRASTRUCTURE & PLATFORM (6 agents)**

#### 🔌 **next-js-architect**
**Trigger:** Full-stack Next.js work (App Router, data fetching, streaming, Suspense)
**Specific Use Case:** Designs app structure, implements streaming/progressive rendering, optimizes server components, handles middleware patterns
**Question It Answers:** "What's the optimal Next.js architecture for this feature?"

#### 🏢 **multi-tenancy-architect**
**Trigger:** Workspace isolation, RBAC, team sharing, row-level security, org data segregation
**Specific Use Case:** Designs permission boundaries, implements role inheritance, creates capability-based access control models
**Question It Answers:** "How do we keep teams' data isolated and permissions consistent?"

#### 🔐 **supabase-auth-security**
**Trigger:** Authentication systems, API key management, session architecture, encryption, user flow
**Specific Use Case:** Implements OAuth/magic links, designs session upgrades (anon→auth), BYO key encryption, JWT management
**Question It Answers:** "How do we authenticate and encrypt securely with Supabase?"

#### 🗄 **observability-architect**
**Trigger:** Monitoring systems, dashboards, alerting strategies, SLA/SLO metrics, incident response, telemetry pipelines
**Specific Use Case:** Designs health metrics, implements end-to-end tracing, creates cost analytics dashboards, sets alerting thresholds
**Question It Answers:** "How do we know if the system is healthy and meeting SLOs?"

#### ⚡ **streaming-specialist**
**Trigger:** Real-time communication, Server-Sent Events (SSE), network interruptions, stream resilience
**Specific Use Case:** Implements auto-reconnection with exponential backoff, message deduplication, stream buffering, corporate proxy fallbacks
**Question It Answers:** "How do we ensure 99%+ stream completion even on poor networks?"

#### 🚀 **frontend-performance**
**Trigger:** Performance targets, Core Web Vitals, code splitting, lazy loading, memory leaks
**Specific Use Case:** Implements virtual scrolling, bundle optimization, compression, performance profiling, aggressive performance targets
**Question It Answers:** "How do we achieve sub-1.5s Time to First Value?"

---

### 🔗 **DATA & CONNECTORS (4 agents)**

#### 🧠 **knowledge-retrieval-architect**
**Trigger:** RAG systems, document retrieval, citation accuracy, hallucination reduction, relevance ranking
**Specific Use Case:** Implements retrieval verification, confidence scoring, multi-document ranking, cache strategies
**Question It Answers:** "How do we make RAG accurate and cite-able?"

#### 🧠 **memory-architect**
**Trigger:** Intelligent memory systems, thread summarization, entity extraction, knowledge graphs, context recall
**Specific Use Case:** Implements thread summarization algorithms, entity/relationship tracking, vector embeddings, temporal decay
**Question It Answers:** "How do we maintain persistent context across long conversations?"

#### 🔗 **data-connector-architect**
**Trigger:** Multi-source data connectors, OAuth flows, incremental sync, conflict resolution, deduplication
**Specific Use Case:** Designs secure auth, implements rate limiting, builds conflict resolution, ensures privacy-preserving indexing
**Question It Answers:** "How do we sync data from multiple sources securely and efficiently?"

#### 💾 **file-system-connector-specialist**
**Trigger:** Local file system sync, File System Access API, permission requests, incremental file sync, change detection
**Specific Use Case:** Designs permission UX, implements file change detection with diff tracking, local indexing
**Question It Answers:** "How do we sync local files safely and efficiently?"

---

### 💰 **OPTIMIZATION & EFFICIENCY (3 agents)**

#### 💵 **cost-optimizer**
**Trigger:** Token counting, cost calculation, AI model usage tracking, budget forecasting
**Specific Use Case:** Implements real-time token counting, cost accumulation, model cost comparison, transparent pricing
**Question It Answers:** "What's the actual token cost of this operation?"

#### 🛡 **safe-action-detector**
**Trigger:** Intent classification, risk scoring, auto-execution vs. approval workflows
**Specific Use Case:** Classifies user intents as safe (auto-execute) or privileged (require approval), minimizes false positives
**Question It Answers:** "Is this action safe to auto-execute or does it need approval?"

#### ⚠️ **rate-limiter-architect** (Alias: Rate Limits & Abuse Prevention)
**Trigger:** Rate limiting, quota enforcement, abuse prevention, DDoS mitigation
**Specific Use Case:** Implements per-user/per-IP quotas, sliding window algorithms, burst handling, abuse detection
**Question It Answers:** "How do we prevent abuse while allowing legitimate usage?"

---

### 🔍 **EXPLORATION & ANALYSIS (4 agents)**

#### 🔎 **Explore-Agent**
**Trigger:** Need to quickly understand codebase structure, find files by pattern, answer "how do X work?"
**Specific Use Case:** Fast searches across codebases, pattern matching (e.g., "src/components/**/*.tsx"), multi-location analysis
**Question It Answers:** "What files match this pattern or contain this concept?"

#### 📋 **project-historian**
**Trigger:** Verify no duplicate work, check what's been completed, audit scope creep, review work from other AI models
**Specific Use Case:** Maintains task continuity, prevents duplicate implementations, validates alignment with roadmap
**Question It Answers:** "Has this feature already been implemented?"

#### 🤔 **general-purpose**
**Trigger:** Complex research questions, multi-step reasoning, code search, exploring unknown domains
**Specific Use Case:** General-purpose reasoning, multi-round investigation, open-ended exploration
**Question It Answers:** "What's the answer to this complex question?"

#### 🔐 **repo-guardian**
**Trigger:** Repository integrity, permission validation, governance rules
**Specific Use Case:** Ensures repo consistency, validates permissions, maintains governance compliance
**Question It Answers:** "Is this repo in a good state?"

---

### ⚙️ **SPECIALIZED SYSTEMS (4 agents)**

#### 🪜 **Plan-Agent**
**Trigger:** Planning implementation steps before writing code (similar to Explore)
**Specific Use Case:** Multi-step task planning, breaking down complex features, sequencing implementation
**Question It Answers:** "What's the step-by-step plan to implement this?"

#### 🔧 **statusline-setup**
**Trigger:** Configuring Claude Code status line settings
**Specific Use Case:** User status line configuration and optimization
**Question It Answers:** "How should my Claude Code status line be configured?"

#### 🖥️ **startup-app-manager**
**Trigger:** Computer startup issues, performance problems, app crashes, system sluggishness
**Specific Use Case:** Analyzes startup processes, identifies resource hogs, recommends app disabling/removal
**Question It Answers:** "What's slowing down my computer on boot?"

#### 📡 **agent-deployment-monitor**
**Trigger:** Proactively verify all agents are deployed and accessible at session start
**Specific Use Case:** Scans agent registry, validates deployment status across all projects, catches gaps immediately
**Question It Answers:** "Are all agents properly deployed and ready?"

---

### 📱 **EMERGING / SPECIALIZED (1 agent)**

#### 🎪 **anonymous-sessions-architect**
**Trigger:** Anonymous user flows, session upgrade patterns, data preservation during registration
**Specific Use Case:** Designs session merging, quota/limit enforcement, smooth anon→auth transitions
**Question It Answers:** "How do we handle anonymous users upgrading to registered accounts?"

---

## **Agent Decision Tree**

```
IF touching code?          → code-reviewer
IF touching security?      → security-reviewer
IF architecture/strategy?  → tech-lead
IF affecting UI/UX?        → ux-reviewer + observability-architect (if telemetry)
IF authentication?         → supabase-auth-security
IF database/migration?     → observability-architect (monitoring the change)
IF streaming/SSE?          → streaming-specialist
IF performance targets?    → frontend-performance
IF data connectors?        → data-connector-architect
IF RAG/retrieval?          → knowledge-retrieval-architect
IF memory/context?         → memory-architect
IF token costs?            → cost-optimizer
IF intent/approval?        → safe-action-detector
IF exploring codebase?     → Explore-Agent
IF checking progress?      → project-historian
```

**Rule:**
Identify the TOP 2-3 agents needed for your task BEFORE writing any code. Invoke them in parallel when possible.

---

## 3. What Claude Must Do Every Session

At the beginning of EVERY session, Claude must:

1. **Load & read this file**  
   Confirm by summarizing the rules back.

2. **Ask which model to use**  
   Never guess. Never escalate automatically.

3. **Ask which agents to initialize**  
   If unclear, propose options.

4. **Follow the diff discipline**  
   - max 200 LOC per diff  
   - tests before code  
   - no hidden changes  

---

## 4. Required Start Prompt for All Claude Code Work

Paste this at the start of each Claude session:

```
Before doing anything, load and review AGENT_AND_MODEL_GUIDE.md from the repo.

Ask me:
1. Which model I want to use for this session
2. Which agents to engage based on the guide
3. The task to complete

Do not auto-escalate models.

Follow all agent rules and diff discipline in the guide.
```

---

## 5. Enforcement

- If Claude forgets to load this file → stop and reload it.
- If Claude tries to auto-switch models → stop and ask for manual selection.
- If agents are skipped → stop and request correction.

---

This file serves as the authoritative protocol for model-selection and agent-invocation for all Relay AI development.
