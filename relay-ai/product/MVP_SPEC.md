# MVP Specification: 30-Day Launch

## Vision
In 30 days, deliver a **consumer-first AI assistant** that makes Copilot obsolete by being **cheaper, simpler, and provably secure**.

## Target: 100 Signups | 10 Paying | 1 Copilot Switch

---

## Feature Roadmap

### Week 1-2: Core Experience (Foundation)

#### Must-Have Features

**1. Google OAuth Login**
- Single-click signup via Google Workspace
- Auto-detect company domain (e.g., user@acme.com → "Acme Workspace")
- Auto-provision RLS namespace
- Session stored in JWT (Supabase-signed)
- **Time to login:** <5 seconds
- **Success metric:** 0 failed logins due to auth

**2. Document Upload + RAG Search**
- Accept: PDF, DOCX, TXT, MD
- Max file: 10MB (MVP)
- Upload → Async embedding (Knowledge API ✓ exists)
- Search: Vector similarity + RLS filtering
- Results: Show source document + confidence score
- **Time to search:** <1 second p95
- **Success metric:** search_latency_p95 < 1.0s

**3. Security Dashboard (THE DIFFERENTIATOR)**
- Live activity feed:
  ```
  ✓ Document uploaded - Encrypted with your key
  ✓ 3 searches performed - 0 data leaked
  ✓ Teammate accessed - Permission verified
  ```
- Trust metrics:
  ```
  | 100% | Queries Isolated |
  | 0 | Times Models Trained on Your Data |
  | 256-bit | Encryption Strength |
  ```
- Action buttons:
  ```
  [Download Today's Security Report]
  [Export All My Data]
  [Delete Everything]
  ```
- **Time to understand:** <10 seconds ("Oh, my data is ACTUALLY safe")
- **Success metric:** 80% of free users view dashboard

**4. Team Invites (Bottom-Up Growth)**
- "Invite teammate" button
- Generate invite link (valid 7 days)
- Invitee lands in same workspace, different RLS context
- Inviter + invitee both get +5 queries
- **Time to add teammate:** <30 seconds
- **Success metric:** 30% of users invite 1+ teammate

#### UI/UX Specifications

**Landing Page (`/`)**
```
Hero:
  "Relay — the provably secure AI assistant for your team."
  Subheading: "Cheaper than Copilot. Your data stays yours. We prove it daily."

CTA: [Sign up free] [Security proof] [Copilot comparison]

Social proof:
  "⭐⭐⭐⭐⭐ Finally, AI we can trust." — Sarah, Founder @ TechCo
```

**Dashboard (`/app`)**
```
Left sidebar:
  - [+ Upload Document]
  - Documents list (paginated)
  - Settings

Main area (after first upload):
  - Search box (prominent)
  - Results area

Right sidebar:
  - Security Dashboard (always visible)
  - Usage meter (X/10 queries remaining)
```

**Security Dashboard Component**
```typescript
// See: relay-ai/product/web/components/SecurityDashboard.tsx
- Activity feed (live updates)
- Trust metrics (green badges)
- "Why this matters" tooltips
- Buttons: Download report, Export data, Delete all
```

---

### Week 3: Copilot Killer Features

#### Feature: "Proof Mode"
```
Every AI response shows:
- Which documents were used (with quote)
- Confidence score (70-95%)
- Sources (downloadable PDF)
- Audit trail link
```

#### Feature: "Team Brain"
```
Shared knowledge WITHOUT data mixing:
- Upload → Shared document
- User A sees search results
- User B sees ONLY own docs + shared
- Perfect for SMB shared drives
```

#### Feature: "Never Forgets"
```
Conversation memory across sessions:
- "Remember that report from last week?"
- Searches previous context automatically
- Export conversation as markdown
- All searchable
```

---

### Week 4: Go-to-Market Readiness

#### Feature: Usage Limits + Upgrade Flow
```
Free tier:
- 10 queries/day
- 1 document upload/day
- Hit limit → soft paywall

Upgrade modal:
- "Go Pro for $9/month"
- Show calculator: "Your team needs X queries"
- Annual discount offer (pay $80, get $108 value)
```

#### Feature: Onboarding Wizard
```
Step 1: "Upload your first doc" (30s)
Step 2: "Ask a question" (20s)
Step 3: "See your security proof" (10s)
Step 4: "Invite a teammate" (20s)

Total: <90 seconds to "aha moment"
```

---

## Database Schema (Minimal)

```sql
-- Extend existing Supabase schema

-- Users (from Supabase Auth)
auth.users (email, created_at)  -- Managed by Supabase

-- Workspaces (new)
CREATE TABLE workspaces (
  id UUID PRIMARY KEY,
  name TEXT,                    -- Auto-detected domain
  user_hash TEXT UNIQUE,        -- HMAC(workspace_id) for RLS
  created_at TIMESTAMP
);

-- Documents (existing Knowledge API)
-- See: src/knowledge/db/* (move to relay-ai/platform/api/knowledge/)

-- Team members (new, minimal)
CREATE TABLE team_members (
  id UUID PRIMARY KEY,
  workspace_id UUID,
  user_id UUID,
  role TEXT,                    -- 'owner', 'member'
  created_at TIMESTAMP,
  -- RLS: owner sees all, members see only own + shared
);

-- Usage tracking (new, for billing)
CREATE TABLE usage_events (
  id UUID PRIMARY KEY,
  workspace_id UUID,
  event_type TEXT,             -- 'upload', 'search', 'share'
  token_count INT,
  created_at TIMESTAMP
);
```

---

## API Endpoints (MVP)

```
Authentication:
  POST /auth/google              -- OAuth callback handler
  POST /auth/logout
  GET  /auth/profile             -- Current user + workspace

Documents:
  POST /api/v1/documents/upload  -- Store + trigger embedding
  GET  /api/v1/documents         -- List (RLS-filtered)
  DELETE /api/v1/documents/{id}  -- Delete cascade

Search:
  POST /api/v1/search            -- Vector search (RLS-filtered)

Team:
  POST /api/v1/team/invite       -- Create invite link
  POST /api/v1/team/join         -- Accept invite
  GET  /api/v1/team/members      -- List (RLS-filtered)

Security:
  GET  /api/v1/security/audit    -- Audit log
  GET  /api/v1/security/report   -- Daily security snapshot
  POST /api/v1/data/export       -- Initiate export
  POST /api/v1/data/delete       -- Initiate full deletion
```

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| TTFV (Time to First Value) | <1.0s p95 | From search submit to results |
| Search latency | <500ms p95 | Vector query + RLS filter |
| Upload latency | <2.0s p95 | File upload + embedding enqueue |
| Security dashboard render | <100ms | Client-side only |
| Page load | <1.5s p95 | Landing page in browser |
| Login flow | <3.0s | Google OAuth → Dashboard |

---

## Security Requirements (No Compromise)

✓ JWT required on all endpoints (Bearer token)
✓ RLS enforcement per request (verify app.user_hash set)
✓ AES-256-GCM encryption on sensitive fields
✓ X-Request-ID tracing on all responses
✓ Rate limiting: 100 queries/hour per user (free), unlimited (pro)
✓ Error sanitization: No stack traces, file paths, secrets in responses
✓ Metrics emitted: query_latency, index_operation, security_violations
✓ Audit log: Every action recorded + downloadable

---

## Success Metrics (30 Days)

```
User Acquisition:
  - 100 signups
  - 10 users on paid tier ($9/month)
  - 1 company switched from Copilot

Product Quality:
  - NPS > 40 (from user interviews)
  - Error rate < 1% (monitored via Prometheus)
  - Security violations = 0
  - TTFV p95 < 1.0s

Engagement:
  - 60% of users complete "upload → search" in first session
  - 30% of users invite a teammate
  - 20% of users sign up for paid tier

---

Blockers (if not met, pivot strategy):
- TTFV > 2.0s (performance issue)
- Security violations > 0 (fatal)
- Free-to-paid conversion < 5% (product-market fit issue)
```

---

## Out of Scope (Week 5+)

- ❌ Slack integration (Week 5)
- ❌ Gmail integration (Week 5)
- ❌ Calendar intelligence (Week 6)
- ❌ Mobile app (Week 8)
- ❌ Custom AI models (Month 3)
- ❌ Multi-workspace orgs (Month 3)

**Reason:** Every feature adds complexity. Week 1-4 = relentless focus on core (upload → search → security proof → invite teammate).

---

## Definition of Done

A feature ships when:

1. **Security Gate PASS**
   - JWT enforced
   - RLS verified
   - Rate limits tested
   - Error responses sanitized

2. **UX Gate PASS**
   - Empty state handled
   - Loading state visible
   - Error suggestions wired
   - Keyboard accessibility tested
   - X-Request-ID surfaced in UI

3. **Performance Gate PASS**
   - TTFV < 1.0s p95
   - No regressions vs baseline
   - Metrics emitted

4. **Canary Gate PASS**
   - Staged rollout: 5% → 25% → 100%
   - Error rate monitored
   - Success rate > 99%
   - Rollback plan ready

---

## File Structure

```
relay-ai/product/web/
├── pages/
│   ├── index.tsx              # Landing
│   ├── app/
│   │   ├── dashboard.tsx      # Main app
│   │   ├── documents/
│   │   │   └── [id].tsx       # Document viewer
│   │   └── settings.tsx       # User settings
│   └── security.tsx           # Security proof page
├── components/
│   ├── SecurityDashboard.tsx  # Activity + metrics
│   ├── DocumentUpload.tsx
│   ├── SearchResults.tsx
│   └── TeamInvite.tsx
├── lib/
│   ├── api.ts                 # API client
│   ├── auth.ts                # JWT + session
│   └── security.ts            # Audit log + proof generation
└── styles/
    └── globals.css            # Tailwind
```

---

**Status:** Ready to build. All dependencies exist (Knowledge API, RLS, Auth).
**Next:** Start Next.js scaffold (Week 1).
