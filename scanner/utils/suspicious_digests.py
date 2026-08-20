"""Append suspicious digest posts for human/agent pattern updates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def suspicious_log_path(logs_dir: Path, run_time: datetime) -> Path:
    return logs_dir / f"suspicious_digests_{run_time.strftime('%Y-%m-%d')}.md"


def append_suspicious_digest(
    logs_dir: Path,
    run_time: datetime,
    *,
    username: str,
    post_url: str,
    reason: str,
    text: str,
) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = suspicious_log_path(logs_dir, run_time)
    handle = str(username).lstrip("@")
    block = (
        f"## @{handle}\n\n"
        f"- Post: {post_url}\n"
        f"- Reason: {reason}\n"
        f"- Logged: {run_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"```\n{text.rstrip()}\n```\n\n"
    )
    if not path.exists():
        header = (
            f"# Suspicious digests {run_time.strftime('%Y-%m-%d')}\n\n"
            "Pass this file to an AI agent to analyze posts and update "
            "`config/digest_patterns.json` (add/fix patterns and channel bindings).\n\n"
        )
        path.write_text(header + block, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(block)
    return path


def pattern_alert_row(
    *,
    username: str,
    post_url: str,
    reason: str,
    log_path: Path,
) -> dict[str, Any]:
    return {
        "username": str(username).lstrip("@"),
        "post_url": post_url,
        "reason": reason,
        "log_path": str(log_path),
    }
