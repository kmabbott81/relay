# Relay Web — Marketing Site + Consumer App Shell

Next.js 14 consumer-facing application for Relay AI.

## Features

- **Landing page** (`/`) — Hero, features, comparison
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
├── layout.tsx          # Root layout with nav + footer (a11y)
├── page.tsx            # Landing page (hero + features + comparison)
├── globals.css         # Tailwind + custom styles
├── security/
│   └── page.tsx        # Security proof page
└── pricing/
    └── page.tsx        # Pricing tiers page

components/
├── SecurityBadge.tsx    # Visible security indicators (a11y)
└── SecurityDashboard.tsx # Activity feed + metrics (a11y)
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

## Next Steps

1. **Wire API** — Connect to relay-ai/platform/api/mvp.py
2. **Add auth** — Google OAuth callback
3. **Dashboard** — User account management
4. **Upload widget** — Document upload UI

## Contributing

- Follow TypeScript strict mode
- Run `npm run lint` before committing
- Maintain a11y standards
- Update tests alongside features

## License

Proprietary — Relay AI 2025
