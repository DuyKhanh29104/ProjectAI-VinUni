#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Deploy a Git ref to the Label Guardian self-hosted VM.

This script packages a clean Git snapshot, syncs it to the VM deploy directory,
then builds, migrates, restarts and verifies the Docker Compose stack.

Usage:
  scripts/deploy_selfhost_vm.sh [git-ref]

Examples:
  scripts/deploy_selfhost_vm.sh origin/main
  scripts/deploy_selfhost_vm.sh main
  scripts/deploy_selfhost_vm.sh 03640122

Environment overrides:
  VM_HOST=label-guardian-vm
  VM_APP_DIR=/opt/label-guardian/app
  SELFHOST_ENV_FILE=/opt/label-guardian/.env.production
  SELFHOST_DATA_DIR=/opt/label-guardian/data
  SELFHOST_GCLOUD_CONFIG_DIR=/opt/label-guardian/gcloud
  IMAGE_TAG=vm-api
  APP_HEALTH_URL=https://api.labelguardian.space/health
  APP_READY_URL=https://api.labelguardian.space/ready
  APP_V1_HEALTH_URL=https://api.labelguardian.space/api/v1/health
  DEPLOY_HEALTH_ATTEMPTS=30
  DEPLOY_HEALTH_INTERVAL_SECONDS=2
  SKIP_MIGRATIONS=1
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

REF="${1:-origin/main}"
VM_HOST="${VM_HOST:-label-guardian-vm}"
VM_APP_DIR="${VM_APP_DIR:-/opt/label-guardian/app}"
SELFHOST_ENV_FILE="${SELFHOST_ENV_FILE:-/opt/label-guardian/.env.production}"
SELFHOST_DATA_DIR="${SELFHOST_DATA_DIR:-/opt/label-guardian/data}"
SELFHOST_GCLOUD_CONFIG_DIR="${SELFHOST_GCLOUD_CONFIG_DIR:-/opt/label-guardian/gcloud}"
IMAGE_TAG="${IMAGE_TAG:-vm-api}"
APP_HEALTH_URL="${APP_HEALTH_URL:-https://api.labelguardian.space/health}"
APP_READY_URL="${APP_READY_URL:-https://api.labelguardian.space/ready}"
APP_V1_HEALTH_URL="${APP_V1_HEALTH_URL:-https://api.labelguardian.space/api/v1/health}"
DEPLOY_HEALTH_ATTEMPTS="${DEPLOY_HEALTH_ATTEMPTS:-30}"
DEPLOY_HEALTH_INTERVAL_SECONDS="${DEPLOY_HEALTH_INTERVAL_SECONDS:-2}"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-0}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

if ! command -v ssh >/dev/null 2>&1; then
  echo "ssh is required" >&2
  exit 1
fi

if ! command -v scp >/dev/null 2>&1; then
  echo "scp is required" >&2
  exit 1
fi

git rev-parse --is-inside-work-tree >/dev/null
COMMIT_SHA="$(git rev-parse --verify "${REF}^{commit}")"
SHORT_SHA="$(git rev-parse --short "$COMMIT_SHA")"
ARCHIVE="/tmp/label-guardian-${SHORT_SHA}.tar.gz"

echo "Deploy ref: $REF"
echo "Commit: $COMMIT_SHA"
echo "VM host: $VM_HOST"
echo "VM app dir: $VM_APP_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  cat >&2 <<'WARNING'

Warning: local worktree has uncommitted or untracked files.
They will NOT be included unless they are committed into the selected Git ref.
Press Ctrl+C within 5 seconds to cancel.

WARNING
  sleep 5
fi

git archive --format=tar.gz --output="$ARCHIVE" "$COMMIT_SHA"

REMOTE_ARCHIVE="/tmp/label-guardian-${SHORT_SHA}.tar.gz"
REMOTE_RELEASE="/tmp/label-guardian-release-${SHORT_SHA}"

echo "Uploading archive..."
scp "$ARCHIVE" "${VM_HOST}:${REMOTE_ARCHIVE}"

echo "Syncing and restarting on VM..."
ssh "$VM_HOST" \
  "REMOTE_ARCHIVE='$REMOTE_ARCHIVE' \
   REMOTE_RELEASE='$REMOTE_RELEASE' \
   VM_APP_DIR='$VM_APP_DIR' \
   SELFHOST_ENV_FILE='$SELFHOST_ENV_FILE' \
   SELFHOST_DATA_DIR='$SELFHOST_DATA_DIR' \
   SELFHOST_GCLOUD_CONFIG_DIR='$SELFHOST_GCLOUD_CONFIG_DIR' \
   IMAGE_TAG='$IMAGE_TAG' \
   SHORT_SHA='$SHORT_SHA' \
   APP_HEALTH_URL='$APP_HEALTH_URL' \
   APP_READY_URL='$APP_READY_URL' \
   APP_V1_HEALTH_URL='$APP_V1_HEALTH_URL' \
   DEPLOY_HEALTH_ATTEMPTS='$DEPLOY_HEALTH_ATTEMPTS' \
   DEPLOY_HEALTH_INTERVAL_SECONDS='$DEPLOY_HEALTH_INTERVAL_SECONDS' \
   SKIP_MIGRATIONS='$SKIP_MIGRATIONS' \
   bash -s" <<'REMOTE'
set -euo pipefail

cleanup_release() {
  rm -rf "$REMOTE_RELEASE" "$REMOTE_ARCHIVE"
}
trap cleanup_release EXIT

rm -rf "$REMOTE_RELEASE"
mkdir -p "$REMOTE_RELEASE" "$VM_APP_DIR"
tar -xzf "$REMOTE_ARCHIVE" -C "$REMOTE_RELEASE"

rsync -a --delete \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.git' \
  --exclude 'data/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'node_modules/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  "$REMOTE_RELEASE"/ "$VM_APP_DIR"/

cd "$VM_APP_DIR"

export SELFHOST_ENV_FILE
export SELFHOST_DATA_DIR
export SELFHOST_GCLOUD_CONFIG_DIR
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"

STABLE_IMAGE_TAG="$IMAGE_TAG"
CANDIDATE_IMAGE_TAG="${STABLE_IMAGE_TAG}-${SHORT_SHA}"
PREVIOUS_IMAGE_TAG="${STABLE_IMAGE_TAG}-previous"
HAS_STABLE=0

if sudo docker image inspect "label-guardian-backend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1; then
  HAS_STABLE=1
  sudo docker tag "label-guardian-backend:${STABLE_IMAGE_TAG}" \
    "label-guardian-backend:${PREVIOUS_IMAGE_TAG}"
fi

wait_for_url() {
  local url="$1"
  local attempt
  for ((attempt = 1; attempt <= DEPLOY_HEALTH_ATTEMPTS; attempt++)); do
    if curl --fail --silent --show-error --max-time 10 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$DEPLOY_HEALTH_INTERVAL_SECONDS"
  done
  return 1
}

rollback_to_stable() {
  if [[ "$HAS_STABLE" != "1" ]]; then
    echo "No stable image exists; automatic rollback is unavailable." >&2
    return 1
  fi

  echo "Candidate failed. Restoring stable tag: ${STABLE_IMAGE_TAG}" >&2
  export IMAGE_TAG="$STABLE_IMAGE_TAG"
  sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
    -f docker-compose.selfhost.yml \
    --profile internet \
    up -d --remove-orphans --no-build backend proxy
}

echo "Building candidate tag: $CANDIDATE_IMAGE_TAG"
export IMAGE_TAG="$CANDIDATE_IMAGE_TAG"

sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
  -f docker-compose.selfhost.yml \
  build backend

if [[ "$SKIP_MIGRATIONS" != "1" ]]; then
  sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
    -f docker-compose.selfhost.yml \
    --profile migrate \
    run --rm backend-migrate
fi

if ! sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
  -f docker-compose.selfhost.yml \
  --profile internet \
  up -d --remove-orphans backend proxy; then
  rollback_to_stable || true
  exit 1
fi

if ! wait_for_url "$APP_HEALTH_URL" || ! wait_for_url "$APP_READY_URL" || ! wait_for_url "$APP_V1_HEALTH_URL"; then
  rollback_to_stable || true
  exit 1
fi

sudo docker tag "label-guardian-backend:${CANDIDATE_IMAGE_TAG}" \
  "label-guardian-backend:${STABLE_IMAGE_TAG}"
echo "Candidate healthy; promoted to stable tag: $STABLE_IMAGE_TAG"

sudo -E docker compose --env-file "$SELFHOST_ENV_FILE" \
  -f docker-compose.selfhost.yml \
  --profile internet \
  ps

REMOTE

echo "Verifying public endpoints..."
curl -f "$APP_HEALTH_URL"
echo
curl -f "$APP_READY_URL"
echo
curl -f "$APP_V1_HEALTH_URL"
echo
echo "Deploy complete: $SHORT_SHA"
