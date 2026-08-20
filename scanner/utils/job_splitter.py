"""Split multi-vacancy digest posts using JSON digest patterns."""

from __future__ import annotations

import re
from typing import Any

from utils.url_helpers import extract_links_from_text

_BULLET_LINE = re.compile(r"^[•\-\*]\s+")


def is_digest_candidate(text: str) -> bool:
    if not text:
        return False
    links = extract_links_from_text(text)
    if len(links) < 2:
        return False
    lines = text.splitlines()
    bullet_lines = sum(1 for line in lines if _BULLET_LINE.match(line.strip()))
    lines_with_url = sum(
        1 for line in lines if "http://" in line.lower() or "https://" in line.lower()
    )
    return bullet_lines >= 2 or lines_with_url >= 2


def _compile_patterns(raw_list: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(item, re.IGNORECASE) for item in raw_list]


def split_with_pattern(text: str, pattern: dict[str, Any]) -> list[str]:
    start_res = _compile_patterns(list(pattern.get("start_line") or []))
    skip_res = _compile_patterns(list(pattern.get("skip_line") or []))
    if not start_res:
        return []

    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        body = "\n".join(current).strip()
        if body:
            blocks.append(body)
        current = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        if any(rx.search(stripped) for rx in skip_res):
            continue
        if any(rx.search(stripped) for rx in start_res):
            flush()
            current.append(stripped)
            continue
        if current:
            current.append(stripped)

    flush()
    return blocks


def split_digest(
    text: str,
    patterns: list[dict[str, Any]],
    pattern_id: str | None = None,
) -> tuple[list[str] | None, str | None]:
    """Return (blocks, matched_pattern_id) or (None, None) on miss."""
    if not text or not patterns:
        return None, None

    ordered = patterns
    if pattern_id:
        preferred = [p for p in patterns if p.get("id") == pattern_id]
        rest = [p for p in patterns if p.get("id") != pattern_id]
        ordered = preferred + rest

    for pattern in ordered:
        min_blocks = int(pattern.get("min_blocks") or 2)
        blocks = split_with_pattern(text, pattern)
        if len(blocks) >= min_blocks:
            return blocks, str(pattern.get("id") or "")
    return None, None
