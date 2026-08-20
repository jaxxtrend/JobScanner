# JobScanner

Telegram scanner for **Technical Artist / pipeline / real-time optimization** vacancies.

It reads channels you already follow, filters posts with JSON keyword lists, and writes a daily Markdown report. Tunable data lives in JSON — not in Python.

## How it works

```text
channels.json  →  Telegram API  →  per message:
  1. Telegraph page?     → split into jobs, filter each
  2. RVC vacancy URLs?   → one candidate per link (API text)
  3. Digest pattern hit? → one candidate per block
  4. Else                → whole post as one candidate
  → keywords / stopwords / resume_stopwords / near-dup / URL dedup
  → output/YYYY-MM-DD.md
```

**Pass** means the candidate matched at least one `keywords` entry and did not hit `stopwords` / `resume_stopwords`, and is not a near-duplicate of an already accepted card.

Report line per source:

`ok @channel — N passed / M posts / D domain`

| Field | Meaning |
| --- | --- |
| `posts` | Messages in the scan window with text |
| `domain` | Posts that contain a `domain_markers` phrase (gamedev / Unity / …) — topic signal, not web domains |
| `passed` | Vacancies that became cards |

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env`:

- `TG_API_ID` and `TG_API_HASH` from [my.telegram.org](https://my.telegram.org/auth)
- `OUTPUT_PATH` — optional; defaults to `output/` in the repo

The Telegram account used for login must already be subscribed to every channel in `scanner/config/channels.json`.

Session file after first login: `scanner/sessions/` (not committed).

## Config (edit JSON, not Python)

| File | Role |
| --- | --- |
| [`scanner/config/settings.json`](scanner/config/settings.json) | Window, keywords, green/red, stopwords, resume_stopwords, domain markers, thresholds |
| [`scanner/config/channels.json`](scanner/config/channels.json) | Sources to scan |
| [`scanner/config/digest_patterns.json`](scanner/config/digest_patterns.json) | How to split multi-vacancy digests |

### Channels

List of `@usernames`, or objects when a digest pattern is pinned:

```json
[
  "@cgfreelance",
  "@devjobs",
  { "username": "@offerclaw", "digest_pattern": "bullet_role_url" },
  { "username": "@forgamedev", "digest_pattern": "linkedin_job_bullets" }
]
```

- Delete a line to skip a source. Titles are taken from Telegram at scan time.
- Optional object fields: `enabled`, `require_tags`, `digest_pattern`.

### Filters (`settings.json`)

| List | Role |
| --- | --- |
| `keywords` | Job titles that must appear (required to pass) |
| `green` | Stack / contract highlights only (shown on the card, does not gate pass) |
| `redwords` | Flags on the card (does not reject) |
| `stopwords` | Reject the candidate |
| `resume_stopwords` | Reject resume / “looking for work” posts |
| `domain_markers` | Count toward the `domain` stat only |

Also: `last_days`, `rescan_hours`, `letters_limit` (keyword search window in text), `near_dup_threshold`, `groups_limit`.

### Digest patterns

Some channels post **several vacancies in one message**. Patterns in `digest_patterns.json` split those into blocks; each block is filtered alone.

Built-in pattern ids:

- `bullet_role_url` — OfferClaw-style `• Role — Company (url)`
- `linkedin_job_bullets` — Forgamedev-style `🔹Role` / markdown LinkedIn job links

Flow:

1. Try patterns (channel `digest_pattern` first, then the rest).
2. If a pattern yields **2+ blocks** → filter each block.
3. Else if the post has **2+ job-board vacancy URLs** (LinkedIn jobs, OfferClaw vacancy, Greenhouse, Lever, HH, …) and nothing split it → **do not** accept the whole post; write an alert instead.
4. Else → treat as a normal single post (even if it has portfolio / YouTube / forms links).

**Pattern miss workflow**

1. Console WARNING
2. Append full post to `scanner/logs/suspicious_digests_YYYY-MM-DD.md`
3. Section **Pattern alerts** in the daily Markdown report

Pass that suspicious log to an agent and ask to update `digest_patterns.json` (and optionally set `digest_pattern` on the channel). There is no AI inside the scanner runtime.

**Telegraph** (`telegra.ph`) and **RVC** (`app.rvc.global/vacancy/...`) have their own splitters: Telegraph jobs and one card per RVC link.

## Run

From the repo root:

```bash
python scanner/main.py
python scanner/main.py --days 10
python scanner/main.py --channel 1
python scanner/main.py --channel cgfreelance
python scanner/main.py --channel offerclaw
```

`--channel` accepts a username, a 1-based index from `channels.json`, or a range like `1-3`.

## Scan window

| Case | Window |
| --- | --- |
| Channel without a cursor | last `last_days` days |
| Channel with a cursor | new message ids **plus** the last `rescan_hours` (48) so recent edits are seen |

Cursors: `scanner/state/cursors.json` (gitignored).

## Output

- Daily report: `output/YYYY-MM-DD.md`
- Same-day re-run **merges** cards by post URL (earlier cards are kept; edited posts update the existing card)
- Dedup across days: `scanner/sessions/dedup_cache.json` — first vacancy URL in the text, or the Telegram post URL when there is no external link
- Scan logs: `scanner/logs/scan_*.log`
- Suspicious digests: `scanner/logs/suspicious_digests_YYYY-MM-DD.md`

### Report sections

1. **Sources** — per-channel status and counters  
2. **Pattern alerts** — only when multi-job digests failed to split (if any)  
3. **Vacancies** — cards with post link, salary, keywords, green, flags, links, text  

## Local-only paths

`jobs_release/` is a local example from another search profile. It is gitignored and is not part of this repository.
