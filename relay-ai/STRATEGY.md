# Relay: The Provably Secure Copilot Alternative

## Executive Summary

**Relay** is a consumer-first, enterprise-secure AI assistant built for SMBs (10-100 employees). We beat Microsoft Copilot by being:
- **Cheaper:** $9/user/month vs Copilot $30/user/month (70% lower)
- **Faster:** 5-minute self-serve setup vs 2-4 hours IT complexity
- **Safer:** Provable security (public canary reports) vs "trust us" claims
- **Better UX:** Works with any app, not just Microsoft Office

## The Market Gap

**Microsoft Copilot's Weaknesses (Our Wedge):**
1. **Expensive** - SMBs are price-sensitive; Copilot = $360/year per user
2. **Complex setup** - Requires IT involvement; SMBs want self-service
3. **Data training** - Models train on your data (privacy concern for regulated industries)
4. **Security theater** - No audit trail; "trust us" approach
5. **Office-centric** - Only works well in Teams/Office ecosystem

**Relay's Advantages:**
1. **90% cheaper** - $108/year vs $360
2. **5-minute setup** - Google OAuth → auto-provisioned workspace
3. **Your data stays yours** - Cryptographically enforced, never trains models
4. **Transparent security** - Daily canary reports, downloadable audit logs
5. **Universal** - Works with Gmail, Drive, Slack, Shopify, any web app

## Target Customer Profile

**Primary: SMB Owner (Executive Decision Maker)**
- 50-100 person company
- Budget-conscious ($500-2K/month for tools)
- Frustrated with Copilot complexity
- Wants proof of security (not claims)

**Secondary: IT Manager**
- Currently pushing Copilot to execs
- Concerned about data leakage
- Needs compliance/audit trail
- Impressed by transparent security

**Tertiary: End User**
- Wants AI that actually works (not bloated)
- Prefers personal account to enterprise complex auth
- Values speed (TTFV <1 second)
- Will switch if personal + work are equally secure

## Product Positioning

**Headline:** "Relay — the provably secure AI assistant your team actually loves."

**Subheading:** "Cheaper than Copilot. Faster to value. Your data stays yours. We prove it daily."

**Core Promise:**
> You get the best AI assistant. We make it impossible for your data to leak. Here's the proof.

## Technical Moat

### Layer 1: Per-User RLS (Row-Level Security)
- PostgreSQL policies enforce user isolation at database level
- User A literally cannot query User B's rows (not application-enforced)
- Verified by daily canary tests
- Competitors: Tenant-level isolation only (weaker)

### Layer 2: AES-256-GCM Encryption + HMAC Binding
- File metadata encrypted with user's key
- HMAC prevents tampering even if attacker has ciphertext
- Encryption key derived from JWT (not stored on disk)

### Layer 3: Visible Security Dashboard
- Live audit log of every query
- "Your data never trained models" counter
- "Data exfiltration attempts" = 0 badge
- Downloadable daily security report
- **This is what Copilot doesn't have**

## Go-to-Market Strategy

### Phase 1: SMB Founder Virality (Week 1-4)
- **Target:** Founders of 50-person companies
- **Channel:** Product Hunt, Hacker News, r/smallbusiness
- **Hook:** "Copilot alternative. 70% cheaper. Security proof included."
- **Call-to-action:** "Try free. No credit card. See your data fortress."

### Phase 2: Team Bottom-Up (Week 5-8)
- **Strategy:** Free tier generates team invites
- **Mechanic:** "Invite teammate → both get 2x queries"
- **Result:** Organic team growth without IT involvement
- **Outcome:** Teams request switch from Copilot

### Phase 3: Enterprise Scale (Week 9-12)
- **Target:** IT managers now evangelized by employees
- **Package:** SSO, SLA, priority support
- **Price:** $500-1000/month for 100+ users
- **Lock-in:** Habits + data history

## Pricing Strategy

| Tier | Users | Price | Use Case | Goal |
|------|-------|-------|----------|------|
| **Personal Free** | 1 | $0 | Try it out (10 queries/day) | Conversion funnel top |
| **Student** | 1 | $0 | Campus (unlimited with .edu) | Lifetime customer |
| **Professional** | 1 | $9/mo | Power users | Revenue per user |
| **Team** | 5 | $49/mo | Small company | Viral growth |
| **Business** | 25 | $199/mo | Growing company | Revenue scale |
| **Enterprise** | 100+ | Custom | Large SMB | Account control |

**Key:** Every tier is dramatically cheaper than Copilot. Free tier exists to break IT gatekeeping.

## 90-Day Roadmap

| Phase | Timeline | Deliverable | Success Metric |
|-------|----------|-------------|-----------------|
| **MVP** | Days 1-30 | Google OAuth + Docs RAG + Security Dashboard | 100 signups |
| **Launch** | Days 31-60 | Product Hunt + Copilot comparison + Email integration | 500 signups, 10 paying |
| **Scale** | Days 61-90 | Team features + Slack connector + Enterprise tier | 1,000 users, 50 paying, 5 Copilot switches |

## Success Criteria (Year 1)

- **Users:** 10,000 (personal + team tiers)
- **Revenue:** $100,000 MRR
- **Unit Economics:** <$1 CAC, >$50 LTV
- **Copilot Switches:** 500 companies migrating
- **Security Record:** Zero breaches, 365+ days no data leaks
- **NPS:** >70 (SaaS benchmark: 50)

## Why We Win

| Factor | Copilot | Relay | Winner |
|--------|---------|-------|--------|
| **Price** | $30/user/mo | $9/user/mo | Relay |
| **Setup** | 2-4 hours | 5 minutes | Relay |
| **Data Privacy** | "Trust us" | Daily proof | Relay |
| **Free Tier** | None | Yes (10/day) | Relay |
| **Audit Trail** | Limited | Full transparency | Relay |
| **Personal Use** | Banned | Welcomed | Relay |
| **Works Everywhere** | Office only | Any app | Relay |

## Investment & Team

### MVP Phase (30 days, 1 founder)
- Focus: Product excellence over scale
- Resources: Existing code (Knowledge API + RLS system)
- Constraints: Solo builder = ruthless feature cut

### Launch Phase (30 days, 1-2 people)
- Add: Designer (UI/copy), GTM (launch strategy)
- Focus: User research + virality loops
- Budget: <$5K (runway from friends & family)

### Scale Phase (30 days, 3-5 people)
- Add: Growth manager, Support, Backend specialist
- Focus: Enterprise sales + operational scaling
- Budget: $20K (from early revenue)

## Competitive Moat (Defensible)

1. **Security Evidence** - We publish daily canary reports; competitors can't replicate overnight
2. **Cost Structure** - Our tech stack (Railway + Supabase + open-weights) is cheaper; we can undercut forever
3. **User Community** - Network effects on knowledge sharing (SMBs help SMBs)
4. **Data Network** - Over time, our proprietary knowledge base (anonymized) becomes valuable for evals

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Microsoft Copilot lowers price | Kills pricing advantage | Focus on security/UX first; move upmarket if needed |
| OpenAI releases ChatGPT for SMBs | Direct competition | We're vertical (SMB) + security-focused; harder to copy |
| Churn (users go back to Copilot) | Revenue loss | Locked-in via team habits + data history; low churn expected |
| Security incident | Brand death | Our advantage; deep security hygiene culture |

## Success Looks Like (Year 1)

- Founder of a 50-person marketing agency: "We switched 30 people from Copilot. Same feature set. Half the price. Better security."
- CTO of a manufacturing company: "Our IT team was forcing Copilot. Employees started using Relay personally. Now we're evaluating it enterprise-wide."
- Reddit post (r/smallbusiness): "Finally, an AI tool that's not a scam. Relay is the only one that lets me download my own data."

---

**Status:** Live in production with R2 Knowledge API ✓ | RLS + RLS enforcement ✓ | Canary evidence system ✓

**Next:** Build consumer UX on top of proven backend.
