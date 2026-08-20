# JobScanner

Telegram scanner for **Technical Artist / pipeline / real-time optimization** vacancies.

Reads channels listed in [`config/channels.json`](config/channels.json), filters posts with JSON keyword lists, writes a daily Markdown report. Tunable data lives in repo-root [`config/`](config/) — not in Python. Runtime data lives in [`cache/`](cache/) (created on first run, gitignored).

## Quick start

```powershell
pip install -r requirements.txt
copy .env.example .env
# fill TG_API_ID and TG_API_HASH from https://my.telegram.org/auth

.\run.ps1
.\run.ps1 --channel offerclaw
.\run.ps1 --days 10
```

`run.ps1` prefers `.venv\Scripts\python.exe` when present, otherwise `python` from PATH.

Optional venv:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### First login (once)

`TG_API_ID` / `TG_API_HASH` only identify the **app** to Telegram. The scanner still needs to log in as **your user account** (Telethon user session, not a bot).

On the first `.\run.ps1`:

1. Telethon may prompt `Please enter your phone (or bot token):` — that “(or bot token)” text is generic Telethon wording. Enter your Telegram number in international format (e.g. `+79991234567`). Do **not** paste a bot token; this project does not use bots.
2. Enter the login code Telegram sends you (SMS or in-app).
3. If 2FA is enabled, enter your cloud password.

A session file is written to `cache/sessions/my_account.session`. Later runs reuse it and skip the phone prompt.

After login Telethon may print a ToS reminder — normal. Sources come from [`config/channels.json`](config/channels.json), not from your join list. Public channels are usually readable by username; private ones need membership (report status `private … — join the chat first`).

### API usage

The scanner is **on-demand** (one pass per `.\run.ps1`, not a daemon). History is bounded by `last_days` / cursors (`rescan_hours` for edits); Telethon’s per-channel fetch cap (20k) is only a safety ceiling. If Telegram returns `FloodWait`, the scanner sleeps for the requested time and retries that channel once. Avoid running it in a tight loop.

## How it works

```text
config/channels.json  →  Telegram API  →  per message:
  1. Telegraph page?              → split into jobs, filter each
  2. RVC vacancy URLs?            → one candidate per link (API text)
  3. Channel has digest binding?  → apply that one pattern, filter each block
  4. Else                         → whole post as one candidate
  → keywords / stopwords / resume_stopwords / near-dup / URL dedup
  → output/YYYY-MM-DD.md
```

**Pass** = matched at least one `keywords` entry, no `stopwords` / `resume_stopwords`, not a near-duplicate of an already accepted card.

Source line in the report:

`ok @channel — N passed / M posts / D domain`

| Field | Meaning |
| --- | --- |
| `posts` | Messages in the scan window with text |
| `domain` | Posts containing a `domain_markers` phrase (topic signal, not web domains) |
| `passed` | Vacancies that became cards |

## Layout

```text
config/                 # settings, channels, digest patterns
cache/                  # auto-created on first run (gitignored)
  sessions/             # Telegram session + dedup_cache.json
  state/                # cursors.json
  logs/                 # scan_*.log + suspicious_digests_*.md
run.ps1                 # Windows launcher
scanner/                # Python code
output/                 # daily Markdown reports
.env / .env.example
requirements.txt
```

## Config (`config/`)

| File | Who edits | Role |
| --- | --- | --- |
| [`settings.json`](config/settings.json) | you | Window, keywords, green/red, stopwords, resume_stopwords, domain markers |
| [`channels.json`](config/channels.json) | you | Sources as `https://t.me/...` links |
| [`digest_patterns.json`](config/digest_patterns.json) | AI agent (via suspicious log) | Split patterns + per-channel `bindings` |

### Channels

```json
[
  "https://t.me/cgfreelance",
  "https://t.me/devjobs",
  "https://t.me/offerclaw"
]
```

Objects are allowed only for rare flags (`enabled`, `require_tags`) — not for digest patterns.

### Filters (`settings.json`)

| List | Role |
| --- | --- |
| `keywords` | Required job-title matches to pass |
| `green` | Stack / contract highlights on the card (does not gate pass) |
| `redwords` | Flags on the card (does not reject) |
| `stopwords` | Reject |
| `resume_stopwords` | Reject resume / “looking for work” posts |
| `domain_markers` | Count toward the `domain` stat only |

Also: `last_days`, `rescan_hours`, `letters_limit`, `near_dup_threshold`, `groups_limit`.

### Digest patterns (internal)

Multi-vacancy digests are split only for channels listed in `bindings`:

```json
{
  "bindings": {
    "offerclaw": "bullet_role_url",
    "forgamedev": "linkedin_job_bullets"
  },
  "patterns": [ ... ]
}
```

- Only the bound pattern is applied (no try-all).
- No binding → no digest split (Telegraph / RVC still work).
- Do not edit this file by hand for day-to-day use.

**Pattern miss** (post has 2+ job-board vacancy URLs and the bound pattern failed or is missing):

1. Console WARNING  
2. Full post → `cache/logs/suspicious_digests_YYYY-MM-DD.md`  
3. **Pattern alerts** in the daily report  

Hand that suspicious log to an **AI agent** (e.g. Cursor). The agent analyzes the posts, adds/fixes a pattern, and updates `bindings` in `config/digest_patterns.json`. The scanner does not call AI at runtime.

Single vacancies with portfolio / YouTube / forms links are not treated as digests.

**Telegraph** (`telegra.ph`) and **RVC** (`app.rvc.global/vacancy/...`) have their own splitters.

## Scan window

| Case | Window |
| --- | --- |
| No cursor yet | last `last_days` days |
| Cursor exists | new message ids **plus** last `rescan_hours` (48) for edits |

Cursors: `cache/state/cursors.json`.

## Output

| Path | Content |
| --- | --- |
| `output/YYYY-MM-DD.md` | Daily report (same-day re-run merges by post URL) |
| `cache/sessions/dedup_cache.json` | Cross-day URL dedup |
| `cache/logs/scan_*.log` | Run logs |
| `cache/logs/suspicious_digests_*.md` | Failed digests for AI pattern updates |

Report sections: **Sources** → **Pattern alerts** (if any) → **Vacancies**.

## Env

| Variable | Required | Notes |
| --- | --- | --- |
| `TG_API_ID` | yes | from [my.telegram.org](https://my.telegram.org/auth) — app credentials only |
| `TG_API_HASH` | yes | same |
| `OUTPUT_PATH` | no | defaults to `output/` |

Phone number and login code are **not** env vars: Telethon asks for them interactively on first run and stores the session under `cache/sessions/`.

`--channel` accepts a username, a 1-based index from `channels.json`, or a range like `1-3`.

## Local-only

`jobs_release/` is a local example from another search profile (gitignored, not part of the repo).
