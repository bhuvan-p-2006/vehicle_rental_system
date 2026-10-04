# Vehicle Rental System

Fullstack vehicle rental platform: online catalog, rental requests with Aadhaar and
driving-licence proofs uploaded to S3-compatible object storage, and a manual staff approval workflow.

React (Zod) · FastAPI (Pydantic) · Postgres (Alembic) · RustFS (S3) · Docker Compose.

The authoritative specification is [`SPEC.md`](./SPEC.md).

## Prerequisites

| Tool | Required for | Install |
|------|---------------|---------|
| [uv](https://docs.astral.sh/uv/) | backend deps, migrations, tests, quality gates | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker + Compose | running the full stack | https://docs.docker.com/get-docker/ |
| Node 20+ | frontend dev server / build | https://nodejs.org |

Run `make doctor` to check all three.

## Quick start (Docker)

```bash
cp .env.example .env
make up          # docker compose up --build -d
```

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:30 | — |
| API | http://localhost:8000 | — |
| API docs | http://localhost:8000/docs | — |
| Object storage console | http://localhost:9001 | `minioadmin` / `minioadmin` |

Demo accounts (created by the seed step on first boot):

| Role | Email | Password |
|------|-------|----------|
| Customer | `customer@demo.com` | `Customer123` |
| Staff | `staff@demo.com` | `Staff123` |

`make logs` to tail output, `make down` to stop.

## Local development

```bash
make install      # uv sync + npm install + create backend/.env from the example
make up           # or: docker compose up db storage
make migrate      # apply migrations (host-side, via backend/.env)
make seed         # demo data
make dev          # API with auto-reload on :8000
make frontend-dev # Vite dev server on :3000
```

`make install` writes `backend/.env` from `backend/.env.example`. That file points at
`localhost`, so host-side commands (`make dev`, `make migrate`, `make seed`) can reach
the containers — the Docker-internal hostname `db` will not resolve from your shell.

## Everyday commands

Run `make help` for the full list.

| Command | Purpose |
|---------|---------|
| `make check` | All gates: lint, format, types, tests |
| `make test` | Backend API test suite |
| `make lint` / `make format` | ruff |
| `make typecheck` | mypy (strict) |
| `make migration m="add foo"` | Autogenerate an Alembic revision |
| `make reset-db` | Downgrade to base, re-migrate, re-seed (destructive) |
| `make logs` / `make ps` / `make shell` | Container operations |

## Business rules

Enforced server-side; the UI only mirrors them (SPEC §1.4).

| Rule | Behaviour |
|------|-----------|
| R1 | One outstanding rental per customer (`pending`, `approved`, or `active`) |
| R2 | Start date at least 14 days out |
| R3 | Maximum 14-day duration |
| R4 | Both proofs required: Aadhaar + driving licence |
| R5 | Manual staff approval only; every decision audited |

Errors come back as `{ "detail": { "code": "...", "message": "..." } }` with stable
codes (`ACTIVE_RENTAL_EXISTS`, `VEHICLE_UNAVAILABLE`, `INVALID_TRANSITION`, …).

## How a rental is requested

1. Customer picks a vehicle and dates on the detail page.
2. The browser asks the API for a presigned PUT URL per proof and uploads the
   bytes **directly** to object storage — the API never proxies file bytes.
3. The customer submits the request with the returned object keys plus file
   metadata.
4. Staff approve or reject from the queue; approval is what actually blocks the
   vehicle's calendar.

Proofs live in a private bucket. Download URLs are short-lived and issued only to
the request owner and verifying staff.

## Toolchain

Python is managed by [uv](https://docs.astral.sh/uv/) — `backend/pyproject.toml` and
`backend/uv.lock` are the only source of dependency truth; there is no
`requirements.txt`. The backend container installs from the same lockfile
(`uv sync --frozen`), so local and container environments cannot drift.

```bash
cd backend
uv sync            # create/update the venv
uv run pytest       # or use `make test` from the root
uv run alembic upgrade head
```

Python commands in docs and scripts always go through `uv run`; use `make <target>`
rather than typing long command lines (SPEC §13.4).

## Layout

```
.
├── SPEC.md              # authoritative specification
├── Makefile             # canonical dev entrypoint
├── docker-compose.yml   # db, minio, backend, frontend
├── .env.example
├── backend/             # FastAPI (uv-managed)
│   ├── pyproject.toml   # deps + ruff/mypy/pytest config
│   ├── uv.lock          # committed, reproducible
│   ├── alembic/         # migrations
│   └── app/
│       ├── models/      # SQLAlchemy
│       ├── schemas/     # Pydantic v2 contracts
│       ├── services/    # business rules
│       └── routers/     # HTTP + RBAC guards
└── frontend/            # React + TypeScript + Zod
    └── src/
        ├── schemas/     # Zod mirrors of the Pydantic contracts
        ├── services/    # axios client
        └── pages/       # catalog, rental wizard, staff queue
```

## Testing

The suite exercises the public HTTP contract only — status codes, response shapes,
state transitions, and RBAC — never internal function names or SQL (SPEC §10).

```bash
make test
```

It runs against an in-process ASGI client with a temporary SQLite database and a
stubbed object store, so no Docker or Postgres is required.

## Troubleshooting

**Backend exits at boot** — usually the database is not ready; `make logs`. Startup
waits on healthchecks, so a hard failure is usually a real config error.

**Migrations fail** — confirm `DATABASE_URL` points at a reachable Postgres, then
`make migrate`. To start clean: `make reset-db`.

**Object storage unavailable** — the API still starts, but proof upload returns
`STORAGE_UNAVAILABLE`. Check `make ps` for the `storage` service, that the bucket
name matches `MINIO_BUCKET`, and that `MINIO_PUBLIC_ENDPOINT` is reachable from your
browser (inside Compose it must be a host address, not the internal `storage:9000`).

**Port already in use** — the stack binds 30, 8000, 5432, 9000 and 9001. Override in
`.env` or free the port.