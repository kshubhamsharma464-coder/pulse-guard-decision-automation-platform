# Auth & Security -- Phase 2

JWT authentication, RBAC, rate limiting, and security headers, added
additively on top of Phase 1's persistence layer. Default behavior is
unchanged: every endpoint that worked without credentials before this
phase still works without credentials, unless an operator explicitly sets
`AUTH_REQUIRED=true`.

## What changed

- **New entities**: `User`, `Role`, and `Permission`
  (`app/domain/entities/`), each with a repository interface
  (`app/domain/interfaces/`), an in-memory implementation seeded with
  sane defaults, and a Postgres implementation (same pattern as every
  repository in Phase 1 -- see `docs/persistence.md`).
- **JWT issuance/verification** (`app/core/security.py`): access tokens
  (15 min default) and refresh tokens (7 days default), HS256, signed with
  `Settings.jwt_secret`. Password hashing uses PBKDF2-HMAC-SHA256
  (310,000 iterations) from the stdlib -- see that file's docstring for
  why this was chosen over bcrypt/argon2.
- **RBAC** (`app/interfaces/api/security.py`): `get_current_principal`
  resolves a request's `Authorization: Bearer <jwt>` header into a
  `Principal` (subject, roles, resolved permissions).
  `require_permission("some:code")` is a FastAPI dependency factory that
  enforces it.
- **New endpoints** (`app/interfaces/api/auth_router.py`, tag "Auth"):
  `POST /api/v1/auth/register`, `POST /api/v1/auth/login`,
  `POST /api/v1/auth/refresh`, and `GET /api/v1/auth/me`.
- **RBAC wired onto existing endpoints**: `POST /api/v1/incidents/evaluate`
  now requires `incidents:evaluate`; `GET /api/v1/decisions/{id}` and
  `.../history` require `decisions:read`. Both are no-ops when
  `AUTH_REQUIRED=false` and the caller presents no credentials (see
  "Backward compatibility" below) -- this is why none of the 94
  pre-existing tests needed to change.
- **Security headers** (`app/interfaces/api/middleware/security_headers.py`):
  always-on -- `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, and `Strict-Transport-Security`
  when served over HTTPS. Purely additive response headers; can't break
  anything.
- **Rate limiting** (`app/interfaces/api/middleware/rate_limit.py`):
  fixed-window, in-memory, keyed by client IP. Disabled by default
  (`RATE_LIMIT_ENABLED=false`) specifically so the test suite (many
  requests, one TestClient/IP, same window) is unaffected unless an
  operator opts in.

## Backward compatibility -- the actual mechanism

`require_permission(code)`'s logic, exactly:

1. No credentials presented, `AUTH_REQUIRED=false` (default) -> pass
   through unchecked. This is every existing test and every existing
   caller, byte-for-byte.
2. No credentials presented, `AUTH_REQUIRED=true` -> `401` before
   `require_permission` is even reached (`get_current_principal` raises).
3. Credentials presented (JWT) -> **always** validated for real and
   checked against the required permission, *regardless* of
   `AUTH_REQUIRED`. Presenting a bad token is never silently ignored.

So turning auth on is one env var (`AUTH_REQUIRED=true`); turning it off
is the default; and a caller who wants to start authenticating early
(e.g. to test their integration) can do so before the operator flips the
switch.

## RBAC model

Three roles ship by default (`in_memory_role_repository.py`):

| Role | Permissions |
|---|---|
| `admin` | everything |
| `operator` | `incidents:evaluate`, `decisions:read`, `decisions:override`, `escalations:acknowledge` |
| `viewer` (default for new users) | `decisions:read` |

Permission catalog (`in_memory_permission_repository.py`): `incidents:evaluate`,
`decisions:read`, `decisions:override`, `rules:manage`,
`escalations:acknowledge`, `users:manage`, `apikeys:manage`. Roles store a
plain list of permission codes rather than a role_permissions join table
-- see `app/domain/entities/role.py`'s docstring for why that's a
deliberate simplification, not an oversight.

Role membership is baked into the JWT at issuance (`roles` claim);
permission resolution happens fresh on every request against
`RoleRepository` (not cached in the token), so changing what a role can do
takes effect immediately without waiting for tokens to expire -- only
*which roles a user has* is fixed for the lifetime of that access token.

## Authentication model

API-key issuance and use are no longer part of the public HTTP surface.
The remaining repository/model support is retained only as internal
implementation detail and is not exposed via the API.

## Running it

Zero setup required -- `AUTH_REQUIRED` defaults to `false`. To exercise
auth locally:

```bash
curl -X POST localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email": "you@example.com", "password": "correcthorse123", "roles": ["admin"]}'

curl -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "you@example.com", "password": "correcthorse123"}'
# -> {"accessToken": "...", "refreshToken": "...", ...}

curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <accessToken>'
```

To require auth on the incident/decision endpoints, set
`AUTH_REQUIRED=true` in `.env` (or `docker compose run -e AUTH_REQUIRED=true`)
and restart.

Under Postgres (`PERSISTENCE_BACKEND=postgres`), after `alembic upgrade head`:

```bash
python3 scripts/seed_default_roles_permissions.py
```

seeds the same three default roles + permission catalog the in-memory
backend ships with automatically. No default admin user is seeded --
register the first one via the API (see `scripts/seed_default_roles_permissions.py`'s
own docstring for why a hardcoded default credential was deliberately not
added).

## Not included in this phase (flagged, not silently skipped)

- **Role/permission assignment via API** -- roles are only assigned at
  registration time (`roles` field on `POST /api/v1/auth/register`) or
  by hand in the database. A `PATCH /api/v1/users/{id}/roles`-style
  endpoint, gated by `users:manage`, is real follow-up work.
- **API-key management via API** -- the API no longer exposes any API-key
  management workflow; repository support remains internal-only.
- **Token revocation / blocklist** -- access tokens are valid until they
  expire (15 min default); there's no server-side revocation list. Each
  token carries a `jti` (unique id) specifically so a revocation list
  could be added later without a token-format change.
- **OAuth/SSO** -- the spec calls this out as future work explicitly; not
  attempted here.
- **Distributed rate limiting** -- the current limiter is in-memory,
  per-process. Fine for a single instance or as a backstop in front of a
  real gateway/WAF; not a substitute for one in a multi-replica
  deployment.

## Verification performed

- Full regression suite: 125 passed (94 pre-existing + 17 new auth/RBAC
  tests + 4 new Postgres auth-repository round-trip tests + 3 middleware
  tests + 7 `app/core/security.py` unit tests), zero changes to any
  pre-existing test file.
- `tests/test_auth.py` covers: register/login/refresh/me happy paths;
  duplicate-email and unknown-role rejection; wrong-password rejection;
  invalid/wrong-type token rejection; JWT-only RBAC enforcement both ways
  (`AUTH_REQUIRED=false` stays open, `AUTH_REQUIRED=true` actually blocks
  unauthenticated/under-permissioned callers and admits
  correctly-permissioned ones via JWT).
- `tests/test_postgres_repositories.py` (appended) round-trips
  `User`/`Role`/`Permission`/`APIKey` through the same SQLite-substitute
  methodology as every other Postgres repository in this project.
- `tests/test_middleware.py` verifies security headers are present on
  every response and that rate limiting is a true no-op until enabled,
  then actually returns `429` once it is.
- `tests/test_security_core.py` unit-tests password hashing (salted,
  rejects wrong password, rejects a garbage hash), API key
  generation/verification, and JWT issuance/decoding (correct claims,
  refresh-as-access rejected, expired token rejected, wrong secret
  rejected) independent of the HTTP layer.
- The Alembic migration (`migrations/versions/0002_auth_tables.py`) was
  verified with `alembic upgrade head --sql` (offline mode), same as
  Phase 1's migration -- inspected for correct `JSONB`/`UUID` types,
  unique constraints, and the `api_keys.owner_user_id -> users.id`
  foreign key.
