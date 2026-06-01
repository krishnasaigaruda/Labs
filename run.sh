#!/usr/bin/env bash
# Launch ToolLabs on a local web server.
#
# The Aesthetic Checker needs an http origin (blob: previews + AI fetch don't
# work from file://). This serves the folder at http://localhost:PORT and opens
# the tool in your browser.
#
# Usage:  ./run.sh [port]      (default 8000)

cd "$(dirname "$0")" || exit 1
PORT="${1:-8787}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found on your PATH." >&2
  exit 1
fi

exec python3 serve.py "$PORT"
