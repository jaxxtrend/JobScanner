"""Fetch Telegraph pages and split them into vacancy-like blocks."""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


def fetch_telegraph_page(url: str) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        log.error("Failed to fetch Telegraph page %s: %s", url, exc)
        return None


def extract_links_from_line(line: str) -> list[str]:
    url_pattern = re.compile(r"(https?://[^\s]+)", re.IGNORECASE)
    matches = url_pattern.findall(line)
    return [m.rstrip(".,)") for m in matches]


def _parse_jobs_from_lines(text_content: str) -> list[dict[str, str]]:
    job_keywords = [
        "manager", "developer", "analyst", "engineer", "specialist",
        "consultant", "coordinator", "director", "lead", "senior",
        "technical artist", "tech artist",
        "менеджер", "разработчик", "аналитик", "инженер", "специалист",
        "художник", "лид",
    ]
    jobs: list[dict[str, str]] = []
    current_job: dict[str, str] | None = None
    for line in text_content.split("\n"):
        line = line.strip()
        if not line:
            continue
        is_job_title = any(kw in line.lower() for kw in job_keywords)
        links_in_line = extract_links_from_line(line)
        if is_job_title or (links_in_line and len(line) < 200):
            if current_job and current_job.get("title"):
                jobs.append(current_job)
            current_job = {
                "title": line,
                "company": "",
                "location": "",
                "description": "",
                "link": links_in_line[0] if links_in_line else "",
            }
        elif current_job and current_job.get("title"):
            if not current_job["company"] and (
                " at " in line.lower() or " @ " in line.lower() or " в " in line.lower()
            ):
                current_job["company"] = line
            elif not current_job["location"] and any(
                loc in line.lower() for loc in ["remote", "удаленно", "location", "локация"]
            ):
                current_job["location"] = line
            elif links_in_line and not current_job["link"]:
                current_job["link"] = links_in_line[0]
            elif len(line) > 20:
                current_job["description"] += line + "\n"
    if current_job and current_job.get("title"):
        jobs.append(current_job)
    return jobs


def _parse_jobs_from_platform_links(article, source_url: str) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    job_platforms = [
        "linkedin.com", "indeed.com", "glassdoor.com", "greenhouse.io",
        "lever.co", "workable.com", "apply",
    ]
    for link in article.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True)
        if not any(platform in href.lower() for platform in job_platforms):
            continue
        prev_elements: list[str] = []
        current = link.find_previous()
        while current and len(prev_elements) < 3:
            if current.name in ["h1", "h2", "h3", "h4", "strong", "b"]:
                prev_elements.insert(0, current.get_text(strip=True))
                break
            prev_elements.insert(0, current.get_text(strip=True))
            current = current.find_previous()
        title = " ".join(prev_elements) if prev_elements else text
        jobs.append({
            "title": title,
            "company": "",
            "location": "",
            "description": "",
            "link": href,
        })
    if not jobs:
        log.info("No platform job links on Telegraph page %s", source_url)
    return jobs


def parse_telegraph_jobs(html: str, source_url: str) -> list[dict[str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article") or soup.find("div", class_="tl_article_content")
    if not article:
        log.warning("No article content on Telegraph page %s", source_url)
        return []
    text_content = article.get_text(separator="\n", strip=True)
    jobs = _parse_jobs_from_lines(text_content)
    if not jobs:
        jobs = _parse_jobs_from_platform_links(article, source_url)
    log.info("Found %s Telegraph jobs on %s", len(jobs), source_url)
    return jobs


def extract_telegraph_links_from_message(text: str) -> list[str]:
    if not text:
        return []
    telegraph_pattern = re.compile(r"(https?://telegra\.ph/[^\s]+)", re.IGNORECASE)
    matches = telegraph_pattern.findall(text)
    return [m.rstrip(".,)") for m in matches]
