# JobScanner

Telegram scanner for Technical Artist / pipeline / real-time optimization vacancies. Daily output is Markdown, not Excel. Tunable data lives in JSON.

`jobs_release/` is a local example from another search profile. It is gitignored and is not part of this repository.

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env`:

- `TG_API_ID` and `TG_API_HASH` from [my.telegram.org](https://my.telegram.org/auth)
- `OUTPUT_PATH` — optional; defaults to `output/` in the repo

The Telegram account used for login must already be subscribed to the channels listed in `scanner/config/channels.json`.

## Config (edit JSON, not Python)

- [`scanner/config/settings.json`](scanner/config/settings.json) — window, keyword lists, stopwords, domain markers, `rescan_hours`
- [`scanner/config/channels.json`](scanner/config/channels.json) — sources: `enabled`, `relevance_score`, `require_tags`, `category`

Keywords are job titles. Stack and contract type are `green` (highlight only). A post with only `Remote` or `Python` does not pass.

Set `"enabled": false` to skip a dead username. Do not delete the row.

## Run

From the repo root:

```bash
python scanner/main.py
python scanner/main.py --days 10
python scanner/main.py --channel 1
python scanner/main.py --channel 1-5
```

First login asks for phone number and Telegram code. Session file: `scanner/sessions/` (not committed).

## Scan window

- Channel without a cursor: last `last_days` days
- Channel with a cursor: new message ids plus the last `rescan_hours` (48) hours so recent edits are seen
- Cursors: `scanner/state/cursors.json` (gitignored)

## Output

`output/YYYY-MM-DD.md`. A second run on the same day merges cards by post URL and does not drop earlier cards. Edited posts that reappear update the existing card.

## Scores

`relevance_score` is a manual 0–10 rating of the source. Channels below `min_relevance` are not scanned. This does not rank individual vacancies.
