"""Write and merge daily Markdown vacancy reports."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

_POST_RE = re.compile(r"^- Post: (\S+)", re.MULTILINE)
_HEADING_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — ", re.MULTILINE)


def format_salary(salary: Any) -> str:
    if salary is None:
        return ""
    amount = getattr(salary, "amount", None)
    currency = getattr(salary, "currency", None)
    if amount is None or not currency:
        return ""
    return f"{amount} {currency}"


def render_card(card: dict[str, Any]) -> str:
    username = str(card["source_username"]).lstrip("@")
    links = card.get("links") or ""
    text = (card.get("text") or "").rstrip()
    lines = [
        f"### {card['date']} — {card['source']} (@{username})",
        "",
        f"- Post: {card['post']}",
        f"- Salary: {format_salary(card.get('salary'))}",
        f"- Keywords: {card.get('keywords') or ''}",
        f"- Green: {card.get('green') or ''}",
        f"- Flags: {card.get('flags') or ''}",
        f"- Links: {links.replace(chr(10), ' ').strip()}",
        "",
        text,
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_sources(stats_list: list[dict[str, Any]]) -> str:
    lines = ["## Sources", ""]
    for row in stats_list:
        username = str(row["username"]).lstrip("@")
        status = row["status"]
        if status == "ok":
            lines.append(
                f"- ok @{username} — {row['passed']} passed / {row['total']} posts / {row['domain']} domain"
            )
        elif status == "not_found":
            lines.append(f"- not_found @{username}")
        elif status == "private":
            lines.append(f"- private @{username} — join the chat first")
        elif status == "no_messages_in_window":
            lines.append(f"- no_messages_in_window @{username}")
        elif status == "channel_silent":
            lines.append(f"- channel_silent @{username}")
        else:
            lines.append(f"- {status} @{username}")
    lines.append("")
    return "\n".join(lines)


def parse_existing_cards(text: str) -> dict[str, str]:
    """Map Post URL -> full ### card block including trailing newline."""
    if not text.strip():
        return {}
    chunks = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    cards: dict[str, str] = {}
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("### "):
            continue
        match = _POST_RE.search(chunk)
        if not match:
            continue
        post = match.group(1)
        cards[post] = chunk.rstrip() + "\n"
    return cards


def _card_sort_key(block: str) -> str:
    match = _HEADING_RE.search(block)
    if match:
        return match.group(1)
    return ""


def merge_report(
    path: Path,
    run_time: datetime,
    found_count: int,
    scanned_count: int,
    window_note: str,
    stats_list: list[dict[str, Any]],
    new_cards: list[dict[str, Any]],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if path.exists():
        existing = parse_existing_cards(path.read_text(encoding="utf-8"))

    for card in new_cards:
        existing[card["post"]] = render_card(card)

    ordered = sorted(existing.values(), key=_card_sort_key, reverse=True)
    date_label = run_time.strftime("%Y-%m-%d")
    header = (
        f"# Job scan {date_label}\n\n"
        f"Ran {run_time.strftime('%H:%M')}, {window_note}. "
        f"Found {found_count}, scanned {scanned_count} sources.\n\n"
    )
    body = header + render_sources(stats_list) + "\n## Vacancies\n\n"
    if ordered:
        body += "\n".join(block.rstrip() + "\n" for block in ordered)
    else:
        body += "_No vacancies in this file yet._\n"
    path.write_text(body, encoding="utf-8")
    return path
