#!/bin/bash

cd "$(dirname "$0")" || exit 1

PYTHON_CMD=""

if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_CMD="python3.11"
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_CMD="python3.12"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "No Python 3 was found."
    echo "Install Python 3.11 or 3.12, then run this file again."
    echo
    read -r -p "Press Return to close..."
    exit 1
fi

"$PYTHON_CMD" "scripts/setup_jarvis.py"
STATUS=$?

echo
read -r -p "Press Return to close..."
exit "$STATUS"
