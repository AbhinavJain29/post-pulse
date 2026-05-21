"""Tests for core/config.py"""
import json
from pathlib import Path

import pytest

from core.config import Settings, load, save, DEFAULT_DATA_DIR


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

def test_settings_defaults():
    s = Settings()
    assert s.anthropic_api_key == ""
    assert s.scrape_limit == 10
    assert s.ai_feedback_enabled is False
    assert s.data_dir == DEFAULT_DATA_DIR


def test_settings_derived_paths():
    s = Settings(data_dir=Path("/tmp/pp"))
    assert s.db_path == Path("/tmp/pp/tracker.db")
    assert s.cookies_path == Path("/tmp/pp/linkedin_cookies.json")
    assert s.pipeline_state_path == Path("/tmp/pp/pipeline_state.json")
    assert s.config_path == Path("/tmp/pp/config.json")


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------

def test_load_returns_defaults_when_no_file(tmp_path):
    s = load(data_dir=tmp_path)
    assert s.anthropic_api_key == ""
    assert s.scrape_limit == 10
    assert s.ai_feedback_enabled is False
    assert s.data_dir == tmp_path


def test_load_reads_existing_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "anthropic_api_key": "sk-test-123",
        "scrape_limit": 50,
    }))
    s = load(data_dir=tmp_path)
    assert s.anthropic_api_key == "sk-test-123"
    assert s.scrape_limit == 50


def test_load_partial_config_uses_defaults_for_missing_keys(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"anthropic_api_key": "sk-abc"}))
    s = load(data_dir=tmp_path)
    assert s.anthropic_api_key == "sk-abc"
    assert s.scrape_limit == 10  # default
    assert s.ai_feedback_enabled is False  # default


def test_load_corrupt_json_returns_defaults(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{this is not valid json")
    s = load(data_dir=tmp_path)
    assert s.anthropic_api_key == ""
    assert s.scrape_limit == 10


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_path):
    s = Settings(anthropic_api_key="sk-new", scrape_limit=10, data_dir=tmp_path)
    save(s)
    assert s.config_path.exists()


def test_save_round_trip(tmp_path):
    s = Settings(anthropic_api_key="sk-roundtrip", scrape_limit=99,
                 ai_feedback_enabled=False, data_dir=tmp_path)
    save(s)
    loaded = load(data_dir=tmp_path)
    assert loaded.anthropic_api_key == "sk-roundtrip"
    assert loaded.scrape_limit == 99
    assert loaded.ai_feedback_enabled is False


def test_save_creates_data_dir_if_missing(tmp_path):
    nested = tmp_path / "nested" / "dir"
    s = Settings(data_dir=nested)
    save(s)
    assert nested.exists()
    assert s.config_path.exists()


def test_save_overwrites_existing_config(tmp_path):
    s1 = Settings(anthropic_api_key="sk-old", data_dir=tmp_path)
    save(s1)
    s2 = Settings(anthropic_api_key="sk-new", data_dir=tmp_path)
    save(s2)
    loaded = load(data_dir=tmp_path)
    assert loaded.anthropic_api_key == "sk-new"
