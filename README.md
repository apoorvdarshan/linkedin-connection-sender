# LinkedIn Connection Sender

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](#)

Send LinkedIn **connection requests filtered by country / role**, at a slow,
human-like pace — by driving a **real Chrome browser** (Playwright). Log in once
to an isolated session, then it clicks **Connect → Send** like a human.

> ⚠️ **Disclaimer.** This automates LinkedIn, which **violates the User
> Agreement** — your account can be restricted. Invites are the most-policed
> action: LinkedIn enforces a **weekly invite cap** and can **restrict accounts**
> that send too fast or get too many "I don't know this person" ignores. Keep
> volumes sane, target relevant people, use at your own risk.

---

## 🚦 Sending policy (the one rule)

> **Invites are sent ONLY via real-browser UI automation — clicking Connect →
> Send. The internal "Voyager" API is NEVER used to send invitations.**

The API is used **only for read-only work** (searching / fetching a candidate
list). Sending through the API is what gets accounts **401-restricted and signed
out** — the browser, clicking real buttons, is far harder to detect and is the
only sanctioned send path here. If you fork this, keep that line.

## The tools

| Script | Purpose | Uses |
|---|---|---|
| `linkedin_connect_browser.py` | **Send invites** (login + find + click) | Real browser UI only |
| `fetch_candidates.py` | Build a candidate list (read-only) | API search (read-only) |

## Quickstart

```bash
./.venv/bin/pip install playwright

# 1) one-time: sign in to the isolated session (a real Chrome window opens)
./.venv/bin/python linkedin_connect_browser.py login

# 2) dry run (new-headless) — lists who it WOULD connect, sends nothing
./.venv/bin/python linkedin_connect_browser.py run

# 3) send for real, human-paced
LIVE=1 ./.venv/bin/python linkedin_connect_browser.py run
```

- Login must be a **visible** window (you can't type into a headless one). Every
  `run` after that is **new-headless** (`HEADFUL=1` to watch it).
- The session lives in an **isolated profile** (`~/.linkedin-connect-profile`),
  separate from your main Chrome — so if LinkedIn ever flags the automation,
  only this throwaway session is hit, never your real browser.

### Commands

| Command | What it does |
|---|---|
| `login` | One-time visible sign-in; saves the isolated session |
| `run` | Search `KEYWORDS` in `TARGET_COUNTRY` and Connect→Send to results |
| `sendlist` | Invite people in `LIST` (a CSV) by **searching each by name** |
| `profilesend` | Last-mile: invite remaining `LIST` people via their profile page |

Env knobs: `LIVE=1` (actually send), `LIMIT=N` (per-run cap), `KW="..."`
(override keyword), `GAP_MIN` / `GAP_MAX` (seconds between invites),
`LIST=candidates.csv` (target a specific reviewed list), `HEADFUL=1` (watch).

## Build a candidate list (read-only)

```bash
./.venv/bin/python fetch_candidates.py     # writes candidates.csv
```
Runs several keyword searches (founders/CEOs, HR/recruiters, engineers, …),
dedups, and writes `candidates.csv` (category, name, jobtitle, location,
urn_id). **Read-only — sends nothing.** Then send to that exact list with
`LIST=candidates.csv ... sendlist`.

## How it works (architecture)

A **3-stage pipeline** on a saved, **isolated** session:

1. **Session (one-time)** — `login` opens real Chrome; you sign in once (2FA
   fine); the session is saved and reused.
2. **Find** — search People by **country (geo) + keyword**, 2nd/3rd-degree,
   collecting **invitable** candidates (cards showing "Connect").
3. **Send (UI automation)** — the headless browser clicks **Connect → Send** per
   person, randomized gaps, **stops** on any weekly-limit / restriction dialog.
   An invite counts as sent **only if the Send button was actually clicked.**

## Configuration

Edit the constants at the top of `linkedin_connect_browser.py`:

| Setting | Default | What it does |
|---|---|---|
| `TARGET_COUNTRY` | `"United States"` | Country to target (must be in `GEO_URN`) |
| `KEYWORDS` | `"software engineer"` | Role/keyword (override per run with `KW=`) |
| `PER_RUN_LIMIT` | `15` | Max invites per run — keep low |
| `WEEKLY_LIMIT` | `80` | Soft self-cap |
| `MIN/MAX_DELAY_SEC` | `30` / `90` | Gap between invites (or `GAP_MIN`/`GAP_MAX`) |

### Supported countries

US, India, UK, Canada, Australia, Germany, France, Netherlands, Ireland,
Singapore, UAE, Saudi Arabia, Spain, Italy, Brazil, Japan, China, Pakistan,
Bangladesh, New Zealand. Add more via the `GEO_URN` map (find a geo id by
filtering People search by location and reading `geoUrn` in the URL).

## Troubleshooting

| Symptom | Meaning |
|---|---|
| **Stops: restriction / limit dialog** | You hit the weekly cap or are throttled. Stop, let it rest. |
| **0 candidates / "no Connect"** | Everyone on-page is pending/connected, or widen `KEYWORDS`. |
| **Login not detected** | Re-run `login` and finish signing in before the 5-min timeout. |

## Support

- 💖 [GitHub Sponsors](https://github.com/sponsors/apoorvdarshan)
- ☕ [Ko-fi](https://ko-fi.com/apoorvdarshan)

## License

[MIT](LICENSE) © Apoorv Darshan
