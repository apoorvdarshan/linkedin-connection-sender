#!/usr/bin/env python3
"""
linkedin_connect.py
===================
Send LinkedIn CONNECTION REQUESTS to people filtered by COUNTRY (and optionally
role/keyword), at a slow, human-ish pace. Built to be run manually or on a
weekly schedule to grow your network in a target geography.

  - Logs in via your signed-in Chrome session (no password, works with 2FA).
  - Finds people by country (LinkedIn geo IDs) + optional keyword/title.
  - Sends note-less invites (free accounts only get ~5 invite NOTES/month).
  - Throttles heavily, caps per run, remembers who it already invited.

------------------------------------------------------------------------------
READ THIS FIRST  -- invites are the single riskiest thing to automate
------------------------------------------------------------------------------
1. LinkedIn enforces a WEEKLY invite limit (~100-200/week, often ~100). Going
   over -> warnings, then restriction. Keep PER_RUN_LIMIT * runs/week well under.
2. If invitees click "I don't know this person" / Ignore, LinkedIn can BLOCK
   your account from sending invites for weeks. Target RELEVANT people (use
   KEYWORDS) so they actually accept.
3. This uses LinkedIn's internal Voyager API -> violates the User Agreement;
   your account can be restricted. Use at your own risk.
4. If the invite call returns 401/403 or a quota code, your account is currently
   invite-restricted or at its weekly cap -- STOP and let it rest.

Login (tried in order): Chrome auto-read -> LI_AT/LI_JSESSIONID env -> password.
See the cookie notes near build_api(). Run:

  ./.venv/bin/python linkedin_connect.py            # DRY RUN (sends nothing)
  LIVE=1 ./.venv/bin/python linkedin_connect.py     # actually send
"""

import csv
import os
import sys
import time
import json
import random
import getpass

try:
    from linkedin_api import Linkedin
    from requests.cookies import RequestsCookieJar
except ImportError:
    sys.exit("Missing dependency. Run:  pip install linkedin-api browser-cookie3")

# ----------------------------------------------------------------------------
# CONFIG -- tune these
# ----------------------------------------------------------------------------
TARGET_COUNTRY = "United States"   # must be a key in GEO_URN below
KEYWORDS       = "software engineer"  # role/keyword filter ("" = anyone). Keep
                                      # this relevant to lower ignore/reject rate.
NETWORK_DEPTHS = ["S", "O"]        # who to invite: S=2nd, O=3rd+ (NOT already
                                   # connected). Never "F" (already connected).

PER_RUN_LIMIT  = 20                # max invites to send in ONE run (stay low!)
WEEKLY_LIMIT   = 80                # soft self-cap across the rolling week
MIN_DELAY_SEC  = 25.0              # invites need BIG gaps -- much slower than
MAX_DELAY_SEC  = 70.0              # unfollows -- to look human and stay safe.

SENT_FILE      = "sent_invites.csv"   # remembers who you've invited (resumable)
NOTE           = ""                # leave "" (note-less). Free accounts only get
                                   # ~5 invite notes/month, so bulk notes fail.

# LinkedIn geo URN IDs for the `regions` search facet. Add more as needed
# (find an id: filter People search by a location, read geoUrn in the URL).
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


# ----------------------------------------------------------------------------
# Login (Chrome cookies / env / password) -- same proven flow as before
# ----------------------------------------------------------------------------
def _jar(li_at, jsession):
    jar = RequestsCookieJar()
    jar.set("li_at", li_at, domain=".linkedin.com")
    jar.set("JSESSIONID", jsession, domain=".linkedin.com")
    return jar


def cookies_from_chrome():
    try:
        import browser_cookie3
    except ImportError:
        print("  (browser-cookie3 not installed -- pip install browser-cookie3)")
        return None
    cookie_file = None
    profile = os.environ.get("CHROME_PROFILE")
    if profile:
        cookie_file = os.path.expanduser(
            f"~/Library/Application Support/Google/Chrome/{profile}/Cookies")
    try:
        cj = browser_cookie3.chrome(cookie_file=cookie_file,
                                    domain_name="linkedin.com")
    except Exception as e:
        print(f"  (couldn't read Chrome cookies: {e})")
        return None
    li_at = jsession = None
    for c in cj:
        if c.name == "li_at":
            li_at = c.value
        elif c.name == "JSESSIONID":
            jsession = c.value
    if not (li_at and jsession):
        print("  (Chrome has no LinkedIn session -- are you signed in? "
              "Try CHROME_PROFILE=...)")
        return None
    return _jar(li_at, jsession)


def build_api():
    li_at, jsession = os.environ.get("LI_AT"), os.environ.get("LI_JSESSIONID")
    if li_at and jsession:
        print("Logging in with cookies from environment (2FA-safe)...")
        api = Linkedin("", "", cookies=_jar(li_at, jsession))
        print("  session loaded.\n")
        return api
    print("Reading your LinkedIn session from Chrome...")
    jar = cookies_from_chrome()
    if jar is not None:
        api = Linkedin("", "", cookies=jar)
        print("  session loaded from Chrome.\n")
        return api
    print("Falling back to password login (fails under 2FA)...")
    email = os.environ.get("LI_EMAIL") or input("LinkedIn email: ").strip()
    password = os.environ.get("LI_PASSWORD") or getpass.getpass("LinkedIn password: ")
    api = Linkedin(email, password)
    print("  logged in.\n")
    return api


# ----------------------------------------------------------------------------
# Find candidates + send invites
# ----------------------------------------------------------------------------
def find_candidates(api, country, keywords, depths, want):
    geo = GEO_URN.get(country)
    if not geo:
        sys.exit(f"Unknown TARGET_COUNTRY '{country}'. Add its geo id to GEO_URN "
                 f"(known: {', '.join(sorted(GEO_URN))}).")
    print(f"Searching: '{keywords or 'anyone'}' in {country} "
          f"(geo {geo}), depths {depths}...")
    people = api.search_people(keywords=keywords or None, regions=[geo],
                               network_depths=depths, limit=max(want * 3, 30))
    cands = [{"urn_id": p["urn_id"], "name": p.get("name", ""),
              "jobtitle": p.get("jobtitle", ""), "location": p.get("location", "")}
             for p in people if p.get("urn_id")]
    print(f"  {len(cands)} candidates found.")
    return cands


def send_invite(api, urn_id, note=""):
    """
    POST one invite via verifyQuotaAndCreateV2 and read the real outcome.
    Returns (status, code, outcome) where outcome is one of:
      'sent' | 'pending' | 'limit' | 'auth' | 'error'
    """
    s = api.client.session
    csrf = s.cookies.get("JSESSIONID", "").strip('"')
    payload = {"invitee": {"inviteeUnion":
               {"memberProfile": f"urn:li:fsd_profile:{urn_id}"}},
               "customMessage": note}
    params = {"action": "verifyQuotaAndCreateV2",
              "decorationId": "com.linkedin.voyager.dash.deco.relationships."
                              "InvitationCreationResultWithInvitee-2"}
    url = ("https://www.linkedin.com/voyager/api/"
           "voyagerRelationshipsDashMemberRelationships")
    r = s.post(url, params=params, data=json.dumps(payload), headers={
        "csrf-token": csrf,
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "content-type": "application/json; charset=UTF-8",
        "x-restli-protocol-version": "2.0.0",
    })
    code = None
    try:
        code = (r.json().get("data") or {}).get("code")
    except Exception:
        pass
    if r.status_code in (200, 201):
        return r.status_code, code, "sent"
    if code in ("CANT_RESEND_YET",) or r.status_code == 409:
        return r.status_code, code, "pending"
    if r.status_code == 429 or (code and ("QUOTA" in code or "LIMIT" in code)):
        return r.status_code, code, "limit"
    if r.status_code in (401, 403):
        return r.status_code, code, "auth"
    return r.status_code, code, "error"


def load_sent():
    done = set()
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, newline="") as f:
            for row in csv.reader(f):
                if row:
                    done.add(row[0])
    return done


def mark_sent(urn_id, name, outcome):
    new = not os.path.exists(SENT_FILE)
    with open(SENT_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["urn_id", "name", "outcome"])
        w.writerow([urn_id, name, outcome])


def main():
    try:
        api = build_api()
    except Exception as e:
        sys.exit(f"Login failed: {e}\n(For 2FA, set LI_AT + LI_JSESSIONID.)")
    live = os.environ.get("LIVE") == "1"
    per_run = int(os.environ.get("LIMIT", PER_RUN_LIMIT))

    sent = load_sent()
    if len(sent) >= WEEKLY_LIMIT:
        print(f"Weekly self-cap reached ({len(sent)}/{WEEKLY_LIMIT} in "
              f"{SENT_FILE}). Clear it next week or raise WEEKLY_LIMIT.")
        return

    cands = find_candidates(api, TARGET_COUNTRY, KEYWORDS, NETWORK_DEPTHS, per_run)
    todo = [c for c in cands if c["urn_id"] not in sent][:per_run]
    print(f"\n{len(sent)} already invited | {len(todo)} to invite this run "
          f"(cap {per_run}).")

    if not todo:
        print("Nobody new to invite. Widen KEYWORDS or try later.")
        return

    if not live:
        print("\n*** DRY RUN -- would invite (set LIVE=1 to actually send): ***")
        for c in todo:
            print(f"  + {c['name']}  ({c['jobtitle'][:40]} | {c['location']})")
        print(f"\nLIVE=1 ./.venv/bin/python {os.path.basename(__file__)}")
        return

    count = 0
    for c in todo:
        status, code, outcome = send_invite(api, c["urn_id"], NOTE)
        if outcome == "sent":
            mark_sent(c["urn_id"], c["name"], "sent")
            count += 1
            print(f"[{count}/{len(todo)}] invited {c['name']}  ({c['location']})")
        elif outcome == "pending":
            mark_sent(c["urn_id"], c["name"], "pending")
            print(f"  (already pending/connected) {c['name']} -- skipping")
        elif outcome == "limit":
            print(f"\nWEEKLY LIMIT reached (HTTP {status}, code {code}). "
                  f"Stopping -- this is LinkedIn's cap, not a bug.")
            break
        elif outcome == "auth":
            print(f"\nHTTP {status}: account is invite-restricted or signed out. "
                  f"Stopping. Let it rest / re-check your login.")
            break
        else:
            print(f"  FAILED ({status}, code {code}) for {c['name']}")
        time.sleep(random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC))

    print(f"\nDone. Sent {count} invite(s) this run. Logged to {SENT_FILE}.")


if __name__ == "__main__":
    main()
