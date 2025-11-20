# Environment Variables Snapshot - 2025-10-07

**Note:** Values are REDACTED for security. This document lists variable names only.

## Backend (Railway)

### Database
- `DATABASE_URL` - Private Postgres connection string
- `DATABASE_PUBLIC_URL` - Public Postgres connection string (for migrations from CI)

### Authentication
- `ACTIONS_SIGNING_SECRET` - HMAC secret for webhook signing (64-char hex)

### Rate Limiting
- `RATE_LIMIT_ENABLED` - Enable/disable rate limiting (default: true)
- `RATE_LIMIT_EXEC_PER_MIN` - Executions per minute per workspace (default: 60)
- `REDIS_URL` - Redis connection string (optional, falls back to in-process)

### Actions/Webhooks
- `ACTIONS_ENABLED` - Enable actions endpoints (default: true)
- `WEBHOOK_URL` - Webhook receiver URL for testing

### Telemetry/Observability
- `TELEMETRY_ENABLED` - Enable Prometheus metrics (default: true)
- `OTEL_ENABLED` - Enable OpenTelemetry export (default: false)
- `OTEL_ENDPOINT` - OTLP endpoint (optional)

### CI/CD (GitHub Secrets)
- `RAILWAY_TOKEN` - Railway CLI token for deployments
- `ADMIN_KEY` - Admin API key for smoke tests
- `DEV_KEY` - Developer API key for smoke tests

## Studio (Vercel)

### Backend Integration
- `NEXT_PUBLIC_API_BASE_URL` - Backend API URL (https://relay-production-f2a6.up.railway.app)
- `API_BASE_URL` - Server-side API URL

### Authentication
- `NEXTAUTH_SECRET` - NextAuth session secret
- `NEXTAUTH_URL` - NextAuth callback URL

### OAuth Providers (Planned for Sprint 52)
- `GOOGLE_CLIENT_ID` - TBD
- `GOOGLE_CLIENT_SECRET` - TBD
- `GITHUB_CLIENT_ID` - TBD
- `GITHUB_CLIENT_SECRET` - TBD

---

## Configuration Sources

**Backend:**
- Railway project: relay-backend
- Variables managed via: `railway variables`
- Secrets set in GitHub Actions for CI/CD

**Studio:**
- Vercel project: relay-studio
- Variables managed via: Vercel dashboard
- Environment-specific: production, preview, development

---

## Security Notes

1. All secrets use 64-char hex or equivalent entropy
2. Database URLs use SSL mode (sslmode=require)
3. No secrets committed to git
4. Secrets rotated quarterly (last rotation: TBD)
5. Railway secrets masked in logs

---

Generated: 2025-10-07
Source: Railway CLI, Vercel dashboard, GitHub Secrets
