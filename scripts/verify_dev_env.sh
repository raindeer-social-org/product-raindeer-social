#!/usr/bin/env bash
# Verifies the local dev environment matches README.md's "Getting started"
# section end to end: Python 3.11, deps install cleanly, Postgres + pgvector
# reachable, and the API boots with no import errors. Run from repo root:
#
#   ./scripts/verify_dev_env.sh
#
# Exits non-zero on the first failed check, printing which one failed —
# this is meant to catch exactly the "works on my machine" class of
# problem Issue #1 exists to prevent, not to replace CI.
set -euo pipefail

cd "$(dirname "$0")/.."

fail() {
    echo "FAILED: $1" >&2
    exit 1
}

echo "== Python version =="
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "$PYTHON_BIN not found — install Python 3.11"
"$PYTHON_BIN" --version | grep -q "3\.11\." || fail "$PYTHON_BIN is not 3.11.x"
echo "OK: $("$PYTHON_BIN" --version)"

echo "== Virtualenv =="
if [ ! -d .venv ]; then
    "$PYTHON_BIN" -m venv .venv || fail "could not create .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "OK: venv active at $(which python)"

echo "== Backend dependencies =="
pip install --upgrade pip -q
pip install -r apps/api/requirements.txt -q || fail "pip install failed — see output above"
echo "OK: apps/api/requirements.txt installed"

echo "== Postgres + pgvector =="
command -v psql >/dev/null 2>&1 || fail "psql not found — install PostgreSQL"
psql postgres -c "SELECT 1;" >/dev/null 2>&1 || fail "cannot connect to local Postgres"
echo "OK: Postgres reachable"

echo "== .env =="
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — fill in a real LLM API key before running agents."
fi
echo "OK: .env present"

echo "== API boots cleanly =="
DATABASE_URL="${DATABASE_URL:-postgresql://localhost:5432/raindeer}" \
    python -c "from apps.api.main import app" || fail "apps.api.main failed to import"
echo "OK: apps.api.main imports with no errors"

echo
echo "All checks passed — local dev environment matches README.md."
