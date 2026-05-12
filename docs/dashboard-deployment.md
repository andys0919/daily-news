# Investment Dashboard — Local Tunnel Deployment

`https://invest.aihost.dev/` is served from this Mac through Cloudflare Tunnel.
It is not a Cloudflare Pages / wrangler deployment.

## Live Topology

| Layer | Current value |
|---|---|
| Public URL | `https://invest.aihost.dev/` |
| Tunnel config | `~/.cloudflared/dailynews-aihost.yml` |
| Tunnel service | `~/Library/LaunchAgents/com.dailynews.cloudflared.plist` |
| Origin server | `127.0.0.1:8055` |
| Origin service | `~/Library/LaunchAgents/com.dailynews.dashboard-server.plist` |
| Static directory | `/Users/andy/Code/projects/telegram-bot/daily-news/web/dist` |
| Data export | `launchd/export-dashboard-data.sh` |

The dashboard server is a local `python3 -m http.server` process. Cloudflared
proxies `invest.aihost.dev` to that local origin.

## Daily Refresh

The normal daily path is:

1. `launchd/run-daily-news.sh` runs `main.py`.
2. `launchd/generate-source-atlas.sh` refreshes the source atlas.
3. `launchd/export-dashboard-data.sh` reads `data/news.db`, writes
   `web/src/data/*.json`, and runs `npm run build`.
4. The launchd dashboard server continues serving the rebuilt `web/dist/`.

Manual refresh:

```bash
bash launchd/export-dashboard-data.sh
```

Use a non-default database only when intentionally exporting from another
checkout:

```bash
DASHBOARD_DB_PATH=/Users/andy/Code/projects/telegram-bot/daily-news/data/news.db \
  bash launchd/export-dashboard-data.sh
```

Skip the Astro build only for diagnostics:

```bash
DASHBOARD_SKIP_BUILD=1 bash launchd/export-dashboard-data.sh
```

## Build Locally

```bash
cd web
npm install
npm run build
```

`npm run build` runs `astro check` and then emits static files under
`web/dist/`.

## Verify Live Services

```bash
launchctl print "gui/$(id -u)/com.dailynews.dashboard-server"
launchctl print "gui/$(id -u)/com.dailynews.cloudflared"
lsof -nP -iTCP:8055 -sTCP:LISTEN
curl -I http://127.0.0.1:8055/
curl -I https://invest.aihost.dev/
```

Expected result:

- both launchd services are `state = running`
- `127.0.0.1:8055` has a Python listener
- local origin and public URL return `200`

## Restart Live Dashboard

After changing the static path or service plist:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.dailynews.dashboard-server.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.dailynews.dashboard-server.plist
launchctl kickstart -k "gui/$(id -u)/com.dailynews.dashboard-server"

launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.dailynews.cloudflared.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.dailynews.cloudflared.plist
launchctl kickstart -k "gui/$(id -u)/com.dailynews.cloudflared"
```

Then re-run the verification commands above.

## Watchlist

The dashboard watchlist is tracked in:

```bash
data/watchlist.yaml
```

`dashboard_export.py` reads that file by default and writes the resolved list
to `web/src/data/watchlist.json`.

## Known Data Limits

- Yahoo Finance live prices are intentionally not part of this deployment path
  because the local IP has been rate-limited.
- Consensus estimates require a paid data vendor and are not generated from the
  current free-source pipeline.
- Insider / 13F / short-interest tables exist, but remain empty until their
  ingest jobs have real source payloads to persist.
