# Post Pulse

Post Pulse is a local LinkedIn post analytics tracker. It scrapes your posts via browser automation, optionally generates Claude AI feedback on each one, and displays everything in a local web dashboard. All data stays on your machine — there's no central server.

---

## Install

```bash
git clone https://github.com/your-username/post-pulse.git
cd post-pulse
pip install -e .
playwright install chromium
```

## Run

```bash
post-pulse
```

The app opens at `http://localhost:8080` (tries ports 8080–8084 if 8080 is busy). On first launch it redirects to the Settings page where you can add your Anthropic API key.

## First-time setup

1. Open Settings → paste your [Anthropic API key](https://console.anthropic.com/) → click **Verify & Save**
2. Adjust **Posts per sync** (default: 10) and toggle **AI Feedback** on or off
3. Go to the Dashboard → click **Sync Now**
4. A Chrome window opens — log in to LinkedIn if prompted
5. Posts and AI feedback appear in the dashboard once the sync completes

## CLI usage

```bash
python tracker.py                  # scrape with defaults
python tracker.py --limit 25       # scrape up to 25 posts
python tracker.py --no-ai          # skip AI feedback
python tracker.py --reset          # clear all scraped data
```

## Data

Everything lives in `~/.post-pulse/`:

| File | Contents |
|------|----------|
| `tracker.db` | SQLite database of posts + AI feedback |
| `config.json` | Settings (API key, preferences) |
| `linkedin_cookies.json` | LinkedIn session (auto-managed) |

## Requirements

- Python 3.11+
- Google Chrome (used by Playwright for scraping)
- Anthropic API key (optional — only needed for AI feedback)
