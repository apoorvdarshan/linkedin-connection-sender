#!/usr/bin/env python3
"""
linkedin_connect_browser.py
===========================
Browser-driven LinkedIn connection sender (Playwright). Instead of hitting the
internal API directly (easy to fingerprint), this drives a REAL Chrome: you log
in once in a visible window, the session is saved to a local profile, and later
runs reuse it in new-headless mode and behave like a human (scrolling, random
delays, real button clicks).

  Lower detection risk than raw API calls -- BUT not magic: LinkedIn's weekly
  invite cap (~100) is server-side and applies no matter what. Stay well under
  it, target relevant people, and use at your own risk (this still breaks the
  LinkedIn User Agreement).

Three commands:
  login    one-time, opens a VISIBLE window -> you sign in (2FA ok) -> session saved
  run      DRY RUN in new-headless -> lists who it WOULD connect with (no clicks)
  run +LIVE=1  actually clicks Connect, human-paced

  ./.venv/bin/python linkedin_connect_browser.py login
  ./.venv/bin/python linkedin_connect_browser.py run
  LIVE=1 ./.venv/bin/python linkedin_connect_browser.py run

Setup (one-time):
  ./.venv/bin/pip install playwright
  # uses your installed Chrome via channel="chrome"; if that fails, run:
  ./.venv/bin/playwright install chromium
"""

import os
import sys
import csv
import time
import random
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit("Missing dependency. Run:\n"
             "  ./.venv/bin/pip install playwright\n"
             "  ./.venv/bin/playwright install chromium   # only if channel=chrome fails")

# ----------------------------------------------------------------------------
# CONFIG -- tune these
# ----------------------------------------------------------------------------
TARGET_COUNTRY = "United States"
KEYWORDS       = "software engineer"
PER_RUN_LIMIT  = 15                 # invites per run -- keep low (weekly cap ~100)
MIN_DELAY_SEC  = 30.0               # human gap between Connect clicks
MAX_DELAY_SEC  = 90.0

# Dedicated, isolated browser profile (NOT your main Chrome) so automation never
# clashes with your normal browsing. The login/session lives here, outside the repo.
PROFILE_DIR    = str(Path.home() / ".linkedin-connect-profile")
SENT_FILE      = "sent_invites.csv"

# LinkedIn geo region IDs for the People-search `geoUrn` filter.
GEO_URN = {
    "United States": "103644278", "India": "102713980",
    "United Kingdom": "101165590", "Canada": "101174742",
    "Australia": "101452733", "Germany": "101282230", "France": "105015875",
    "Netherlands": "102890719", "Ireland": "104738515", "Singapore": "102454443",
    "United Arab Emirates": "104305776", "Saudi Arabia": "100459316",
    "Spain": "105646813", "Italy": "103350119", "Brazil": "106057199",
    "Japan": "101355337", "China": "102890883", "Pakistan": "101022442",
    "Bangladesh": "106215326", "New Zealand": "105490917",
}

# JS that hides the most common automation tells before any page script runs.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = window.chrome || { runtime: {} };
"""


# ----------------------------------------------------------------------------
def jitter(a=MIN_DELAY_SEC, b=MAX_DELAY_SEC):
    time.sleep(random.uniform(a, b))


def human_scroll(page, steps=None):
    """Scroll down in a few irregular chunks, like a person skimming."""
    for _ in range(steps or random.randint(3, 6)):
        page.mouse.wheel(0, random.randint(300, 700))
        time.sleep(random.uniform(0.6, 1.8))


def wiggle_mouse(page):
    for _ in range(random.randint(1, 3)):
        page.mouse.move(random.randint(60, 1100), random.randint(120, 700),
                        steps=random.randint(4, 12))
        time.sleep(random.uniform(0.2, 0.7))


def launch(p, headless):
    """Persistent Chrome context -> cookies/session survive between runs."""
    ctx = p.chromium.launch_persistent_context(
        PROFILE_DIR,
        channel="chrome",                 # use installed Chrome (no big download)
        headless=headless,                # Playwright's chromium headless = new mode
        viewport={"width": 1280, "height": 820},
        args=["--disable-blink-features=AutomationControlled",
              "--start-maximized"],
    )
    ctx.add_init_script(STEALTH_JS)
    return ctx


def load_sent():
    done = set()
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, newline="") as f:
            for row in csv.reader(f):
                if row:
                    done.add(row[0])
    return done


def mark_sent(name, outcome):
    new = not os.path.exists(SENT_FILE)
    with open(SENT_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["name", "outcome"])
        w.writerow([name, outcome])


def logged_in(page):
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    time.sleep(random.uniform(2, 4))
    return "/login" not in page.url and "/authwall" not in page.url


# ----------------------------------------------------------------------------
def cmd_login():
    """Open a VISIBLE window, let the user sign in, persist the session."""
    print("Opening Chrome -- sign in to LinkedIn (do 2FA if asked).")
    with sync_playwright() as p:
        ctx = launch(p, headless=False)        # MUST be visible to log in
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        input("\n>>> After you're fully logged in (you can see your feed), "
              "come back here and press ENTER to save the session... ")
        ok = logged_in(page)
        ctx.close()
    if ok:
        print(f"\n✓ Session saved to {PROFILE_DIR}. You can now run:  "
              f"./.venv/bin/python {os.path.basename(__file__)} run")
    else:
        print("\n✗ Didn't detect a logged-in session. Re-run 'login' and make "
              "sure you reach the feed before pressing ENTER.")


def search_url(country, keywords):
    geo = GEO_URN.get(country)
    if not geo:
        sys.exit(f"Unknown TARGET_COUNTRY '{country}'. Known: {', '.join(sorted(GEO_URN))}")
    return ("https://www.linkedin.com/search/results/people/?"
            f"keywords={quote(keywords)}"
            f"&geoUrn=%5B%22{geo}%22%5D"
            "&network=%5B%22S%22%2C%22O%22%5D"   # 2nd + 3rd degree (invitable)
            "&origin=FACETED_SEARCH")


def cmd_run(live):
    headless = os.environ.get("HEADFUL") != "1"     # default: new-headless
    per_run = int(os.environ.get("LIMIT", PER_RUN_LIMIT))
    sent = load_sent()

    with sync_playwright() as p:
        ctx = launch(p, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if not logged_in(page):
            ctx.close()
            sys.exit("Not logged in. Run the 'login' command first (visible window).")

        print(f"Searching: '{KEYWORDS}' in {TARGET_COUNTRY} (2nd/3rd degree)...")
        page.goto(search_url(TARGET_COUNTRY, KEYWORDS), wait_until="domcontentloaded")
        time.sleep(random.uniform(3, 5))

        count = 0
        pages_seen = 0
        while count < per_run and pages_seen < 10:
            pages_seen += 1
            wiggle_mouse(page)
            human_scroll(page)

            # "Connect" buttons on result cards carry aria-label "Invite X to connect"
            buttons = page.locator("button[aria-label^='Invite']")
            n = buttons.count()
            if n == 0:
                print("  no Connect buttons on this page (everyone may be "
                      "pending/connected, or selectors changed).")

            for i in range(n):
                if count >= per_run:
                    break
                btn = buttons.nth(i)
                try:
                    label = btn.get_attribute("aria-label") or "Invite to connect"
                    name = label.replace("Invite", "").replace("to connect", "").strip()
                except Exception:
                    name = f"candidate#{i}"
                if name in sent:
                    continue

                if not live:
                    print(f"  [DRY] would connect: {name}")
                    mark_sent(name, "dry")     # so dry runs don't repeat names
                    count += 1
                    continue

                try:
                    btn.scroll_into_view_if_needed()
                    wiggle_mouse(page)
                    btn.click()
                    time.sleep(random.uniform(1.5, 3.0))
                    # modal: prefer note-less "Send without a note", else "Send"
                    for sel in ("button[aria-label='Send without a note']",
                                "button:has-text('Send without a note')",
                                "button[aria-label='Send now']",
                                "button:has-text('Send')"):
                        m = page.locator(sel)
                        if m.count() > 0:
                            m.first.click()
                            break
                    mark_sent(name, "sent")
                    count += 1
                    print(f"  [{count}/{per_run}] connected: {name}")
                    # dismiss any leftover modal, then human pause
                    page.keyboard.press("Escape")
                    jitter()
                except PWTimeout:
                    print(f"  timeout on {name} -- skipping")
                except Exception as e:
                    print(f"  couldn't connect {name}: {e}")

            # next page
            nxt = page.locator("button[aria-label='Next']")
            if count < per_run and nxt.count() > 0 and nxt.first.is_enabled():
                nxt.first.click()
                time.sleep(random.uniform(3, 6))
            else:
                break

        ctx.close()
    print(f"\nDone. {'Sent' if live else 'Would send (dry)'} {count} this run. "
          f"Logged to {SENT_FILE}.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "login":
        cmd_login()
    elif cmd == "run":
        cmd_run(live=os.environ.get("LIVE") == "1")
    else:
        print(__doc__)
        sys.exit("Usage: linkedin_connect_browser.py [login|run]   "
                 "(LIVE=1 to actually send; HEADFUL=1 to watch)")


if __name__ == "__main__":
    main()
