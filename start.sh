#!/usr/bin/env bash
# ============================================================
#   VEDNIX AI — one-click launcher (macOS / Linux)
#   Bas yeh chalao:  ./start.sh
#   Na Ollama janna zaroori, na pip, na npm — sab apne aap:
#     1. Python check          5. Vednix Engine auto-install
#     2. Backend venv + deps   6. Engine start + model download
#     3. Node check            7. Backend + Frontend start
#     4. Frontend install      8. Browser khud khul jayega
#   Rokna ho to Ctrl+C.
# ============================================================
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    python3 scripts/launch.py
elif command -v python >/dev/null 2>&1; then
    python scripts/launch.py
else
    echo ""
    echo "  [X] Python nahi mila."
    echo "  [-] Ek baar install karo Python 3.11+:  https://www.python.org/downloads/"
    echo ""
    exit 1
fi
