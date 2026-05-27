# Post Pulse

Post Pulse is a local LinkedIn post analytics tracker. It scrapes your posts via browser automation, optionally generates Claude AI feedback on each one, and displays everything in a local web dashboard. All data stays on your machine — there's no central server.

---

## Install

```bash
git clone https://github.com/AbhinavJain29/post-pulse.git
cd post-pulse
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install  # installs browser drivers (separate from the pip package)
```

> **Note:** Post Pulse uses your existing Google Chrome installation. Make sure Chrome is installed before running.

## Run

```bash
post-pulse
```

The app opens at `http://localhost:8080` (tries ports 8080–8084 if 8080 is busy).

## First-time setup

1. Go to the Dashboard → choose how many posts to fetch → click **Sync Now**
2. A Chrome window opens — log in to LinkedIn if prompted
3. Posts appear in the dashboard once the sync completes

## Data

Everything lives in `~/.post-pulse/`:

| File | Contents |
|------|----------|
| `tracker.db` | SQLite database of posts + AI feedback |
| `config.json` | Settings (API key, preferences) |
| `linkedin_cookies.json` | LinkedIn session (auto-managed) |

### Note: 
The metrics are pulled once and not on every sync. For the latest posts, you might notice discrepancies in the metrics.

## Requirements

- Python 3.11+
- Google Chrome (Playwright drives your installed Chrome — not a bundled browser)
