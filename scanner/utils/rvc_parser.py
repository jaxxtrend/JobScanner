"""Load full vacancy text from public RVC API when a post contains a link."""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

RVC_VACANCY_PATTERN = re.compile(
    r"(https?://app\.rvc\.global/vacancy/view/([^\s\)\],/?#]+))",
    re.IGNORECASE,
)
RVC_API_BASE = "https://api.rvc.global"


def extract_rvc_links_from_message(text: str) -> list[str]:
    if not text:
        return []
    return [m[0].rstrip(".,)") for m in RVC_VACANCY_PATTERN.findall(text)]


def slug_from_rvc_url(url: str) -> str | None:
    match = RVC_VACANCY_PATTERN.search(url)
    return match.group(2) if match else None


def fetch_rvc_vacancy(slug: str) -> dict[str, Any] | None:
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        response = requests.get(
            f"{RVC_API_BASE}/vacancies/{slug}",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        log.error("Failed to load RVC vacancy %s: %s", slug, exc)
        return None


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return unescape(soup.get_text(separator="\n", strip=True))


def vacancy_to_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    position = data.get("position") or data.get("keyCompetency")
    if position:
        parts.append(str(position))
    company = data.get("companyName")
    if company:
        parts.append(str(company))
    description = _html_to_text(data.get("description", ""))
    if description:
        parts.append(description)
    for section in data.get("sections") or []:
        title = section.get("title", "").strip()
        content = section.get("content", "").strip()
        if content:
            label = f"{title}:" if title else ""
            parts.append(f"{label}\n{content}".strip())
    skills = data.get("skills") or []
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    return "\n\n".join(part for part in parts if part)


def enrich_message_with_rvc(content: str) -> tuple[str, dict[str, Any] | None]:
    rvc_links = extract_rvc_links_from_message(content)
    if not rvc_links:
        return content, None
    slug = slug_from_rvc_url(rvc_links[0])
    if not slug:
        return content, None
    data = fetch_rvc_vacancy(slug)
    if not data:
        return content, None
    full_text = vacancy_to_text(data)
    if not full_text:
        return content, None
    enriched = f"{content}\n\n--- RVC ---\n{full_text}"
    log.info(
        "Loaded RVC description: %s — %s",
        data.get("position") or data.get("keyCompetency") or "N/A",
        data.get("companyName") or "N/A",
    )
    return enriched, data
