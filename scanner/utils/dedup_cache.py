"""JSON cache of vacancy links already written to reports."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def load_seen_links(cache_path: Path) -> set[str]:
    if not cache_path.exists():
        return set()
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        links = set(data.get("seen_links", []))
        log.info("Dedup cache loaded %s links from %s", len(links), cache_path)
        return links
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read dedup cache {cache_path}: {exc}") from exc


def save_seen_links(seen_links: set[str], cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "seen_links": sorted(seen_links),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Dedup cache saved %s links to %s", len(seen_links), cache_path)
