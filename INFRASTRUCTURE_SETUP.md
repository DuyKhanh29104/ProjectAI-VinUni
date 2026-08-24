# Infrastructure Setup on Another Machine

This runbook reproduces the current Label Guardian infrastructure on another
development or private staging machine. The recommended path uses Docker Compose
for PostgreSQL and the FastAPI backend.

This document covers the local PostgreSQL topology. Developers connecting the
backend to the shared Supabase database should follow
[docs/SUPABASE_DEVELOPMENT.md](./docs/SUPABASE_DEVELOPMENT.md) instead; the local
backup, restore, and `psql` commands below do not operate on Supabase.

## What this deployment includes

| Component | Compose service | Address from the host | Persistent storage |
| --- | --- | --- | --- |
| PostgreSQL 16 | `postgres` | `localhost:${POSTGRES_PORT}` (default `5432`) | Named volume `postgres_data` |
| FastAPI backend | `backend` | `http://localhost:8000` | Host directory `./data` mounted at `/app/data` |

The backend waits for PostgreSQL, runs `alembic upgrade head`, and then starts
Uvicorn. The current Alembic head is `cceb13cd2021`.

With `COMPOSE_PROJECT_NAME=label_guardian`, Docker creates the physical volume as
`label_guardian_postgres_data`. Keep the project name stable or Compose will
select a different volume and the database can appear empty.

This Compose stack does **not** deploy the frontend, CVAT, MinIO, an ingestion
worker, Redis, Celery, TLS, or an authentication layer. Do not expose it directly
to the public internet. See [CLOUD_DEPLOYMENT.md](./docs/CLOUD_DEPLOYMENT.md) for the
split cloud topology.

This is a source-level recreation for development/private staging, not a
bit-for-bit reproducible production release. The current base image tags
(`python:3.12-slim`, `postgres:16-alpine`) and Python dependency ranges can move.
For strict releases, pin image digests and dependency versions or publish one
immutable backend image tagged with the Git SHA.

## 1. Release the exact source from the current machine

Migration files are application source code. They must be transferred with the
same Git commit as the models and backend; do not regenerate migration IDs on the
target machine.

Before cloning elsewhere, run these checks on the source machine:

```powershell
git status --short
git diff --check
git ls-files --error-unmatch migrations/versions/8f3a2c7d91e4_add_qa_image_source_metadata.py
git ls-files --error-unmatch migrations/versions/cceb13cd2021_make_ingestion_schema_postgresql_.py
.\.venv\Scripts\python.exe -m alembic heads
git rev-parse HEAD
```

On Linux/macOS, use `.venv/bin/python -m alembic heads` for the Alembic check.

If either tracked-file check fails, review the working tree and commit all intended
infrastructure and migration changes—including this runbook—before continuing. A
local Docker image can contain untracked files even though a fresh Git clone
cannot.

Record the final commit SHA. The source and target machines must report the same
SHA:

```powershell
git rev-parse HEAD
```

Do not transfer `.env` through Git. If existing database rows or local datasets
must move too, follow [Moving existing data](#7-moving-existing-data).

## 2. Prepare the target machine

Install:

- Git.
- Docker Desktop on Windows/macOS, or Docker Engine with Docker Compose v2 on
  Linux.
- Enough disk space for Docker images, the PostgreSQL volume, `./data`, and
  backups.

Python is not required for the all-Compose setup. Node.js 20.19+ or 22.12+ and
npm are required only for the optional frontend; Node.js 24 is recommended.

Confirm Docker is running:

```text
docker version
docker compose version
```

Before startup, choose a network posture. Compose binds PostgreSQL and the backend
to `127.0.0.1` by default. Keep those defaults for local development and for a
server behind a same-host reverse proxy. If remote access is required, change the
appropriate bind address intentionally and enforce access in the host or cloud
firewall before startup. PostgreSQL must never be public. Put a TLS reverse proxy,
authenticated gateway, or private VPN in front of the API; the application does
not yet provide production authentication/RBAC. Verify listening interfaces after
startup with `Get-NetTCPConnection` on Windows, `ss -lnt` on Linux, or
`lsof -nP -iTCP -sTCP:LISTEN` on macOS.

## 3. Clone the released revision

PowerShell (replace `RELEASE_COMMIT_SHA` with the recorded full SHA):

```powershell
git clone --branch develop https://github.com/AI20K-Build-Phase-Cohort-3/P-209.git label-guardian
Set-Location label-guardian
git checkout --detach RELEASE_COMMIT_SHA
git rev-parse HEAD
```

Linux/macOS (replace `RELEASE_COMMIT_SHA` with the recorded full SHA):

```bash
git clone --branch develop https://github.com/AI20K-Build-Phase-Cohort-3/P-209.git label-guardian
cd label-guardian
git checkout --detach RELEASE_COMMIT_SHA
git rev-parse HEAD
```

Verify that the printed SHA matches the recorded release SHA. If deploying a
specific tag or commit, check it out before creating any containers.

Also verify that Alembic sees the expected migration:

```text
git ls-files migrations/versions
```

Both `8f3a2c7d91e4...py` and `cceb13cd2021...py` must be present. A missing
revision must be fixed by deploying the correct source; do not work around it by
editing `alembic_version` or running `alembic stamp`.

## 4. Configure `.env`

PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` before the first PostgreSQL startup. At minimum, review these values:

```dotenv
# Keep this name stable; changing it later selects a different Docker volume.
COMPOSE_PROJECT_NAME=label_guardian

POSTGRES_BIND_ADDRESS=127.0.0.1
POSTGRES_DB=label_guardian
POSTGRES_USER=label_guardian
POSTGRES_PASSWORD=REPLACE_WITH_A_LONG_URL_SAFE_SECRET
POSTGRES_PORT=5432

# Used by Alembic or Python commands executed on the host.
DATABASE_URL=postgresql+asyncpg://label_guardian:REPLACE_WITH_A_LONG_URL_SAFE_SECRET@localhost:5432/label_guardian

# Used only by the optional synchronous ingestion runtime.
LABEL_GUARDIAN_DATABASE_URL=postgresql+psycopg://label_guardian:REPLACE_WITH_A_LONG_URL_SAFE_SECRET@localhost:5432/label_guardian

APP_ENV=development
BACKEND_BIND_ADDRESS=127.0.0.1
CORS_ORIGINS=http://localhost:5173

# Host Python uses the relative path; Compose mounts ./data at /app/data and
# overrides it with the container path.
DATASET_ROOT=data/derived/demo-v1/yolo
DOCKER_DATASET_ROOT=/app/data/derived/demo-v1/yolo
```

Important configuration rules:

- Use a strong PostgreSQL password containing URL-safe characters only for the
  current Compose implementation: letters, numbers, `_`, and `-`. Reserved URL
  or Compose interpolation characters can break the generated connection URL.
- The username, password, database, and host port in the host URLs must match the
  corresponding `POSTGRES_*` values.
- Host tools connect to `localhost:${POSTGRES_PORT}`. The backend container uses
  `postgres:5432`; Compose overrides its `DATABASE_URL` automatically.
- If host port `5432` is occupied, use another value such as `5433` and update
  both host-side URLs. The container address remains `postgres:5432`.
- PostgreSQL uses `POSTGRES_*` only when initializing an empty volume. Editing
  them later does not change credentials in an existing database.
- Replace or clear placeholder API keys. Never commit, print, or send `.env` over
  an insecure channel.
- `CORS_ORIGINS` controls browser origins; it is not authentication.
- Files under `data/` are ignored by Git. Copy or restore them separately if the
  real-data API is needed.
- Restrict `.env` and backup-file permissions to the deployment account. On
  Windows, use a private NTFS directory/ACL; on Linux/macOS, use mode `600` for
  secret files and `700` for their parent directory.

For a server-like environment, use `APP_ENV=production`, exact HTTPS frontend
origins, managed secrets, private networking, and an authenticated gateway. The
current backend also connects using the PostgreSQL bootstrap user; create a
separate least-privileged application role before treating this as production.

Create the bind-mounted data directory before building:

PowerShell:

```powershell
New-Item -ItemType Directory -Force data | Out-Null
```

Linux/macOS:

```bash
mkdir -p data
```

On Linux, make it readable and writable by the backend container's non-root user
without making it world-writable. A bind mount hides the ownership established
inside the image, so host filesystem permissions still apply.

## 5. Start PostgreSQL and the backend

Use a controlled first-start sequence. The following Docker commands are the same
in PowerShell, Linux, and macOS:

```text
docker compose config --quiet
docker compose pull postgres
docker compose build --pull backend
docker compose up -d --wait postgres
docker compose run --rm backend python -m alembic upgrade head
docker compose up -d --wait backend
docker compose ps
docker compose logs --tail 100 postgres backend
```

Always use `docker compose config --quiet`; the non-quiet form expands and prints
environment values, including secrets.

If an older Compose version does not support `--wait`, run `docker compose up -d`
and wait until `docker compose ps` reports the service as healthy before the next
command.

The `backend` startup script also automatically runs:

```text
python -m alembic upgrade head
```

The second migration run during backend startup is an intentional no-op. Do not
generate a new revision on the target machine. Existing revision files
describe how to build the schema; Alembic records the applied revision in the
database table `alembic_version`.

## 6. Verify the installation

Confirm the migration state:

```text
docker compose exec -T backend python -m alembic heads
docker compose exec -T backend python -m alembic current
docker compose exec -T backend python -m alembic check
```

`heads` and `current` should both resolve to `cceb13cd2021 (head)`, and `check`
should report no new upgrade operations.

Confirm a real PostgreSQL query, not only the container health check.

PowerShell:

```powershell
$DbUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
$DbName = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U $DbUser -d $DbName -c 'SELECT current_database(), current_user, 1 AS ok;'
```

Linux/macOS:

```bash
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user, 1 AS ok;"'
```

PowerShell API check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Linux/macOS API check:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Useful URLs:

- Health: `http://127.0.0.1:8000/health`
- Versioned health: `http://127.0.0.1:8000/api/v1/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

The health endpoint confirms application liveness but does not replace the SQL
check above.

## 7. Moving existing data

Alembic transfers schema history, not PostgreSQL rows, datasets, model weights,
or object-store files. To move the current state, transfer each data store
separately. A PostgreSQL dump is internally consistent while the database is
running, but it is not transactionally coordinated with `./data` or an external
object store. Stop the backend and quiesce every other writer when those stores
must form one consistent snapshot.

### Export PostgreSQL on the source machine

The commands below stop the Compose backend, create a timestamped custom-format
dump inside PostgreSQL, and copy it to a sibling backup directory outside the Git
checkout. This avoids PowerShell binary-redirection corruption and accidental Git
inclusion. Stop immediately if any command fails; never delete the container copy
until the host copy and checksum have succeeded.

PowerShell:

```powershell
$ErrorActionPreference = 'Stop'
docker compose stop backend
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the backend writer.' }
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not become healthy.' }
$DbUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read POSTGRES_USER.' }
$DbName = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read POSTGRES_DB.' }
$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$BackupDir = Join-Path (Split-Path -Parent $PWD.Path) 'label-guardian-backups'
$ContainerDump = "/tmp/label-guardian-$Stamp.dump"
$HostDump = Join-Path $BackupDir "label-guardian-$Stamp.dump"
New-Item -ItemType Directory -Force $BackupDir | Out-Null
docker compose exec -T postgres pg_dump "--username=$DbUser" "--dbname=$DbName" --format=custom --no-owner --no-acl "--file=$ContainerDump"
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed.' }
docker compose exec -T postgres pg_restore --list $ContainerDump
if ($LASTEXITCODE -ne 0) { throw 'The container dump could not be read.' }
docker compose cp "postgres:$ContainerDump" $HostDump
if ($LASTEXITCODE -ne 0) { throw 'Copying the dump to the host failed.' }
Get-FileHash $HostDump -Algorithm SHA256
docker compose exec -T postgres rm -f $ContainerDump
```

Linux:

```bash
set -euo pipefail
docker compose stop backend
docker compose up -d --wait postgres
db_user="$(docker compose exec -T postgres printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')"
stamp="$(date -u +%Y%m%d-%H%M%S)"
backup_dir="../label-guardian-backups"
container_dump="/tmp/label-guardian-${stamp}.dump"
host_dump="${backup_dir}/label-guardian-${stamp}.dump"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
docker compose exec -T postgres pg_dump --username="$db_user" --dbname="$db_name" --format=custom --no-owner --no-acl --file="$container_dump"
docker compose exec -T postgres pg_restore --list "$container_dump"
docker compose cp "postgres:$container_dump" "$host_dump"
sha256sum "$host_dump"
docker compose exec -T postgres rm -f "$container_dump"
```

On macOS, use the same shell commands but replace the final checksum command
with:

```bash
shasum -a 256 "$host_dump"
```

Encrypt and transfer the dump over a trusted channel. It can contain sensitive
application data. Record the checksum with the release SHA and Alembic revision.
Copy `./data` and any external object-store data independently while writers are
quiesced. If the source machine must remain active after the snapshot, run
`docker compose start backend` only after every required copy is complete.

Do not copy a live PostgreSQL Docker volume directory between operating systems
or PostgreSQL versions. Keep encrypted off-host backups on a defined schedule and
periodically prove them with a full restore drill; `pg_restore --list` alone does
not prove that restoration succeeds.

Define backup frequency and retention from the acceptable recovery point (RPO)
and recovery time (RTO), rather than treating the Docker volume as a backup.

### Restore PostgreSQL on the target machine

Verify the transferred checksum, then restore into a new or empty target database
before starting the backend. Set the dump path in the first command. Stop
immediately on any failure; the unique container filename prevents an old dump
from being restored accidentally.

PowerShell:

```powershell
$ErrorActionPreference = 'Stop'
$HostDump = 'C:\SECURE_BACKUP_DIRECTORY\label-guardian-TIMESTAMP.dump'
Get-FileHash $HostDump -Algorithm SHA256
docker compose stop backend
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the target backend.' }
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not become healthy.' }
$DbUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read POSTGRES_USER.' }
$DbName = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read POSTGRES_DB.' }
$ContainerRestore = "/tmp/label-guardian-restore-$([guid]::NewGuid().ToString('N')).dump"
docker compose cp $HostDump "postgres:$ContainerRestore"
if ($LASTEXITCODE -ne 0) { throw 'Copying the dump into PostgreSQL failed.' }
docker compose exec -T postgres pg_restore "--username=$DbUser" "--dbname=$DbName" --no-owner --no-acl --exit-on-error --single-transaction $ContainerRestore
if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed; the target transaction was rolled back.' }
docker compose exec -T postgres rm -f $ContainerRestore
```

Linux:

```bash
set -euo pipefail
host_dump="/SECURE_BACKUP_DIRECTORY/label-guardian-TIMESTAMP.dump"
sha256sum "$host_dump"
docker compose stop backend
docker compose up -d --wait postgres
db_user="$(docker compose exec -T postgres printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')"
container_restore="/tmp/label-guardian-restore-$(date -u +%Y%m%d-%H%M%S)-$$.dump"
docker compose cp "$host_dump" "postgres:$container_restore"
docker compose exec -T postgres pg_restore --username="$db_user" --dbname="$db_name" --no-owner --no-acl --exit-on-error --single-transaction "$container_restore"
docker compose exec -T postgres rm -f "$container_restore"
```

On macOS, verify the checksum with `shasum -a 256 "$host_dump"`. Compare it with
the source checksum before restoring.

Restore `./data` and external object-store content to their configured locations
before starting the backend. Then run:

```text
docker compose build --pull backend
docker compose run --rm backend python -m alembic upgrade head
docker compose up -d --wait backend
```

The backend then applies any migrations newer than the dump. Repeat all checks in
[Verify the installation](#6-verify-the-installation) before directing traffic to
the target machine. Do not allow both machines to accept writes after cutover.

If the target database is not empty, stop and choose an explicit merge or
replacement strategy. Do not use destructive restore options without a verified
backup.

## 8. Optional frontend

The frontend is not included in Compose.

PowerShell:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Linux/macOS:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

For the API-backed queue:

```dotenv
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=
```

An empty `VITE_API_BASE_URL` uses the local Vite proxy to
`http://127.0.0.1:8000`. For a separately hosted frontend, set the public backend
URL at build time and add the frontend origin to backend `CORS_ORIGINS`. Never put
`CVAT_PAT` or other backend secrets in frontend environment files.

The current backend container installs only core dependencies. It does not include
the `agent`, `agent-yolo`, `ingestion`, or `cvat` optional dependency groups.

## 9. Routine operations

View status and logs:

```text
docker compose ps
docker compose logs -f postgres backend
```

Stop and restart while preserving data:

```text
docker compose stop
docker compose start
```

Remove containers and the network while preserving the PostgreSQL volume:

```text
docker compose down
```

**Never run `docker compose down -v` unless permanent deletion of the PostgreSQL
volume is intentional and a verified backup exists.** A Docker volume is
persistence, not a backup.

### Deploy an application update

For a single-machine installation:

```text
git fetch --all --prune
git checkout RELEASE_TAG_OR_COMMIT
docker compose stop backend
docker compose build --pull backend
docker compose run --rm backend python -m alembic upgrade head
docker compose up -d --wait backend
docker compose exec -T backend python -m alembic current
```

Back up PostgreSQL before applying migrations. Prefer a forward-fix migration to
an application downgrade. For multiple backend replicas, run Alembic once as a
dedicated release job and set `RUN_MIGRATIONS=false` on the web replicas. The
Compose value is configurable through the environment; the Supabase override
disables startup migrations and verifies that the database is already at the
committed head.

Do not automate downgrades. In particular, downgrade `9d2f3c4b5a6e` deletes
local-dataset QA cases and related audit rows, and it can fail while restoring
`NOT NULL` CVAT columns when existing rows contain null identifiers. Require a
verified backup and data audit, or use a forward-fix migration.

Alembic stores revision IDs, not migration-file checksums. Editing a historical
migration after it has run is invisible to Alembic, which is another reason to
deploy immutable release commits.

## 10. Troubleshooting

| Symptom | Cause and action |
| --- | --- |
| `.env` is missing | Create it from `.env.example`; the backend service requires the file. |
| `No module named psycopg2` during Alembic | An explicit sync-driver URL or older migration environment was deployed. Use `postgresql+asyncpg://` and verify the released `migrations/env.py` and `src/db/session.py`. |
| Backend cannot connect to `localhost` | Inside Compose, PostgreSQL is `postgres:5432`. Host-run commands use `localhost:${POSTGRES_PORT}`. |
| Authentication fails after editing `.env` | The existing volume retains its original PostgreSQL credentials. Restore the old values or deliberately migrate to a new database. |
| `Can't locate revision ...` | The deployed Git revision is missing migration files. Deploy the exact release; do not hide it with `alembic stamp`. |
| `current` is older than `heads` | Run `alembic upgrade head` using the released backend image, then investigate any migration error. |
| Database looks empty after moving the repository | The Compose project name or directory changed, selecting a different named volume. Keep `COMPOSE_PROJECT_NAME` stable. |
| Port `5432` is already in use | Change `POSTGRES_PORT` and both host-side database URLs. The container still uses `postgres:5432`. |
| `invalid length of startup packet` | Usually an HTTP/TCP probe connected to PostgreSQL without speaking its protocol. If recurring, isolate or firewall port `5432`. |
| API health succeeds but database operations fail | `/health` is application liveness. Run the explicit `psql` query and inspect backend logs. |
| Dataset path is missing | Put files below host `./data` and set `DOCKER_DATASET_ROOT` to the corresponding `/app/data/...` path. |
| `/app/data` permission error on Linux | Ensure the host bind-mounted directory is accessible to the non-root user inside the backend image. |
| Disk space drops quickly | Check PostgreSQL data, datasets, Docker images/build cache, backups, and container logs. |

Diagnostic commands:

```text
docker compose ps
docker compose logs --tail 200 postgres
docker compose logs --tail 200 backend
docker compose exec -T backend python -m alembic current
```

PowerShell database readiness:

```powershell
$DbUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
$DbName = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
docker compose exec -T postgres pg_isready -U $DbUser -d $DbName
```

Linux/macOS database readiness:

```bash
docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## Acceptance checklist

- The target is running the recorded Git SHA.
- Every intended migration file is tracked, including `8f3a2c7d91e4` and
  `cceb13cd2021`.
- PostgreSQL and the backend report healthy.
- The expected physical volume is `label_guardian_postgres_data` and contains the
  intended database.
- `alembic current` reports `cceb13cd2021 (head)`.
- `alembic check` reports no pending model changes.
- A real SQL query succeeds.
- The API health endpoint succeeds.
- Only intended network ports are reachable.
- Secrets are absent from Git, images, command output, and logs.
- PostgreSQL, `./data`, and external object storage have separate off-host
  backups where applicable.
- A backup has been restored successfully into a disposable database or
  environment.
- Restarting the stack preserves PostgreSQL rows.
