## Why

daily-news produces rich data (news, financials, transcripts, insider, 13F, short-interest, macro) but consumption is via shell-rendered markdown or daily HTML report. An interactive web dashboard makes the data usable for daily investment decisions.

## What Changes

- Add `dashboard_export.py` Python module that reads SQLite + bundle and writes JSON snapshots.
- Add `web/` Astro project (Tailwind, shadcn-style components, uPlot charts) with 5 pages: home, per-stock, news, calendar, decisions.
- Add Cloudflare Pages config (template only, no real secrets).
- Add deployment guide under `docs/dashboard-deployment.md`.

## Capabilities

### New Capabilities
- `investment-dashboard-export`: Export daily-news SQLite data to JSON for static-site consumption.
- `investment-dashboard-web`: Astro-based static site with 5 dashboard pages.

## Impact

- New files only. No edits to existing Python pipeline modules, `config.yaml`, or existing templates.
- New CF Pages project `daily-news-dashboard` — isolated, deploys to subdomain only.
- No deployment executed by ralph. User runs `wrangler deploy` manually.
