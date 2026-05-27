# Post Pulse

Post Pulse is a local LinkedIn post analytics tracker. It scrapes your posts via browser automation, optionally generates Claude AI feedback on each one, and displays everything in a local web dashboard. All data stays on your machine — there's no central server.

---

## Requirements

- **Python 3.11+** — check your version with:
  ```bash
  python3 --version
  ```
  If it's missing or below 3.11, download it from: https://www.python.org/downloads/
- **Google Chrome** — Playwright drives your installed Chrome, not a bundled browser

## Install

Do this once for intial install:

```bash
git clone https://github.com/AbhinavJain29/post-pulse.git
cd post-pulse
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

> **Note:** Post Pulse uses your existing Google Chrome installation. Make sure Chrome is installed before running.

## Run

Every time you open a new terminal, navigate to the project directory and activate the virtual environment first:

```bash
cd <PATH-TO-CLONED-REPO>/post-pulse
source .venv/bin/activate
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
