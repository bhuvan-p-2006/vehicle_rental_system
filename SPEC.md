# Vehicle Rental System — Application Specification

## 1. Overview

### 1.1 Problem Statement
Starting a vehicle rental company where customers rent vehicles from a catalog. No system exists today for browsing vehicles, submitting identity proofs online, or staff approval.

### 1.2 Solution
Fullstack web application:

- **Frontend:** React JS + Zod for client-side form validation (role-aware UI for customers and staff)
- **Backend:** Python FastAPI + Pydantic v2 for authoritative server-side validation (REST JSON API, RBAC, business-rule enforcement)
- **Database:** Postgres (users, vehicles, rental requests, audit) with Alembic for schema migrations / maintenance
- **Object storage:** S3-compatible object storage for Aadhaar + driving licence images (RustFS in local Compose, private bucket)
- **Toolchain:** uv manages the Python project (deps, lockfile, venv, script tasks) — see §13. Frontend uses npm with a committed lockfile.
- **Packaging:** Monorepo with Docker Compose — single command brings up frontend, backend, database, object storage. Frontend and backend are built/run in two separate containers from `frontend/Dockerfile` and `backend/Dockerfile`.

### 1.3 User Flow
1. Customer registers / logs in
2. Browses vehicle catalog (public read, filters)
3. Selects vehicle + start/end dates + contact details
4. Uploads Aadhaar card photo + driving licence photo
5. Submits rental request → status `pending`
6. Staff logs in → sees pending queue with proofs → manually verifies → `approved` / `rejected` with reason
7. Customer sees status; approved rental blocks vehicle calendar and counts toward one-vehicle limit
8. Lifecycle continues: `approved → active → completed`, or `cancelled` at pending/approved stage

### 1.4 Business Rules (normative)
- **R1 – One vehicle at a time:** A customer may have at most one outstanding rental in `pending`, `approved`, or `active` state. `rejected`, `cancelled`, `completed` do not count.
- **R2 – Advance booking:** `start_date >= booking_date + 14 days`. Requests with earlier start are rejected with a machine-readable error.
- **R3 – Max duration:** `0 < (end_date - start_date) <= 14 days`. Longer durations rejected.
- **R4 – Identity proofs mandatory:** Every request requires exactly two artifacts: Aadhaar image and licence image. Request cannot transition to `pending` without both stored.
- **R5 – Manual staff approval:** No auto-approval. Only `staff` role can approve/reject. All decisions audited (who, when, reason). Registration always yields role `customer` and rejects any client-supplied `role` field, so staff accounts can only be provisioned by seed or staff-only creation.

## 2. Actors & RBAC

| Role | Capabilities |
|------|--------------|
| Anonymous | Browse catalog, register, login |
| Customer | Browse, create request, upload own proofs, view own requests/history, cancel own pending request |
| Staff | All customer read + view approval queue + view proofs + approve/reject + manage vehicles + mark active/completed/cancelled |

Enforcement:
- JWT access tokens carry `user_id` + `role`.
- Every endpoint declares required role via dependency guard; UI routing mirrors but never replaces server checks.
- Staff accounts provisioned via seed or staff-only creation — no open self-registration as staff.
- Proof read URLs only issued to request owner and staff.

## 3. Functional Requirements

### 3.1 Auth
- Register customer (email unique, password hashed with bcrypt).
- Passwords are capped at 72 bytes at the schema boundary. bcrypt ignores bytes past 72, so rejecting longer input is required — silently truncating would let two distinct passwords authenticate each other.
- Login returns a JWT access token. Logout clears the client session (tokens are stateless; no server-side revocation list in v1).
- Role-based route guards + a uniform 401/403 error envelope. A missing `Authorization` header returns 401 with code `MISSING_TOKEN`.
- Login failures return one message for both unknown-email and wrong-password, so account existence is not disclosed.

### 3.2 Vehicle Catalog
- Public `GET` list with pagination, filter by type/status/availability window, search by make/model.
- Public `GET` detail: specs, price/day, photos, status, rental terms.
- Staff `POST / PUT / PATCH / DELETE` (soft-deactivate via status: `available | maintenance | retired`).
- Only `available` vehicles requestable; availability computed against approved/active overlapping reservations.

### 3.3 Rental Requests
- Customer `POST`: vehicle_id, start_date, end_date, contact details, proof object keys.
- Server validates R1–R4 atomically; on violation returns 422 with codes: `START_TOO_SOON`, `DURATION_TOO_LONG`, `ACTIVE_RENTAL_EXISTS`, `VEHICLE_UNAVAILABLE`, `PROOFS_MISSING`.
- Customer `GET` own requests + history; `DELETE/cancel` own pending.
- Overlap rule: once a request is approved, overlapping requests for same vehicle/date range are blocked.
- Dates stored UTC; comparison on date basis with documented cutoff (server date).

### 3.4 Proofs & Storage
- Accepted types: JPEG/PNG/WebP/PDF; per-file cap 5 MB (enforced on both the declared metadata and the browser-side file). Malware scanning is out of scope for v1.
- Flow A (default): the client requests a presigned PUT (`POST /rentals/upload-url`) and uploads the bytes **directly** to object storage, then submits the returned `object_key` with the rental request. The API never proxies file bytes. Flow B (multipart proxy through the backend) remains a documented fallback.
- Proof metadata travels with the rental request (`proofs[]`: `kind`, `object_key`, `content_type`, `size`), so the database records real content type and size rather than placeholders.
- Presigned URLs are short-lived (15 min). GET URLs are issued only to the request owner and verifying staff.
- Two storage endpoints are configured: `MINIO_ENDPOINT` for the backend's own S3 calls, and `MINIO_PUBLIC_ENDPOINT` for presigning. Inside a container network the internal hostname does not resolve in the browser, and SigV4 signs the `Host` header, so presigned URLs must be signed against the browser-reachable host. Leave the public endpoint unset for single-host deployments.
- An explicit `MINIO_REGION` avoids a bucket-location lookup on every presign request.
- DB stores only object keys plus metadata; never bytes.
- Object key pattern: `rentals/{draft_id}/{aadhaar|licence}.{ext}`.
- Re-upload allowed while `pending` only.

### 3.5 Staff Approval
- Staff list requests per lifecycle state (`GET /rentals?status=...`, default `pending`). Every bucket must be reachable — a rental approved once would otherwise leave the queue and never be activatable or completable, leaving the customer blocked by R1 permanently.
- `POST approve` / `POST reject {reason}` — reason required on reject.
- `POST activate` / `POST complete` transitions by staff.
- **Cancellation:** a customer may cancel only their own *pending* request. Staff may cancel any rental that still holds a vehicle (`pending`, `approved`, or `active`), which is how a committed booking is released when the customer drops out; the reason is recorded on the audit trail. Terminal states (`completed`, `rejected`, `cancelled`) are immutable — further transitions return `INVALID_TRANSITION`.
- Customer sees status + reason on refresh; polling sufficient for v1.
- Audit log: decision, actor, timestamp, previous→new state, reason.

### 3.6 Validation (normative: Pydantic backend, Zod frontend)
- Backend is authoritative: all requests validated with Pydantic v2 schemas (`BaseModel`, `Field`, `field_validator`, `model_validator`). Frontend validation is UX-only and never trusted.
- Backend Pydantic enforces: email format, password min length, UUID types, date types, R2 (start >= today+14d), R3 (0 < duration <= 14d), proof keys present, enum states, pagination bounds. Business rules R1/R4/R5 + overlap checks enforced in service layer after schema validation, returning `code` errors from §3.3.
- Frontend validates same shapes with Zod schemas (`z.object`, `z.coerce.date`, `z.string().email()`, refinements for R2/R3, file schemas for type/size) wired to forms via `react-hook-form + @hookform/resolvers/zod`. Zod mirrors backend messages so users see identical errors pre-submit; backend 422 `code` still rendered if server rejects.
- Contract parity: Zod and Pydantic schemas for auth, vehicle, rental-create, approval-decision kept field-name/type compatible; any backend schema change requires matching frontend Zod update in same PR.

## 4. Non-Functional Requirements
- Docker single-command boot; env-driven config (ports, secrets, bucket names, DB URL).
- Responsive web (desktop + mobile browser); no native apps.
- PII: private bucket, short-lived URLs, least-privilege staff access. Retention policy TBD.
- Seed data for local dev: demo customer, demo staff, sample vehicles, pre-created bucket.

## 5. Architecture

- Monorepo layout: `/frontend` (React + Zod), `/backend` (FastAPI + Pydantic + SQLAlchemy + Alembic, managed by uv), `docker-compose.yml`, `Makefile`, shared `.env.example`. No shared code package in v1; Pydantic/Zod schemas kept in parity manually per §3.6.
- React SPA → FastAPI REST (`/api/v1`) → Postgres + S3-compatible object storage.
- Backend layers: routers → Pydantic schemas → services (Auth, Catalog, RentalValidator, Approval, Storage) → persistence (SQLAlchemy) + S3 client. All schema changes via Alembic migrations (autogenerate + hand-reviewed, upgrade/downgrade, single `alembic_version` linear history).
- Centralized `RentalValidator` used by both creation and approval so rules cannot drift.
- OpenAPI docs auto-generated by FastAPI.
- Docker Compose services: `frontend` (separate container from `frontend/Dockerfile`, serves built SPA behind nginx), `backend` (separate container from `backend/Dockerfile`, runs Alembic + Uvicorn), `db` (volume `pgdata`), `storage` (S3-compatible object store, volume `object-data`, bucket auto-created by the backend on boot). Frontend talks to the backend through the nginx `/api` proxy; containers communicate over the compose network.
- Object storage: RustFS is the Compose default because MinIO withdrew its community server image from Docker Hub. The backend uses a plain S3 client, so any S3-compatible server works — point `MINIO_ENDPOINT`/`MINIO_PUBLIC_ENDPOINT` at it.
- Healthchecks: `db` (pg_isready), `storage`, `backend` (`GET /health`); each service waits on `condition: service_healthy` rather than sleeping (§13.6).

## 6. Data Model (logical)

- **users:** id, name, email unique, password_hash, role (customer|staff), created_at
- **vehicles:** id, type/category, make, model, year, registration_no unique, seats/capacity, price_per_day, status, image_refs, created_at/updated_at
- **rental_requests:** id, customer_id FK, vehicle_id FK, start_date, end_date, status (pending|approved|rejected|active|completed|cancelled), contact details, rejection_reason, created_at/updated_at
- **proof_documents:** id, request_id FK (cascade delete), kind (aadhaar|licence), object_key, content_type, size, uploaded_at
- **audit_events:** id, request_id FK (cascade delete), actor_id FK, action (submitted|approved|rejected|activated|completed|cancelled), from_status, to_status, reason, created_at
- **Constraints:**
  - R1 is enforced by a **partial unique index** on `rental_requests(customer_id)` scoped to `status IN ('pending','approved','active')`. A plain `UNIQUE (customer_id, status)` is explicitly wrong — it would forbid a customer from ever holding two completed or rejected rows. The partial index both expresses the rule and closes the check-then-insert race; the service maps the resulting `IntegrityError` back to `ACTIVE_RENTAL_EXISTS`.
  - The index's `WHERE` predicate is declared for both Postgres and SQLite, because a dialect that ignores it would silently degrade to a full unique constraint on `customer_id`.
  - One proof per kind per request (unique on `request_id, kind`).
  - Indexes supporting the overlap scan (`vehicle_id, start_date, end_date`) and the approval queue (`status`).

### 6.1 Database Maintenance (Alembic — normative)
- Alembic is the sole mechanism for DDL: no manual `CREATE/ALTER TABLE` in app code, seed scripts, or against running DBs. The seed script inserts rows only — it must never call `create_all`.
- `backend/alembic.ini` deliberately carries no `sqlalchemy.url`; `alembic/env.py` reads it from `app.config` so configuration has one source of truth (§13.5).
- Migrations live in `backend/alembic/versions/` with descriptive `<rev>_*.py`, linear down-revision chain, and both `upgrade()` and `downgrade()` tested.
- Workflow: modify SQLAlchemy models → `uv run alembic revision --autogenerate -m "<change>"` → review/correct diff (data migrations, partial/exclusion constraints, backfills) → `uv run alembic upgrade head` locally → commit models + migration together → CI runs `upgrade head` then `downgrade -1` / `upgrade head` on ephemeral Postgres.
- Backend container runs `alembic upgrade head` on startup before serving/seed; seed data runs only after migrations succeed. Fresh env = `upgrade head` from empty DB must reproduce full schema.
- Destructive migrations (drop column/table, type change) require explicit data-migration plan and staff sign-off in the PR.

## 7. API Contract (REST, `/api/v1`)

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `GET /vehicles` (filters: `type`, `status`, `search`, `available_from`/`available_to`, `page`, `page_size`), `GET /vehicles/{id}`
- `POST /vehicles`, `PUT /vehicles/{id}`, `PATCH /vehicles/{id}/status` (staff)
- `POST /rentals/upload-url` (presigned PUT; body: `kind`, `filename`, `content_type`, `size`, `draft_id`) (customer)
- `POST /rentals` (customer) — body includes `proofs[]` of `{kind, object_key, content_type, size}`
- `GET /rentals/me`, `POST /rentals/{id}/cancel` (customer: own + pending; staff: pending/approved/active)
- `GET /rentals/{id}` (owner or staff), `GET /rentals/{id}/proofs` (presigned GET links, owner or staff)
- `GET /rentals` (staff queue; `status` query param, default `pending`) — every lifecycle bucket must be listable, otherwise a rental approved once could never be activated or completed and the customer would stay blocked by R1 indefinitely
- `POST /rentals/{id}/approve`, `POST /rentals/{id}/reject`, `POST /rentals/{id}/activate`, `POST /rentals/{id}/complete` (staff)
- `GET /health` (unversioned liveness probe used by the container healthcheck)
- Errors are uniform: `{ "detail": { "code": "...", "message": "...", "errors": [...] } }`. Codes: `VALIDATION_ERROR`, `MISSING_TOKEN`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `EMAIL_TAKEN`, `ROLE_REQUIRED`, `FORBIDDEN`, `NOT_YOUR_RENTAL`, `ACTIVE_RENTAL_EXISTS`, `VEHICLE_UNAVAILABLE`, `VEHICLE_NOT_FOUND`, `INVALID_TRANSITION`, `CANNOT_CANCEL`, `RENTAL_NOT_FOUND`, `STORAGE_UNAVAILABLE`.
- 401 unauthenticated, 403 forbidden, 404 missing, 409 conflict (including business-rule conflicts), 422 schema/rule validation.

## 8. Frontend Structure

- Stack: React + TypeScript + Zod + react-hook-form (`@hookform/resolvers/zod`); colocated `schemas/*.ts` mirroring backend Pydantic per §3.6.
- Public: catalog list, vehicle detail, login/register.
- Customer workspace: new-request wizard (1. dates+vehicle → 2. details → 3. uploads → 4. review/submit), my rentals, history.
- Staff workspace: approval queue, request detail with proof viewer, approve/reject with reason modal, vehicle management CRUD.
- Token attached to API calls; friendly rendering of `code` errors; upload progress UI.

## 9. Docker & Local Dev

- `make up` (= `docker compose up --build`) starts all four services. Backend entrypoint applies `alembic upgrade head` before starting API/seed, so DB schema is always current.
- Local (non-Docker) backend loop: `make install` then `make dev` — `uv sync` provisions the venv from `uv.lock`, `uv run uvicorn app.main:app --reload` serves with auto-reload.
- Host-side commands (`make migrate`, `make seed`, `make reset-db`, `make dev`) read `backend/.env`, which `make install` creates from `backend/.env.example`. It points at `localhost`, because the Compose-internal hostname `db` does not resolve from the host shell. Containers get their configuration from `docker-compose.yml` instead.
- Migration commands, always through uv: `make migration` (autogenerate), `make migrate` (`upgrade head`), `uv run alembic downgrade -1`, `uv run alembic history / current`.
- Every Python command in docs, Makefile, and CI goes through `uv run`; a bare `pip install` or `alembic` invocation in documentation is a defect (§13.1).
- Object storage console on http://localhost:9001 for local inspection; the backend auto-creates the bucket on boot.
- Demo credentials and seed command documented in README and `.env.example`; volumes persist DB and object data across restarts.
- Prerequisite check belongs to `make doctor`, which verifies uv, Docker, and Node are present and on expected versions.

## 10. Testing Strategy

- Primary seam: **backend HTTP API** (confirmed). Tests assert status codes, shapes, transitions, RBAC — never internals.
- Cases: RBAC matrix, date boundaries (13d reject / 14d accept, 14d duration accept / 15d reject), single-rental limit, overlap blocking, proofs-missing rejection, lifecycle + audit, staff reachability of every lifecycle bucket, staff cancellation of a committed booking, catalog filtering and availability window, fleet CRUD, auth edge cases, and the JSON shape of money fields.
- Greenfield: establish backend API test suite (`httpx` ASGI client against an ephemeral Postgres + stubbed object storage) as convention, run via `uv run pytest`. Frontend E2E deferred; Docker boot verified manually.
- Tests must not require Docker to run locally: the suite provisions its own database and stubs the S3 client so `make test` works on a bare checkout (§13.4).

## 11. Out of Scope (v1)

Payments/deposits/refunds, OCR/DigiLocker KYC, SMS/email push, fleet optimization, insurance, native apps, prod HA/CDN/WAF/observability, legacy migration.

## 12. Risks & Notes

- Date-boundary timezone bugs — mitigate with UTC + explicit cutoff + boundary tests.
- Double-booking race — mitigate with transactional checks + DB guard.
- PII exposure — mitigate with private bucket + short-lived URLs + role-checked issuance.
- Next step: split into tickets (auth/RBAC, catalog, rental rules, proofs/storage, approval queue, docker) before implementation.

## 13. Developer Experience (normative)

### 13.1 uv as the Python project manager
- `uv` is the **only** supported way to install, lock, and run Python dependencies. No `pip install -r requirements.txt`, no `requirements.txt` in the repo.
- `backend/pyproject.toml` is the single source of truth for Python dependencies, the `requires-python` floor, and all tool config (ruff, mypy, pytest).
- `backend/uv.lock` is committed. Every environment — developer laptop, Docker image, CI — is built from that exact lockfile.
- `uv sync` creates/updates `backend/.venv`. Day-to-day commands use `uv run <cmd>` so the activated venv is implicit and never the developer's responsibility.
- `uv add` / `uv remove` are the only sanctioned ways to change dependencies, so the lockfile updates atomically with `pyproject.toml`. Hand-editing dependency lists is a review failure.

### 13.2 Reproducibility
- Docker builds run `uv sync --frozen` (or `uv sync --locked`) and fail if `pyproject.toml` and `uv.lock` disagree. Local and container environments must not drift.
- Containers pin base images by tag; the Python version is pinned once via `requires-python` and `.python-version`, never per-command.
- Dependency additions must state why in the PR; anything that pulls a new transitive dependency is called out explicitly.

### 13.3 Quality gates (all must pass before merge)
| Gate | Tool | Command |
|------|------|---------|
| Lint | ruff | `uv run ruff check .` |
| Format | ruff | `uv run ruff format --check .` |
| Types | mypy | `uv run mypy app` |
| Tests | pytest | `uv run pytest` |
| Migrations | alembic | `uv run alembic upgrade head` then `downgrade base` then `upgrade head` |

- ruff owns both linting and formatting — no Black, no isort, no flake8.
- mypy runs in strict-ish mode on `app/` (annotations required, no untyped defs). New public functions need annotations.
- Test suite is the §10 backend API suite; a failing test is a failing build.
- CI runs the same commands as the Makefile so local and CI results match.

### 13.4 Task runner
- A root `Makefile` is the canonical entry point for repeatable commands. Docs and humans invoke `make <target>`, never raw long command lines.
- Required targets: `make help`, `make install`, `make dev`, `make up`, `make down`, `make logs`, `make migrate`, `make migration`, `make seed`, `make test`, `make lint`, `make format`, `make typecheck`, `make check` (lint+format+types+tests), `make shell`, `make clean`.
- Each target must be a thin wrapper that delegates to `uv run` (backend) or `npm` (frontend) — no duplicated logic between Makefile and docs.

### 13.5 Configuration & secrets
- `.env.example` is committed and documents every variable with a safe default. Real `.env` is gitignored. A root `.env.example` covers the Compose stack; `backend/.env.example` covers host-side runs (§9) and is copied to `backend/.env` by `make install`.
- All configuration arrives through `pydantic-settings` (`app/config.py`). No module reads `os.environ` directly.
- Settings are lru_cached and read once at startup; secrets have no usable default in production profiles.
- Frontend reads only `VITE_`-prefixed variables, injected at build time, documented in `.env.example`.

### 13.6 Container hygiene
- Multi-stage builds; final images contain runtime dependencies only — no compilers, no lockfile caches, no test/dev groups.
- Containers run as a non-root user.
- Containers carry a `HEALTHCHECK`; compose uses healthchecks + `depends_on: condition: service_healthy` so startup ordering is deterministic rather than sleep-based.
- Docker build context excludes `.venv`, `node_modules`, `__pycache__`, `.git`, test artifacts.

### 13.7 Frontend developer requirements
- npm with a committed `package-lock.json`; CI and Docker use `npm ci` (never `npm install`).
- `npm run build` runs `tsc --noEmit` first, so type errors break the build.
- `.env.example` documents `VITE_API_URL`; local dev proxies `/api` to the backend container (see `vite.config.ts`).

### 13.8 Repository hygiene
- `.gitignore` covers `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `node_modules`, `dist`, `.env`.
- A root `README.md` documents prerequisites (uv, Docker, Node), the `make` targets, demo credentials, and how to run migrations.
- Every intentional change to schema or API contract is reflected in this spec in the same PR.
