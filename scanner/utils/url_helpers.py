"""Normalize URLs for dedup and extract links from Telegram posts."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_url_for_dedup(url: str) -> str:
    if not url:
        return url

    url = url.strip().lower()

    if "getmatch.ru" in url:
        match = re.search(r"/vacancies/(\d+)", url)
        if match:
            return f"getmatch.ru/vacancies/{match.group(1)}"
        match = re.search(r"utm_term=vacancy__vacancy__(\d+)", url)
        if match:
            return f"getmatch.ru/vacancies/{match.group(1)}"

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    tracking_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "s",
        "source",
        "medium",
        "campaign",
        "content",
        "term",
        "ref",
        "referral",
        "referrer",
        "track",
        "tracking",
        "fbclid",
        "gclid",
        "yclid",
        "ttclid",
        "si",
        "trk",
        "trk_contact",
        "trk_email",
        "original_referer",
    }
    cleaned_params = {k: v for k, v in query_params.items() if k.lower() not in tracking_params}
    cleaned_query = urlencode(cleaned_params, doseq=True)
    netloc = parsed.netloc.replace("www.", "")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, netloc, path, parsed.params, cleaned_query, ""))


def message_url(username: str, chat_id: int, msg_id: int) -> str:
    if username and not str(username).lstrip("-").isdigit():
        return f"https://t.me/{username}/{msg_id}"
    return f"https://t.me/c/{abs(chat_id)}/{msg_id}"


def extract_links_from_text(text: str) -> list[str]:
    if not text:
        return []
    url_pattern = re.compile(r"(https?://[^\s)]+)", re.IGNORECASE)
    matches = url_pattern.findall(text)
    return [m.rstrip(".,)") for m in matches]
