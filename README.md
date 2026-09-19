# Psychometric Business Services

FastAPI backend with tenant database authentication and permission checks.

## Doctor Management

Use `/auth/login` to obtain a token, then send `Authorization: Bearer <access_token>`.
Interactive API documentation is available at `/docs` while the server is running.

| Method | Path | Permission | Success |
| --- | --- | --- | --- |
| POST | `/doctors` | `DOCTOR_CREATE` | 201 |
| GET | `/doctors?limit=20&offset=0` | `DOCTOR_VIEW` | 200 |
| GET | `/doctors/{doctor_id}` | `DOCTOR_VIEW` | 200 |
| PATCH | `/doctors/{doctor_id}` | `DOCTOR_UPDATE` | 200 |

Create example (replace the example password):

```json
{
  "email": "doctor@example.com",
  "password": "replace-with-a-strong-password",
  "first_name": "Anita",
  "last_name": "Sharma",
  "doctor_code": "DOC-001",
  "specialization": "Psychiatry",
  "experience_years": 5
}
```

Creation saves the user, hashed password, DOCTOR role assignment and doctor profile
in one transaction. Responses exclude passwords and password hashes. All operations
use the authenticated tenant's database. List responses contain `items`, `limit`
and `offset` (limit 1–100).

PATCH accepts profile fields, email, first name and status (`ACTIVE`, `INACTIVE`,
`LOCKED`). Omitted fields remain unchanged; nullable profile fields can be cleared
with null. Status updates both user and doctor so inactive accounts cannot log in.
Doctor code, password and verification fields cannot be changed through PATCH.

Errors: missing authentication 401, denied permission 403, missing doctor 404,
duplicate email/mobile/doctor code 409, invalid input 422, missing DOCTOR role 503.

Requires the existing tenant migrations in the local `psychometric-db-models/`
folder, including users, roles, permissions, user_roles and doctors. No database
migration is applied by this service change. Existing email uniqueness is case
sensitive in that schema; APIs normalize emails and check existing emails without
case sensitivity. Other database writers should also normalize email addresses.

Permissions are checked against the token's effective role. Only DOCTOR tokens can create patients, even if another role has PATIENT_CREATE. No temporary `/test/*`
routes are installed.

## Verification

```bash
.venv/bin/python -m unittest discover -v
```

Tests exercise the ASGI API and mock database connections, covering authorization,
validation, missing records, password hashing, role assignment, rollback propagation
and status synchronization. They do not verify a running PostgreSQL instance.

## Login and account boundaries

All roles use `POST /auth/login` with tenant_code, email and password. Every
successful login issues a distinct JWT tied to that user, tenant and effective
role (HOSPITAL_ADMIN, DOCTOR or PATIENT). Send it as `Authorization: Bearer <token>`
on subsequent business APIs. Expiry is configured by
`JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 30); `expires_in` is in seconds.
Log in again after expiry. Login and `/health` are public; database/debug
inspection routes are not exposed.

Permissions are checked for the JWT role only, and each request rechecks the
active account, assigned role and active tenant. Tokens from another role do
not confer its permissions.

- Hospital doctor creation: `POST /doctors` requires a HOSPITAL_ORGANIZATION tenant,
  HOSPITAL_ADMIN token and DOCTOR_CREATE permission.
- Individual doctor: provision the tenant and DOCTOR login account first.
  After login, `POST /doctors/me` creates a profile for that same user in an
  INDIVIDUAL_DOCTOR tenant, using PROFILE_UPDATE permission. Supply doctor_code
  and optional profile fields; do not supply email, password or user_id.
  `PATCH /doctors/me` updates their own profile, excluding account status.
  `GET /doctors/me` reads the logged-in doctor's profile using PROFILE_VIEW.
  Public signup/account provisioning is not implemented here.
- Patient creation: `POST /patients` requires a DOCTOR token and PATIENT_CREATE
  in either tenant type. It creates patient credentials and links the patient
  to the authenticated active doctor. The patient then logs in separately with
  their own credentials to obtain a PATIENT token.

Patient-specific assessment/profile APIs are not implemented yet; `/auth/me`
returns the authenticated account for all three roles.

## Complete database resource APIs

See [resource API guide](docs/resource-api.md) and
[per-table coverage](docs/database-api-coverage.md) for all 63 tables.
The [Postman collection](postman/psychometrics-all-apis.postman_collection.json)
includes existing workflows, platform login, platform resources, tenant maintenance
and tenant business resource requests. Separate platform authentication is required
for platform and maintenance operations.
