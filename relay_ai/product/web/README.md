# Relay Web — Marketing Site + Consumer App Shell

Next.js 14 consumer-facing application for Relay AI.

## Features

- **Landing page** (`/`) — Hero, features, comparison (with beta app link)
- **Beta dashboard** (`/beta`) — Live product experience
  - User authentication (Supabase magic links)
  - File upload & management
  - AI-powered semantic search
  - Usage tracking & quotas
  - Row-level security per user
- **Security proof** (`/security`) — Live dashboard, compliance docs
- **Pricing page** (`/pricing`) — All tier options, FAQ
- **SecurityBadge component** — Visible security on responses
- **SecurityDashboard component** — Activity feed, metrics, audit actions

## Stack

- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Linting:** ESLint + Prettier

## Development

### Setup
```bash
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

### Build
```bash
npm run build
npm run start
```

### Linting
```bash
npm run lint
npm run type-check
```

### Accessibility Tests
```bash
npm run test:a11y
```

## Architecture

```
app/
├── layout.tsx                 # Root layout with nav + footer (a11y)
├── page.tsx                   # Landing page (hero + features + comparison)
├── globals.css                # Tailwind + custom styles
├── beta/
│   └── page.tsx               # Beta dashboard (auth + file upload + search)
├── security/
│   └── page.tsx               # Security proof page
└── pricing/
    └── page.tsx               # Pricing tiers page

components/
├── SecurityBadge.tsx          # Visible security indicators (a11y)
└── SecurityDashboard.tsx      # Activity feed + metrics (a11y)
```

## Accessibility (a11y)

- ✓ Semantic HTML (`<nav>`, `<main>`, `<footer>`, etc.)
- ✓ ARIA labels and live regions
- ✓ Keyboard navigation (Tab, Enter, Escape)
- ✓ Color contrast (WCAG AAA)
- ✓ Alt text on images
- ✓ Focus indicators
- ✓ Screen reader tested

## Security

- ✗ No hardcoded secrets (checked by CI)
- ✗ No API keys in code
- ✓ Environment variables for sensitive config
- ✓ Content Security Policy ready (TODO)

## Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Deployment

### Railway

```bash
git push origin main
# Railway auto-builds and deploys
```

### Vercel

```bash
vercel deploy
```

## Performance

- **TTFV target:** <1.0s p95
- **Lighthouse:** 90+
- **Bundle size:** <100KB (gzipped)

## Current Status

✅ **Beta dashboard is live and functional** at `/beta`
- Supabase authentication (magic links) working
- File upload & indexing API integration ready
- Semantic search connected to knowledge API
- Usage tracking per user implemented

## Next Steps (Roadmap)

1. **Google OAuth** — Add Google sign-in as alternative to magic links
2. **User account management** (`/account`) — Profile, billing, API keys
3. **Admin dashboard** (`/admin`) — Usage analytics, content moderation
4. **Mobile responsiveness** — Optimize beta dashboard for mobile

## Contributing

- Follow TypeScript strict mode
- Run `npm run lint` before committing
- Maintain a11y standards
- Update tests alongside features

## License

Proprietary — Relay AI 2025
