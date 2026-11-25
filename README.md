# Compugit PyREST

A reusable Flask foundation for REST APIs. It includes an application factory,
named database adapters, JWT authentication, database-backed role checks,
optional Redis caching, shared production authentication state, request
middleware, health endpoints, and a minimal user-management API.

This is a secure-by-default starting point, not a complete production deployment
or a certification. Each service still needs its own API, authorization rules,
deployment controls, and integration tests.

## Architecture

### Main components

| Area | Responsibility |
| --- | --- |
| `app/__init__.py` | Creates the Flask application, validates effective settings, initializes extensions and connections, registers routes and handlers, exposes the CLI command, and closes resources. |
| `app/config.py` | Loads and validates environment settings, including database definitions, CORS, proxy trust, request limits, and production requirements. |
| `app/api/routes/` | HTTP endpoints for authentication, users, and health. New application endpoints should normally be added as Flask blueprints. |
| `app/api/services/users.py` | User operations shared by relational databases and MongoDB; route handlers use this service rather than writing database queries directly. |
| `app/api/models/` | SQLAlchemy relational models. The user model stores roles and departments as serialized lists. |
| `app/database/` | Database interface, connection factory, SQLAlchemy adapter, and MongoDB adapter. Named connections are exposed in Flask's `current_app.extensions["databases"]`. |
| `app/core/auth/` | Password policy and JWT callbacks/authorization helpers. |
| `app/core/security_state.py` | Token revocation, per-identity revocation epochs, and login/registration rate limiting. Uses Redis when enabled; otherwise it uses process-local state for development/testing. |
| `app/core/cache.py` | Namespaced JSON cache interface backed by Redis. |
| `app/core/middleware.py` | Request IDs, request-size limit, response security headers, and no-store headers on auth/user routes. |
| `app/core/errors.py` and `app/core/logging.py` | JSON error responses and stderr logging with request IDs. |
| `tests/` | Focused tests for configuration, auth, users, cache/security state, and health/readiness behavior. |

### Request lifecycle

1. `run.py` or `wsgi.py` loads `.env` and calls the `create_app` factory.
2. The factory validates settings, initializes Flask-JWT-Extended, optional CORS,
   named database connections, the optional Redis client, the cache and security
   state, then registers middleware, error handlers, blueprints, and Swagger
   where enabled.
3. Middleware assigns a request ID and configures response protections.
4. An endpoint validates input and invokes a service. The built-in user service
   uses `PRIMARY_DATABASE`; other configured databases are available to
   application code but are not automatically routed or failed over.
5. JWT-protected requests are checked against revocation state. Role-protected
   routes load the user's current roles from the primary database, so role
   changes take effect without waiting for token expiry.
6. The endpoint returns JSON. Errors are normalized by the registered error
   handlers, and application logs include the request ID.

### Database and Redis design

`DATABASES` is a JSON object of named connections. Supported database types are
`sqlite`, `postgresql`, `mysql`, and `mongodb`. If omitted, the development
default is SQLite at `instance/app.sqlite3`. All configured connections are
initialized during startup; `PRIMARY_DATABASE` selects the connection used by
the built-in user service.

Relational connections use SQLAlchemy, short-lived sessions, rollback on
exceptions, and connection pre-ping. When `AUTO_CREATE_SCHEMA=True`, the
primary relational connection uses SQLAlchemy's `create_all()` at startup to
create missing tables. This is enabled by default in every environment. It does
not alter existing tables, rename columns, transform existing data, or track
schema versions. Set it to `False` only when the database schema has already
been provisioned to match the application models. MongoDB creates collections
as data is written.

Redis has two uses:

* The optional JSON cache is available as
  `current_app.extensions["cache"]`.
* When enabled, Redis holds shared token-revocation state and distributed
  login/registration rate-limit counters. Production requires Redis for this
  shared security state and returns service errors rather than silently
  accepting requests if it cannot be checked.

When Redis is disabled in development/testing, the cache is a no-op and
security state is held in process memory. That state is not shared across
workers or instances and is not suitable for production.

## API guide

All endpoints are mounted under the following prefixes. JWTs are sent using
`Authorization: Bearer <token>`. The refresh endpoint requires a refresh token;
the other protected endpoints require an access token.

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health/live` | Public | Process liveness. |
| `GET` | `/health/ready` | Public | Checks configured database connections and Redis when enabled. |
| `POST` | `/auth/register` | Public, when enabled | Creates a regular user from `userName`, `email`, and `password`. |
| `POST` | `/auth/login` | Public | Accepts a username (or `userName`/`email`) and password; returns access and refresh JWTs. |
| `POST` | `/auth/refresh` | Refresh JWT | Revokes the submitted refresh token and returns a rotated token pair. |
| `POST` | `/auth/logout` | Access JWT | Revokes the current token and all tokens for that identity. |
| `POST` | `/auth/pwupdate` | Access JWT | Requires `oldPassword` and `newPassword`; invalidates the identity's other sessions. |
| `GET` | `/users/profile` | Access JWT | Reads the authenticated user's profile. |
| `GET` | `/users` | Admin | Lists users with `limit`, `offset`, and optional `isActive` filters. |
| `POST` | `/users` | Admin | Creates a user; roles and login status may be assigned by an admin. |
| `GET` | `/users/<user_id>` | Admin | Reads a user by ID. |
| `PUT`, `PATCH` | `/users/<user_id>` | Admin | Updates supported user fields. |
| `DELETE` | `/users/<user_id>` | Admin | Deletes a user and revokes their sessions. |

Passwords are never included in user API responses. Public registration is
disabled by default, creates only regular users, and is rejected by production
configuration until an email-verification flow is added. Admin creation is
performed through the CLI, not an unauthenticated API endpoint.

## Local development

1. Create and activate a virtual environment, then install dependencies:

   ```sh
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`. The defaults use local SQLite, allow
   development schema creation, and disable Redis and CORS.
3. Start the development server:

   ```sh
   python run.py
   ```

4. Create an administrator. The command prompts for a hidden, confirmed
   password:

   ```sh
   flask --app wsgi:app create-admin
   ```

5. Use the admin account to create other users or exercise the protected user
   management endpoints.

The development server binds to `HOST` and `PORT` from `.env` (defaults:
`0.0.0.0:5000`). Swagger is enabled for local development by default.


## Configuration and usage

### Databases

Example PostgreSQL configuration:

```dotenv
DATABASES={"main":{"type":"postgresql","uri":"postgresql+psycopg2://<user>:<password>@<host>:5432/<database>"}}
PRIMARY_DATABASE=main
```

Configure only the databases the service uses. Additional named connections
are available through `current_app.extensions["databases"]`; application code
must choose and use them explicitly. The starter does not provide automatic
multi-database routing, replication, or failover.

### Redis cache

Enable the optional Redis cache with:

```dotenv
ENABLE_CACHE=True
CACHE_DB={"type":"redis","uri":"redis://<host>:6379/0"}
```

Example use inside an application context:

```python
cache = current_app.extensions["cache"]
cache.set("summary", {"count": 3}, ttl_seconds=60)
value = cache.get("summary")
cache.delete("summary")
```

Cache keys are namespaced by application name. Cache TTL must be positive.

### CORS

Cross-origin access is disabled by default. When browser clients need it, enable
CORS and set exact origins:

```dotenv
ENABLE_CORS=True
CORS_ORIGINS=https://frontend.example
CORS_SUPPORTS_CREDENTIALS=False
```

Production origins must use HTTPS. Wildcard origins are not accepted in
production, and wildcard origins cannot be combined with credentialed CORS.
Bearer-token authentication does not require credentialed CORS.

### Proxy trust and request limits

If a trusted reverse proxy/load balancer terminates TLS, set `TRUST_PROXY=True`
and configure `PROXY_FIX_X_FOR`, `PROXY_FIX_X_PROTO`, and `PROXY_FIX_X_HOST` to
the exact number of trusted hops setting those headers. Do not enable this for
requests that can bypass the trusted proxy. `API_MAX_CONTENT_LENGTH` defaults
to 2 MiB.

## Production setup

Before deploying:

1. Set `ENV=production`, `DEBUG=False`, a unique `SECRET_KEY` of at least 32
   characters, and `ENABLE_SWAGGER=False`. Store secrets in a deployment secret
   manager, not in source control.
2. Configure a non-SQLite primary database and Redis. For a fresh relational
   database, leave `AUTO_CREATE_SCHEMA=True` (the default) so the app creates
   missing tables at startup. Set it to `False` only if you provision a
   compatible schema yourself. Keep public registration disabled unless the
   service implements email verification.
3. Configure exact trusted CORS origins if needed. Configure proxy trust only
   when requests arrive through the stated trusted proxy chain.
4. Create the initial administrator using the interactive CLI command shown
   above.
5. Run behind a TLS-terminating proxy/load balancer, use a non-root service
   account, restrict network access to database and Redis services, and ship
   stderr logs to a protected centralized logging system.

Gunicorn configuration is provided in `gunicorn.conf.py`; a typical launch
command is:

```sh
gunicorn -c gunicorn.conf.py wsgi:app
```

TLS certificates, network policy, secret delivery, monitoring, log retention,
and deployment health-check policy are external deployment responsibilities.

## Security behavior and boundaries

- Passwords are hashed using Werkzeug's password helpers. The configured
  minimum password length cannot be lower than 12 characters.
- Login and registration requests are rate limited by client address and
  identity. Redis makes these counters shared across production workers.
- Logout and password changes revoke identity-wide sessions. Refresh tokens are
  rotated, and disabled/deleted users have their sessions revoked by the
  relevant flows.
- User listing and management requires the `admin` role. Role checks read from
  the primary database. The API prevents ordinary last-admin removal, but the
  count-then-update safeguard is not atomic under concurrent requests.
- Responses include request IDs and security headers; authentication and
  account changes emit audit-oriented log events. Logs do not replace a
  dedicated audit pipeline or access/retention controls.
- Email verification, password reset, MFA, application-specific authorization,
  and production integration testing against real PostgreSQL/MySQL/MongoDB and
  Redis services are not included.
- The app creates missing relational tables but does not manage changes to
  existing schemas or data. Coordinate model/schema changes with your database
  operator before deploying updated application code.
