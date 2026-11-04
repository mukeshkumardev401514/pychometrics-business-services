# Database resource API coverage

Generated with `python scripts/export_resource_docs.py`. Every table is listed below.

Platform token: `/platform/auth/login`. Tenant token: `/auth/login`.
Keys are UUIDs, except migration versions and comma-separated composite keys in the listed order.

| Database | Table | Key | Administrative operations | Tenant operations | Source |
| --- | --- | --- | --- | --- | --- |
| platform | `schema_migrations` | `version` | GET | — | `psychometric-db-models/platform/V000__migration_history.sql` |
| platform | `platform_users` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V003__platform_users.sql` |
| platform | `tenants` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V004__tenants.sql` |
| platform | `tenant_domains` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V005__tenant_domains.sql` |
| platform | `tenant_database_config` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V006__tenant_database_config.sql` |
| platform | `tenant_provisioning_history` | `id` | GET | — | `psychometric-db-models/platform/V007__tenant_provisioning_history.sql` |
| platform | `assessments` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V009__assessments.sql` |
| platform | `assessment_versions` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V010__assessment_versions.sql` |
| platform | `assessment_sections` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V011__assessment_sections.sql` |
| platform | `questions` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V012__questions.sql` |
| platform | `question_options` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V013__question_options.sql` |
| platform | `assessment_dimensions` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V014__assessment_dimensions.sql` |
| platform | `question_option_scores` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V015__question_option_scores.sql` |
| platform | `scoring_rules` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V016__scoring_rules.sql` |
| platform | `assessment_pricing` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V017__assessment_pricing.sql` |
| platform | `assessment_categories` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V018__assessment_categories.sql` |
| platform | `subscription_plans` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V021__subscription_plans.sql` |
| platform | `tenant_subscriptions` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V022__tenant_subscriptions.sql` |
| platform | `platform_payments` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V023__platform_payments.sql` |
| platform | `payment_events` | `id` | GET | — | `psychometric-db-models/platform/V024__payment_events.sql` |
| platform | `payment_refunds` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V025__payment_refunds.sql` |
| platform | `doctor_payout_accounts` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V026__doctor_payout_accounts.sql` |
| platform | `payout_batches` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V027__payout_batches.sql` |
| platform | `doctor_payouts` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V028__doctor_payouts.sql` |
| platform | `doctor_payout_items` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/platform/V029__doctor_payout_items.sql` |
| tenant | `schema_migrations` | `version` | GET | — | `psychometric-db-models/tenant/V000__migration_history.sql` |
| tenant | `roles` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/tenant/V002__roles_permissions.sql` |
| tenant | `permissions` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/tenant/V002__roles_permissions.sql` |
| tenant | `role_permissions` | `role_id,permission_id` | POST, GET, DELETE | — | `psychometric-db-models/tenant/V002__roles_permissions.sql` |
| tenant | `users` | `id` | POST, GET, PATCH, DELETE | — | `psychometric-db-models/tenant/V003__users.sql` |
| tenant | `user_roles` | `user_id,role_id` | POST, GET, DELETE | — | `psychometric-db-models/tenant/V003__users.sql` |
| tenant | `user_otp_verifications` | `id` | GET | — | `psychometric-db-models/tenant/V003__users.sql` |
| tenant | `doctors` | `id` | POST, GET, PATCH, DELETE | GET, PATCH, DELETE | `psychometric-db-models/tenant/V004__doctors.sql` |
| tenant | `patients` | `id` | POST, GET, PATCH, DELETE | GET, PATCH, DELETE | `psychometric-db-models/tenant/V005__patients.sql` |
| tenant | `doctor_patients` | `id` | POST, GET, PATCH, DELETE | GET, PATCH, DELETE | `psychometric-db-models/tenant/V006__doctor_patients.sql` |
| tenant | `assessment_assignments` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V007__assessment_assignments.sql` |
| tenant | `assessment_attempts` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V008__assessment_attempts.sql` |
| tenant | `assessment_answers` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V009__assessment_answers.sql` |
| tenant | `assessment_results` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V010__assessment_results.sql` |
| tenant | `assessment_result_dimensions` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V011__assessment_result_dimensions.sql` |
| tenant | `followups` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V012__followups.sql` |
| tenant | `notifications` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V013__notifications.sql` |
| tenant | `consents` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V014__consents.sql` |
| tenant | `audit_logs` | `id` | GET | — | `psychometric-db-models/tenant/V015__audit_logs.sql` |
| tenant | `tenant_settings` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V016__tenant_settings.sql` |
| tenant | `user_settings` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V017__user_settings.sql` |
| tenant | `password_reset_tokens` | `id` | GET | — | `psychometric-db-models/tenant/V018__password_reset_tokens.sql` |
| tenant | `organization_profile` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V019__organization_profile.sql` |
| tenant | `departments` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V020__departments.sql` |
| tenant | `doctor_departments` | `doctor_id,department_id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V020__departments.sql` |
| tenant | `assessment_access` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V021__assessment_access.sql` |
| tenant | `doctor_availability` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V022__doctor_availability.sql` |
| tenant | `appointments` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V023__appointments.sql` |
| tenant | `notification_preferences` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V024__notification_preferences.sql` |
| tenant | `assessment_reports` | `id` | POST, GET, PATCH, DELETE | GET | `psychometric-db-models/tenant/V025__assessment_reports.sql` |
| tenant | `assessment_retry_history` | `id` | GET | GET | `psychometric-db-models/tenant/V026__assessment_retry_history.sql` |
| tenant | `clinical_notes` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V027__clinical_notes.sql` |
| tenant | `patient_documents` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V028__patient_documents.sql` |
| tenant | `doctor_patient_messages` | `id` | POST, GET, PATCH, DELETE | POST, GET, PATCH, DELETE | `psychometric-db-models/tenant/V029__doctor_patient_messages.sql` |
| tenant | `patient_timeline_events` | `id` | GET | GET | `psychometric-db-models/tenant/V030__patient_timeline_events.sql` |
| tenant | `consent_history` | `id` | GET | GET | `psychometric-db-models/tenant/V031__consent_history.sql` |
| tenant | `assessment_payment_history` | `id` | GET | GET | `psychometric-db-models/tenant/V032__assessment_payment_history.sql` |
| tenant | `assessment_access_audit` | `id` | GET | GET | `psychometric-db-models/tenant/V033__assessment_access_audit.sql` |

GET includes list and detail. DELETE archives doctor/patient profiles and refuses referenced records.
Platform assessment catalog, tenants, payments and tenant assignments have DELETE routes that return 409; use status updates because their cross-database references cannot cascade safely.
History, migration bookkeeping and authentication challenge tables are read-only. Existing doctor/patient creation routes retain their transactional behavior.
Tenant methods additionally enforce role, permission and ownership checks; see `docs/resource-api.md`.

## Migration file inventory

| File | Tables declared |
| --- | --- |
| `psychometric-db-models/platform/V000__migration_history.sql` | platform.schema_migrations |
| `psychometric-db-models/platform/V001__extensions.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/platform/V002__enums.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/platform/V003__platform_users.sql` | platform.platform_users |
| `psychometric-db-models/platform/V004__tenants.sql` | platform.tenants |
| `psychometric-db-models/platform/V005__tenant_domains.sql` | platform.tenant_domains |
| `psychometric-db-models/platform/V006__tenant_database_config.sql` | platform.tenant_database_config |
| `psychometric-db-models/platform/V007__tenant_provisioning_history.sql` | platform.tenant_provisioning_history |
| `psychometric-db-models/platform/V008__assessment_enums.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/platform/V009__assessments.sql` | platform.assessments |
| `psychometric-db-models/platform/V010__assessment_versions.sql` | platform.assessment_versions |
| `psychometric-db-models/platform/V011__assessment_sections.sql` | platform.assessment_sections |
| `psychometric-db-models/platform/V012__questions.sql` | platform.questions |
| `psychometric-db-models/platform/V013__question_options.sql` | platform.question_options |
| `psychometric-db-models/platform/V014__assessment_dimensions.sql` | platform.assessment_dimensions |
| `psychometric-db-models/platform/V015__question_option_scores.sql` | platform.question_option_scores |
| `psychometric-db-models/platform/V016__scoring_rules.sql` | platform.scoring_rules |
| `psychometric-db-models/platform/V017__assessment_pricing.sql` | platform.assessment_pricing |
| `psychometric-db-models/platform/V018__assessment_categories.sql` | platform.assessment_categories |
| `psychometric-db-models/platform/V019__add_category_to_assessments.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/platform/V020__financial_enums.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/platform/V021__subscription_plans.sql` | platform.subscription_plans |
| `psychometric-db-models/platform/V022__tenant_subscriptions.sql` | platform.tenant_subscriptions |
| `psychometric-db-models/platform/V023__platform_payments.sql` | platform.platform_payments |
| `psychometric-db-models/platform/V024__payment_events.sql` | platform.payment_events |
| `psychometric-db-models/platform/V025__payment_refunds.sql` | platform.payment_refunds |
| `psychometric-db-models/platform/V026__doctor_payout_accounts.sql` | platform.doctor_payout_accounts |
| `psychometric-db-models/platform/V027__payout_batches.sql` | platform.payout_batches |
| `psychometric-db-models/platform/V028__doctor_payouts.sql` | platform.doctor_payouts |
| `psychometric-db-models/platform/V029__doctor_payout_items.sql` | platform.doctor_payout_items |
| `psychometric-db-models/platform/V030__assessment_metadata.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/seed/platform/V001__assessment_categories.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/seed/platform/V003__sample_financial_data.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/tenant/V000__migration_history.sql` | tenant.schema_migrations |
| `psychometric-db-models/tenant/V001__enums.sql` | Enums, extension, alteration or seed data; no separate table endpoint |
| `psychometric-db-models/tenant/V002__roles_permissions.sql` | tenant.roles, tenant.permissions, tenant.role_permissions |
| `psychometric-db-models/tenant/V003__users.sql` | tenant.users, tenant.user_roles, tenant.user_otp_verifications |
| `psychometric-db-models/tenant/V004__doctors.sql` | tenant.doctors |
| `psychometric-db-models/tenant/V005__patients.sql` | tenant.patients |
| `psychometric-db-models/tenant/V006__doctor_patients.sql` | tenant.doctor_patients |
| `psychometric-db-models/tenant/V007__assessment_assignments.sql` | tenant.assessment_assignments |
| `psychometric-db-models/tenant/V008__assessment_attempts.sql` | tenant.assessment_attempts |
| `psychometric-db-models/tenant/V009__assessment_answers.sql` | tenant.assessment_answers |
| `psychometric-db-models/tenant/V010__assessment_results.sql` | tenant.assessment_results |
| `psychometric-db-models/tenant/V011__assessment_result_dimensions.sql` | tenant.assessment_result_dimensions |
| `psychometric-db-models/tenant/V012__followups.sql` | tenant.followups |
| `psychometric-db-models/tenant/V013__notifications.sql` | tenant.notifications |
| `psychometric-db-models/tenant/V014__consents.sql` | tenant.consents |
| `psychometric-db-models/tenant/V015__audit_logs.sql` | tenant.audit_logs |
| `psychometric-db-models/tenant/V016__tenant_settings.sql` | tenant.tenant_settings |
| `psychometric-db-models/tenant/V017__user_settings.sql` | tenant.user_settings |
| `psychometric-db-models/tenant/V018__password_reset_tokens.sql` | tenant.password_reset_tokens |
| `psychometric-db-models/tenant/V019__organization_profile.sql` | tenant.organization_profile |
| `psychometric-db-models/tenant/V020__departments.sql` | tenant.departments, tenant.doctor_departments |
| `psychometric-db-models/tenant/V021__assessment_access.sql` | tenant.assessment_access |
| `psychometric-db-models/tenant/V022__doctor_availability.sql` | tenant.doctor_availability |
| `psychometric-db-models/tenant/V023__appointments.sql` | tenant.appointments |
| `psychometric-db-models/tenant/V024__notification_preferences.sql` | tenant.notification_preferences |
| `psychometric-db-models/tenant/V025__assessment_reports.sql` | tenant.assessment_reports |
| `psychometric-db-models/tenant/V026__assessment_retry_history.sql` | tenant.assessment_retry_history |
| `psychometric-db-models/tenant/V027__clinical_notes.sql` | tenant.clinical_notes |
| `psychometric-db-models/tenant/V028__patient_documents.sql` | tenant.patient_documents |
| `psychometric-db-models/tenant/V029__doctor_patient_messages.sql` | tenant.doctor_patient_messages |
| `psychometric-db-models/tenant/V030__patient_timeline_events.sql` | tenant.patient_timeline_events |
| `psychometric-db-models/tenant/V031__consent_history.sql` | tenant.consent_history |
| `psychometric-db-models/tenant/V032__assessment_payment_history.sql` | tenant.assessment_payment_history |
| `psychometric-db-models/tenant/V033__assessment_access_audit.sql` | tenant.assessment_access_audit |
