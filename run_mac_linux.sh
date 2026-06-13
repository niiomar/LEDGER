#!/bin/bash
echo ""
echo " GMM Kasoa Media — Contributions System"
echo " ========================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo " ERROR: Python 3 is not installed."
    echo " Install it from https://www.python.org/downloads/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo " Setting up virtual environment for the first time..."
    python3 -m venv venv
    source venv/bin/activate
    echo " Installing dependencies..."
    pip install -r requirements.txt --quiet
    echo " Done."
else
    source venv/bin/activate
fi

echo " Starting server..."
echo " Open your browser and go to:  http://127.0.0.1:5000"
echo " Press Ctrl+C to stop the server."
echo ""
python3 app.py
