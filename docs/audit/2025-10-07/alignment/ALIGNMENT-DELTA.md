# Roadmap Alignment Delta - 2025-10-07

**Baseline:** Sprint 51 complete (Phases 1-3)
**Next:** Sprint 52 (Chat MVP, OAuth, Load Testing)

---

## Feature Matrix

| Feature Area | Planned | Implemented | Gap | Effort | Risk | Sprint |
|--------------|---------|-------------|-----|--------|------|--------|
| **Identity & Auth** |
| API Key Auth | ✅ | ✅ | None | - | - | 51-P1 |
| User Sessions | ✅ | ✅ | None | - | - | 51-P1 |
| RBAC (admin/dev/viewer) | ✅ | ✅ | None | - | - | 51-P1 |
| OAuth (Google/GitHub) | ✅ | ❌ | Providers not integrated | L | Med | 52 |
| Multi-workspace support | ✅ | ✅ | Workspace isolation exists | - | - | 51-P1 |
| **Actions API** |
| List actions | ✅ | ✅ | None | - | - | 49 |
| Preview (token generation) | ✅ | ✅ | None | - | - | 49 |
| Execute (webhook adapter) | ✅ | ✅ | None | - | - | 49 |
| Idempotency | ✅ | ✅ | None | - | - | 50 |
| Additional adapters (gRPC, async) | ✅ | ❌ | Only webhook implemented | L | Low | 53+ |
| **Security & Hardening** |
| Rate limiting (per-workspace) | ✅ | ✅ | None | - | - | 51-P2 |
| Webhook HMAC signing | ✅ | ✅ | None | - | - | 50/51-P2 |
| Security headers (HSTS, CSP) | ✅ | ✅ | None | - | - | 51-P2 |
| Audit logging + redaction | ✅ | ✅ | None | - | - | 51-P1 |
| Secrets scanning (CI) | ✅ | ⚠️ | Manual only, not automated | S | Low | 52 |
| **Observability** |
| Prometheus metrics | ✅ | ✅ | None | - | - | 46 |
| OTel tracing | ✅ | ⚠️ | Code exists, not deployed | M | Low | 48 |
| SLOs defined | ✅ | ✅ | None | - | - | 51-P3 |
| Alert rules | ✅ | ⚠️ | Defined but not deployed | S | Med | 52 |
| Grafana dashboards | ✅ | ⚠️ | Defined but not deployed | S | Med | 52 |
| Error budget tracking | ✅ | ❌ | No automated reports | M | Low | 52 |
| **Operational Excellence** |
| CI/CD pipeline | ✅ | ⚠️ | Defined but not merged | S | High | 52 |
| Automated migrations | ✅ | ⚠️ | Workflow exists, not active | S | High | 52 |
| Database backups | ✅ | ⚠️ | Workflow exists, not active | S | High | 52 |
| Restore drills | ✅ | ⚠️ | Script exists, never run | M | Med | 52 |
| Rollback automation | ✅ | ⚠️ | Partial (notes only, no API) | M | Med | 52 |
| **Studio (Frontend)** |
| Actions list/preview UI | ✅ | ✅ | None | - | - | 49 |
| Chat MVP | ✅ | ❌ | `/chat` endpoint not implemented | L | Med | 52 |
| OAuth login flow | ✅ | ❌ | No provider integration | L | Med | 52 |
| User dashboard | ✅ | ⚠️ | Basic, needs polish | M | Low | 53 |
| Workspace switcher | ✅ | ❌ | Single workspace only | M | Low | 53 |
| **Performance & Scale** |
| Load testing (100 RPS) | ✅ | ❌ | No load tests implemented | M | Low | 52 |
| Horizontal scaling | ✅ | ⚠️ | Single instance only | L | Med | 53 |
| Redis caching | ✅ | ⚠️ | Used for rate limits only | M | Low | 53 |
| DB connection pooling | ✅ | ✅ | None | - | - | Base |

---

## Priority Gaps

### P0 - Blockers for Production Scale
1. **CI/CD Not Merged** - Phase 2/3 PRs not merged, no automated deploys
2. **Backups Not Active** - No automated database backups
3. **Alert Rules Not Deployed** - Metrics exist but no alerting

### P1 - Critical for Next Sprint
4. **OAuth Integration** - Required for Chat MVP user experience
5. **Restore Drill Untested** - Backups may not be valid
6. **Rollback Automation Incomplete** - Manual intervention required

### P2 - Important but Not Urgent
7. **OTel Tracing** - Code exists but not deployed
8. **Error Budget Tracking** - Manual SLO compliance checks only
9. **Secrets Scanning** - Manual, should be in CI/CD

### P3 - Nice to Have
10. **Horizontal Scaling** - Single instance sufficient for now
11. **Additional Adapters** - gRPC, async (webhook sufficient)
12. **Workspace Switcher UI** - Single workspace OK for MVP

---

## Recommended Prioritization (Sprint 52)

### Week 1: Merge & Activate Phase 2/3
- Merge sprint/51-phase2-harden → main
- Merge sprint/51-phase3-ops → main
- Configure GitHub secrets
- Import Grafana dashboards + alert rules
- Verify nightly backup cron runs
- Run manual restore drill

### Week 2: OAuth + Chat MVP Foundation
- Google OAuth provider integration
- GitHub OAuth provider (optional)
- `/chat` endpoint scaffolding (Studio)
- User session management in Studio

### Week 3: Chat MVP + Load Testing
- Complete Chat UI implementation
- Add load testing (100 RPS baseline)
- Generate performance report
- Create Sprint 52 evidence package

### Week 4: Polish & Stabilize
- Fix P1/P2 issues from audit
- Complete rollback automation
- Automate error budget tracking
- Sprint 52 handoff document

---

## Risk Assessment

### High Risk
- **CI/CD Merge:** Breaking change potential, test thoroughly
- **Backup Validity:** Untested restores = unrecoverable data loss risk

### Medium Risk
- **OAuth Integration:** Third-party dependency, rate limits, revocations
- **Load Testing:** May reveal performance bottlenecks
- **Alert Fatigue:** Poorly tuned thresholds = ignored alerts

### Low Risk
- **Secrets Scanning:** Tooling exists, easy integration
- **OTel Tracing:** Already coded, deploy-only change
- **Workspace Switcher:** UI-only, no backend changes needed

---

## Effort Estimates

| Size | Hours | Examples |
|------|-------|----------|
| S    | 1-4   | Import dashboards, configure secrets, merge PRs |
| M    | 4-12  | OAuth integration, restore drill, error budget automation |
| L    | 12-24 | Chat MVP, load testing, horizontal scaling |
| XL   | 24+   | Multi-region, advanced scaling |

---

## Alignment Score

**Overall:** 🟡 **YELLOW** (75% aligned)

**Breakdown:**
- ✅ **Green (90%+):** Identity/Auth, Actions API, Audit Logging
- 🟡 **Yellow (60-89%):** Observability, Operational Excellence, Frontend
- 🔴 **Red (<60%):** Performance & Scale, OAuth Integration

**Recommendation:** Merge Phase 2/3 immediately to move Operational Excellence to Green. OAuth + Chat MVP in Sprint 52 will move Frontend to Green.

---

Generated: 2025-10-07
Source: Sprint 51 status documents, OpenAPI spec, codebase analysis
