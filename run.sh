#!/usr/bin/env bash
# Convenience launcher. Dry run by default; pass LIVE=1 to actually send.
#   ./run.sh           -> dry run (shows who it WOULD invite)
#   LIVE=1 ./run.sh    -> send for real
cd "$(dirname "$0")"
exec ./.venv/bin/python linkedin_connect.py
