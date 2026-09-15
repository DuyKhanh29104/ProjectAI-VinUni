# Hybrid Deployment: Vercel Frontend + VM Backend

> Cập nhật: 2026-08-27

This guide is the production deployment path for the public Label Guardian
deploy repository.

`railway.json` is retained only as a legacy deployment artifact. Railway is not
part of the current production topology and must not be used as the source of
truth for health checks, migrations or runtime environment variables.

## Target Architecture

```text
github.com/8uandj/Label_guardian
  -> Vercel deploys frontend/
  -> GCP VM self-hosted runner deploys backend + Caddy API proxy
```

Public domains:

```text
labelguardian.space       -> Vercel frontend
www.labelguardian.space   -> Vercel frontend
api.labelguardian.space   -> GCP VM backend API
```

The VM remains responsible for FastAPI, YOLO/agent runtime, GCS access, dataset
cache and database migrations. Vercel only receives build-time public frontend
variables.

## Quick Runbook

Run these steps in order from the deploy repository:

```bash
git remote -v
git branch --show-current
cd frontend
npm ci
npm run build
cd ..
git add -A
git commit -m "configure hybrid Vercel frontend and VM backend deploy"
git push origin main
```

Connect `8uandj/Label_guardian` to Vercel with root directory `frontend`, then
install a GitHub self-hosted runner for the same repository on the VM.

After this, `push main` on the deploy repository deploys the frontend through
Vercel and the backend through the VM runner.

## 1. Keep Secrets Out Of Git

Never commit local secrets or runtime data:

```text
.env
.env.*
/data
/frontend/node_modules
/node_modules
/.venv
cache/
```

Recommended workflow for production changes:

```text
feature branch or local fix
  -> reviewed merge/commit
  -> push to main in 8uandj/Label_guardian
  -> Vercel and VM runner deploy from main
```

Do not edit production code directly on the VM. The VM should be runtime plus
CI runner, not the source of truth.

## 2. Configure Vercel Frontend

Import the deploy repository into Vercel.

Project settings:

```text
Framework Preset: Vite
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
Production Branch: main
```

Environment variables:

```env
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=https://api.labelguardian.space
VITE_DATASET_ID=nuscenes
VITE_DATASET_NAME=nuScenes cloud dataset
VITE_DATASET_FORMAT=nuScenes
VITE_DATASET_VERSION=v1.0-trainval
VITE_AUTH_MODE=supabase
VITE_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
VITE_SUPABASE_ANON_KEY=<SUPABASE_PUBLISHABLE_OR_ANON_KEY>
```

These values are public in the browser bundle. Do not put database URLs, GCS
credentials, JWT secrets or LLM keys in Vercel.

## 3. Configure DNS

In Namecheap Advanced DNS:

```text
A      @      <Vercel apex IP or Vercel-provided record>
CNAME  www    <Vercel-provided cname>
A      api    34.143.247.68
```

Use the exact records Vercel shows for `labelguardian.space` and
`www.labelguardian.space`. Keep `api.labelguardian.space` pointed to the VM.

## 4. Configure Backend Environment On VM

Edit:

```bash
sudo nano /opt/label-guardian/.env.production
```

Required public-facing values:

```env
APP_ENV=production
AUTH_ENABLED=true
CORS_ORIGINS=https://labelguardian.space,https://www.labelguardian.space
PUBLIC_DOMAIN=api.labelguardian.space
ACME_EMAIL=<TEAM_EMAIL>

DATASET_BACKEND=database
DATASET_ID=nuscenes
DATASET_VERSION=v1.0-trainval
DATASET_DEFAULT_SPLIT=trainval-full

SELFHOST_ENV_FILE=/opt/label-guardian/.env.production
SELFHOST_DATA_DIR=/opt/label-guardian/data
SELFHOST_GCLOUD_CONFIG_DIR=/opt/label-guardian/gcloud
```

Keep Supabase, database, GCS and LLM credentials only in this VM file.

## 5. Install GitHub Self-Hosted Runner On VM

In the deploy repository, open:

```text
Settings -> Actions -> Runners -> New self-hosted runner
```

Choose Linux x64 and run the commands GitHub provides on the VM.

Recommended runner directory:

```bash
mkdir -p ~/actions-runner
cd ~/actions-runner
```

After configuration, install it as a service:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

The workflow in `.github/workflows/deploy-selfhost.yml` runs on:

```yaml
runs-on: [self-hosted, linux, x64]
```

## 6. Backend Deploy Flow

On every push to `main`, the self-hosted workflow:

- checks `/opt/label-guardian/.env.production`;
- builds the backend candidate image;
- applies Alembic migrations;
- starts `backend` and `proxy` with Docker Compose;
- verifies `https://api.labelguardian.space/health`, `/ready`, and `/api/v1/health`;
- promotes the candidate image to the stable `vm-api` tag.

Manual fallback from a local machine:

```bash
scripts/deploy_selfhost_vm.sh origin/main
```

## 7. Supabase Auth Settings

Add frontend URLs in Supabase Auth:

```text
Site URL: https://labelguardian.space

Additional Redirect URLs:
https://labelguardian.space
https://www.labelguardian.space
https://labelguardian.space/*
https://www.labelguardian.space/*
```

Do not use `api.labelguardian.space` as a login redirect target; it is only the
backend API origin.

## 8. Smoke Checks

Frontend:

```bash
curl -I https://labelguardian.space
```

Backend:

```bash
curl -f https://api.labelguardian.space/health
curl -f https://api.labelguardian.space/ready
curl -f https://api.labelguardian.space/api/v1/health
```

VM logs:

```bash
ssh label-guardian-vm
cd /opt/label-guardian/app
sudo docker compose --env-file /opt/label-guardian/.env.production -f docker-compose.selfhost.yml logs -f backend
sudo docker compose --env-file /opt/label-guardian/.env.production -f docker-compose.selfhost.yml logs -f proxy
```

## Conflict Avoidance

- The deploy mirror `main` branch is the only production source.
- VM edits are temporary debugging only; move them back to Git before deploy.
- `.env.production`, GCS ADC config and dataset cache live on the VM, outside Git.
- Vercel has only frontend public variables.
- Backend migrations should be backward-compatible because rollback only restores
  containers, not database schema.
