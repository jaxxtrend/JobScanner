"""Per-channel Telegram message cursors for incremental scans."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def load_cursors(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read cursor file {path}: {exc}") from exc
    channels = data.get("channels", {})
    if not isinstance(channels, dict):
        raise ValueError(f"{path}: 'channels' must be an object")
    return channels


def save_cursors(path: Path, channels: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"channels": channels}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved cursors for %s channels to %s", len(channels), path)


def last_id_for(cursors: dict[str, dict[str, Any]], key: str) -> int | None:
    entry = cursors.get(key)
    if not entry:
        return None
    value = entry.get("last_id")
    if value is None:
        return None
    return int(value)
