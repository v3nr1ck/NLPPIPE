#!/bin/bash
# =============================================================================
#  CMMS NLP Pipeline — macOS Launcher
#  Double-click this file in Finder to launch the interactive demo.
#  First run: sets up Python venv + installs dependencies (~30 seconds)
#  Subsequent runs: instant
#
#  If macOS blocks it on first run:
#    Right-click → Open  (or run: chmod +x launch.command)
# =============================================================================
set -e
cd "$(dirname "$0")"

echo ""
echo "  🐶 CMMS NLP Pipeline — v1.1.0"
echo "  ========================================"
echo ""

# ── Check Python ──────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "  [ERROR] Python 3 not found!"
    echo ""
    echo "  Install via: brew install python"
    echo "  Or download from: https://python.org"
    echo ""
    exit 1
fi

python3 --version
echo ""

# ── Create venv if needed ─────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "  [1/3] Creating virtual environment..."
    python3 -m venv venv
else
    echo "  [1/3] Virtual environment found (skip)"
fi

# ── Install deps ──────────────────────────────────────────────────
echo "  [2/3] Installing dependencies..."
source venv/bin/activate
pip install -q pydantic streamlit

# ── Launch ────────────────────────────────────────────────────────
echo "  [3/3] Launching dashboard..."
echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║  Opening http://localhost:8501 in your browser  ║"
echo "  ║  Press Ctrl+C here to stop the server          ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""

sleep 2
open http://localhost:8501 2>/dev/null || true
streamlit run dashboard.py --server.headless true
