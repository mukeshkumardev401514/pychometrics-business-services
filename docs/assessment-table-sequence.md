# Assessment tables: setup se report tak

Ye logical workflow sequence hai. SQL migrations har database mein numeric
version order (V000, V001, ...) mein run hoti hain.
Neeche file paths `psychometric-db-models/` ke relative hain.

## 1. Platform database: assessment setup

| Order | Table | Purpose | SQL file |
|---|---|---|---|
| 1 | assessment_categories | Category, jaise Aggression | platform/V018__assessment_categories.sql |
| 2 | assessments | Assessment master, jaise BPAQ | platform/V009__assessments.sql |
| 3 | assessment_versions | Assessment ka version | platform/V010__assessment_versions.sql |
| 4 | assessment_sections | Version ke sections | platform/V011__assessment_sections.sql |
| 5 | questions | Section ke questions | platform/V012__questions.sql |
| 6 | question_options | Question ke answer options | platform/V013__question_options.sql |
| 7 | assessment_dimensions | Scoring domains/dimensions | platform/V014__assessment_dimensions.sql |
| 8 | question_option_scores | Option ka dimension-wise score | platform/V015__question_option_scores.sql |
| 9 | scoring_rules | Score range ki interpretation/recommendation | platform/V016__scoring_rules.sql |
| 10 | assessment_pricing | Version ki pricing | platform/V017__assessment_pricing.sql |

Category relation `platform/V019__add_category_to_assessments.sql` mein hai:
`assessments.category_id` references `assessment_categories.id`.

```text
assessment_categories
└── assessments
    └── assessment_versions
        ├── assessment_sections → questions → question_options
        ├── assessment_dimensions
        ├── question_option_scores ← options + dimensions
        ├── scoring_rules ← dimensions
        └── assessment_pricing
```

## 2. Tenant database: patient assessment flow

Prerequisite: `users` → `doctors` / `patients` → `doctor_patients`.

| Order | Table | Purpose | SQL file |
|---|---|---|---|
| 1 | assessment_assignments | Doctor patient ko assessment/version assign karta hai | tenant/V007__assessment_assignments.sql |
| 2 | assessment_access | Assessment access record | tenant/V021__assessment_access.sql |
| 3 | assessment_attempts | Patient ka attempt | tenant/V008__assessment_attempts.sql |
| 4 | assessment_answers | Attempt ke answers | tenant/V009__assessment_answers.sql |
| 5 | assessment_results | Calculated result | tenant/V010__assessment_results.sql |
| 6 | assessment_result_dimensions | Dimension-wise result | tenant/V011__assessment_result_dimensions.sql |
| 7 | assessment_reports | Generated report | tenant/V025__assessment_reports.sql |
| 8 | followups | Doctor ka follow-up | tenant/V012__followups.sql |

```text
Assignment → Access → Attempt → Answers
                                 ↓
                               Result
                                 ├── Dimension-wise results
                                 └── Report → Follow-up
```

Ye workflow illustration hai; har arrow direct foreign key nahi hai.
Platform aur tenant alag databases hain. Tenant ke `assessment_id`,
`assessment_version_id`, question aur option references par direct
cross-database foreign keys nahi hain.

## 3. Supporting tables

| Purpose | Database | Tables |
|---|---|---|
| Payment | Platform | platform_payments, payment_events, payment_refunds |
| Payment history | Tenant | assessment_payment_history |
| Retry | Tenant | assessment_retry_history |
| Consent | Tenant | consents, consent_history |
| Access tracking | Tenant | assessment_access_audit |
| Notifications/history | Tenant | notifications, patient_timeline_events, audit_logs |
| Clinical records | Tenant | clinical_notes, patient_documents, appointments, doctor_patient_messages |

## 4. BPAQ JSON ki current mapping

| Input key | Existing location |
|---|---|
| evaluation_id | assessments.code |
| evaluation_name | assessments.name |
| category | assessment_categories.name, linked through category_id |
| description | assessments.description |

Baaki requested metadata columns ke changes abhi apply nahi kiye gaye hain.
JSON mein missing values ke liye `null` use karein, `NaN` nahi.
