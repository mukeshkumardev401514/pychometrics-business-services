# Database resource APIs

The migration catalog contains 25 platform tables and 38 tenant tables. See
[the complete table and migration inventory](database-api-coverage.md) for every
endpoint and supported operation. Swagger at `/docs` includes concrete request
schemas for each resource, including enums, UUIDs, lengths, decimal precision,
required fields and nullable PATCH fields.

## Authentication and routes

| API family | Token | Purpose |
| --- | --- | --- |
| `/data/<table-name>` | Existing tenant JWT from `/auth/login` | Tenant business operations with role, permission and ownership checks |
| `/platform/data/<table-name>` | Platform JWT from `/platform/auth/login` | Platform administration |
| `/platform/tenants/{tenant_id}/data/<table-name>` | Platform JWT | Explicit tenant maintenance and account/RBAC administration |

Table names use hyphens in URLs: `assessment_assignments` becomes
`assessment-assignments`. Each mutable resource has POST, GET list, GET detail,
PATCH and DELETE, with the exceptions described below. Lists accept `limit`
(1–100) and `offset` and return `{items, limit, offset}`.

Example: `/data/appointments/{uuid}`. Composite keys are comma-separated in SQL
primary-key order, e.g. `/platform/tenants/{tenant_id}/data/user-roles/{user_id},{role_id}`.
`role_permissions` and `user_roles` contain only key columns; replacing such a
relationship uses DELETE and POST, not PATCH. All foreign-key columns are
immutable on PATCH. Explicit null clears nullable fields; omission leaves fields
unchanged. Unknown and server-managed fields are rejected.

Platform login accepts `email` and `password`. It requires an existing ACTIVE
record in `platform_users`; the first account must be provisioned outside the API.
The schema has no platform role column: every active platform user is treated as
a platform operator. Platform tokens have a separate audience/type, use the
configured JWT expiry and cannot authenticate tenant APIs. Hospital-admin tokens
cannot authenticate platform APIs. Passwords supplied on platform/tenant user
creation or update are hashed. Hashes, OTP codes, reset/access token hashes,
payment signatures and secret references are not returned.

Platform maintenance is a trusted operator interface. Tenant users must use
`/data` or the existing workflow endpoints; possession of a hospital-admin token
never grants cross-tenant access.

## Tenant access

- Hospital admins manage organization profiles, departments, department mappings,
  tenant settings and doctor profiles. They can read operational patient,
  assignment, appointment and followup records in their tenant, but cannot create
  patients or read clinical results/notes through these resource routes.
- Doctors access their own doctor records and assigned patients. Clinical notes,
  appointments, availability, documents, messages and followups are scoped to the
  authenticated doctor. Patient reads require an active doctor-patient mapping.
- Patients see their own profile, assignments, attempts/answers, access records,
  followups, appointments, notifications, consents and conversations. They can
  manage their own settings/preferences/consents and authored messages.
- Settings/preferences/notifications are scoped to the logged-in user, including
  hospital admins. Message edits/deletes require the original sender.
- Assessment attempts, answers, access grants, scoring results and generated
  reports are maintenance-managed records. Tenant CRUD does not implement an
  assessment execution/payment-verification workflow or allow users to grant
  themselves access or write scores.
- Existing seeded permissions are checked where their resource group applies.
  New groups without a seeded permission use explicit role and ownership rules
  in `app/resources/policy.py`.

Use existing `/doctors`, `/doctors/me` and `/patients` for hospital doctor,
individual doctor and patient creation. These preserve the existing account,
password, role and primary-doctor transactions. `/data/doctors` and
`/data/patients` add profile-row read/update/archive operations; account fields
such as patient email/name are maintained through the privileged user resource.

## Relations and deletion

Declared foreign keys are checked in the selected database. Referenced records
must be accessible to the tenant caller. Additional checks compare repeated
patient, doctor, assignment, attempt, assessment and version IDs through parent
records, including option/question and dimension/version relationships. Clinical
records containing doctor and patient IDs require an active mapping.

Assessment/question/dimension/payment references crossing the database boundary
are checked explicitly. Payment/payout doctor and patient references are checked
in the referenced tenant. Payout accounts must match the payout's tenant/doctor.
All mutations and tenant audit writes commit in one local transaction. Cross-
database validation is not a distributed transaction; external database writers
must preserve these relationships too.

DELETE archives doctors/patients by setting both profile and user INACTIVE.
For other locally referenced records it returns 409 instead of cascading or
nulling relationships. Platform assessment catalog, tenants, payments and tenant
assignments refuse hard deletion because of cross-database references; use their
status fields where present. A doctor can cancel an assignment, but cannot mark
it paid/completed. Catalog components without status fields remain retained with
their parent assessment. Deleting a department mapping and recreating it is the
supported way to move a doctor to another department.

Migration bookkeeping, provisioning history, audit/history/event tables and
OTP/reset-token records are read-only, even for platform operators. History
rows are system evidence, not editable business objects. New tenant resource
mutations append audit logs; platform maintenance actions record the operator ID
in the audit description rather than falsely referencing a tenant user ID.
Domain history generation (payment events, assessment retries, etc.) still belongs
to its dedicated workflow; raw CRUD does not synthesize those events.

## Operational boundaries

These APIs manage database records. They do not execute payment/refund/payout
transactions, provision physical tenant databases, upload files, send messages
or notifications, generate reports or run scoring. Tenant registration via CRUD
creates metadata only; use the existing provisioning scripts for database setup.
Tenant database configuration changes require an application restart to clear
cached pools. File/document APIs manage metadata and storage keys only.

No existing migration files were changed or applied to configured databases.
The catalog compiler reads the checked-in migration format; after new migrations,
update its handling if the DDL syntax changes, regenerate the catalog and run
schema parity/integration tests before exposing new tables. Unlisted tenant
resources are denied by default.

## Verification and generated artifacts

```bash
.venv/bin/python scripts/build_resource_catalog.py
.venv/bin/python scripts/export_resource_docs.py
.venv/bin/python -m unittest discover -v
```

Integration tests create and remove a disposable UTF-8 PostgreSQL 18 cluster in
`/tmp`, using local Unix sockets and no production credentials. They apply all
platform/tenant schema migrations and verify every catalog column/primary key,
CRUD, constraints, ownership, platform login and related-record protection.
They skip when the PostgreSQL 18 test binaries are unavailable. The suite does
not execute financial seed data or contact payment/storage providers.
