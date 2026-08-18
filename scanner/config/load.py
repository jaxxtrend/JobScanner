"""Load JSON config and environment secrets. No defaults for missing keys."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCANNER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCANNER_DIR.parent
CONFIG_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = SCANNER_DIR / "sessions"
STATE_DIR = SCANNER_DIR / "state"
LOGS_DIR = SCANNER_DIR / "logs"

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
                f"channels.json[{index}] needs a username string or "
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
        raise ValueError("channels.json must be an array of @usernames")
    return [_normalize_channel(raw, i) for i, raw in enumerate(raw_list, start=1)]


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
