#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Sync the current deployed source snapshot from the Label Guardian VM to local.

This is intended for inspection, recovery, or comparing what is currently on the
VM. Normal development should still happen through Git branches.

Usage:
  scripts/sync_selfhost_vm_from_vm.sh [target-dir]

Examples:
  scripts/sync_selfhost_vm_from_vm.sh
  scripts/sync_selfhost_vm_from_vm.sh ../label-guardian-vm-snapshot
  DELETE_EXTRA=1 scripts/sync_selfhost_vm_from_vm.sh ../label-guardian-vm-snapshot

Dangerous overwrite mode:
  ALLOW_CURRENT_REPO_OVERWRITE=1 scripts/sync_selfhost_vm_from_vm.sh .

Environment overrides:
  VM_HOST=label-guardian-vm
  VM_APP_DIR=/home/hung8uandj/P-209-develop
  DELETE_EXTRA=1
  DRY_RUN=1
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

VM_HOST="${VM_HOST:-label-guardian-vm}"
VM_APP_DIR="${VM_APP_DIR:-/home/hung8uandj/P-209-develop}"
TARGET_DIR="${1:-../label-guardian-vm-snapshot}"
DELETE_EXTRA="${DELETE_EXTRA:-0}"
DRY_RUN="${DRY_RUN:-0}"
ALLOW_CURRENT_REPO_OVERWRITE="${ALLOW_CURRENT_REPO_OVERWRITE:-0}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required" >&2
  exit 1
fi

if ! command -v ssh >/dev/null 2>&1; then
  echo "ssh is required" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
TARGET_ABS="$(cd "$TARGET_DIR" && pwd)"
CURRENT_REPO_ROOT=""

if git rev-parse --show-toplevel >/dev/null 2>&1; then
  CURRENT_REPO_ROOT="$(git rev-parse --show-toplevel)"
fi

if [[ -n "$CURRENT_REPO_ROOT" && "$TARGET_ABS" == "$CURRENT_REPO_ROOT" && "$ALLOW_CURRENT_REPO_OVERWRITE" != "1" ]]; then
  cat >&2 <<'ERROR'
Refusing to sync VM files directly into the current Git repo.

Use a snapshot directory instead:
  scripts/sync_selfhost_vm_from_vm.sh ../label-guardian-vm-snapshot

If you really need to overwrite the current repo, run:
  ALLOW_CURRENT_REPO_OVERWRITE=1 scripts/sync_selfhost_vm_from_vm.sh .
ERROR
  exit 1
fi

if [[ -n "$CURRENT_REPO_ROOT" && "$TARGET_ABS" == "$CURRENT_REPO_ROOT" && -n "$(git status --porcelain)" ]]; then
  cat >&2 <<'ERROR'
Current Git repo has local changes. Refusing to overwrite it from VM.

Commit, stash, or use a separate snapshot directory first.
ERROR
  exit 1
fi

RSYNC_ARGS=(-az --human-readable --itemize-changes)

if [[ "$DELETE_EXTRA" == "1" ]]; then
  RSYNC_ARGS+=(--delete)
fi

if [[ "$DRY_RUN" == "1" ]]; then
  RSYNC_ARGS+=(--dry-run)
fi

RSYNC_ARGS+=(
  --exclude '.env'
  --exclude '.env.*'
  --exclude '.git'
  --exclude 'data/'
  --exclude 'frontend/node_modules/'
  --exclude 'node_modules/'
  --exclude '.venv/'
  --exclude '__pycache__/'
  --exclude '.pytest_cache/'
  --exclude '.ruff_cache/'
  --exclude '.mypy_cache/'
  --exclude 'label_guardian.egg-info/'
)

echo "VM host: $VM_HOST"
echo "VM app dir: $VM_APP_DIR"
echo "Target dir: $TARGET_ABS"
echo "Delete extra local files: $DELETE_EXTRA"
echo "Dry run: $DRY_RUN"

rsync "${RSYNC_ARGS[@]}" "${VM_HOST}:${VM_APP_DIR}/" "${TARGET_ABS}/"

echo "Sync complete: $TARGET_ABS"
