#!/bin/bash

cd "$(dirname "$0")" || exit 1

if [ -x ".venv/bin/python" ]; then
    ".venv/bin/python" "scripts/stop_jarvis.py"
else
    python3 "scripts/stop_jarvis.py"
fi

STATUS=$?

echo
read -r -p "Press Return to close..."
exit "$STATUS"
