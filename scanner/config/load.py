"""Load JSON config and environment secrets. No defaults for missing keys."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCANNER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCANNER_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
CACHE_DIR = REPO_ROOT / "cache"
SESSIONS_DIR = CACHE_DIR / "sessions"
STATE_DIR = CACHE_DIR / "state"
LOGS_DIR = CACHE_DIR / "logs"


def ensure_cache_dirs() -> Path:
    """Create cache/ and its subfolders on first run if missing."""
    for path in (CACHE_DIR, SESSIONS_DIR, STATE_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR

_SETTINGS_REQUIRED = (
    "last_days",
    "groups_limit",
    "letters_limit",
    "min_relevance",
    "near_dup_threshold",
    "rescan_hours",
    "keywords",
    "green",
    "redwords",
    "stopwords",
    "resume_stopwords",
    "domain_markers",
)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_settings() -> dict[str, Any]:
    data = _read_json(CONFIG_DIR / "settings.json")
    if not isinstance(data, dict):
        raise ValueError("settings.json must be an object")
    missing = [key for key in _SETTINGS_REQUIRED if key not in data]
    if missing:
        raise ValueError(f"settings.json missing keys: {', '.join(missing)}")
    for list_key in ("keywords", "green", "redwords", "stopwords", "resume_stopwords", "domain_markers"):
        if not isinstance(data[list_key], list):
            raise ValueError(f"settings.json.{list_key} must be an array")
    return data


def parse_telegram_username(value: str) -> str:
    username = value.strip()
    if not username:
        raise ValueError("Empty Telegram username")
    if "t.me/" in username.lower():
        username = username.split("t.me/", 1)[1]
    username = username.split("/")[0].split("?")[0].lstrip("@")
    if not username:
        raise ValueError(f"Cannot parse Telegram username from: {value}")
    return username


def _normalize_channel(raw: Any, index: int) -> dict[str, Any]:
    idx = str(index)
    if isinstance(raw, str):
        username = parse_telegram_username(raw)
        return {
            "id": idx,
            "name": username,
            "link": f"https://t.me/{username}",
            "enabled": True,
            "require_tags": [],
        }
    if isinstance(raw, dict):
        user_raw = raw.get("user") or raw.get("username") or raw.get("link")
        if not user_raw:
            raise ValueError(
                f"channels.json[{index}] needs a t.me URL string or "
                "object with user/username/link"
            )
        username = parse_telegram_username(str(user_raw))
        tags = raw.get("tags") or raw.get("require_tags") or []
        if not isinstance(tags, list):
            raise ValueError(f"channels.json[{index}].tags must be an array")
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"channels.json[{index}].enabled must be a boolean")
        return {
            "id": str(raw.get("id") or idx),
            "name": str(raw.get("name") or username),
            "link": f"https://t.me/{username}",
            "enabled": enabled,
            "require_tags": [str(t) for t in tags],
        }
    raise ValueError(f"channels.json[{index}] must be a string or object")


def load_channels() -> list[dict[str, Any]]:
    data = _read_json(CONFIG_DIR / "channels.json")
    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict) and isinstance(data.get("channels"), list):
        raw_list = data["channels"]
    else:
        raise ValueError("channels.json must be an array of https://t.me/... links")
    return [_normalize_channel(raw, i) for i, raw in enumerate(raw_list, start=1)]


def load_digest_config() -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return (channel_username -> pattern_id, pattern definitions)."""
    data = _read_json(CONFIG_DIR / "digest_patterns.json")
    if not isinstance(data, dict) or not isinstance(data.get("patterns"), list):
        raise ValueError("digest_patterns.json must be an object with a patterns array")

    raw_bindings = data.get("bindings", {})
    if not isinstance(raw_bindings, dict):
        raise ValueError("digest_patterns.json.bindings must be an object")
    bindings: dict[str, str] = {}
    for key, value in raw_bindings.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("digest_patterns.json.bindings keys must be non-empty strings")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"digest_patterns.json.bindings[{key!r}] must be a non-empty pattern id"
            )
        bindings[parse_telegram_username(key).lower()] = value.strip()

    patterns: list[dict[str, Any]] = []
    for index, raw in enumerate(data["patterns"]):
        if not isinstance(raw, dict):
            raise ValueError(f"digest_patterns.json.patterns[{index}] must be an object")
        pattern_id = raw.get("id")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            raise ValueError(f"digest_patterns.json.patterns[{index}].id must be a non-empty string")
        start_line = raw.get("start_line")
        if not isinstance(start_line, list) or not start_line:
            raise ValueError(
                f"digest_patterns.json.patterns[{index}].start_line must be a non-empty array"
            )
        skip_line = raw.get("skip_line", [])
        if not isinstance(skip_line, list):
            raise ValueError(f"digest_patterns.json.patterns[{index}].skip_line must be an array")
        min_blocks = raw.get("min_blocks", 2)
        if not isinstance(min_blocks, int) or min_blocks < 2:
            raise ValueError(
                f"digest_patterns.json.patterns[{index}].min_blocks must be an integer >= 2"
            )
        patterns.append({
            "id": pattern_id.strip(),
            "description": str(raw.get("description") or ""),
            "start_line": [str(item) for item in start_line],
            "skip_line": [str(item) for item in skip_line],
            "min_blocks": min_blocks,
        })

    pattern_ids = {p["id"] for p in patterns}
    for channel, pattern_id in bindings.items():
        if pattern_id not in pattern_ids:
            raise ValueError(
                f"digest_patterns.json.bindings[{channel!r}] points to unknown pattern {pattern_id!r}"
            )
    return bindings, patterns


def load_env() -> tuple[int, str, Path]:
    load_dotenv(REPO_ROOT / ".env")
    api_id = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise ValueError(
            "TG_API_ID and TG_API_HASH must be set in the repo-root .env "
            "(copy .env.example)."
        )
    try:
        api_id_int = int(api_id)
    except ValueError as exc:
        raise ValueError("TG_API_ID must be an integer") from exc
    output_raw = os.getenv("OUTPUT_PATH", "").strip()
    output_path = Path(output_raw) if output_raw else REPO_ROOT / "output"
    return api_id_int, api_hash, output_path
