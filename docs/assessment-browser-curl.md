# Assessment browser curl commands

These browser APIs accept either a **doctor login token** with `ASSESSMENT_ASSIGN` permission
or a **platform owner token**. They include DRAFT/imported content and scoring weights.
Patients use separate assignment-scoped endpoints below.
The URL retains `/platform/assessment-browser` for compatibility.
Import `postman/assessment-browser.postman_collection.json` for the doctor workflow.

Apply platform migration `V031__assessment_subcategories.sql` before using these APIs
or the importers. Schema: category → optional sub-category → assessment → version →
domain (section) → sub-domain (dimension). Sub-domains are linked to domains through question scores.

In the XLSX Bio sheet (or JSON), add optional `assessment_subcategory` text.
The importer creates/reuses that sub-category inside the selected category.
Blank or missing `assessment_subcategory` clears the assessment's sub-category on re-import.
Existing assessments remain unassigned until imported or linked to a sub-category.

## 1. Login

```bash
BASE_URL='http://localhost:8000'
curl --fail-with-body -sS -X POST "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"tenant_code":"YOUR_TENANT_CODE","email":"doctor@example.com","password":"YOUR_PASSWORD"}'

# Copy access_token from the login response.
TOKEN='YOUR_DOCTOR_ACCESS_TOKEN'
API="$BASE_URL/platform/assessment-browser"
```

## 2. All categories

```bash
curl --fail-with-body -sS "$API/categories?limit=100&offset=0" -H "Authorization: Bearer $TOKEN"
```

## 3. Assessments inside a category

```bash
# Copy category id from step 2.
CATEGORY_ID='CATEGORY_UUID'
curl --fail-with-body -sS "$API/assessments?category_id=$CATEGORY_ID&limit=100&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

### Separate sub-categories and their assessments

```bash
curl --fail-with-body -sS "$API/sub-categories?limit=100&offset=0" \
  -H "Authorization: Bearer $TOKEN"
curl --fail-with-body -sS "$API/sub-categories?category_id=$CATEGORY_ID" \
  -H "Authorization: Bearer $TOKEN"
SUBCATEGORY_ID='SUBCATEGORY_UUID'
curl --fail-with-body -sS "$API/assessments?subcategory_id=$SUBCATEGORY_ID" \
  -H "Authorization: Bearer $TOKEN"

# Admin-only maintenance: use a separate platform login token.
PLATFORM_TOKEN='YOUR_PLATFORM_ADMIN_ACCESS_TOKEN'
# Create a sub-category using the platform data API.
curl --fail-with-body -sS -X POST "$BASE_URL/platform/data/assessment-subcategories" \
  -H "Authorization: Bearer $PLATFORM_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"category_id\":\"$CATEGORY_ID\",\"code\":\"SOCIAL_ANXIETY\",\"name\":\"Social Anxiety\"}"
```

## 4. All assessments / find imported assessment by Bio assessment_id

```bash
curl --fail-with-body -sS "$API/assessments?limit=100&offset=0" -H "Authorization: Bearer $TOKEN"
curl --fail-with-body -sS --get "$API/assessments" --data-urlencode 'code=PSY-0134' \
  -H "Authorization: Bearer $TOKEN"
```

## 5. Assessment metadata and all versions

```bash
# Copy assessment id from step 3 or 4.
ASSESSMENT_ID='ASSESSMENT_UUID'
curl --fail-with-body -sS "$API/assessments/$ASSESSMENT_ID" -H "Authorization: Bearer $TOKEN"
```

## 6. Version details, counts and pricing history

```bash
# Copy the desired version id from step 5 (not version_number).
VERSION_ID='VERSION_UUID'
curl --fail-with-body -sS "$API/versions/$VERSION_ID" -H "Authorization: Bearer $TOKEN"
```

## 7. Domains

```bash
curl --fail-with-body -sS "$API/versions/$VERSION_ID/domains?limit=100&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

## 8. All sub-domains / sub-domains of one domain

```bash
curl --fail-with-body -sS "$API/versions/$VERSION_ID/sub-domains?limit=100&offset=0" \
  -H "Authorization: Bearer $TOKEN"
DOMAIN_ID='DOMAIN_UUID'
curl --fail-with-body -sS "$API/versions/$VERSION_ID/sub-domains?domain_id=$DOMAIN_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## 9. Questions with nested options and weightage

```bash
curl --fail-with-body -sS "$API/versions/$VERSION_ID/questions?limit=100&offset=0" \
  -H "Authorization: Bearer $TOKEN"

# Filter questions by domain.
curl --fail-with-body -sS "$API/versions/$VERSION_ID/questions?domain_id=$DOMAIN_ID" \
  -H "Authorization: Bearer $TOKEN"

# Filter by sub-domain, or combine both filters.
SUB_DOMAIN_ID='SUB_DOMAIN_UUID'
curl --fail-with-body -sS "$API/versions/$VERSION_ID/questions?sub_domain_id=$SUB_DOMAIN_ID" \
  -H "Authorization: Bearer $TOKEN"
curl --fail-with-body -sS "$API/versions/$VERSION_ID/questions?domain_id=$DOMAIN_ID&sub_domain_id=$SUB_DOMAIN_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Lists return `items`, `limit`, and `offset`. Increase offset by limit until items is empty
to retrieve every page. Limit is 1–100 (default 100). Unknown version/domain/sub-domain
IDs in scoped endpoints return 404; malformed UUIDs or invalid pagination return 422.
An assessment lookup by code returns an empty list when no match exists.
Each question contains `options`; each option contains `scores` with `sub_domain_id`,
`sub_domain`, and `weightage`. Zero and negative weights are preserved.

After import, compare the version counts, Bio metadata, question text, option text and
weightage with Excel. These endpoints read data; they do not publish or modify it.

## Platform owner login (alternative to doctor login)

```bash
curl --fail-with-body -sS -X POST "$BASE_URL/platform/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.com","password":"YOUR_PASSWORD"}'
# Copy returned access_token into TOKEN, then use the same browser requests above.
```

## Doctor assigns an assessment

```bash
DOCTOR_TOKEN='YOUR_DOCTOR_TOKEN'
DOCTOR_ID='DOCTOR_UUID'
PATIENT_ID='PATIENT_UUID'
curl --fail-with-body -sS -X POST "$BASE_URL/data/assessment-assignments" \
  -H "Authorization: Bearer $DOCTOR_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"doctor_id\":\"$DOCTOR_ID\",\"patient_id\":\"$PATIENT_ID\",\"assessment_id\":\"$ASSESSMENT_ID\",\"assessment_version_id\":\"$VERSION_ID\"}"
```

The patient must be linked to the authenticated doctor. The existing assignment API
creates a PENDING_PAYMENT assignment. Assignment alone does not bypass payment/consent.

## Patient login and assigned assessment content

```bash
curl --fail-with-body -sS -X POST "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"tenant_code":"YOUR_TENANT_CODE","email":"patient@example.com","password":"YOUR_PASSWORD"}'
PATIENT_TOKEN='YOUR_PATIENT_ACCESS_TOKEN'
curl --fail-with-body -sS "$BASE_URL/patient/assessments?limit=100&offset=0" \
  -H "Authorization: Bearer $PATIENT_TOKEN"
ASSIGNMENT_ID='ASSIGNMENT_UUID'
curl --fail-with-body -sS "$BASE_URL/patient/assessments/$ASSIGNMENT_ID/questions?limit=100&offset=0" \
  -H "Authorization: Bearer $PATIENT_TOKEN"
```

Patients need `ASSESSMENT_VIEW` permission. They can list only their own assignments.
Questions require an ASSIGNED/IN_PROGRESS, unexpired assignment, completed payment when
required, and ACTIVE assessment_access for the same patient with payment/consent verified,
no revocation and a valid access window. The assessment and version must be PUBLISHED.
Foreign assignments return 404; pending/closed/revoked/expired access returns 403.
Patient options omit weightage, scoring rules, and internal option values.
These APIs read content; payment, consent verification, activation and answer submission
remain separate workflows.
