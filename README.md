# JobScanner

Telegram scanner for **Technical Artist / pipeline / real-time optimization** vacancies.

It reads channels you already follow, filters posts with JSON keyword lists, and writes a daily Markdown report. Tunable data lives in repo-root `config/` — not buried in Python.

## How it works

```text
config/channels.json  →  Telegram API  →  per message:
  1. Telegraph page?     → split into jobs, filter each
  2. RVC vacancy URLs?   → one candidate per link (API text)
  3. Channel has digest binding? → apply that one pattern, filter each block
  4. Else                → whole post as one candidate
  → keywords / stopwords / resume_stopwords / near-dup / URL dedup
  → output/YYYY-MM-DD.md
```

**Pass** means the candidate matched at least one `keywords` entry, did not hit `stopwords` / `resume_stopwords`, and is not a near-duplicate of an already accepted card.

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

Optional local venv (used automatically by `run.ps1`):

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

Fill `.env`:

- `TG_API_ID` and `TG_API_HASH` from [my.telegram.org](https://my.telegram.org/auth)
- `OUTPUT_PATH` — optional; defaults to `output/` in the repo

The Telegram account used for login must already be subscribed to every channel in [`config/channels.json`](config/channels.json).

Session file after first login: `cache/sessions/` (not committed). The `cache/` tree is created automatically on first run.

## Config (edit JSON under `config/`)

| File | Who edits | Role |
| --- | --- | --- |
| [`config/settings.json`](config/settings.json) | you | Window, keywords, green/red, stopwords, resume_stopwords, domain markers |
| [`config/channels.json`](config/channels.json) | you | Sources as clickable `https://t.me/...` links |
| [`config/digest_patterns.json`](config/digest_patterns.json) | AI agent (via suspicious log) | Digest split patterns + per-channel bindings |

### Channels

Plain list of Telegram links (easy to open in the browser):

```json
[
  "https://t.me/cgfreelance",
  "https://t.me/devjobs",
  "https://t.me/offerclaw"
]
```

Objects are still allowed for rare flags (`enabled`, `require_tags`) — not for digest patterns.

### Filters (`settings.json`)

| List | Role |
| --- | --- |
| `keywords` | Job titles that must appear (required to pass) |
| `green` | Stack / contract highlights only (shown on the card, does not gate pass) |
| `redwords` | Flags on the card (does not reject) |
| `stopwords` | Reject the candidate |
| `resume_stopwords` | Reject resume / “looking for work” posts |
| `domain_markers` | Count toward the `domain` stat only |

Also: `last_days`, `rescan_hours`, `letters_limit`, `near_dup_threshold`, `groups_limit`.

### Digest patterns (internal)

Some channels post **several vacancies in one message**. Definitions and bindings live only in `digest_patterns.json`:

```json
{
  "bindings": {
    "offerclaw": "bullet_role_url",
    "forgamedev": "linkedin_job_bullets"
  },
  "patterns": [ ... ]
}
```

- A channel uses **only** the pattern named in `bindings` (no try-all over every pattern).
- Channels without a binding are never digest-split (Telegraph / RVC still apply).
- You normally do **not** edit this file by hand.

**When a multi-job digest fails to split** (post has 2+ job-board vacancy URLs: LinkedIn jobs, OfferClaw vacancy, Greenhouse, …):

1. Console WARNING  
2. Full post appended to `cache/logs/suspicious_digests_YYYY-MM-DD.md`  
3. **Pattern alerts** section in the daily Markdown report  

Hand that suspicious log to an **AI agent** (e.g. Cursor). The agent should analyze the failed posts, add/fix a pattern, and update `bindings` in `config/digest_patterns.json`. The scanner itself does not call AI at runtime.

Ordinary single vacancies with portfolio / YouTube / forms links are **not** treated as digests.

**Telegraph** (`telegra.ph`) and **RVC** (`app.rvc.global/vacancy/...`) have their own splitters.

## Run

From the repo root (preferred on Windows):

```powershell
.\run.ps1
.\run.ps1 -Channel offerclaw
.\run.ps1 --days 10
.\run.ps1 --channel 1
```

`run.ps1` uses `.venv\Scripts\python.exe` when present, otherwise `python` from PATH, and forwards all args to `scanner/main.py`.

Equivalent:

```bash
python scanner/main.py
python scanner/main.py --channel cgfreelance
```

`--channel` accepts a username, a 1-based index from `channels.json`, or a range like `1-3`.

## Scan window

| Case | Window |
| --- | --- |
| Channel without a cursor | last `last_days` days |
| Channel with a cursor | new message ids **plus** the last `rescan_hours` (48) so recent edits are seen |

Cursors: `cache/state/cursors.json` (gitignored).

## Output

- Daily report: `output/YYYY-MM-DD.md`
- Same-day re-run **merges** cards by post URL
- Dedup across days: `cache/sessions/dedup_cache.json`
- Scan logs: `cache/logs/scan_*.log`
- Suspicious digests (for AI pattern updates): `cache/logs/suspicious_digests_YYYY-MM-DD.md`

### Report sections

1. **Sources** — per-channel status and counters  
2. **Pattern alerts** — multi-job digests that failed to split (if any)  
3. **Vacancies** — cards with post link, salary, keywords, green, flags, links, text  

## Layout

```text
config/                 # user + agent JSON (settings, channels, digest patterns)
cache/                  # created on first run (sessions, state, logs)
run.ps1                 # Windows launcher
scanner/                # Python code (load.py under scanner/config/)
output/                 # daily Markdown reports
```

`cache/` layout:

```text
cache/sessions/         # Telegram session + dedup cache
cache/state/            # cursors
cache/logs/             # scan + suspicious digest logs
```

## Local-only paths

`jobs_release/` is a local example from another search profile. It is gitignored and is not part of this repository.
