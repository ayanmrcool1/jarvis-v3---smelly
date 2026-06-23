#!/bin/bash

cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
    echo "JARVIS has not been set up yet."
    echo "Run setup_mac.command first."
    echo
    read -r -p "Press Return to close..."
    exit 1
fi

".venv/bin/python" "scripts/launch_jarvis.py" --hud web --detached
STATUS=$?

echo
if [ "$STATUS" -ne 0 ]; then
    read -r -p "Press Return to close..."
fi
exit "$STATUS"
