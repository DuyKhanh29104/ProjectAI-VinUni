#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Configure this deploy repo for the hybrid production topology:

  Vercel hosts frontend/
  VM hosts backend + Caddy API proxy

Run this inside the deploy repo.

Usage:
  scripts/configure_hybrid_deploy_repo.sh

Environment overrides:
  FRONTEND_DOMAIN=labelguardian.space
  API_DOMAIN=api.labelguardian.space
  DEPLOY_BRANCH=main
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
FRONTEND_DOMAIN="${FRONTEND_DOMAIN:-labelguardian.space}"
API_DOMAIN="${API_DOMAIN:-api.labelguardian.space}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

cd "$REPO_ROOT"

python - "$FRONTEND_DOMAIN" "$API_DOMAIN" "$DEPLOY_BRANCH" <<'PY'
from pathlib import Path
import sys

frontend_domain, api_domain, deploy_branch = sys.argv[1:4]


def rewrite(path: str, replacements: list[tuple[str, str]]) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
        elif new not in text:
            raise SystemExit(f"Expected text not found in {path}: {old!r}")
    file_path.write_text(text, encoding="utf-8")


rewrite(
    ".github/workflows/deploy-selfhost.yml",
    [
        ("branches: [develop]", f"branches: [{deploy_branch}]"),
        ("group: selfhost-deploy-develop", f"group: selfhost-deploy-{deploy_branch}"),
        ("APP_HEALTH_URL: https://labelguardian.space/healthz", f"APP_HEALTH_URL: https://{api_domain}/health"),
        ("APP_READY_URL: https://labelguardian.space/ready", f"APP_READY_URL: https://{api_domain}/ready"),
        (
            'if docker image inspect "label-guardian-backend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1 && \\\n'
            '             docker image inspect "label-guardian-frontend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1; then\n'
            '            docker tag "label-guardian-backend:${STABLE_IMAGE_TAG}" "label-guardian-backend:${STABLE_IMAGE_TAG}-previous"\n'
            '            docker tag "label-guardian-frontend:${STABLE_IMAGE_TAG}" "label-guardian-frontend:${STABLE_IMAGE_TAG}-previous"\n'
            "          fi",
            'if docker image inspect "label-guardian-backend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1; then\n'
            '            docker tag "label-guardian-backend:${STABLE_IMAGE_TAG}" "label-guardian-backend:${STABLE_IMAGE_TAG}-previous"\n'
            "          fi",
        ),
        ("Build candidate images", "Build candidate backend image"),
        ("docker compose --env-file \"$SELFHOST_ENV_FILE\" -f docker-compose.selfhost.yml build backend frontend", "docker compose --env-file \"$SELFHOST_ENV_FILE\" -f docker-compose.selfhost.yml build backend"),
        ("up -d --remove-orphans --no-build backend frontend proxy", "up -d --remove-orphans --no-build backend proxy"),
        ("up -d --remove-orphans backend frontend proxy", "up -d --remove-orphans backend proxy"),
        ('\n          docker tag "label-guardian-frontend:${IMAGE_TAG}" "label-guardian-frontend:${STABLE_IMAGE_TAG}"', ""),
    ],
)

rewrite("Caddyfile.selfhost", [("reverse_proxy frontend:80", "reverse_proxy backend:8000")])

rewrite(
    "docker-compose.selfhost.yml",
    [
        ("depends_on:\n      frontend:\n        condition: service_healthy", "depends_on:\n      backend:\n        condition: service_healthy"),
    ],
)

rewrite(
    "deploy/selfhost.env.example",
    [
        (
            "# Public HTTPS origin where users open the frontend. Required by production CORS validation.\n"
            "CORS_ORIGINS=https://label-guardian.example.com",
            "# Public HTTPS origins where users open the Vercel frontend. Required by production CORS validation.\n"
            f"CORS_ORIGINS=https://{frontend_domain},https://www.{frontend_domain}",
        ),
        (
            "# Public internet deployment. Point this domain's DNS A record to the server IP,\n"
            "# then run compose with --profile internet.\n"
            "PUBLIC_DOMAIN=label-guardian.example.com",
            "# Public backend API deployment. Point this domain's DNS A record to the server IP,\n"
            "# then run compose with --profile internet. The Caddy proxy forwards this host to FastAPI.\n"
            f"PUBLIC_DOMAIN={api_domain}",
        ),
    ],
)

rewrite(
    "deploy/vercel.env.example",
    [
        ("VITE_API_BASE_URL=https://<RAILWAY_PUBLIC_DOMAIN>", f"VITE_API_BASE_URL=https://{api_domain}"),
        ("VITE_DATASET_VERSION=v1.0-mini", "VITE_DATASET_VERSION=v1.0-trainval"),
    ],
)

rewrite(
    "scripts/deploy_selfhost_vm.sh",
    [
        ("APP_HEALTH_URL=https://labelguardian.space/healthz", f"APP_HEALTH_URL=https://{api_domain}/health"),
        ("APP_READY_URL=https://labelguardian.space/ready", f"APP_READY_URL=https://{api_domain}/ready"),
        (
            'APP_HEALTH_URL="${APP_HEALTH_URL:-https://labelguardian.space/healthz}"',
            f'APP_HEALTH_URL="${{APP_HEALTH_URL:-https://{api_domain}/health}}"',
        ),
        (
            'APP_READY_URL="${APP_READY_URL:-https://labelguardian.space/ready}"',
            f'APP_READY_URL="${{APP_READY_URL:-https://{api_domain}/ready}}"',
        ),
        (
            'if sudo docker image inspect "label-guardian-backend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1 &&\n'
            '   sudo docker image inspect "label-guardian-frontend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1; then\n'
            "  HAS_STABLE=1\n"
            '  sudo docker tag "label-guardian-backend:${STABLE_IMAGE_TAG}" \\\n'
            '    "label-guardian-backend:${PREVIOUS_IMAGE_TAG}"\n'
            '  sudo docker tag "label-guardian-frontend:${STABLE_IMAGE_TAG}" \\\n'
            '    "label-guardian-frontend:${PREVIOUS_IMAGE_TAG}"\n'
            "fi",
            'if sudo docker image inspect "label-guardian-backend:${STABLE_IMAGE_TAG}" >/dev/null 2>&1; then\n'
            "  HAS_STABLE=1\n"
            '  sudo docker tag "label-guardian-backend:${STABLE_IMAGE_TAG}" \\\n'
            '    "label-guardian-backend:${PREVIOUS_IMAGE_TAG}"\n'
            "fi",
        ),
        ("up -d --remove-orphans --no-build backend frontend proxy", "up -d --remove-orphans --no-build backend proxy"),
        ("build backend frontend", "build backend"),
        ("up -d --remove-orphans backend frontend proxy", "up -d --remove-orphans backend proxy"),
        (
            'sudo docker tag "label-guardian-backend:${CANDIDATE_IMAGE_TAG}" \\\n'
            '  "label-guardian-backend:${STABLE_IMAGE_TAG}"\n'
            'sudo docker tag "label-guardian-frontend:${CANDIDATE_IMAGE_TAG}" \\\n'
            '  "label-guardian-frontend:${STABLE_IMAGE_TAG}"',
            'sudo docker tag "label-guardian-backend:${CANDIDATE_IMAGE_TAG}" \\\n'
            '  "label-guardian-backend:${STABLE_IMAGE_TAG}"',
        ),
    ],
)
PY

echo "Hybrid deploy repo configuration applied."
echo "Review changes, then commit in the deploy repo."
