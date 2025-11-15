# Project Index: openai-agents-workflows-2025.09.28-v1

**Project Name**: djp-workflow (Relay AI)
**Project Start Date**: 2025-09-28
**Current Date**: 2025-11-11
**Total Commits**: 356 (4 added in 2025-11-11 session)
**Primary Branch**: main
**Repository**: Git-based version control

---

## Project Overview

Relay AI is a multi-agent AI orchestration platform with knowledge management capabilities. The project implements a modern AI workflow system with secure multi-tenant architecture, deployed across Railway (API), Vercel (Web), and Supabase (Database).

### Core Capabilities:
- AI agent orchestration and workflow execution
- Knowledge base management with vector search
- Secure multi-tenant architecture with RLS
- OAuth-based authentication (Gmail, Microsoft, Slack, Notion)
- Real-time streaming with SSE
- Comprehensive observability and monitoring

---

## Project Structure

### Primary Codebase:
```
relay_ai/                    # Main application namespace
├── platform/                # Backend platform services
│   ├── api/                # API implementations (FastAPI)
│   ├── security/           # Security, encryption, RLS
│   ├── ai/                 # AI agent services
│   ├── tests/tests/        # Test suite (127+ test files)
│   └── ...                 # Additional platform modules
├── product/                # Product layer
│   └── web/               # Next.js web application
└── core/                  # Core utilities and shared code

scripts/                    # Deployment and utility scripts (30+ files)
.github/workflows/          # CI/CD automation (15 workflows)
docs/                      # Project documentation
```

### Module Namespace:
- **Current**: `relay_ai.*` (as of Phase 1 & 2, completed 2024-11-10)
- **Previous**: `src.*` (deprecated and fully migrated)

---

## Deployment Infrastructure

### Beta Environment (OPERATIONAL ✅)
- **API**: Railway - `relay-beta-api`
  - URL: https://relay-beta-api.railway.app
  - Database: PostgreSQL on Railway
  - Status: Operational (fixed 2024-11-10)
- **Web**: Vercel - `relay-beta-web`
  - URL: https://relay-studio-one.vercel.app
  - Framework: Next.js 14
  - Status: Live
- **Database**: Supabase - `relay-beta-db`
  - Region: US West
  - Features: RLS, Vector extensions
  - Status: Connected

### Staging Environment (CONFIGURED, NOT DEPLOYED)
- **API**: `relay-staging-api` (planned on Railway)
- **Web**: `relay-staging-web` (Vercel project created)
- **Database**: Not yet provisioned
- **Workflow**: `deploy-staging.yml` (disabled until infrastructure ready)

### Production Environment (CONFIGURED, NOT DEPLOYED)
- **API**: `relay-prod-api` (planned on Railway)
- **Web**: `relay-prod-web` (Vercel project created)
- **Database**: `relay-prod-db` (Supabase project created)
- **Workflow**: `deploy-prod.yml` (ready, not triggered)

---

## Major Project Phases

### Phase 1: Naming Convention Implementation (2025-11-02)
**Status**: ✅ Complete
**Commits**: 3d58aa1, 01bf372
**Scope**: Documentation and config loader updates for `relay_ai.*` namespace
**Documentation**: `NAMING_CONVENTION_PHASE1_2_COMPLETE.md`

### Phase 2: Configuration Updates
**Status**: ✅ Complete (with Phase 1)
**Scope**: Config loader and environment variable handling

### Phase 3: Infrastructure Renaming & Setup (2025-11-02 to 2024-11-10)
**Status**: ✅ Beta Complete, Staging/Prod Pending
**Major Work**:
- Part A: GitHub Actions workflows created (3 workflows)
- Part B: Railway service renamed to `relay-beta-api`
- Part C: Vercel and Supabase projects created
- GitHub Secrets: 24 secrets configured (8 × 3 environments)
**Documentation**: `PHASE3_COMPLETE.md`, `PHASE3_EXECUTION_SUMMARY.md`

### Import Migration Completion (2024-11-10 & 2025-11-11)
**Status**: ✅ Complete
**Commits**: 7255b70, a5d31d2, 66a63ad, ec9288e
**Scope**: Fixed 187 files with old `src.*` imports → `relay_ai.*`
**Trigger**: Railway production crash (ModuleNotFoundError)
**Documentation**:
- `PROJECT_HISTORY/SESSIONS/2024-11-10_railway-deployment-fix-and-import-migration.md`
- `PROJECT_HISTORY/SESSIONS/2025-11-11_production-fix-complete.md`
- `PROJECT_HISTORY/CHANGE_LOG/2024-11-10-module-migration-completion.md`
- `PROJECT_HISTORY/CHANGE_LOG/2025-11-11-import-migration-final.md`
- `SESSION_2025-11-11_COMPLETE.md`

---

## Component Status Matrix

| Component | Status | Last Updated | Location | Notes |
|-----------|--------|--------------|----------|-------|
| **Backend API** | ✅ Operational | 2024-11-10 | Railway | Fixed import crash |
| **Web Frontend** | ✅ Live | 2024-11-10 | Vercel | Beta dashboard accessible |
| **Database** | ✅ Connected | 2025-11-02 | Supabase | RLS enabled |
| **Test Suite** | ✅ Imports Fixed | 2024-11-10 | relay_ai/platform/tests/tests/ | 127 test files |
| **CI/CD Pipelines** | ⚠️ Partial | 2025-11-02 | .github/workflows/ | Test path needs fix |
| **Monitoring** | ✅ Active | 2025-10-08 | Prometheus + Grafana | Metrics collection live |
| **OAuth Adapters** | ✅ Implemented | 2025-10-04 | relay_ai/platform/ | Gmail, Microsoft, Slack, Notion |
| **Vector Search** | ✅ Implemented | 2025-10-31 | relay_ai/platform/api/knowledge/ | Supabase pgvector |
| **Encryption** | ✅ Implemented | 2025-10-19 | relay_ai/platform/security/ | Envelope encryption |

---

## Critical File Locations

### Production-Critical Files:
```
relay_ai/platform/api/knowledge/api.py          # Knowledge API (fixed 2024-11-10)
relay_ai/platform/security/memory/api.py        # Memory API (fixed 2024-11-10)
relay_ai/platform/security/memory/index.py      # Memory index (fixed 2024-11-10)
relay_ai/product/web/app/page.tsx              # Homepage (updated 2024-11-10)
```

### Configuration Files:
```
.env                                           # Local development environment
.env.beta.example                             # Beta environment template
.env.example                                  # General template
pyproject.toml                                # Python project config
requirements.txt                              # Python dependencies
relay_ai/product/web/package.json             # Web app dependencies
```

### Infrastructure as Code:
```
.github/workflows/deploy-beta.yml             # Beta deployment automation
.github/workflows/deploy-staging.yml          # Staging (disabled)
.github/workflows/deploy-prod.yml             # Production (ready)
.github/workflows/ci.yml                      # Continuous integration
docker/                                       # Docker configurations
alembic/                                      # Database migrations
```

### Documentation:
```
README.md                                     # Project overview
PHASE3_COMPLETE.md                            # Phase 3 summary
PHASE3_EXECUTION_SUMMARY.md                   # Infrastructure guide
BETA_LAUNCH_CHECKLIST.md                      # Beta deployment checklist
NAMING_CONVENTION.md                          # Naming standards
PROJECT_HISTORY/                              # Historical records (this directory)
```

---

## Known Issues & Technical Debt

### Current Issues (as of 2024-11-10):

1. **GitHub Workflow Test Path Mismatch**
   - **File**: `.github/workflows/deploy-beta.yml`
   - **Problem**: Looks for `tests/` directory (doesn't exist)
   - **Reality**: Tests at `relay_ai/platform/tests/tests/`
   - **Impact**: CI/CD test step fails
   - **Severity**: Medium
   - **Status**: Documented, not fixed

2. **Vulnerable aiohttp Dependency**
   - **Package**: `aiohttp 3.9.3`
   - **Vulnerabilities**: 4 known issues
   - **Impact**: Potential security exposure
   - **Severity**: High
   - **Status**: Documented, not fixed

3. **Pre-existing Linting Issues**
   - **Location**: Multiple test files
   - **Problem**: Style warnings
   - **Impact**: Low (tests run, just warnings)
   - **Status**: Documented, not prioritized

### Resolved Issues:

1. ✅ **Railway Deployment Crash** (2024-11-10)
   - **Cause**: Old `src.*` imports in production API files
   - **Fix**: Commit 7255b70 - Updated to `relay_ai.*`
   - **Status**: Resolved

2. ✅ **Incomplete Import Migration** (2024-11-10)
   - **Cause**: 184 files still using `src.*` pattern
   - **Fix**: Commit a5d31d2 - Bulk migration script
   - **Status**: Resolved

3. ✅ **Beta Dashboard Discoverability** (2024-11-10)
   - **Cause**: No navigation from homepage to `/beta`
   - **Fix**: Commit 66a63ad - Added "Try Beta" buttons
   - **Status**: Resolved

---

## Recent Development Activity

### Last 10 Commits:
```
ec9288e (2025-11-11) docs: Session 2025-11-11 complete - critical fixes and full audit
66a63ad (2025-11-11) feat: Add 'Try Beta' navigation to homepage and update documentation
a5d31d2 (2025-11-11) refactor: Bulk update all src.* imports to relay_ai.* across codebase
7255b70 (2025-11-11) fix: Update src.* imports to relay_ai.* in critical API files
d38bbae (2024-11-10) docs: Phase 3 Complete - All infrastructure renamed and configured
a3cfc96 (2024-11-10) ci: temporarily disable staging workflow until infrastructure ready
5389227 (2024-11-10) docs: Phase 3 Part B - Railway service rename successfully executed
afaf5fe (2025-11-10) docs: Phase 3 complete - Execution summary and checklist
11fcacf (2025-11-10) docs: Phase 3 Part B & C - Infrastructure setup guides
a2304f4 (2025-11-10) feat: Phase 3 Part A - Create stage-specific GitHub Actions workflows
```

### Active Development Sessions:

**Most Recent Session**: 2025-11-11 (30 minutes)
- **Focus**: Critical production fix + import migration completion + historical documentation
- **Commits**: 4 (7255b70, a5d31d2, 66a63ad, ec9288e)
- **Files Changed**: 190 (186 code + 4 documentation)
- **Status**: ✅ Complete
- **Documentation**:
  - `PROJECT_HISTORY/SESSIONS/2025-11-11_production-fix-complete.md`
  - `SESSION_2025-11-11_COMPLETE.md`
  - `PROJECT_HISTORY/CHANGE_LOG/2025-11-11-import-migration-final.md`

**Previous Session**: 2024-11-10 (3 hours)
- **Focus**: Initial Railway crash investigation and partial fix
- **Commits**: 3 (7255b70, a5d31d2, 66a63ad)
- **Files Changed**: 189
- **Status**: ✅ Complete
- **Documentation**: `PROJECT_HISTORY/SESSIONS/2024-11-10_railway-deployment-fix-and-import-migration.md`

---

## Development Team & AI Models

### Primary Contributors:
- **Kyle Mabbott** (kmabbott81@gmail.com) - Project Owner
- **Claude Code (Sonnet 4.5)** - AI Development Assistant
- **ChatGPT** - Strategic planning and documentation (referenced in memory docs)

### AI Model Roles:
- **Claude Code**: Primary implementation, bug fixes, infrastructure work
- **ChatGPT**: Project roadmap, strategic guidance, memory management
- **Project Historian (this agent)**: Historical record keeping, documentation

---

## Testing & Quality Assurance

### Test Coverage:
- **Test Files**: 127+ files
- **Test Location**: `relay_ai/platform/tests/tests/`
- **Test Framework**: pytest
- **Coverage Areas**:
  - Actions (Gmail, Microsoft, Google adapters)
  - AI services (permissions, queue, schemas)
  - Authentication (OAuth, state management)
  - Cryptography (envelope encryption)
  - Integration tests
  - Knowledge base (security, acceptance)
  - Memory (API, encryption, RLS)
  - Rollout gates
  - Stream security
  - Core platform functionality

### Test Execution:
```bash
# Run full test suite:
pytest relay_ai/platform/tests/tests/ -v

# Run specific category:
pytest relay_ai/platform/tests/tests/actions/ -v
```

### CI/CD Testing:
- **Automated**: GitHub Actions on push to main
- **Status**: ⚠️ Test path needs fix (see known issues)
- **Smoke Tests**: Included in deployment workflows

---

## Dependencies & Technology Stack

### Backend:
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL (Railway + Supabase)
- **Vector Search**: pgvector extension
- **ORM**: SQLAlchemy + Alembic migrations
- **Auth**: Supabase Auth + OAuth adapters
- **Encryption**: Cryptography library (envelope encryption)
- **Monitoring**: Prometheus + Grafana
- **Testing**: pytest

### Frontend:
- **Framework**: Next.js 14
- **Language**: TypeScript
- **UI Library**: React
- **Styling**: Tailwind CSS (assumed)
- **Auth**: Supabase client
- **Deployment**: Vercel

### Infrastructure:
- **API Hosting**: Railway
- **Web Hosting**: Vercel
- **Database**: Supabase (managed PostgreSQL)
- **CI/CD**: GitHub Actions
- **Container**: Docker (configurations present)
- **Version Control**: Git

---

## Security & Compliance

### Security Features:
- ✅ Row-Level Security (RLS) for multi-tenant isolation
- ✅ Envelope encryption for sensitive data
- ✅ OAuth 2.0 authentication (multiple providers)
- ✅ JWT-based session management
- ✅ CORS configuration
- ✅ Rate limiting (documented)
- ⚠️ Dependency vulnerabilities (aiohttp - needs update)

### Security Documentation:
```
SECURITY.md                                   # Security policy
SECURITY-NOTICE.md                            # Security notices
DEPLOYMENT_SECURITY_AUDIT.md                  # Security audit report
DEPLOYMENT_SECURITY_FINDINGS_SUMMARY.md       # Findings summary
TENANT_ISOLATION_VERIFICATION_REPORT.md       # RLS verification
```

---

## Observability & Monitoring

### Monitoring Stack:
- **Metrics**: Prometheus (prometheus.yml configured)
- **Visualization**: Grafana dashboards
- **Logs**: Railway logs + Vercel analytics
- **Alerts**: alerts.yml configuration

### Key Metrics:
- API response times
- Error rates
- Database query performance
- OAuth success rates
- Vector search latency
- File upload sizes

### Documentation:
```
DEPLOYMENT_OBSERVABILITY_DESIGN.md            # Observability architecture
DEPLOYMENT_OBSERVABILITY_IMPLEMENTATION.md    # Implementation guide
DEPLOYMENT_OBSERVABILITY_QUICKSTART.md        # Quick start guide
DEPLOYMENT_OBSERVABILITY_SUMMARY.md           # Summary
INDEX_DEPLOYMENT_OBSERVABILITY.md             # Index of docs
grafana-dashboard-sprint60-phase1.json        # Grafana dashboard config
```

---

## Historical Documentation Archive

The project has extensive historical documentation from previous development phases. These files are retained for reference but represent completed work:

### Sprint Documentation (2025-09-28 to 2025-10-17):
```
2025.09.28-1404-START-HERE.md
2025.09.28-2030-DJP-IMPLEMENTATION-COMPLETE.md
2025.09.29-1445-NEXT-SPRINT-COMPLETE.md
2025.09.30-0912-RELEASE-ENGINEERING-COMPLETE.md
2025.10.01-1906-SPRINT5-DEPLOYMENT-COMPLETE.md
2025.10.04-GA-v1.0.1-COMPLETE.md
... (80+ historical sprint completion docs)
```

### Release Documentation:
```
RELEASE_NOTES_v1.0.0.md
.release_notes_v1.0.0.md
CHANGELOG.md
```

### Architecture & Design:
```
ARCHITECTURAL_REVIEW_PR42_S60_READINESS.md
RECOMMENDED_PATTERNS_S60_MIGRATION.md
KNOWLEDGE_API_DESIGN.md
VECTORSTORE_SCHEMA.sql
```

---

## Next Session Priorities

Based on current project state and documented issues:

### Immediate (Next Session):
1. ✅ **Fix GitHub Workflow Test Path**
   - File: `.github/workflows/deploy-beta.yml`
   - Change: `pytest tests/` → `pytest relay_ai/platform/tests/tests/`
   - Effort: 2 minutes

2. ✅ **Update aiohttp Dependency**
   - Command: `pip install --upgrade aiohttp`
   - Update: `requirements.txt`
   - Effort: 5 minutes
   - Impact: Resolves 4 security vulnerabilities

3. ✅ **Run Full Test Suite**
   - Command: `pytest relay_ai/platform/tests/tests/ -v`
   - Purpose: Verify import migration success
   - Effort: 10-20 minutes

### Short-term (This Week):
4. **Add Import Linting**
   - Prevent future `from src.` imports
   - Add to pre-commit hooks or ruff config
   - Effort: 15 minutes

5. **Document Import Convention**
   - Update CONTRIBUTING.md with namespace standards
   - Effort: 10 minutes

### Future (As Needed):
6. **Deploy Staging Environment**
   - Create Railway service: `relay-staging-api`
   - Deploy web to Vercel staging project
   - Provision staging database

7. **Deploy Production Environment**
   - Follow staging pattern for production
   - Reference: `PHASE3_VERCEL_SUPABASE_SETUP.md`

8. **Beta User Onboarding**
   - Reference: `BETA_LAUNCH_CHECKLIST.md`
   - Invite first 5-10 beta users

---

## Search Keywords for Future Reference

To help future AI agents and developers find relevant information:

**Module Migration**: `src.* imports`, `relay_ai namespace`, `ModuleNotFoundError`, `import migration`

**Production Issues**: `Railway crash`, `deployment failure`, `health check`, `production hotfix`

**Infrastructure**: `Phase 3`, `beta environment`, `staging setup`, `Vercel deployment`, `Railway service`, `Supabase database`

**Testing**: `pytest`, `test suite`, `relay_ai/platform/tests/tests/`, `import errors`

**Security**: `RLS`, `encryption`, `OAuth`, `multi-tenant`, `vulnerability scan`

**Documentation**: `PROJECT_HISTORY`, `CHANGE_LOG`, `session records`, `completion summary`

---

## Maintenance Notes

### This Index:
- **Created**: 2024-11-10
- **Last Updated**: 2025-11-11 (Session 2025-11-11 documentation)
- **Update Frequency**: After major sessions or phase completions
- **Maintained By**: Project Historian Agent

### Update Triggers:
- New development session completed
- Major infrastructure change
- Project phase completion
- Significant bug fix or feature addition
- Deployment to new environment

---

## Quick Reference

### Check Project Health:
```bash
# API Health:
curl https://relay-beta-api.railway.app/health

# Web App:
open https://relay-studio-one.vercel.app/

# Git Status:
git status
git log --oneline -10

# Test Suite:
pytest relay_ai/platform/tests/tests/ -v
```

### Common Commands:
```bash
# Run API locally:
cd relay_ai
python -m uvicorn platform.api.main:app --reload

# Run web app locally:
cd relay_ai/product/web
npm run dev

# Run migrations:
alembic upgrade head

# Deploy to Railway (beta):
git push origin beta
```

### Emergency Contacts:
- **Project Owner**: Kyle Mabbott (kmabbott81@gmail.com)
- **Railway Dashboard**: https://railway.app/
- **Vercel Dashboard**: https://vercel.com/
- **Supabase Dashboard**: https://supabase.com/

---

**End of Project Index**

This index provides a comprehensive overview of the project structure, status, and historical context. For detailed session information, consult `PROJECT_HISTORY/SESSIONS/`. For change details, see `PROJECT_HISTORY/CHANGE_LOG/`.
