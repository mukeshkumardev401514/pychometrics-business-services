# Assessment assignment and payment

Use the tenant hostname and a doctor/patient Bearer token for tenant routes.

1. Doctor: `POST /data/assessment-assignments`

```json
{"doctor_id":"DOCTOR_UUID","patient_id":"PATIENT_UUID","assessment_id":"ASSESSMENT_UUID","assessment_version_id":"VERSION_UUID"}
```

The default is `PENDING_PAYMENT`; do not send system-managed status/payment fields.

2. Record an actual collected payment through the trusted platform workflow. Existing platform operator API: `POST /platform/data/platform-payments` (platform administrator token). Required fields include tenant_id, assessment_id, assessment_version_id, amount, doctor_percentage, platform_percentage, doctor_amount, platform_amount. Bind assignment_id, doctor_id, patient_id to the assignment. A settled record must have status `PAID` and paid_at. Never use this operator API from the patient UI or mark uncollected money as paid.

3. Doctor or patient: `POST /assessment-assignments/ASSIGNMENT_UUID/payment/confirm`

```json
{"payment_id":"PLATFORM_PAYMENT_UUID"}
```

Checks trusted platform payment status, tenant, assignment, doctor, patient and assessment version. Pending payments return 409. Foreign assignments return 404. Successful retries do not duplicate payment history. Returns assignment_status, payment_status, payment_completed_at, access_status, consent_completed. Payment confirmation moves PENDING_PAYMENT to ASSIGNED; it does not fabricate patient consent or reactivate revoked/expired access.

4. Patient, after displaying the consent text and obtaining agreement: `POST /assessment-assignments/ASSIGNMENT_UUID/consent`

```json
{"granted":true,"consent_version":"1.0","consent_text":"I consent to take this assessment."}
```

Consent can precede or follow confirmation. Access activates when both are verified. Store approved consent wording/version in the calling application. This route grants consent; existing consent management handles revocation.

5. Patient list: `GET /patient/assessments`. Includes payment_status (`PENDING`, `PAID`, `NOT_REQUIRED`), payment_completed_at, access_status, consent_completed, assessment and version IDs.

6. Patient questions: `GET /patient/assessments/ASSIGNMENT_UUID/questions`. Payment, consent, expiry and access checks remain enforced.

No database migration is required. This implements reconciliation against platform payment records, not Razorpay checkout, signature verification, or webhooks. Those gateway integrations still need to be connected before automatic online collection. No payment is charged by these endpoints.
