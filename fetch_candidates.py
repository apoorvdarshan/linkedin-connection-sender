#!/usr/bin/env python3
"""
fetch_candidates.py
===================
READ-ONLY candidate finder. Builds a list of US people to (later) invite,
weighted toward FOUNDERS / CEOs and especially HR / RECRUITERS, plus the
engineer / full-stack / web / app roles.

- Uses the ISOLATED browser session's cookies (`~/.linkedin-connect-profile`) so
  your MAIN Chrome is never touched.
- Sends NOTHING. It only searches and writes `candidates.csv`.
- Runs several keyword searches (one search alone caps ~40 results) and dedups.

  ./.venv/bin/python fetch_candidates.py
"""
import csv
import sys
import time
import random
from collections import Counter

from requests.cookies import RequestsCookieJar
from linkedin_api import Linkedin
from playwright.sync_api import sync_playwright

PROFILE = "/Users/ApoorvDarshan/.linkedin-connect-profile"
US_GEO  = "103644278"
TARGET  = int(os.environ.get("TARGET", "210"))   # how many NEW candidates to find
OUT     = os.environ.get("OUT", "candidates.csv")
SKIP_SENT = "sent_invites.csv"                    # exclude anyone already invited

# Priority order (HR first, then founders/CEOs, then engineers). Per-category
# caps (scaled to TARGET) keep a balanced mix.
import math as _math
_c = _math.ceil
CATEGORY_CAP = {"hr/recruiter": _c(TARGET * 0.4),
                "founder/ceo":  _c(TARGET * 0.4),
                "engineer":     _c(TARGET * 0.35)}
KEYWORDS = [
    ("hr/recruiter", "technical recruiter"),
    ("hr/recruiter", "talent acquisition"),
    ("hr/recruiter", "tech recruiter"),
    ("hr/recruiter", "hiring manager"),
    ("founder/ceo",  "founder"),
    ("founder/ceo",  "ceo"),
    ("founder/ceo",  "co-founder"),
    ("founder/ceo",  "cto"),
    ("engineer",     "software engineer"),
    ("engineer",     "full stack developer"),
    ("engineer",     "web developer"),
    ("engineer",     "app developer"),
]


def isolated_cookies():
    """Pull li_at + JSESSIONID from the isolated session (main Chrome untouched)."""
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        time.sleep(2)                       # JSESSIONID is only set after a load
        cookies = ctx.cookies()
        ctx.close()
    d = {c["name"]: c["value"] for c in cookies}
    if "li_at" not in d:
        sys.exit("No li_at in the isolated session. Run the browser 'login' first.")
    js = d.get("JSESSIONID") or '"ajax:0000000000000000000"'
    if not js.startswith('"'):
        js = f'"{js}"'                      # linkedin-api expects the quotes
    jar = RequestsCookieJar()
    jar.set("li_at", d["li_at"], domain=".linkedin.com")
    jar.set("JSESSIONID", js, domain=".linkedin.com")
    return jar


def _norm(s):
    import re
    s = re.sub(r"[^a-z ]", "", (s or "").lower())
    return " ".join(s.split()[:2])


def _already_sent_keys():
    """Normalized names of everyone already invited (so we never re-list them)."""
    keys = set()
    if os.path.exists(SKIP_SENT):
        for r in csv.reader(open(SKIP_SENT)):
            if r:
                nm = r[1] if len(r) >= 3 else r[0]   # mixed 2-/3-col format
                keys.add(_norm(nm))
    return keys


def main():
    api = Linkedin("", "", cookies=isolated_cookies())
    found = {}                          # urn_id -> row
    cat_count = Counter()
    sent_keys = _already_sent_keys()
    print(f"excluding {len(sent_keys)} already-invited people; target {TARGET}")

    for category, kw in KEYWORDS:
        if len(found) >= TARGET:
            break
        if cat_count[category] >= CATEGORY_CAP[category]:
            continue
        print(f"searching: '{kw}' ({category})...", flush=True)
        try:
            people = api.search_people(keywords=kw, regions=[US_GEO],
                                       network_depths=["S", "O"], limit=60)
        except Exception as e:
            print(f"  error: {e}")
            continue
        new = 0
        for pp in people:
            urn = pp.get("urn_id")
            if not urn or urn in found:
                continue
            if _norm(pp.get("name", "")) in sent_keys:    # already invited
                continue
            if cat_count[category] >= CATEGORY_CAP[category]:
                break
            found[urn] = {
                "category": category, "keyword": kw,
                "name": pp.get("name", ""), "jobtitle": pp.get("jobtitle", ""),
                "location": pp.get("location", ""), "urn_id": urn,
            }
            cat_count[category] += 1
            new += 1
            if len(found) >= TARGET:
                break
        print(f"  +{new} new  (total {len(found)})")
        time.sleep(random.uniform(2.5, 4.5))   # gentle between searches

    rows = list(found.values())
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["category", "keyword", "name",
                                          "jobtitle", "location", "urn_id"])
        w.writeheader()
        w.writerows(rows)

    print(f"\n{'='*50}\nFETCHED {len(rows)} candidates (read-only, none invited)")
    for c, n in cat_count.most_common():
        print(f"  {c:<14} {n}")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
