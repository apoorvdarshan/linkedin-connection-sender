# LinkedIn Connection Sender

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](#)

Send LinkedIn **connection requests filtered by country** (and optionally
role/keyword), at a slow, human-like pace. Run it manually or on a weekly
schedule to grow your network in a target geography — using your already
signed-in Chrome session, no password required.

> ⚠️ **Disclaimer — read before using.** This uses LinkedIn's *internal*
> (unofficial) "Voyager" API, which **violates the LinkedIn User Agreement**.
> Invites are the single most-policed action to automate: LinkedIn enforces a
> **weekly invite cap (~100–200, often ~100)**, and too many "I don't know this
> person" ignores can get your account **restricted from sending invites**. Keep
> volumes low, target relevant people, and use entirely at your own risk.

---

## Features

- 🌍 **Target by country** — search people by LinkedIn geo region (US, India, UK,
  and more in a built-in map).
- 🎯 **Filter by role/keyword** — e.g. `"software engineer"`, so invitees are
  relevant and more likely to accept.
- 🐢 **Human-like pacing** — randomized 25–70s gaps, small per-run and weekly
  caps, so it doesn't look like a bot.
- 🧪 **Dry-run by default** — shows exactly who it *would* invite; nothing is
  sent until you opt in with `LIVE=1`.
- 💾 **Resumable** — logs everyone invited to `sent_invites.csv`, skips repeats,
  and **stops cleanly** when LinkedIn signals the weekly cap.
- 🔐 **No password** — reads your existing Chrome session (works with 2FA).

## How it works

1. Reads `li_at` + `JSESSIONID` from your signed-in Chrome (or env vars).
2. Searches People by **geo region + keyword**, restricted to **2nd/3rd-degree**
   (people you're not already connected to).
3. Sends **note-less** invites via the Voyager `verifyQuotaAndCreateV2`
   endpoint, reading the real result (sent / already-pending / weekly-limit).

## Setup

Requires Python 3.9+ and a virtualenv with the dependencies:

```bash
cd ~/linkedin-connection-sender
python3 -m venv .venv
./.venv/bin/pip install linkedin-api browser-cookie3
```

- First run may show a macOS Keychain prompt to read Chrome's cookies →
  click **Always Allow**.
- Signed in on a non-default Chrome profile?
  `export CHROME_PROFILE="Profile 1"` (find it at `chrome://version`).

## Usage

```bash
./.venv/bin/python linkedin_connect.py          # DRY RUN — lists who it WOULD invite
LIVE=1 ./.venv/bin/python linkedin_connect.py   # actually send
```

The first run is always a **dry run** so you can sanity-check the targets. Add
`LIVE=1` only once the list looks right. `LIMIT=N` overrides the per-run cap for
a single run.

## Configuration

Edit the constants at the top of `linkedin_connect.py`:

| Setting | Default | What it does |
|---|---|---|
| `TARGET_COUNTRY` | `"United States"` | Country to target (must exist in `GEO_URN`) |
| `KEYWORDS` | `"software engineer"` | Role/keyword filter (`""` = anyone in country) |
| `NETWORK_DEPTHS` | `["S", "O"]` | 2nd / 3rd-degree only (never existing connections) |
| `PER_RUN_LIMIT` | `20` | Max invites per run — keep low |
| `WEEKLY_LIMIT` | `80` | Soft self-cap across the week |
| `MIN/MAX_DELAY_SEC` | `25` / `70` | Random pause between invites (seconds) |
| `NOTE` | `""` | Invite note (free accounts get only ~5 notes/month) |

### Supported countries

US, India, UK, Canada, Australia, Germany, France, Netherlands, Ireland,
Singapore, UAE, Saudi Arabia, Spain, Italy, Brazil, Japan, China, Pakistan,
Bangladesh, New Zealand. Add more by dropping a country's geo id into the
`GEO_URN` map (find an id by filtering People search by a location and reading
`geoUrn` in the URL).

## Weekly schedule (optional)

Run it on a cadence with a `launchd` agent (macOS) or `cron`. Keep the per-run
cap small so the weekly total stays comfortably under LinkedIn's limit.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| **HTTP 401 / 403** on send | Account is invite-restricted or signed out — stop, sign back in, let it rest. |
| **Stops with a quota code** | You hit the weekly invite cap. Normal — wait and try again next week. |
| **`already pending/connected`** | You've already invited or are connected to that person — it's skipped. |
| **0 candidates** | Widen `KEYWORDS` or the country, or the search is temporarily rate-limited. |

## Support

If this is useful, you can support the work:

- 💖 [GitHub Sponsors](https://github.com/sponsors/apoorvdarshan)
- ☕ [Ko-fi](https://ko-fi.com/apoorvdarshan)

## License

[MIT](LICENSE) © Apoorv Darshan
