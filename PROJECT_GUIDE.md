# FastAPI Boilerplate ("Fastro"): Project Guide

A plain-language explanation of what this repository is, how it is put together,
how a request flows through it, and what you can build on top of it.

Source: https://github.com/benavlabs/FastAPI-boilerplate (cloned at commit 4deb9c4, version 0.19.0)
License: MIT, so you can use, modify and sell products built on it.

---

## 1. What is this project?

It is a **starter template for building backend APIs in Python**. It is not an
app that does anything useful by itself. It is the plumbing almost every web
backend needs, already built, tested and wired together, so you can skip the
first few weeks of setup and go straight to your own product logic.

Out of the box you get:

| Area               | What's included                                                                     |
|--------------------|-------------------------------------------------------------------------------------|
| Web framework      | FastAPI, fully async                                                                |
| Database           | PostgreSQL via SQLAlchemy 2.0 (async), Alembic migrations                           |
| Validation         | Pydantic v2 schemas                                                                 |
| Auth               | Username/password login, server-side sessions in cookies, CSRF protection, login lockout, Google OAuth |
| Authorization      | Superusers, plus role-based permissions (RBAC) such as `user.read` and `user.update` |
| API keys           | Users can create, list, rotate and delete API keys; models for usage analytics      |
| Rate limiting      | Per-user-tier, per-endpoint limits stored in the DB (Redis-backed)                  |
| Caching            | `@cache` decorator + provider API, Redis or Memcached                               |
| Background jobs    | Taskiq workers with a Redis or RabbitMQ broker                                      |
| Admin panel        | SQLAdmin web UI at `/admin` for users and tiers (can be turned off)                 |
| Security           | Security headers, CORS, GZip, a production config validator that refuses to start with unsafe settings |
| DevOps             | Multi-stage Dockerfile, generated docker-compose files (local / prod / nginx)       |
| CLI tool           | `bp`: generates compose files, makes secrets, audits `.env`, supports plugins       |
| Quality            | 43 test files (unit + integration), ruff linting, mypy, GitHub Actions CI          |

**Who makes it:** Benav Labs. This free version is called **Fastro**. They also
sell **FastroAI**, a paid version that adds Stripe billing, entitlements,
email, a frontend and an AI-agent layer. Much of this repo's design (tiers, API
key usage/cost tracking) is shaped so those features can sit on top later.

---

## 2. Repository layout

The repo is a **uv workspace**: one Python virtualenv at the root covers two packages.

```
boilerplatefastapi/
├── pyproject.toml            # workspace root only (not deployable)
├── uv.lock                   # locked dependency versions
├── backend/                  # THE APPLICATION (what gets deployed)
│   ├── src/
│   │   ├── interfaces/       # how the outside world talks to the app
│   │   ├── infrastructure/   # technical plumbing (DB, cache, auth, queues...)
│   │   └── modules/          # business features, one folder per feature
│   ├── migrations/           # Alembic DB migrations (versions/ is empty; you generate them)
│   ├── scripts/              # one-off setup scripts (first admin, first tier)
│   ├── tests/                # unit + integration tests
│   ├── Dockerfile            # stages: dev / migrate / prod
│   └── .env.example          # every setting, documented
├── cli/                      # the `bp` developer tool (never shipped to prod)
├── docs/                     # full documentation site (56 markdown pages)
└── .github/workflows/        # CI: tests, lint, type-check, docs
```

### The three layers inside `backend/src/`

This is the most important idea in the codebase.

**`interfaces/`: entry points**
- `main.py` builds the FastAPI `app`, adds session middleware and the admin
  panel, and defines `/health`.
- `api/v1/__init__.py` mounts every feature router under `/api/v1/...` and
  attaches the rate-limit dependency to them.
- `admin/` holds the SQLAdmin views for users and tiers, plus admin login.

**`infrastructure/`: shared technical services, with no business rules**
- `app_factory.py`: `create_application()` configures middleware, CORS, GZip,
  security headers, docs visibility per environment, and the startup/shutdown
  lifecycle (DB, cache, auth connections).
- `config/settings.py`: every setting, read from `.env` with pydantic-settings.
- `database/`: async engine, session dependency, `Base`, and the
  `TimestampMixin` / `SoftDeleteMixin` shared column sets.
- `auth/`: wires the **crudauth** library (sessions, CSRF, lockout, OAuth,
  password policy), the `get_current_user` / `get_current_superuser` /
  permission dependencies, and the login/logout routes.
- `cache/`: the `@cache` decorator and pluggable Redis/Memcached backends.
- `taskiq/`: background-job brokers, worker entry point and task registry.
- `logging/`: structured logging with correlation IDs.
- `security/production_validator.py`: startup check for weak secrets, default
  passwords, `CORS=*`, and so on.
- `middleware.py`: Cache-Control and security headers.
- `dependencies.py`: reusable `Annotated` aliases such as `AsyncSessionDep`,
  `CurrentUserDep` and `CurrentSuperUserDep`.

**`modules/`: business features ("vertical slices")**

Each feature is self-contained and follows the same file pattern:

```
modules/<feature>/
  models.py        # SQLAlchemy tables
  schemas.py       # Pydantic request/response shapes
  crud.py          # FastCRUD data-access object
  service.py       # business logic
  routes.py        # HTTP endpoints
  dependencies.py  # Annotated DI aliases for the service
  permissions.py   # (optional) permission names this feature defines
```

Current modules:

| Module       | Purpose                                                                                |
|--------------|----------------------------------------------------------------------------------------|
| `user`       | Accounts: sign-up, profile, update, soft delete, GDPR anonymisation, tier assignment   |
| `tier`       | Named user groups such as "free" and "pro". No pricing, only a label that rate limits hang off |
| `rate_limit` | DB rows saying "tier X may call path Y N times per P seconds"                           |
| `role`       | RBAC: `Role`, `RolePermission`, `UserRole` tables + a permission registry              |
| `api_keys`   | `APIKey`, `KeyUsage`, `KeyPermission` tables; key create/list/update/delete, usage & analytics endpoints |
| `common`     | Shared exceptions, error handlers, base schemas                                        |

**Why this matters:** to add a feature you add a new folder in `modules/` and
register its router. You don't need to touch the infrastructure.

---

## 3. Data model (database tables)

```
tiers ──< user >── user_roles >── roles ──< role_permissions
  │         │
  │         └──< api_keys ──< key_usage
  │                   └────< key_permissions
  └──< rate_limits
```

- **user**: name, username, email, hashed_password, is_superuser, tier_id,
  OAuth fields (google_id, github_id, email_verified), created/updated/deleted
  timestamps. Deletes are *soft* (`is_deleted`), and a soft-deleted user can't log in.
- **tiers**: `name`, `description`.
- **rate_limits**: `tier_id`, `path`, `limit`, `period` (seconds).
- **roles / role_permissions / user_roles**: a user's effective permissions
  are the union of their roles' permission strings. Superusers bypass checks.
- **api_keys**: only a *hash* and a short prefix are stored, never the raw key.
  Also stores expiry, active flag, JSON permissions and usage limits.
- **key_usage**: one row per API call, with endpoint, status, response time,
  `tokens_used` and `cost_microcents`. This is clearly meant for usage-based
  billing and AI-token metering.

---

## 4. API endpoints (all under `/api/v1`)

**Auth: `/auth`**
- `POST /login`: form login. Sets the session cookie and CSRF cookie. Repeated failures give `429` with `Retry-After`.
- `POST /logout`, `POST /logout-all` (`?keep_current=true` keeps this device logged in)
- `POST /refresh-csrf`, `GET /check-auth`
- `GET /oauth/google`, `GET /oauth/callback/google`: only when Google credentials are set

**Users: `/users`**
- `POST /`: register
- `GET /`: paginated list (needs the `user.read` permission)
- `GET /me`, `GET /{username}`, `PATCH /{username}`, `DELETE /{username}` (soft delete)
- `DELETE /db/{username}`: GDPR anonymise (superuser)
- `GET /{username}/rate-limits`, `GET|PATCH /{username}/tier`

**Tiers: `/tiers`**: `GET /`, `GET /{name}`

**Rate limits: `/rate-limits`**: `GET /`, `GET|PATCH|DELETE /{name}`

**API keys: `/api-keys`**: `POST /`, `GET /`, `GET|PATCH|DELETE /{key_id}`,
`GET /{key_id}/usage`, `GET /{key_id}/analytics`, `GET /summary/user`

**Other:** `GET /health`, `/docs` (Swagger), `/redoc`, `/admin`

Docs visibility depends on the environment. They are public in local and
development, superuser-only in staging, and hidden in production unless you
enable them.

---

## 5. How a request flows through the app

Example: `PATCH /api/v1/users/alice`

1. **Middleware** runs first: security headers, GZip, CORS, cache headers and
   rate-limit headers.
2. **Router** `/api/v1/users` matches. Its **rate-limit dependency** looks up
   the caller's tier, finds the `rate_limits` row for that path (or uses the
   default of 100 requests per 60 seconds), and checks the counter in Redis.
   Over the limit, the caller gets `429`.
3. **Auth dependency** (`CurrentUserDep`): crudauth reads the session cookie,
   validates it in Redis, checks the CSRF header on unsafe methods, and loads
   the user.
4. **Permissions** (`CurrentPermissionsDep`): loads the user's role
   permissions once per request.
5. **Route handler** calls `UserService`. The service checks self-or-admin
   rules and blocks privilege escalation, then updates through FastCRUD using
   an `AsyncSessionDep` DB session.
6. **Errors** raised anywhere are turned into clean JSON responses by the
   shared handlers in `modules/common/utils/error_handler.py`.

---

## 6. Running it

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
uv sync --all-packages --all-extras        # install everything
cp backend/.env.example backend/.env       # then edit values
uv run bp env gen-secret                   # paste the output into SECRET_KEY
uv run bp deploy generate local            # writes a docker-compose.yml
docker compose up --build                  # API at http://127.0.0.1:8000/docs
```

**Without Docker:** you need Postgres and Redis running locally. In
`backend/.env`, set the `*_HOST` values to `localhost`, then:

```bash
cd backend
uv run alembic revision --autogenerate -m "initial"   # migrations/versions is empty
uv run alembic upgrade head
uv run python -m scripts.setup_initial_data            # first admin + default tier
uv run fastapi dev src/interfaces/main.py
uv run taskiq worker infrastructure.taskiq.worker:default_broker   # 2nd terminal
```

(Or leave `CREATE_TABLES_ON_STARTUP=true` for quick local hacking. Use
migrations for anything real.)

**Tests:** `cd backend && uv run pytest`. Integration tests use
testcontainers, so Docker must be running.

**Production checklist:** set `ENVIRONMENT=production`, use a strong
`SECRET_KEY`, non-default DB and Redis passwords, and real `CORS_ORIGINS`.
Also set `TRUSTED_PROXY_HOPS=1` behind nginx. `uv run bp env validate` audits
all of this for you.

---

## 7. Things that are scaffolded but NOT finished

Know these before you build on the boilerplate:

1. **No background tasks are defined.** Taskiq brokers and the worker are
   wired up, but no `@broker.task` exists anywhere yet. The worker runs with
   nothing to do.
2. **API keys can be managed but not used to authenticate.** The service can
   verify a key (`APIKeyService._verify_api_key`), but no request dependency
   reads an `X-API-Key` header and logs the user in. `KeyUsage` rows are never
   written either, so the usage/analytics endpoints return empty data until
   you add that.
3. **GitHub OAuth is only half there.** The `.env` settings and the user
   columns exist, but only the Google provider is wired in `auth/setup.py`.
4. **No email.** There's no password reset, email verification or
   notifications, because there's no mail pipeline.
5. **No migrations are committed.** `migrations/versions/` is empty, so you
   need to generate the first one.
6. **Tiers have no pricing or billing.** They are labels only.
7. **No JWT or bearer-token auth.** Auth is cookie sessions, which suits
   browser frontends. Mobile apps and machine clients would use API keys once
   point 2 is finished.

---

## 8. What you can build on it

Almost any product that needs "users + a database + an API." Good fits include:

- **SaaS backend**: tiers become plans, and rate limits become plan quotas.
  Add Stripe webhooks that change `user.tier_id`.
- **AI / LLM product API**: the `KeyUsage.tokens_used` and `cost_microcents`
  columns are already built for metering LLM calls per user and per key.
  Put your LLM calls in a new module and run long jobs through Taskiq.
- **Public developer API**: finish API-key auth and sell access by tier with
  per-endpoint rate limits. The analytics endpoints already exist.
- **Internal tools / admin dashboards**: SQLAdmin gives you a free CRUD UI.
  Add a `ModelView` per table.
- **Mobile or SPA backend**: pair it with React, Next.js or Vue using session
  cookies and CSRF, or add JWT for mobile.
- **Marketplace, booking, e-commerce or content platform**: add modules for
  products, orders, bookings or posts, following the same slice pattern.

---

## 9. Suggested roadmap

Roughly in the order you'd want them.

**Step 1: Make it yours (day 1)**
- Rename the app in `.env` (`APP_NAME`, `APP_DESCRIPTION`, `VERSION`) and in
  `interfaces/main.py`, which hardcodes a title and version.
- Push it to your own GitHub repo. Keep `benavlabs` as an `upstream` remote so
  you can pull their future updates.
- Generate the first Alembic migration and commit it.
- Run the test suite once to confirm everything is green.

**Step 2: Add your first feature module**
- Copy the shape of `modules/tier/`, the simplest module: models, schemas,
  crud, service, routes, dependencies.
- Register the router in `interfaces/api/v1/__init__.py`.
- Add a `permissions.py` with `@register_permissions("<resource>")` if it
  needs RBAC.
- Import the model where Alembic can see it, then run `alembic revision --autogenerate`.
- Add tests next to the existing ones.

**Step 3: Close the gaps from section 7 that your product needs**
- API-key auth dependency (header, then `APIKeyService`, then principal) plus a
  middleware or dependency that writes `KeyUsage` rows.
- A real Taskiq task (for example, sending an email or processing an upload)
  and a route that enqueues it.
- An email provider (Resend, SES or Postmark) for verification and password reset.
- GitHub OAuth, which crudauth supports, by adding it to `_oauth_providers()`.

**Step 4: Monetisation, if you're building a product**
- Stripe checkout and webhooks that set the user's tier.
- Seed `rate_limits` rows per tier, per path.
- Usage-based billing from `KeyUsage`.

**Step 5: Production hardening**
- `uv run bp deploy generate nginx` for an nginx-fronted stack, with TLS.
- Managed Postgres (Neon, RDS or Supabase) via `DATABASE_URL`, and managed Redis.
- Observability: Sentry for errors, and OpenTelemetry or Logfire for traces.
  The logging layer already has correlation IDs.
- CI/CD: extend `.github/workflows` to build and push the Docker image and run
  the `migrate` stage before deploying.
- Backups, and a Redis password for every Redis DB (0 cache, 1 rate limit,
  2 sessions, 3 queue).

**Step 6: Frontend**
- Any SPA can talk to it. Set `CORS_ORIGINS` to the frontend's origin, send
  cookies with `credentials: "include"`, and echo the CSRF cookie in the
  request header on POST, PATCH and DELETE.

---

## 10. Where to read more

- `docs/` in this repo, or the published site: https://benavlabs.github.io/FastAPI-boilerplate
  - `docs/user-guide/project-structure.md`: the layering in depth
  - `docs/user-guide/authentication/`: sessions, OAuth, permissions
  - `docs/user-guide/database/`: models, CRUD, migrations, Neon
  - `docs/user-guide/production.md`: deployment
  - `docs/cli/plugins.md`: writing your own `bp` commands and features
- `docs/changelog.md`: what changed in each version. v0.19.0 moved auth to crudauth.
- `backend/.env.example`: every setting, with comments.
- Community Discord: https://discord.com/invite/TEmPs22gqB
