# Self-hosted Deployment

This path self-hosts the backend and HTTPS API proxy. The public frontend is
deployed separately on Vercel; repository secrets and backend credentials stay
on the VM. GitHub Actions schedules work on the self-hosted runner, which builds
and runs the backend containers on the same machine.

## Server Contract

Install these on the self-hosted server:

- Docker Engine with Compose v2.
- A GitHub Actions self-hosted runner with labels `self-hosted`, `linux`, `x64`.
- Network access from the server to Supabase PostgreSQL and the private GCS
  bucket.
- Firewall access for the API proxy on TCP ports `80` and `443` when using the
  `internet` profile.

Create the runtime directory:

```bash
sudo mkdir -p /opt/label-guardian/data /opt/label-guardian/secrets /opt/label-guardian/gcloud
sudo chown -R "$USER":"$USER" /opt/label-guardian
```

Copy [deploy/selfhost.env.example](../deploy/selfhost.env.example) to:

```bash
/opt/label-guardian/.env.production
```

Fill the real values there. Do not commit this file. The most important values
are:

- `DATABASE_URL`
- `LABEL_GUARDIAN_DATABASE_URL`
- `SUPABASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `AUTH_BOOTSTRAP_ADMIN_EMAILS`
- `CORS_ORIGINS`
- `LABEL_GUARDIAN_GCS_BUCKET`
- `LABEL_GUARDIAN_GCS_PROJECT`
- one GCS credential mechanism. Prefer keyless ADC mounted from
  `/opt/label-guardian/gcloud`; use `LABEL_GUARDIAN_GCS_CREDENTIALS_PATH` only
  when service account key creation is allowed.

When service account key creation is blocked by organization policy, create
Application Default Credentials on the runner and store them in the mounted
directory:

```bash
export CLOUDSDK_CONFIG=/opt/label-guardian/gcloud
gcloud auth application-default login
gcloud config set project ai-lab-16-gcp-505508
```

Leave `LABEL_GUARDIAN_GCS_CREDENTIALS_PATH` and
`LABEL_GUARDIAN_GCS_CREDENTIALS_JSON` unset in `/opt/label-guardian/.env.production`.

## Deploy From CI/CD

The workflow [.github/workflows/deploy-selfhost.yml](../.github/workflows/deploy-selfhost.yml)
runs on pushes to `main` and can also be started manually.

It performs:

1. Validate `/opt/label-guardian/.env.production`.
2. Build the backend Docker image locally.
3. Run `alembic upgrade head` once.
4. Start `backend` and `proxy` via
   [docker-compose.selfhost.yml](../docker-compose.selfhost.yml).
5. Check `/health`, `/ready`, and `/api/v1/health` through the API proxy.

## Manual Deploy

From a checked-out copy of the repository on the server:

```bash
export SELFHOST_ENV_FILE=/opt/label-guardian/.env.production
export SELFHOST_DATA_DIR=/opt/label-guardian/data
export IMAGE_TAG="$(git rev-parse --short HEAD)"

docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml config --quiet
docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml build backend
docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml --profile migrate run --rm backend-migrate
docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml up -d --remove-orphans backend
docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml ps
```

## Internet HTTPS

For a real public deployment, point a DNS `A` record to the self-hosted server:

```text
api.labelguardian.space -> 34.143.247.68
```

Open inbound TCP ports `80` and `443` on the server firewall/router. Then set:

```env
APP_ENV=production
PUBLIC_DOMAIN=api.labelguardian.space
ACME_EMAIL=admin@example.com
CORS_ORIGINS=https://labelguardian.space,https://www.labelguardian.space
```

For Supabase Auth, add the same URL in Supabase Dashboard:

```text
Authentication -> URL Configuration
Site URL: https://labelguardian.space
Redirect URLs:
https://labelguardian.space
https://www.labelguardian.space
https://labelguardian.space/*
https://www.labelguardian.space/*
```

Deploy with the internet proxy profile:

```bash
docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml --profile migrate run --rm backend-migrate
docker compose --env-file "$SELFHOST_ENV_FILE" -f docker-compose.selfhost.yml --profile internet up -d --remove-orphans backend proxy
```

Caddy obtains and renews Let's Encrypt certificates automatically. Check it with:

```bash
curl -f https://api.labelguardian.space/health
curl -f https://api.labelguardian.space/ready
curl -f https://api.labelguardian.space/api/v1/health
```

## Safe Deploy and Automatic Rollback

Both the self-hosted workflow and `scripts/deploy_selfhost_vm.sh` build a unique
candidate image without changing the running stable image. The candidate replaces
the containers only after the build and migration steps succeed. `/health`,
`/ready`, and `/api/v1/health` must then pass before the candidate is promoted
to `vm-api`.

If container startup or any health check fails, Compose recreates backend from
`vm-api`. The prior stable image is also retained under `vm-api-previous` for
manual recovery. A failed image build does not touch the running containers.

Database rollback is intentionally not automatic. Production migrations must use
an expand/contract sequence and remain compatible with both the old and new app
versions; do not drop or rename a column in the same deployment that stops using it.

## Stop and Start the VM

Docker and the application containers are configured to start after a VM reboot:
Docker must be enabled in systemd and the long-running Compose services use
`restart: unless-stopped`.

Verify the one-time host setup:

```bash
sudo systemctl enable --now docker
sudo systemctl is-enabled docker
sudo docker compose --env-file /opt/label-guardian/.env.production \
  -f docker-compose.selfhost.yml --profile internet ps
```

To save cost, stop and start the VM itself. Do not run `docker compose stop` first,
because containers stopped explicitly under `unless-stopped` stay stopped after
Docker restarts.

```bash
gcloud compute instances stop VM_NAME --zone ZONE
gcloud compute instances start VM_NAME --zone ZONE
```

After start, Docker recreates the previous running state without rebuilding or
redownloading dependencies. Verify readiness with:

```bash
curl --retry 30 --retry-delay 2 --retry-connrefused -f \
  https://api.labelguardian.space/ready
```

## Logs

```bash
docker compose --env-file /opt/label-guardian/.env.production -f docker-compose.selfhost.yml logs -f backend
docker compose --env-file /opt/label-guardian/.env.production -f docker-compose.selfhost.yml --profile internet logs -f proxy
```

## Dataset Behavior

The backend is configured for `DATASET_BACKEND=database` in production. It reads
Supabase metadata and streams private GCS images through `/api/v1`. The local
mounted data directory is still available as `/app/data`, so the official product
cache can act as fallback while full KITTI/nuScenes ingestion catches up.
