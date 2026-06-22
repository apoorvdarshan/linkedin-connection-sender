#!/usr/bin/env bash
# Convenience launcher for the browser (UI-automation) sender.
# Dry run by default; pass LIVE=1 to actually send.
#   ./run.sh           -> dry run (shows who it WOULD invite)
#   LIVE=1 ./run.sh    -> send for real (UI clicks only)
cd "$(dirname "$0")"
exec ./.venv/bin/python linkedin_connect_browser.py run
