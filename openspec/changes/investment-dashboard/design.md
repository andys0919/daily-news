# Design — investment-dashboard

See master spec at `docs/superpowers/specs/2026-05-10-investment-dashboard-design.md`.

## Highlights

- New `web/` directory uses Astro 5 SSG.
- Python `dashboard_export.py` writes JSON to `web/src/data/` at build time (daily cron).
- All deploy secrets parameterised via `.env.example` + `wrangler.toml.template`.
- ralph does NOT execute `wrangler deploy` or `git push`.

## Out of scope

- Real-time data feeds.
- Multi-tenant SaaS.
- Mobile-native app.
