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
def jitter(a=None, b=None):
    # gap between invites; override with GAP_MIN / GAP_MAX env vars
    a = float(os.environ.get("GAP_MIN", MIN_DELAY_SEC)) if a is None else a
    b = float(os.environ.get("GAP_MAX", MAX_DELAY_SEC)) if b is None else b
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
    """Open a VISIBLE window, wait for sign-in, persist the isolated session."""
    print("Opening a Chrome window -- sign in to LinkedIn there (2FA is fine).")
    print(f"This is a SEPARATE session from your normal Chrome ({PROFILE_DIR}).")
    with sync_playwright() as p:
        ctx = launch(p, headless=False)        # MUST be visible to log in
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        print("Waiting for you to finish signing in (up to 5 minutes)...",
              flush=True)
        ok = False
        for _ in range(150):                   # 150 x 2s = 5 min
            time.sleep(2)
            try:
                names = {c["name"] for c in ctx.cookies()}
            except Exception:
                names = set()
            if "li_at" in names:               # li_at = the logged-in token
                ok = True
                break
        time.sleep(2)                          # settle so cookies flush to disk
        ctx.close()
    if ok:
        print(f"\n✓ Session saved to {PROFILE_DIR}. Now run:  "
              f"./.venv/bin/python {os.path.basename(__file__)} run")
    else:
        print("\n✗ No login detected within 5 min. Re-run 'login' and finish "
              "signing in before it times out.")


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
        base_url = search_url(TARGET_COUNTRY, KEYWORDS)

        count = 0
        pages_seen = 0
        seen_run = set()
        stop = False
        while count < per_run and pages_seen < 12 and not stop:
            pages_seen += 1
            # Paginate by URL (&page=N) -- robust, unlike clicking "Next".
            page.goto(base_url + f"&page={pages_seen}",
                      wait_until="domcontentloaded")
            time.sleep(random.uniform(3, 5))
            wiggle_mouse(page)
            human_scroll(page)

            # Process this page by RE-QUERYING fresh each iteration. After a send
            # the DOM updates and old element handles go stale (the cause of the
            # timeouts), so we re-find the exact person by aria-label every time
            # and never touch a shifted/detached element.
            tried_here = set()
            while count < per_run:
                labels = page.locator("[aria-label^='Invite'][aria-label*='to connect']")
                names = []
                for i in range(labels.count()):
                    al = labels.nth(i).get_attribute("aria-label") or ""
                    nm = al.replace("Invite", "").replace("to connect", "").strip()
                    if nm:
                        names.append(nm)
                name = next((nm for nm in names if nm not in sent
                             and nm not in seen_run and nm not in tried_here), None)
                if name is None:
                    break                          # nobody new left on this page
                tried_here.add(name)

                if not live:
                    seen_run.add(name)
                    print(f"  [DRY] would connect: {name}")
                    count += 1
                    continue

                # fresh locator for THIS exact person (robust to DOM shifts)
                btn = page.locator(f'[aria-label="Invite {name} to connect"]').first
                try:
                    btn.scroll_into_view_if_needed()
                    wiggle_mouse(page)
                    btn.click(timeout=8000)
                    time.sleep(random.uniform(1.2, 2.5))
                    # Click a REAL Send button in the modal (tag-agnostic).
                    sent_ok = False
                    for sel in ("[aria-label='Send without a note']",
                                "button:has-text('Send without a note')",
                                "[aria-label='Send now']",
                                "[aria-label='Send']",
                                "button:has-text('Send')"):
                        m = page.locator(sel)
                        if m.count() > 0:
                            m.first.click(timeout=6000)
                            sent_ok = True
                            break

                    if sent_ok:
                        seen_run.add(name)
                        mark_sent(name, "sent")     # only counted if Send clicked
                        count += 1
                        print(f"  [{count}/{per_run}] connected: {name}")
                        page.keyboard.press("Escape")
                        jitter()
                    else:
                        # No Send dialog -> restriction/limit, or Connect-under-'...'
                        body = ""
                        try:
                            body = (page.inner_text("body") or "").lower()
                        except Exception:
                            pass
                        if any(k in body for k in ("weekly invitation limit",
                                "you've reached", "reached the", "restricted",
                                "try again")):
                            print(f"\nSTOP: LinkedIn restriction/limit hit (no Send "
                                  f"dialog for {name}). Account is capped/restricted.")
                            page.keyboard.press("Escape")
                            stop = True
                            break
                        print(f"  skip {name}: no Send dialog "
                              f"(Connect may be under the '...' menu)")
                        page.keyboard.press("Escape")
                        time.sleep(random.uniform(0.8, 1.6))
                except PWTimeout:
                    print(f"  timeout on {name} -- skipping")
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"  couldn't connect {name}: {e}")
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass

            # End of results? A page with no Invite AND no Pending = no people
            # left, so stop paging (otherwise the next URL goes by &page=N).
            if (page.locator("[aria-label^='Invite'][aria-label*='to connect']").count() == 0
                    and page.locator("[aria-label*='Pending']").count() == 0):
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
