# All API collection

Import `psychometrics-all-apis.postman_collection.json` into Postman.
It includes the existing role workflows and all new database resource routes.
See `docs/database-api-coverage.md` for the complete per-table inventory.

1. Open the collection's Variables tab. Set `base_url` (default
   `http://localhost:8000`), `hospital_tenant_code`, and your admin credentials.
2. Set `doctor_email`, `doctor_password`, and a unique `doctor_code`. Run Hospital
   admin → Login, then Create hospital doctor. The token and doctor ID save automatically.
3. Run Hospital doctor → Login to use the doctor's own token. Set patient email,
   password and a unique patient code before Create patient.
4. For an individual doctor, set `individual_tenant_code`, `individual_email`,
   and `individual_password` for a provisioned DOCTOR account. Run Individual
   doctor → Login, then Create my doctor profile if a profile does not exist.
5. Set `patient_tenant_code` to the tenant where the patient was created, then
   run Patient → Login to obtain the patient's own token.

Every protected request already has the appropriate Bearer token variable.
Login again after expiry. Password variables are blank initially; use test
credentials and avoid sharing exports containing populated credentials/tokens.
Run the relevant workflow manually; running the entire collection creates records
in both tenant workflows, and repeated identifiers can produce 409 conflicts.

`doctors.postman_collection.json` is the older doctor-only collection. Use the
new all-API collection for the complete current workflow.

The collection was checked against source routes for complete coverage and valid
JSON/variables. Requests have not been run against a live database.

## Database resource folders

- **Platform authentication:** Set `platform_email` and `platform_password` for
  an existing active platform operator. Login saves `platform_token`.
- **Platform resources:** Use the platform token for the shared platform tables.
- **Tenant maintenance resources:** Set `maintenance_tenant_id`; requires a
  platform token, not a hospital admin token.
- **Tenant resource APIs:** The latest successful admin/doctor/patient login
  saves `resource_token`. Log in as the intended tenant role before using these.

`ref_*` variables are related record UUIDs and must be filled from actual records.
POST saves the resource key for GET/PATCH/DELETE; composite keys are stored in
primary-key order. Request bodies are templates, not a runnable end-to-end data
seed: populate required fields and valid linked IDs before sending. See
`docs/resource-api.md` for supported operations, ownership and delete behavior.

New CRUD functionality was tested against a disposable PostgreSQL database;
the Postman collection itself has not been executed against your running server.
