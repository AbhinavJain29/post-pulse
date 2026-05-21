"""
LinkedIn post scraper using Playwright.
Logs in, navigates to your recent activity, extracts post URLs and content
from the feed, then visits each post's analytics page for accurate metrics.
Persists cookies to avoid repeated logins.
"""
import asyncio
import json
import random
import re
from datetime import datetime, timezone, timedelta, UTC
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page

COOKIES_FILE = "linkedin_cookies.json"
RECENT_ACTIVITY_URL = "https://www.linkedin.com/in/me/recent-activity/shares/"
LOGIN_URL = "https://www.linkedin.com/login"


class LinkedInScraper:
    def __init__(self, headless: bool = False, cookies_path: "Path | str | None" = None):
        self.headless = headless
        self.cookies_path = Path(cookies_path) if cookies_path else Path(COOKIES_FILE)
        self.playwright = None
        self.browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
            channel="chrome",
        )
        context_options = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        self.context = await self.browser.new_context(**context_options)
        if _cookies_are_fresh(self.cookies_path):
            with open(self.cookies_path) as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            print("Loaded saved session cookies.")
        elif self.cookies_path.exists():
            print("Session cookies are stale (>30 days) — will prompt for login.")
        self.page = await self.context.new_page()

    async def login(self) -> bool:
        """
        Open the LinkedIn login page and wait for the user to log in manually.
        If a saved session exists, it's restored automatically.
        Cookies are saved after a successful login.
        """
        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await _random_delay(1.0, 2.5)

        if any(x in self.page.url for x in ["/feed", "/mynetwork", "/in/me"]):
            print("Session restored — already logged in.")
            return True

        print("\nPlease log in to LinkedIn in the browser window.")
        print("Waiting until you're logged in...")

        await self.page.wait_for_url(
            lambda url: any(x in url for x in ["/feed", "/mynetwork", "/in/me"]),
            timeout=300_000,
        )

        cookies = await self.context.cookies()
        with open(self.cookies_path, "w") as f:
            json.dump(cookies, f)
        print("Login successful. Session saved.")
        return True

    async def get_my_posts(
        self,
        limit: int = 200,
        skip_urls: "set[str] | None" = None,
        on_post_ready: "callable | None" = None,
    ) -> list[dict]:
        """
        Phase A: Scroll the activity feed and collect post content + analytics URLs.
        Phase B: Visit each analytics page to extract all metrics.

        skip_urls: set of already-scraped URLs to skip (incremental runs).
        on_post_ready: optional async callback(post, i, total) invoked after each
                       post's analytics are fetched, enabling incremental persistence.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        if skip_urls:
            print(f"\nWill skip {len(skip_urls)} already-scraped URLs...")
        print(f"Navigating to recent activity (cutoff={cutoff.date()}, limit={limit})...")

        # --- Phase A: collect posts from feed ---
        posts = await self._collect_from_feed(limit, skip_urls or set(), cutoff)

        if not posts:
            return []

        # --- Phase B: enrich each post from its analytics page ---
        print(f"\nFetching analytics for {len(posts)} posts...")
        total = len(posts)
        for i, post in enumerate(posts, 1):
            print(f"  Analytics ({i}/{total}): {post['url'][:70]}...")
            try:
                metrics = await self._fetch_post_analytics(post["url"])
                post.update(metrics)
            except Exception as e:
                print(f"  Warning: analytics fetch failed — {e}")
            if on_post_ready:
                await on_post_ready(post, i, total)
            await _random_delay(1.5, 3.0)

        print(f"\nDone. {len(posts)} posts with full metrics.")
        return posts

    async def _collect_from_feed(
        self,
        limit: int,
        skip_urls: set[str],
        cutoff: datetime,
    ) -> list[dict]:
        """Scroll the activity feed and collect post stubs (content + analytics URL)."""
        await self.page.goto(RECENT_ACTIVITY_URL, wait_until="domcontentloaded")
        await _random_delay(2.5, 4.5)

        container_selectors = [
            ".feed-shared-update-v2",
            "[data-urn*='activity']",
            ".occludable-update",
        ]

        posts = []
        seen_in_feed: set[str] = set()
        seen_elements = 0
        done = False
        max_scroll_attempts = 50

        for _ in range(max_scroll_attempts):
            post_elements = []
            for sel in container_selectors:
                post_elements = await self.page.query_selector_all(sel)
                if post_elements:
                    break

            new_elements = post_elements[seen_elements:]
            seen_elements = len(post_elements)

            for element in new_elements:
                if len(posts) >= limit:
                    done = True
                    break
                try:
                    post = await self._extract_feed_data(element)
                    if not post or not post.get("url"):
                        continue
                    if post["url"] in seen_in_feed:
                        continue

                    post_date = _parse_iso_date(post.get("date_iso", ""))
                    if post_date and post_date < cutoff:
                        print(f"  Reached posts older than {cutoff.date()} — stopping.")
                        done = True
                        break

                    if post["url"] in skip_urls:
                        print(f"  Skipping already-scraped: {post['url'][:70]}...")
                        seen_in_feed.add(post["url"])
                        continue

                    seen_in_feed.add(post["url"])
                    posts.append(post)
                    print(f"  [{len(posts)}] {post['url'][:70]}...")
                    await _random_delay(0.2, 0.6)
                except Exception as e:
                    print(f"  Warning: could not extract post — {e}")

            if done:
                break

            prev_height = await self.page.evaluate("document.body.scrollHeight")
            await _human_scroll(self.page)
            await _random_delay(1.8, 3.5)
            new_height = await self.page.evaluate("document.body.scrollHeight")

            if new_height == prev_height:
                print("  No more posts to load.")
                break

            print(f"  Scrolling... ({len(posts)} posts collected so far)")

        print(f"\nFeed scrape complete: {len(posts)} posts found.")
        return posts

    async def _extract_feed_data(self, element) -> dict | None:
        """Extract content and analytics URL from a single feed post element."""
        post = {
            "url": None,
            "content": "",
            "date_iso": "",
            "impressions": 0,
            "reactions": 0,
            "comments": 0,
            "reposts": 0,
            "profile_viewers": 0,
            "followers_gained": 0,
            "scraped_at": datetime.now().isoformat(),
        }

        # --- Analytics URL (preferred) or post URL ---
        for url_sel in [
            "a[href*='/analytics/post-summary/']",
            "a[href*='/posts/']",
            "a[href*='ugcPost']",
            "a[href*='activity']",
        ]:
            try:
                link = await element.query_selector(url_sel)
                if link:
                    href = await link.get_attribute("href")
                    if href:
                        post["url"] = (
                            "https://www.linkedin.com" + href.split("?")[0]
                            if href.startswith("/")
                            else href.split("?")[0]
                        )
                        break
            except Exception:
                pass

        if not post["url"]:
            return None

        # --- Content ---
        for content_sel in [
            ".feed-shared-update-v2__description",
            ".feed-shared-text",
            ".update-components-text",
            "[data-test-id='main-feed-activity-card__commentary']",
        ]:
            try:
                el = await element.query_selector(content_sel)
                if el:
                    post["content"] = (await el.inner_text()).strip()
                    break
            except Exception:
                pass

        # --- date_iso derived from the Snowflake activity ID in the URL ---
        post["date_iso"] = _date_from_url(post["url"])

        # --- Impressions from feed text (fallback; analytics page is more reliable) ---
        try:
            full_text = await element.inner_text()
            match = re.search(r"([\d,]+)\s+impressions?", full_text, re.IGNORECASE)
            if match:
                post["impressions"] = _parse_count(match.group(1))
        except Exception:
            pass

        return post

    async def _fetch_post_analytics(self, analytics_url: str) -> dict:
        """
        Navigate to a post's analytics page and extract all metrics via
        text-based pattern matching (resilient to DOM class changes).
        """
        metrics = {
            "impressions": 0,
            "reactions": 0,
            "comments": 0,
            "reposts": 0,
            "profile_viewers": 0,
            "followers_gained": 0,
        }

        await self.page.goto(analytics_url, wait_until="domcontentloaded")
        await _random_delay(2.0, 3.5)

        try:
            body_text = await self.page.inner_text("body")
        except Exception as e:
            print(f"  Warning: could not read analytics page — {e}")
            return metrics

        count_patterns = {
            "impressions": r"Impressions\s*\n\s*([\d,.]+[KkMm]?)",
            "reactions": r"Reactions\s*\n\s*([\d,.]+[KkMm]?)",
            "comments": r"Comments\s*\n\s*([\d,.]+[KkMm]?)",
            "reposts": r"Reposts\s*\n\s*([\d,.]+[KkMm]?)",
            "profile_viewers": r"Profile viewers from this post\s*\n\s*([\d,.]+[KkMm]?)",
            "followers_gained": r"Followers gained from this post\s*\n\s*([\d,.]+[KkMm]?)",
        }

        for key, pattern in count_patterns.items():
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                metrics[key] = _parse_count(match.group(1))

        return metrics

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _random_delay(min_s: float, max_s: float):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _human_scroll(page: Page):
    """Scroll down in small random increments to mimic human behaviour."""
    current_y = await page.evaluate("window.scrollY")
    target_y = await page.evaluate("document.body.scrollHeight")
    step = random.randint(300, 600)
    while current_y < target_y:
        current_y = min(current_y + step, target_y)
        await page.evaluate(f"window.scrollTo(0, {current_y})")
        await asyncio.sleep(random.uniform(0.05, 0.15))
        step = random.randint(300, 600)


def _cookies_are_fresh(path: Path, max_age_days: int = 30) -> bool:
    """Return True if the cookies file exists and is less than max_age_days old."""
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age.days < max_age_days


def _extract_activity_id(url: str) -> int | None:
    """Extract the numeric Snowflake activity ID from a LinkedIn post URL.

    Handles two formats:
    - Prefixed: activity:ID / ugcPost:ID / activity-ID (feed and analytics URLs)
    - Bare: /posts/username_title-words-ID-SHORTCODE/ (posts URLs)
    """
    match = re.search(r"(?:activity|ugcPost)[:\-](\d{15,})", url)
    if match:
        return int(match.group(1))
    # /posts/ URLs embed the Snowflake ID as a bare 15+ digit number in the slug
    match = re.search(r"(?<!\d)(\d{15,})(?!\d)", url)
    return int(match.group(1)) if match else None


def _date_from_url(url: str) -> str:
    """Derive post date from the Snowflake activity ID embedded in the URL.

    LinkedIn Snowflake IDs: (id >> 22) gives Unix milliseconds since epoch.
    Returns an ISO 8601 string, or empty string if no activity ID is found.
    """
    activity_id = _extract_activity_id(url)
    if activity_id is None:
        return ""
    ms = activity_id >> 22
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _parse_iso_date(date_iso: str) -> datetime | None:
    if not date_iso:
        return None
    try:
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_count(text: str) -> int:
    """Parse counts like '1,234', '2.1K', '1M' into integers."""
    if not text:
        return 0
    text = text.strip().replace(",", "")
    match = re.search(r"([\d.]+)\s*([KkMm]?)", text)
    if not match:
        return 0
    num = float(match.group(1))
    suffix = match.group(2).upper()
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    return int(num)
