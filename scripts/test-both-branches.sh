#!/usr/bin/env bash
#
# Run the test suite against BOTH branches (main + current) and print a
# clear verdict. Non-destructive: uses a temporary git worktree so the
# primary checkout, index, and untracked files are never touched.
#
# Exit 0 iff both runs pass. Designed for CI and pre-push hooks.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
CURRENT_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
WORKTREE_DIR="$(mktemp -d -t cbl-main.XXXXXX)"

cleanup() {
  git -C "$ROOT" worktree remove --force "$WORKTREE_DIR" >/dev/null 2>&1 || true
  rm -rf "$WORKTREE_DIR"
}
trap cleanup EXIT

if [[ ! -x "$VENV_PY" ]]; then
  echo "error: expected venv at $VENV_PY — run 'python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest'" >&2
  exit 2
fi

run_suite() {
  local label="$1"
  local workdir="$2"
  echo
  echo "────────────────────────────────────────────────────────────────"
  echo "  $label"
  echo "────────────────────────────────────────────────────────────────"
  ( cd "$workdir" && "$VENV_PY" -m pytest tests/ -q --rootdir="$workdir" )
}

# 1) current branch — tests already live here
run_suite "Running on current branch: $CURRENT_BRANCH" "$ROOT"
CURRENT_RC=$?

# 2) main — check out into a fresh worktree and copy tests/ in
git -C "$ROOT" worktree add "$WORKTREE_DIR" "$MAIN_BRANCH" >/dev/null
cp -r "$ROOT/tests" "$WORKTREE_DIR/tests"

set +e
run_suite "Running on $MAIN_BRANCH branch (via worktree)" "$WORKTREE_DIR"
MAIN_RC=$?
set -e

echo
echo "════════════════════════════════════════════════════════════════"
if [[ "$CURRENT_RC" -eq 0 && "$MAIN_RC" -eq 0 ]]; then
  echo "  VERDICT: PASS — contract holds on both $CURRENT_BRANCH and $MAIN_BRANCH"
  exit 0
else
  echo "  VERDICT: FAIL"
  echo "    $CURRENT_BRANCH : rc=$CURRENT_RC"
  echo "    $MAIN_BRANCH    : rc=$MAIN_RC"
  exit 1
fi
