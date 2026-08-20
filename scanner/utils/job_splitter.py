"""Split multi-vacancy digest posts using JSON digest patterns."""

from __future__ import annotations

import re
from typing import Any

from utils.url_helpers import extract_links_from_text

# URLs that usually mean a concrete vacancy card (not portfolio/company page).
_JOB_BOARD_MARKERS = (
    "linkedin.com/jobs/",
    "offerclaw.app/vacancy/",
    "greenhouse.io/",
    "jobs.lever.co/",
    "lever.co/",
    "workable.com/",
    "hh.ru/vacancy",
    "getmatch.ru/vacancies/",
    "wantapply.com/",
    "app.rvc.global/vacancy/",
    "careers.",
)


def job_board_link_count(text: str) -> int:
    if not text:
        return 0
    count = 0
    for url in extract_links_from_text(text):
        low = url.lower()
        if any(marker in low for marker in _JOB_BOARD_MARKERS):
            count += 1
    return count


def is_multi_job_digest(text: str) -> bool:
    """True when the post looks like several vacancy cards, not one job with extra links."""
    return job_board_link_count(text) >= 2


def is_digest_candidate(text: str) -> bool:
    """Backward-compatible alias used by older call sites."""
    return is_multi_job_digest(text)


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
