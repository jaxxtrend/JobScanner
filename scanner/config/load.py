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
    "domain_markers",
)
_CHANNEL_REQUIRED = ("id", "name", "link", "relevance_score", "enabled")


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
    for list_key in ("keywords", "green", "redwords", "stopwords", "domain_markers"):
        if not isinstance(data[list_key], list):
            raise ValueError(f"settings.json.{list_key} must be an array")
    return data


def load_channels() -> list[dict[str, Any]]:
    data = _read_json(CONFIG_DIR / "channels.json")
    if not isinstance(data, dict) or "channels" not in data:
        raise ValueError("channels.json must contain a 'channels' array")
    channels = data["channels"]
    if not isinstance(channels, list):
        raise ValueError("channels.json.channels must be an array")
    result: list[dict[str, Any]] = []
    for i, raw in enumerate(channels):
        if not isinstance(raw, dict):
            raise ValueError(f"channels.json.channels[{i}] must be an object")
        missing = [key for key in _CHANNEL_REQUIRED if key not in raw]
        if missing:
            raise ValueError(f"channels.json.channels[{i}] missing keys: {', '.join(missing)}")
        channel = dict(raw)
        channel.setdefault("category", "")
        tags = channel.get("require_tags") or []
        if not isinstance(tags, list):
            raise ValueError(f"channels.json.channels[{i}].require_tags must be an array")
        channel["require_tags"] = [str(t) for t in tags]
        result.append(channel)
    return result


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
