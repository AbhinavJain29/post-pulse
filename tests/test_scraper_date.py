"""Tests for LinkedIn Snowflake date extraction in scraper.py"""
from datetime import datetime, timezone

from scraper import _extract_activity_id, _date_from_url


# ---------------------------------------------------------------------------
# _extract_activity_id
# ---------------------------------------------------------------------------

def test_extract_from_posts_url():
    # Synthetic URL with "activity" in the slug — covered by the prefix pattern
    url = "https://www.linkedin.com/posts/johndoe_activity-7234567890123456789-abcd/"
    assert _extract_activity_id(url) == 7234567890123456789


def test_extract_from_posts_url_real_format():
    # Real LinkedIn /posts/ URL: ID is a bare number embedded in the slug
    url = "https://www.linkedin.com/posts/johndoe_some-title-words-7234567890123456789-AbCd/"
    assert _extract_activity_id(url) == 7234567890123456789


def test_extract_from_posts_url_no_activity_word():
    # Slug has no "activity" prefix at all — bare-number fallback must fire
    url = "https://www.linkedin.com/posts/janesmith_building-in-public-7300000000000000000-XyZw/"
    assert _extract_activity_id(url) == 7300000000000000000


def test_extract_from_feed_update_url():
    url = "https://www.linkedin.com/feed/update/urn:li:activity:7234567890123456789/"
    assert _extract_activity_id(url) == 7234567890123456789


def test_extract_from_analytics_url():
    url = "https://www.linkedin.com/analytics/post-summary/urn:li:ugcPost:7234567890123456789/"
    assert _extract_activity_id(url) == 7234567890123456789


def test_returns_none_for_url_without_activity_id():
    assert _extract_activity_id("https://www.linkedin.com/in/johndoe/") is None


def test_returns_none_for_empty_string():
    assert _extract_activity_id("") is None


def test_ignores_short_numeric_sequences():
    # Numbers under 15 digits should not match (not a valid Snowflake ID)
    assert _extract_activity_id("https://www.linkedin.com/posts/foo-12345-bar/") is None


# ---------------------------------------------------------------------------
# _date_from_url — known activity ID → expected date
# ---------------------------------------------------------------------------

def test_known_activity_id_gives_correct_date():
    # activity ID 7234567890123456789:
    # 7234567890123456789 >> 22 = 1723733371392 ms = 2024-08-15 (approx)
    activity_id = 7234567890123456789
    ms = activity_id >> 22
    expected = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    url = f"https://www.linkedin.com/posts/johndoe_activity-{activity_id}-xxxx/"
    result = _date_from_url(url)

    dt = datetime.fromisoformat(result)
    assert dt.year == expected.year
    assert dt.month == expected.month
    assert dt.day == expected.day


def test_date_from_real_posts_url():
    # Real-format /posts/ URL: no "activity" prefix in the slug
    activity_id = 7234567890123456789
    url = f"https://www.linkedin.com/posts/johndoe_some-title-words-{activity_id}-AbCd/"
    ms = activity_id >> 22
    expected = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    result = _date_from_url(url)
    dt = datetime.fromisoformat(result)
    assert dt.year == expected.year
    assert dt.month == expected.month
    assert dt.day == expected.day


def test_returns_empty_string_for_url_without_activity_id():
    assert _date_from_url("https://www.linkedin.com/in/johndoe/") == ""


def test_returns_empty_string_for_empty_url():
    assert _date_from_url("") == ""


def test_result_is_iso_format():
    url = "https://www.linkedin.com/posts/user_activity-7234567890123456789-abcd/"
    result = _date_from_url(url)
    # Should parse without raising
    dt = datetime.fromisoformat(result)
    assert dt.tzinfo is not None


def test_date_is_timezone_aware():
    url = "https://www.linkedin.com/posts/user_activity-7234567890123456789-abcd/"
    result = _date_from_url(url)
    dt = datetime.fromisoformat(result)
    assert dt.tzinfo == timezone.utc


def test_two_different_ids_give_different_dates():
    url1 = "https://www.linkedin.com/posts/user_activity-7100000000000000000-a/"
    url2 = "https://www.linkedin.com/posts/user_activity-7200000000000000000-b/"
    assert _date_from_url(url1) != _date_from_url(url2)


def test_older_id_gives_earlier_date():
    url_old = "https://www.linkedin.com/posts/user_activity-7100000000000000000-a/"
    url_new = "https://www.linkedin.com/posts/user_activity-7200000000000000000-b/"
    assert _date_from_url(url_old) < _date_from_url(url_new)
