#!/bin/bash
# Crypto Trading Bot Launcher
# Usage:
#   ./run.sh              # Paper trading (default)
#   ./run.sh paper        # Paper trading
#   ./run.sh live         # Live trading
#   ./run.sh report       # Show report
#   ./run.sh test         # Test connectivity

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$DIR/venv/bin/python3"

if [ ! -f "$PYTHON" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt"
fi

case "${1:-paper}" in
    paper)
        "$PYTHON" "$DIR/web_dashboard.py" &
        DASH_PID=$!
        trap "kill $DASH_PID 2>/dev/null" EXIT
        "$PYTHON" "$DIR/main.py" --mode paper
        ;;
    live)
        "$PYTHON" "$DIR/web_dashboard.py" &
        DASH_PID=$!
        trap "kill $DASH_PID 2>/dev/null" EXIT
        "$PYTHON" "$DIR/main.py" --mode live ${2:+--leverage $2}
        ;;
    report) "$PYTHON" "$DIR/main.py" --report ;;
    test)   "$PYTHON" "$DIR/main.py" --test ;;
    web)    "$PYTHON" "$DIR/web_dashboard.py" ;;
    *)      "$PYTHON" "$DIR/main.py" "$@" ;;
esac
