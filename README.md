# LinkedIn Connection Sender

Personal script to **send LinkedIn connection requests filtered by country**
(and optionally role/keyword), at a slow, human-ish pace — run manually or on a
weekly schedule to grow your network in a target geography.

Uses the unofficial `linkedin-api` (Voyager) library with your **Chrome
session** (no password, works with 2FA).

> ⚠️ **Invites are the riskiest thing to automate on LinkedIn.** There's a
> weekly invite cap (~100–200/week, often ~100), and too many "I don't know this
> person" ignores can get your account **restricted from sending invites**. This
> also violates LinkedIn's User Agreement — use at your own risk. Keep volumes
> low and target relevant people.

## Setup
- `.venv/` — virtualenv with `linkedin-api` + `browser-cookie3` installed.
- Logs in by reading `li_at` + `JSESSIONID` from your signed-in Chrome.
  First run may show a macOS Keychain prompt → **Always Allow**.
- Non-default Chrome profile? `export CHROME_PROFILE="Profile 1"`.

## Usage
```bash
cd ~/linkedin-toolkit
./.venv/bin/python linkedin_connect.py          # DRY RUN — shows who it WOULD invite
LIVE=1 ./.venv/bin/python linkedin_connect.py   # actually send
```
First run is always a **dry run** (sends nothing) so you can sanity-check the
targets. Add `LIVE=1` to send for real.

## Configure (top of `linkedin_connect.py`)
| Setting | What it does |
|---|---|
| `TARGET_COUNTRY` | Country to target (must be in the `GEO_URN` map) |
| `KEYWORDS` | Role/keyword filter, e.g. `"software engineer"` (`""` = anyone) |
| `PER_RUN_LIMIT` | Max invites per run — **keep low** |
| `WEEKLY_LIMIT` | Soft self-cap across the week |
| `MIN/MAX_DELAY_SEC` | Pause between invites (25–70s by default — slow on purpose) |

- Sends **note-less** invites by default (free accounts only get ~5 invite
  *notes*/month, so bulk notes aren't possible).
- Remembers everyone invited in `sent_invites.csv` → safe to re-run; it skips
  people already invited and stops cleanly when LinkedIn signals the weekly cap.
- Targets only **2nd/3rd-degree** people (not existing connections).

## If it stops with HTTP 401/403 or a quota code
Your account is at its **weekly invite cap** or temporarily **invite-restricted**
(common after heavy activity). That's LinkedIn's guardrail, not a bug — stop,
let the account rest, and try again later with smaller volumes.

## Weekly schedule (optional)
Run it on a cadence with a `launchd` agent (macOS) or cron. Keep the per-run cap
small so the weekly total stays well under LinkedIn's limit.

## License
[MIT](LICENSE) © Apoorv Darshan
