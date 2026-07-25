#!/usr/bin/env bash
# TeleDecision Orchestrator -- local setup and run script.
#
# Usage:
#   ./run.sh              install deps, then start the API with reload (test suite SKIPPED for now -- see --with-tests)
#   ./run.sh --with-tests  install deps, run the test suite, then start the API (the old default -- re-enable any time)
#   ./run.sh --test-only   install deps and run the test suite only (no server)
#   ./run.sh --no-install  skip dependency install (venv already set up)
#   ./run.sh --port 9000   run the server on a custom port (default 8000)
#
# Run this from the project root (the folder containing app/, tests/, requirements.txt).

set -euo pipefail

PORT=8000
TEST_ONLY=false
SKIP_INSTALL=false
RUN_TESTS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --test-only) TEST_ONLY=true; RUN_TESTS=true; shift ;;
    --with-tests) RUN_TESTS=true; shift ;;
    --no-install) SKIP_INSTALL=true; shift ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -f "requirements.txt" || ! -d "app" ]]; then
  echo "Run this from the project root (the folder with app/, tests/, requirements.txt)." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ first." >&2
  exit 1
fi

activate_virtualenv() {
  if [[ -f ".venv/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/Scripts/activate"
  elif [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
  else
    echo "No virtualenv activation script found; continuing with the current Python." >&2
  fi
}

resolve_python_bin() {
  if [[ -x ".venv/Scripts/python.exe" ]]; then
    echo ".venv/Scripts/python.exe"
  elif [[ -x ".venv/Scripts/python" ]]; then
    echo ".venv/Scripts/python"
  elif [[ -x ".venv/bin/python" ]]; then
    echo ".venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    echo "python3"
  elif command -v python >/dev/null 2>&1; then
    echo "python"
  else
    echo ""
  fi
}

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Using python3 ($PY_VERSION)"

if [[ "$SKIP_INSTALL" == false ]]; then
  if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment in .venv/ ..."
    python3 -m venv .venv
  fi
  activate_virtualenv
  PYTHON_BIN=$(resolve_python_bin)
  if [[ -n "$PYTHON_BIN" ]]; then
    echo "Using $PYTHON_BIN"
    "$PYTHON_BIN" -m pip install --quiet --upgrade pip
    "$PYTHON_BIN" -m pip install --quiet -r requirements.txt
  else
    echo "Python interpreter not found." >&2
    exit 1
  fi
else
  if [[ -d ".venv" ]]; then
    activate_virtualenv
  fi
fi

PYTHON_BIN=$(resolve_python_bin)
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python interpreter not found." >&2
  exit 1
fi

if [[ "$RUN_TESTS" == true ]]; then
  echo ""
  echo "Running test suite ..."
  "$PYTHON_BIN" -m pytest tests/ -v
  echo ""
  echo "Test suite passed."
else
  echo ""
  echo "Skipping test suite (run with --with-tests to enable)."
fi

if [[ "$TEST_ONLY" == true ]]; then
  exit 0
fi

echo ""
echo "Starting the API on http://127.0.0.1:${PORT}"
echo "  Interactive docs: http://127.0.0.1:${PORT}/docs"
echo "  Health check:     http://127.0.0.1:${PORT}/health"
echo "  Press Ctrl+C to stop."
echo ""
exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --port "${PORT}"
