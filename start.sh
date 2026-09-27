#!/usr/bin/env bash
# Vednix AI one-click launcher for macOS/Linux. Requires Python 3.11+ and Node 20+.
# Creates the project venv, installs dependencies, and starts the API + web app.
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 scripts/launch.py
elif command -v python >/dev/null 2>&1; then
    python scripts/launch.py
else
    echo "Python 3.11+ is required: https://www.python.org/downloads/"
    exit 1
fi
