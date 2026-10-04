# Vehicle Rental — Backend

FastAPI service for the vehicle rental platform. Owns RBAC, rental business rules,
object-storage proofs, and the approval workflow. See [`../SPEC.md`](../SPEC.md) for the
authoritative specification.

## Toolchain

This project is managed by [uv](https://docs.astral.sh/uv/). There is no
`requirements.txt` — `pyproject.toml` + `uv.lock` are the source of truth.

```bash
uv sync              # create/update .venv from uv.lock
uv run uvicorn app.main:app --reload
```

## Commands

Run everything from the repo root via the Makefile:

| Command | Purpose |
|---------|---------|
| `make install` | `uv sync` for backend + `npm ci` for frontend |
| `make dev` | Run backend with auto-reload |
| `make migrate` | `alembic upgrade head` |
| `make migration` | Autogenerate a revision (`m="message"`) |
| `make seed` | Seed demo users and vehicles |
| `make test` | pytest suite |
| `make lint` / `make format` | ruff |
| `make typecheck` | mypy |
| `make check` | lint + format check + typecheck + test |

## Migrations

Alembic is the only mechanism for DDL (SPEC §6.1).

```bash
uv run alembic revision --autogenerate -m "add foo column"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic history
```

## Layout

```
app/
├── main.py          FastAPI app + router wiring
├── config.py        pydantic-settings (single env entrypoint)
├── database.py      engine / SessionLocal / Base
├── models/          SQLAlchemy models
├── schemas/         Pydantic v2 request/response contracts
├── services/        business logic (auth, vehicle, rental, storage)
├── routers/         HTTP layer, role guards
└── utils/deps.py    auth + role dependencies
alembic/             migrations
tests/               backend API suite (SPEC §10)
```

## Configuration

All settings flow through `app/config.py` via `pydantic-settings`; no module reads
`os.environ` directly. Copy `../.env.example` to `.env` for local runs.

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@db:5432/vehicle_rental` | Postgres DSN |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — override in any real env |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `MINIO_ENDPOINT` | `minio:9000` | S3-compatible endpoint |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `minioadmin` | Storage credentials |
| `MINIO_BUCKET` | `vehicle-rental` | Private bucket, auto-created on boot |
| `MINIO_SECURE` | `false` | Set `true` for TLS endpoints |
| `MINIO_PUBLIC_ENDPOINT` | *(empty)* | Browser-reachable endpoint used for presigned URLs. Set to `localhost:9000` under Docker Compose, where the internal hostname does not resolve client-side |
| `MINIO_REGION` | `us-east-1` | Explicit region avoids a bucket-location lookup per presign |