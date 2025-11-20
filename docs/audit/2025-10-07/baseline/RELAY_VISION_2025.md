# Relay Vision: Sprint 48B → 100+ and Beyond

**Target Outcome:** Global AI company worth $10B+, preparing for IPO in Hong Kong, London, New York, or Australia
**Mission:** Change how people worldwide do business, organize personal lives, plan experiences, study, and learn through AI-powered orchestration

---

## First Principles (Never Change)

1. **Human-action OS** - Beautiful, fast UI that turns intent (text/voice/files/screen context) into safe, auditable actions across Microsoft, Google, Apple, and independent systems
2. **Provider-agnostic core** - Multi-model (OpenAI + Azure + Anthropic + Google + local), multi-cloud (AWS/GCP/Azure), multi-tenant with hard isolation
3. **Safety by design** - Preview→Confirm, scoped permissions, signed webhooks, complete audit trails, observable latency/cost per action
4. **Performance as product** - P95 < 500ms on reads, P99 < 1s for orchestrations; JS budget ≤ 120KB; predictable tails
5. **Own the orchestration layer** - The APIs, SDKs, and standards others plug into

---

## Strategic Context & Decisions

### Architecture Status (Sprint 49A Complete)
- **Core engine (API)** - Sprints 42-47 ✅ Complete
  - FastAPI app with health, readiness, Prometheus metrics, OpenTelemetry tracing
- **Performance & Observability** - Sprints 42-48 ✅ Validated
  - CI budgets, Grafana dashboards, uptime & perf-baseline jobs
- **Relay Studio UI (mock layer)** - Sprint 49 Phase A ✅ Scaffolded
  - Command palette, chat stream, action forms running on mocked data
- **Action Framework (API extension)** - Sprint 49 Phase B ⏳ Scheduled (10 PM PDT Oct 5, 2025)
  - /actions endpoints and provider adapters (Microsoft/Google/Independent)

### Platform Evolution Strategy
**Current (Layer 1)** - Sprints 49-55
Railway + Vercel + managed Postgres/Redis for speed and zero DevOps overhead

**Next (Layer 2)** - Sprints 56-60
AWS EKS/GCP GKE, Aurora Postgres, Redis Elasticache, Grafana Cloud for enterprise scale

**Rationale:** Layer 1 delivers identical or better performance for small test cohorts; Layer 2 adds capacity, p99/p999 stability, and regional redundancy at scale

### OpenAI Ecosystem Position
**Decision:** Use OpenAI as reference implementation through Sprint 55

**Rationale:**
- Fastest path to polished demo and early user data
- Industry-standard API with broad third-party support
- Best quality-per-token for complex reasoning

**Risk Mitigation:**
- Maintain thin abstraction layer (LLMProvider interface)
- Enable multi-provider support in Sprints 55-60
- Real differentiation is Relay's orchestration layer and UX, not model provider

### Market Research Window
**Critical Timing:** Sprints 50-52 (after vertical slice works, before building monetization)

**Activities:**
- 10-20 target-segment discovery interviews (operators, analysts, founders, students)
- Gated signup page with willingness-to-pay signals
- Usage telemetry from beta users (action types, frequency, retention)
- Competitive benchmarking (ChatGPT Enterprise, Zapier AI, n8n, Copilot Studio)
- ICP refinement: enterprise ops vs. SMB automation builders vs. prosumers

---

## Phased Roadmap

### Phase I — Product-Market Love & Platform Spine (Sprints 49-60)
**Goal:** Ship vertical slice, prove retention, remove obvious scale blockers

#### Sprints 49B-52: Real actions, developer platform, invite-only beta
**Deliverables:**
- Actions API (provider-agnostic): `/actions` list/preview/execute
- Provider adapters: Independent (SMTP/Webhook/Files), Microsoft (Outlook/Teams/Calendar), Google (Gmail/Chat/Calendar)
- Studio: command palette, chat streaming, Zod-forms, Preview→Confirm, voice PTT, request-ID links to Grafana/Tempo
- SDKs: JS/Python clients; OpenAPI + Postman; example apps
- Keys & rate limits: per-workspace API keys, org/workspace roles, burst control
- Metrics: `action_exec_total`, `action_latency_seconds_bucket`, `action_error_total` exposed to users

**KPI Targets:**
- 30-day retention ≥ 40% for beta devs
- Time-to-first-action < 3 minutes
- P95 action latency < 1.2s

#### Sprints 53-56: Business viability, monetization, first enterprise wins
**Deliverables:**
- Billing: Stripe seat + usage tiers; org limits; cost guards per workspace
- Admin: SSO (OIDC), SCIM, audit exports, data residency labels
- Templates marketplace v1: curated actions + workflows; rev share
- Scale posture: production Postgres/Redis, regional replicas, blue/green deploys, error budgets

**KPI Targets:**
- $50-100k ARR
- ≥10 design-partner orgs
- <1% weekly incident rate

#### Sprints 57-60: "Big ship" migration path
**Deliverables:**
- Cloud portability: Helm + Terraform; EKS/GKE/AKS option
- Managed Postgres (Aurora/Cloud SQL), Redis (ElastiCache/Memorystore)
- Global edge: CDN/Edge functions (Vercel/Cloudflare) for static + auth; region-aware routing
- Multi-model abstraction: swap OpenAI/Claude/Gemini/Azure with config; retrieval & tool-calling parity tests
- Compliance runway: SOC2 Type 1 start; data retention & DLP knobs

**KPI Targets:**
- P99 stability; <0.5% error rate
- Median orgs executing ≥3 actions/day

---

### Phase II — Scale, Verticals, and Moats (Sprints 61-80)
**Goal:** Expand use cases, deepen enterprise, prove margins, build distribution loops

#### Sprints 61-68: Vertical packs & partner ecosystem
**Deliverables:**
- Vertical packs: Sales Ops, Support, Finance, HR—prebuilt action bundles (CRM update, ticket triage, invoice reconcile, candidate stage)
- Connector SDK: partners build verified actions; signed manifests; marketplace v2
- Observability for customers: in-product dashboards (latency/cost by action, department, user), chargeback exports
- Data & privacy: org-level encryption policy, private networks/VPC peering

**KPI Targets:**
- $1-3M ARR
- ≥50 logos
- Marketplace contributes ≥10% GMV

#### Sprints 69-74: Reliability & margin engine
**Deliverables:**
- Smart routing: choose model/provider per request based on cost/latency/SLA
- Caching & memoization: semantic cache for common generations; replay protection
- Async orchestration: durable jobs, saga patterns, retries with jitter; at-least-once semantics plus idempotency keys
- Unit economics: cost per action graph; automated right-sizing; spot/GPU pools for heavy jobs

**KPI Targets:**
- Gross margin ≥70%
- P95 action latency <700ms for common flows

#### Sprints 75-80: Internationalization & compliance
**Deliverables:**
- i18n (full): RTL, locale-aware forms, translation memory
- Compliance: SOC2 Type 2, ISO 27001; data-processing addendum; regional hosting (EU, APAC)
- Channels: Slack/Teams/Email/CLI/mobile; "embed Relay" SDK for third-party apps

**KPI Targets:**
- $5-8M ARR
- <0.3% monthly incident
- EU/APAC data residency enabled

---

### Phase III — Category Leadership & IPO Track (Sprints 81-100+)
**Goal:** Own the "intent→action" category, expand into consumer prosumers, prepare for IPO diligence

#### Sprints 81-88: Consumer prosumer & ambient experiences
**Deliverables:**
- Personal Relay: calendar triage, inbox sweep, shopping approvals, family logistics, travel planning—voice-first on mobile
- Ambient UI: screen-aware actions (browser extension + desktop agent); zero-copy flows (select text → act)
- Trust UX: spend limits, parental controls, "why this action" trace panel

**KPI Targets:**
- DAU/MAU ≥40%
- Stickiness >3 sessions/day for prosumers

#### Sprints 89-94: Autonomous assists (guarded)
**Deliverables:**
- Policy engine: org rules ("never send external after 6pm"; "purchase ≤$200 requires second confirm")
- Autopilot trials: limited domains with reversible actions; hard kill-switch; weekly review dashboards
- Robo-RPA bridge: UI automation fallback (Playwright/RPA) when no API exists, with reliability scoring

**KPI Targets:**
- Measurable hours saved per org
- Autopilot acceptance rate ≥60% in domains allowed

#### Sprints 95-100: IPO readiness & global footprint
**Deliverables:**
- Financials: multi-year audited statements, revenue recognition, ARR quality, cohort LTV/CAC
- Security posture: pen-tests, red-team drills, bug bounty at scale, vendor risk management
- Corporate structure: consider HQ and ADR/dual-listing jurisdictions; evaluate HKEX/LSE/NYSE/ASX with counsel (index inclusion, analyst coverage, governance)
- Brand & community: developer conference; certified partner program; education grants

---

## Parallel Tracks (Evergreen)

### Technology Roadmap
- **Model layer:** Pluggable LLMs, retrieval tools, function calling; "shadow routing" for A/B provider tests
- **Knowledge layer:** Zero-copy retrieval from user stores (M365/Google/Box/Notion/SharePoint); row-level ACLs
- **Action safety:** Dry-run diffs, typed guards, spend/time/recipient controls; signed action manifests
- **Edge inference (future):** Small on-device models for classification, intent, and summarization; privacy wins

### Monetization
- **Tiers:** Free (rate-limited), Pro (seat), Team, Enterprise (SLA, SSO, DLP, residency)
- **Marketplace rev share:** 80/20 early, moving to 85/15 as volume grows
- **Usage add-ons:** Premium models, high-volume actions, compliance packs

### Go-to-Market
- **Bottom-up PLG:** Free tier + viral sharing of "action links" and templates
- **Top-down enterprise:** Industry packs, security reviews, reference architectures, certified partner implementers
- **Community:** Template competitions, partner webinars, docs as content engine

### Org & Culture (Minimal to Durable)
- **0-20:** Founders + product/infra core + 3-5 partner engineers
- **20-60:** Add Security, SRE, Developer Relations, Sales Assist
- **60-150:** Solution architects, regional leads, compliance, finance
- **Principles:** Ship fast, measure honestly, reversible decisions, design taste, zero-ego incident culture

---

## Non-Negotiable KPIs (The Dials We Watch)

| Category | Metrics |
|----------|---------|
| **Retention** | 30/90-day logo & seat retention |
| **Activation** | Time-to-first-action; % actions with Preview→Confirm |
| **Scale** | P95/P99 by action; error rate by provider |
| **Economics** | GM %, $/action, cost per token, COGS by provider |
| **Growth** | ARR, net revenue retention (NRR), marketplace GMV |
| **Trust** | Incident rate, MTTR, security audit pass, DSR turnaround |

---

## Immediate Next Steps (Current: Sprint 49B)

1. **Tonight (Oct 5, 10 PM PDT):** Execute Phase B deployment
   - Webhook + Independent actions live
   - Studio to Vercel
   - Metrics for actions

2. **Tomorrow (Oct 6):** Review PHASE-B-COMPLETE.md, confirm metrics and Studio URL

3. **Sprint 49C-52 backlog:** Set from this roadmap
   - Keys, rate limits
   - SMTP production
   - Teams/Outlook/Gmail previews→exec

4. **Parallel track:** Start SOC2 Type 1 prep (low overhead, big enterprise signal)

---

## Competitive Positioning by Sprint 60

By Sprint 60, Relay will sit in the same league as:

- **ChatGPT Enterprise + Copilot Studio** (AI workspace/chat)
- **n8n Cloud + Zapier AI** (workflow automation)
- **Linear + Notion** (team/org layer)
- **Vercel + Railway + Supabase** (developer platform)
- **Grafana Cloud / Datadog** (native observability)

**But with:**
- Crisper, faster, more human-centered experience
- Native observability inside the product
- Multi-provider flexibility
- Industrial-grade performance (P95 <500ms, JS ≤120KB)

---

*Document created: October 5, 2025*
*Last updated: Sprint 49A complete; Phase B scheduled for 10 PM PDT Oct 5, 2025*
