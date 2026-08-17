"""Scan Telegram channels for Technical Artist vacancies and write a daily Markdown report."""

from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCANNER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCANNER_DIR))

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from config.load import (
    LOGS_DIR,
    SESSIONS_DIR,
    STATE_DIR,
    load_channels,
    load_env,
    load_settings,
)
from utils.cursors import last_id_for, load_cursors, save_cursors
from utils.dedup_cache import load_seen_links, save_seen_links
from utils.extract_salary import Salary, extract_salary
from utils.markdown_writer import merge_report
from utils.rvc_parser import enrich_message_with_rvc
from utils.telegraph_parser import (
    extract_telegraph_links_from_message,
    fetch_telegraph_page,
    parse_telegraph_jobs,
)
from utils.url_helpers import extract_links_from_text, message_url, normalize_url_for_dedup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

LOGS_DIR.mkdir(parents=True, exist_ok=True)
_run_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_file_handler = logging.FileHandler(LOGS_DIR / f"scan_{_run_ts}.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(_file_handler)


def get_unique_keywords(source_list: list[str], search_text: str) -> list[str]:
    found = [kw.lower() for kw in source_list if kw.lower() in search_text]
    unique: dict[str, str] = {}
    for item in found:
        normalized = item.replace(" ", "").replace("-", "").replace("_", "")
        if normalized not in unique:
            unique[normalized] = item
    return sorted(unique.values())


def normalize_text_for_sim(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", text.lower())
    cleaned = re.sub(r"[^0-9a-zа-яё]+", " ", cleaned)
    return " ".join(cleaned.split())


def is_near_duplicate(norm_text: str, accepted_norm_texts: list[str], threshold: float) -> bool:
    for prev in accepted_norm_texts:
        ratio = max(
            difflib.SequenceMatcher(None, norm_text, prev, autojunk=False).ratio(),
            difflib.SequenceMatcher(None, prev, norm_text, autojunk=False).ratio(),
        )
        if ratio >= threshold:
            return True
    return False


def parse_channel_ids(channel_id: str) -> list[str]:
    if not channel_id:
        return []
    ids: list[str] = []
    for part in [p.strip() for p in channel_id.split(",")]:
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                ids.extend(str(i) for i in range(int(start), int(end) + 1))
            except ValueError:
                log.error("Invalid channel range: %s", part)
        else:
            ids.append(part)
    return ids


def telegram_identity(link: str) -> str | int:
    if link.lstrip("-").isdigit():
        return int(link)
    return link.replace("https://t.me/", "").strip().lstrip("@")


def cursor_key(username: str | int) -> str:
    return str(username)


def has_required_tags(text: str, tags: list[str]) -> bool:
    if not tags:
        return True
    text_lc = text.lower()
    return any(tag.lower() in text_lc for tag in tags)


def message_in_window(
    msg_id: int,
    msg_date: datetime,
    last_id: int | None,
    date_from: datetime,
    rescan_since: datetime,
) -> bool:
    if last_id is None:
        return msg_date >= date_from
    return msg_id > last_id or msg_date >= rescan_since


def should_stop_iterating(
    msg_id: int,
    msg_date: datetime,
    last_id: int | None,
    date_from: datetime,
    rescan_since: datetime,
) -> bool:
    if last_id is None:
        return msg_date < date_from
    return msg_id <= last_id and msg_date < rescan_since


def build_card(
    *,
    date_value: datetime,
    source_name: str,
    source_username: str | int,
    post: str,
    text: str,
    keywords: list[str],
    green: list[str],
    flags: list[str],
    links: list[str],
    salary: Salary | None,
) -> dict[str, Any]:
    links_str = "\n".join(links[:5]) if links else ""
    return {
        "date": date_value.strftime("%Y-%m-%d %H:%M"),
        "source": source_name,
        "source_username": source_username,
        "post": post,
        "text": text.strip() + "\n",
        "keywords": "; ".join(keywords),
        "green": "; ".join(green),
        "flags": "; ".join(flags),
        "links": links_str,
        "salary": salary,
    }


def try_accept_text(
    *,
    keyword_text: str,
    full_text: str,
    source_key: str,
    settings: dict[str, Any],
    seen_links: set[str],
    seen_text_hashes: set[str],
    accepted_texts: dict[str, list[str]],
    links: list[str],
) -> bool:
    full_lc = full_text.lower()
    reject_phrases = settings["stopwords"] + settings["resume_stopwords"]
    if any(kw.lower() in full_lc for kw in reject_phrases):
        return False
    matched = get_unique_keywords(
        settings["keywords"], keyword_text.lower()[: settings["letters_limit"]]
    )
    if not matched:
        return False
    if links:
        primary = normalize_url_for_dedup(links[0])
        if primary in seen_links:
            return False
        seen_links.add(primary)
    else:
        text_hash = hashlib.md5(full_text[:200].lower().encode()).hexdigest()
        if text_hash in seen_text_hashes:
            return False
        seen_text_hashes.add(text_hash)
    norm = normalize_text_for_sim(full_text)
    if is_near_duplicate(norm, accepted_texts.get(source_key, []), settings["near_dup_threshold"]):
        return False
    accepted_texts.setdefault(source_key, []).append(norm)
    return True


async def iter_channel_messages(
    client: TelegramClient,
    src: dict[str, Any],
    settings: dict[str, Any],
    date_from: datetime,
    rescan_since: datetime,
    last_id: int | None,
    seen_links: set[str],
    seen_text_hashes: set[str],
    accepted_texts: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any], int | None]:
    results: list[dict[str, Any]] = []
    total = 0
    passed = 0
    domain = 0
    max_id = last_id
    cut_by_date = False
    chat_type = src["type"]
    limit = 20000 if chat_type == "channel" else 10000
    chat = await client.get_entity(src["username"])
    log.info("Scanning %s %s (%s) id %s", chat_type, src["name"], src["username"], chat.id)

    async for msg in client.iter_messages(chat, limit=limit):
        if should_stop_iterating(msg.id, msg.date, last_id, date_from, rescan_since):
            cut_by_date = last_id is None or msg.date < date_from
            break
        if not message_in_window(msg.id, msg.date, last_id, date_from, rescan_since):
            continue
        if max_id is None or msg.id > max_id:
            max_id = msg.id

        content = msg.text or (msg.media.caption if hasattr(msg.media, "caption") else "")
        if not content:
            continue

        total += 1
        text_lc = content.lower()
        if any(marker.lower() in text_lc for marker in settings["domain_markers"]):
            domain += 1

        if not has_required_tags(content, src.get("require_tags") or []):
            continue

        msg_url = message_url(str(src["username"]), chat.id, msg.id)
        source_name = src["name"] + (" (bot)" if chat_type == "bot" else "")
        source_key = cursor_key(src["username"])

        telegraph_links = extract_telegraph_links_from_message(content)
        if telegraph_links:
            for telegraph_url in telegraph_links[:5]:
                html = fetch_telegraph_page(telegraph_url)
                if not html:
                    continue
                for job in parse_telegraph_jobs(html, telegraph_url):
                    job_text = "\n".join(
                        part for part in [
                            job.get("title", ""),
                            job.get("company", ""),
                            job.get("location", ""),
                            job.get("description", ""),
                        ] if part
                    )
                    job_links = extract_links_from_text(job_text)
                    if not job_links and (job.get("link") or telegraph_url):
                        job_links = [job.get("link") or telegraph_url]
                    job_matched = get_unique_keywords(
                        settings["keywords"], job_text.lower()[: settings["letters_limit"]]
                    )
                    if not try_accept_text(
                        keyword_text=job_text,
                        full_text=job_text,
                        source_key=source_key,
                        settings=settings,
                        seen_links=seen_links,
                        seen_text_hashes=seen_text_hashes,
                        accepted_texts=accepted_texts,
                        links=job_links,
                    ):
                        continue
                    passed += 1
                    card_url = job_links[0] if job_links else f"{msg_url}#telegraph"
                    results.append(build_card(
                        date_value=msg.date,
                        source_name=source_name,
                        source_username=src["username"],
                        post=card_url,
                        text=job_text,
                        keywords=job_matched,
                        green=get_unique_keywords(settings["green"], job_text.lower()),
                        flags=get_unique_keywords(settings["redwords"], job_text.lower()),
                        links=job_links,
                        salary=extract_salary(job_text),
                    ))
            continue

        enriched, _rvc = enrich_message_with_rvc(content)
        links = extract_links_from_text(content)
        if not try_accept_text(
            keyword_text=content,
            full_text=enriched,
            source_key=source_key,
            settings=settings,
            seen_links=seen_links,
            seen_text_hashes=seen_text_hashes,
            accepted_texts=accepted_texts,
            links=links,
        ):
            continue

        matched = get_unique_keywords(settings["keywords"], text_lc[: settings["letters_limit"]])
        if len(links) > 3:
            links = links[:3]
        passed += 1
        results.append(build_card(
            date_value=msg.date,
            source_name=source_name,
            source_username=src["username"],
            post=msg_url,
            text=enriched,
            keywords=matched,
            green=get_unique_keywords(settings["green"], enriched.lower()),
            flags=get_unique_keywords(settings["redwords"], enriched.lower()),
            links=links,
            salary=extract_salary(enriched),
        ))

    status = "ok"
    if total == 0:
        status = "no_messages_in_window" if cut_by_date or last_id is not None else "channel_silent"
    stats = {
        "username": src["username"],
        "name": src["name"],
        "total": total,
        "passed": passed,
        "domain": domain,
        "status": status,
    }
    return results, stats, max_id


async def scan_channel_with_retry(
    client: TelegramClient,
    src: dict[str, Any],
    settings: dict[str, Any],
    date_from: datetime,
    rescan_since: datetime,
    last_id: int | None,
    seen_links: set[str],
    seen_text_hashes: set[str],
    accepted_texts: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any], int | None]:
    links_snap = set(seen_links)
    hashes_snap = set(seen_text_hashes)
    accepted_snap = {key: list(vals) for key, vals in accepted_texts.items()}

    def restore_dedup() -> None:
        seen_links.clear()
        seen_links.update(links_snap)
        seen_text_hashes.clear()
        seen_text_hashes.update(hashes_snap)
        accepted_texts.clear()
        accepted_texts.update({key: list(vals) for key, vals in accepted_snap.items()})

    try:
        return await iter_channel_messages(
            client, src, settings, date_from, rescan_since, last_id,
            seen_links, seen_text_hashes, accepted_texts,
        )
    except FloodWaitError as exc:
        log.warning("FloodWait %ss for %s — sleeping", exc.seconds, src["name"])
        restore_dedup()
        await asyncio.sleep(exc.seconds + 1)
        try:
            return await iter_channel_messages(
                client, src, settings, date_from, rescan_since, last_id,
                seen_links, seen_text_hashes, accepted_texts,
            )
        except Exception as retry_exc:
            restore_dedup()
            return [], {
                "username": src["username"],
                "name": src["name"],
                "total": 0,
                "passed": 0,
                "domain": 0,
                "status": f"flood_retry_error: {str(retry_exc)[:50]}",
            }, last_id
    except Exception as exc:
        restore_dedup()
        err_msg = str(exc)
        log.error("Failed reading %s (%s): %s", src["name"], src["username"], err_msg)
        if "No user has" in err_msg or "Cannot find any entity" in err_msg:
            status = "not_found"
        elif "private" in err_msg.lower():
            status = "private"
        elif "FloodWait" in err_msg or "flood" in err_msg.lower():
            status = "flood_wait"
        else:
            status = f"error: {err_msg[:60]}"
        return [], {
            "username": src["username"],
            "name": src["name"],
            "total": 0,
            "passed": 0,
            "domain": 0,
            "status": status,
        }, last_id


async def scan_messages(
    client: TelegramClient,
    settings: dict[str, Any],
    days: int,
    channel_id: str | None,
    output_path: Path,
) -> None:
    start_all = time.perf_counter()
    date_from = datetime.now(timezone.utc) - timedelta(days=days)
    rescan_since = datetime.now(timezone.utc) - timedelta(hours=settings["rescan_hours"])
    channels_cfg = load_channels()

    if channel_id:
        wanted = set(parse_channel_ids(channel_id))
        channels_cfg = [ch for ch in channels_cfg if str(ch["id"]) in wanted]
        if not channels_cfg:
            log.error("No channels matched --channel %s", channel_id)
            return

    selected: list[dict[str, Any]] = []
    for group_info in channels_cfg[: settings["groups_limit"]]:
        if not group_info.get("enabled", True):
            log.info("Skipping %s: enabled=false", group_info.get("name", "?"))
            continue
        score = group_info.get("relevance_score")
        if score is not None and score < settings["min_relevance"]:
            log.info(
                "Skipping %s: relevance_score=%s < min_relevance=%s",
                group_info.get("name", "?"), score, settings["min_relevance"],
            )
            continue
        username = telegram_identity(group_info["link"])
        chat_type = "bot" if str(username).lower().endswith(("bot", "robot")) else "channel"
        selected.append({
            "id": group_info["id"],
            "username": username,
            "name": group_info["name"],
            "link": group_info["link"],
            "type": chat_type,
            "require_tags": group_info.get("require_tags") or [],
            "category": group_info.get("category", ""),
        })

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cursors_path = STATE_DIR / "cursors.json"
    cache_path = SESSIONS_DIR / "dedup_cache.json"
    cursors = load_cursors(cursors_path)
    seen_links = load_seen_links(cache_path)
    seen_text_hashes: set[str] = set()
    accepted_texts: dict[str, list[str]] = {}
    results: list[dict[str, Any]] = []
    stats_list: list[dict[str, Any]] = []
    first_run_channels = 0

    for src in selected:
        key = cursor_key(src["username"])
        last_id = last_id_for(cursors, key)
        if last_id is None:
            first_run_channels += 1
        channel_results, stats, max_id = await scan_channel_with_retry(
            client, src, settings, date_from, rescan_since, last_id,
            seen_links, seen_text_hashes, accepted_texts,
        )
        results.extend(channel_results)
        stats_list.append(stats)
        if max_id is not None:
            cursors[key] = {"last_id": max_id}

    stats_list.sort(key=lambda row: (0 if row["status"] == "ok" else 1, -row["passed"]))
    duration = time.perf_counter() - start_all
    log.info("Found %s vacancies in %.2fs", len(results), duration)

    if first_run_channels == len(selected) and selected:
        window_note = f"window first-run {days} days"
    elif first_run_channels:
        window_note = f"window mixed first-run {days} days / new + {settings['rescan_hours']}h"
    else:
        window_note = f"window new + {settings['rescan_hours']}h"

    run_time = datetime.now()
    report_path = output_path / f"{run_time.strftime('%Y-%m-%d')}.md"
    results.sort(key=lambda row: row.get("date", ""), reverse=True)
    save_seen_links(seen_links, cache_path)
    save_cursors(cursors_path, cursors)
    merge_report(
        report_path,
        run_time,
        len(results),
        len(selected),
        window_note,
        stats_list,
        results,
    )
    log.info("Markdown saved: %s", report_path)


async def async_main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Technical Artist vacancy scanner for Telegram")
    parser.add_argument("--channel", type=str, help="Channel id or range from channels.json (e.g. 1-5 or 2,4)")
    parser.add_argument(
        "--days",
        type=int,
        default=settings["last_days"],
        help=f"History window for channels without a cursor (default {settings['last_days']})",
    )
    args = parser.parse_args()

    api_id, api_hash, output_path = load_env()
    output_path.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS_DIR / "my_account"
    client = TelegramClient(str(session_file), api_id, api_hash)
    async with client:
        await scan_messages(client, settings, days=args.days, channel_id=args.channel, output_path=output_path)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
