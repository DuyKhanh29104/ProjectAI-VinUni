#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Publish the current Label Guardian worktree into a separate deploy mirror repo.

Use this when the primary repository cannot be read by third-party deploy
platforms. The deploy mirror can be connected to Vercel and to the VM
self-hosted runner.

Usage:
  scripts/publish_deploy_mirror.sh [target-dir]

Examples:
  DEPLOY_REMOTE_URL=git@github.com:<ORG>/label-guardian-deploy.git \
    scripts/publish_deploy_mirror.sh ../label-guardian-deploy

  PUSH_DEPLOY_MIRROR=0 scripts/publish_deploy_mirror.sh ../label-guardian-deploy

Environment overrides:
  DEPLOY_REMOTE_URL=git@github.com:<ORG>/<REPO>.git
  DEPLOY_BRANCH=main
  PUSH_DEPLOY_MIRROR=1
  COMMIT_MESSAGE="deploy mirror: update from source <sha>"
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

SOURCE_ROOT="$(git rev-parse --show-toplevel)"
SOURCE_SHA="$(git -C "$SOURCE_ROOT" rev-parse --short HEAD)"
TARGET_DIR="${1:-../label-guardian-deploy}"
DEPLOY_REMOTE_URL="${DEPLOY_REMOTE_URL:-}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PUSH_DEPLOY_MIRROR="${PUSH_DEPLOY_MIRROR:-1}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-deploy mirror: update from source ${SOURCE_SHA}}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
TARGET_ROOT="$(cd "$TARGET_DIR" && pwd)"

if [[ "$TARGET_ROOT" == "$SOURCE_ROOT" ]]; then
  echo "Refusing to publish deploy mirror into the source repository." >&2
  exit 1
fi

if [[ "$TARGET_ROOT" == "$SOURCE_ROOT"/* ]]; then
  echo "Refusing to publish deploy mirror inside the source repository." >&2
  exit 1
fi

if [[ -n "$(git -C "$SOURCE_ROOT" status --porcelain)" ]]; then
  cat >&2 <<WARNING
Warning: source worktree has uncommitted changes.
They WILL be copied to the deploy mirror.

WARNING
fi

if [[ ! -d "$TARGET_ROOT/.git" ]]; then
  git -C "$TARGET_ROOT" init
fi

git -C "$TARGET_ROOT" checkout -B "$DEPLOY_BRANCH"

if [[ -n "$DEPLOY_REMOTE_URL" ]]; then
  if git -C "$TARGET_ROOT" remote get-url origin >/dev/null 2>&1; then
    git -C "$TARGET_ROOT" remote set-url origin "$DEPLOY_REMOTE_URL"
  else
    git -C "$TARGET_ROOT" remote add origin "$DEPLOY_REMOTE_URL"
  fi
fi

rsync -a --delete \
  --exclude '.git' \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'data/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'node_modules/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.mypy_cache/' \
  --exclude 'label_guardian.egg-info/' \
  --exclude '*.pyc' \
  "$SOURCE_ROOT"/ "$TARGET_ROOT"/

git -C "$TARGET_ROOT" add -A

if git -C "$TARGET_ROOT" diff --cached --quiet; then
  echo "Deploy mirror is already up to date: $TARGET_ROOT"
else
  git -C "$TARGET_ROOT" commit -m "$COMMIT_MESSAGE"
fi

if [[ "$PUSH_DEPLOY_MIRROR" == "1" ]]; then
  if ! git -C "$TARGET_ROOT" remote get-url origin >/dev/null 2>&1; then
    echo "No origin remote configured. Set DEPLOY_REMOTE_URL or push manually from $TARGET_ROOT." >&2
    exit 1
  fi
  git -C "$TARGET_ROOT" push -u origin "$DEPLOY_BRANCH"
fi

echo "Deploy mirror ready: $TARGET_ROOT"
