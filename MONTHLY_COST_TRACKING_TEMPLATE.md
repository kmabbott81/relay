# Monthly Cost Tracking Template
**Updated**: 2025-11-11
**Frequency**: Monthly (First Monday of each month)
**Estimated Time**: 15 minutes

---

## TEMPLATE FOR NOVEMBER 2025

### Cost Summary
```
Period: November 1-30, 2025
Prepared by: [Your Name]
Date prepared: 2025-11-01 (OR 2025-12-01 for Dec review)
```

### 1. Infrastructure Costs

**Railway** (Primary Host)
```
Service           | Status | Cost Est. | Actual | Notes
─────────────────────────────────────────────────────
API (relay-*)     | Active | $5-15    | $__    | Eco plan
PostgreSQL        | Active | Included | $__    | 5GB included
Prometheus        | Active | Included | $__    | Monitoring
Grafana           | Active | Included | $__    | Dashboards
─────────────────────────────────────────────────────
Railway Total:            | $5-15   | $__    |
```

**Vercel** (Frontend)
```
Component         | Status | Cost Est. | Actual | Notes
─────────────────────────────────────────────────────
Web app           | Ready  | $0       | $__    | Hobby tier
CDN/Bandwidth     | Ready  | $0       | $__    | Included
Deployments       | Ready  | $0       | $__    | Unlimited in Hobby
─────────────────────────────────────────────────────
Vercel Total:             | $0       | $__    |
```

**GitHub Actions** (CI/CD)
```
Component         | Usage  | Cost Est. | Actual | Notes
─────────────────────────────────────────────────────
Build minutes     | ___/2K | $0       | $__    | ___% of quota
─────────────────────────────────────────────────────
GitHub Total:             | $0       | $__    |
```

**Supabase** (Optional)
```
Component         | Status | Cost Est. | Actual | Notes
─────────────────────────────────────────────────────
Database 1        | Free   | $0       | $__    | Not in use
Database 2        | Free   | $0       | $__    | Not in use
─────────────────────────────────────────────────────
Supabase Total:           | $0       | $__    |
```

**TOTAL INFRASTRUCTURE: $__ (Target: $5-20)**

---

### 2. Token & API Usage

**LLM API Calls** (if using Claude, GPT-4, etc.)
```
Model Used        | Input Tokens | Output Tokens | Cost      | Notes
─────────────────────────────────────────────────────────────────────
Claude-3-Haiku    | ____________ | _____________ | $______   |
Claude-3.5-Sonnet | ____________ | _____________ | $______   |
GPT-4o            | ____________ | _____________ | $______   |
─────────────────────────────────────────────────────────────────────
TOTAL LLM COST:                                  | $______   |
```

**Database Operations**
```
Query Type        | Count    | Avg Cost | Total   | Notes
─────────────────────────────────────────────────────────
SELECT (simple)   | ______   | $0.001K  | $___    |
SELECT (complex)  | ______   | $0.002K  | $___    |
INSERT/UPDATE     | ______   | $0.0005K | $___    |
DELETE            | ______   | $0.0001K | $___    |
─────────────────────────────────────────────────────────
TOTAL DB COST:                          | $___    |
```

**API Operations**
```
Endpoint          | Calls   | Cost/Call | Total   | Notes
─────────────────────────────────────────────────────────
/health           | ______  | $0        | $__     |
/api/queries      | ______  | $0.001    | $__     |
/api/embeddings   | ______  | $0.002    | $__     |
─────────────────────────────────────────────────────────
TOTAL API COST:                        | $__     |
```

---

### 3. Budget vs Actual

**Global Budget** (Recommended: $25/day, $500/month)
```
Budget Category   | Limit    | Spent    | % Used  | Status
─────────────────────────────────────────────────────────
Daily Budget      | $25.00   | $____    | ___%    | ✅/⚠️/🚨
Monthly Budget    | $500.00  | $____    | ___%    | ✅/⚠️/🚨
```

**Tenant Budgets**
```
Tenant Type       | Count | Daily Limit | Spent | % Used | Status
──────────────────────────────────────────────────────────────────
Trial             | __    | $1.00       | $__   | ___%   | ✅/⚠️/🚨
Startup           | __    | $5.00       | $__   | ___%   | ✅/⚠️/🚨
Premium           | __    | $25.00      | $__   | ___%   | ✅/⚠️/🚨
Enterprise        | __    | $100.00     | $__   | ___%   | ✅/⚠️/🚨
```

---

### 4. Cost Anomalies & Alerts

**Anomaly Detection Report**
```
Anomalies detected this month: __

Anomaly #1:
  Tenant: ________________
  Date: __________
  Normal spend: $______/day
  Anomalous spend: $______/day
  Sigma level: ___σ
  Action taken: ________________

Anomaly #2:
  Tenant: ________________
  Date: __________
  Normal spend: $______/day
  Anomalous spend: $______/day
  Sigma level: ___σ
  Action taken: ________________

Budget threshold hits: __
  ⚠️ Soft threshold (80%): __ tenant(s)
  🚨 Hard threshold (100%): __ tenant(s)
```

---

### 5. Performance & Efficiency Metrics

**Cost Efficiency**
```
Metric                        | Target    | Actual | Status
──────────────────────────────────────────────────────────
Cost per user                 | < $0.50   | $__    | ✅/⚠️/🚨
Cost per API request          | < $0.001  | $__    | ✅/⚠️/🚨
Cost per DB query             | < $0.0001 | $__    | ✅/⚠️/🚨
Tokens per dollar             | > 50K     | ____   | ✅/⚠️/🚨
Database cost % of total      | < 50%     | __%    | ✅/⚠️/🚨
```

**Resource Utilization**
```
Resource              | Included   | Used      | % Used | Status
─────────────────────────────────────────────────────────────────
Railway services      | 5          | ___       | ___%   | ✅/⚠️
GitHub Actions mins   | 2,000      | ___       | ___%   | ✅/⚠️
Database storage      | 5 GB       | ___ GB    | ___%   | ✅/⚠️
Network egress        | 50 GB      | ___ GB    | ___%   | ✅/⚠️
```

---

### 6. Trend Analysis

**Cost Over Time** (Last 6 months)
```
Month              | Total Cost | Avg Cost/User | Trend
───────────────────────────────────────────────────────
May 2025           | $______    | $______       | ↗/→/↘
June 2025          | $______    | $______       | ↗/→/↘
July 2025          | $______    | $______       | ↗/→/↘
August 2025        | $______    | $______       | ↗/→/↘
September 2025     | $______    | $______       | ↗/→/↘
October 2025       | $______    | $______       | ↗/→/↘
November 2025      | $______    | $______       | ↗/→/↘

Trend Analysis:
  Cost trajectory: [Linear / Exponential / Flat]
  Primary driver: [Infrastructure / LLM / Database / Other]
  Forecast (12 months): $______
```

---

### 7. Optimization Opportunities

**Completed This Month**
```
☐ Query caching implemented        | Savings: $__/month
☐ Response compression added       | Savings: $__/month
☐ GitHub Actions optimized         | Savings: $__/month
☐ Database indexes added           | Savings: $__/month
☐ Model downgrading deployed       | Savings: $__/month
☐ Other: ___________________       | Savings: $__/month

Total monthly savings: $____
Cumulative annual savings: $____
```

**Recommended Next Steps**
```
Priority 1 (This month):
  [ ] ________________________________ (Est. savings: $__)
  [ ] ________________________________ (Est. savings: $__)

Priority 2 (Next month):
  [ ] ________________________________ (Est. savings: $__)
  [ ] ________________________________ (Est. savings: $__)

Priority 3 (Backlog):
  [ ] ________________________________ (Est. savings: $__)
  [ ] ________________________________ (Est. savings: $__)
```

---

### 8. Tier Upgrade Assessment

**Current Tiers**
```
Service    | Current Tier  | Active Users | Cost/Month | Sufficient? | Notes
────────────────────────────────────────────────────────────────────────────
Railway    | Eco          | ___          | $___       | ✅/⚠️/❌   |
Vercel     | Hobby        | ___          | $0         | ✅/⚠️/❌   |
GitHub     | Free 2K min  | ___          | $0         | ✅/⚠️/❌   |
Supabase   | Free tier    | ___          | $0         | ✅/⚠️/❌   |
```

**Upgrade Triggers**
```
If yes to any:

☐ Active users > 50?
  → Consider Railway Standard ($25/mo base)
  → ETA: ________
  → Cost impact: +$15-20/mo

☐ Daily cost > $25?
  → Evaluate efficiency opportunities first
  → Then consider tier upgrade
  → ETA: ________
  → Cost impact: +$10-30/mo

☐ Need team collaboration?
  → Consider Vercel Pro ($20/mo)
  → ETA: ________
  → Cost impact: +$20/mo

☐ Exceeding 2,000 GitHub min/month?
  → Optimize workflows first
  → Then consider GitHub Actions paid ($21/mo base)
  → ETA: ________
  → Cost impact: +$0.25/min overage
```

---

### 9. Notes & Observations

**What Worked Well**
```
1. ________________________________________
2. ________________________________________
3. ________________________________________
```

**What Needs Improvement**
```
1. ________________________________________
2. ________________________________________
3. ________________________________________
```

**Surprises or Unexpected Costs**
```
1. ________________________________________
2. ________________________________________
3. ________________________________________
```

---

### 10. Sign-Off

**Prepared by**: _________________________ | **Date**: __________

**Reviewed by**: _________________________ | **Date**: __________

**Next review**: _________________________ | **Reminder set**: ✅/❌

---

## USAGE INSTRUCTIONS

### When to Use This Template
- First Monday of each month
- After cost report is generated
- During monthly ops meeting
- Before tier upgrade decisions

### How to Complete It
1. Run: `python scripts/cost_report.py > cost_report.txt`
2. Check: `tail logs/governance_events.jsonl | grep -E "cost_|budget_"`
3. Extract data from reports and fill in blanks
4. Calculate % used for each budget/resource
5. Add notes and observations
6. Get sign-off from technical lead
7. Archive for quarterly review

### Files to Reference
- `INFRASTRUCTURE_COST_ANALYSIS_2025-11-11.md` (Baseline)
- `COST_OPTIMIZATION_ACTION_PLAN.md` (Recommended actions)
- `scripts/cost_report.py --json` (Detailed data export)
- `logs/governance_events.jsonl` (Raw events)
- `config/budgets.yaml` (Budget configuration)

### Red Flags to Watch For
- 🚨 Any hard threshold budget blocks (stop immediately)
- 🚨 Cost spike > 3x baseline (investigate anomaly)
- ⚠️ Cost approaching 80% of budget (throttle non-critical work)
- ⚠️ Resource utilization > 80% (plan upgrade)
- ℹ️ Consistent upward trend (prepare for scaling)

---

## TEMPLATE FOR DECEMBER 2025 (Copy & Paste)

```
### Cost Summary
Period: December 1-31, 2025
Prepared by:
Date prepared:

### 1. Infrastructure Costs
[Use same table format as above]

### 2. Token & API Usage
[Use same table format as above]

### 3. Budget vs Actual
[Use same table format as above]

... [rest of sections] ...
```

---

## QUARTERLY DEEP DIVE CHECKLIST (Every 3 months)

**Q1 2026 Review** (March 31, 2025)
```
☐ Analyze cost trend over 3 months
☐ Review top 10 most expensive operations
☐ Check cache hit rates (target: > 30%)
☐ Review slow query logs
☐ Assess model selection efficiency
☐ Plan tier upgrades for Q2
☐ Update cost projections for year
☐ Document lessons learned
```

**Q2 2026 Review** (June 30, 2025)
```
☐ Analyze cost trend over 6 months
☐ Compare actual vs forecasted costs
☐ Evaluate all optimizations deployed
☐ Plan next optimization phase
☐ Assess tier upgrade needs
☐ Review user growth trajectory
☐ Update 12-month cost forecast
☐ Board presentation prep (if needed)
```

**Q3 2026 Review** (September 30, 2025)
```
☐ Analyze cost trend over 9 months
☐ Full cost-benefit analysis of all optimizations
☐ Plan for Q4 scaling
☐ Evaluate infrastructure architecture
☐ Consider regional expansion costs
☐ Update multi-year cost model
☐ Prepare investor communication
```

**Q4 2026 Review** (December 31, 2025)
```
☐ Full year retrospective
☐ Compare budget vs actual (full year)
☐ ROI analysis for all optimizations
☐ Plan for next year
☐ Assess if tier upgrades needed
☐ 2-year cost forecast
☐ Annual board report
☐ Set budgets for 2027
```

---

## MONTHLY EMAIL TEMPLATE

**Subject**: Cost Report - [Month] 2025

```
Hi [Team],

Monthly cost report for [Month] is ready for review:

📊 Total Cost: $____
💰 Cost/User: $____
📈 Trend: [Up/Flat/Down] (%___ vs last month)
✅ Budget Status: [On track / Approaching limit / Over budget]

Key Highlights:
  • ________________________________
  • ________________________________
  • ________________________________

Anomalies:
  • ________________________________
  • ________________________________

Optimizations Completed:
  • ________________________________
  • ________________________________

Next Steps:
  • ________________________________
  • ________________________________

Full report: [Link to this month's tracking doc]
Questions? See INFRASTRUCTURE_COST_ANALYSIS_2025-11-11.md

Thanks,
[Your Name]
```

---

**Template Version**: 1.0
**Last Updated**: 2025-11-11
**Next Template Update**: 2025-12-11
