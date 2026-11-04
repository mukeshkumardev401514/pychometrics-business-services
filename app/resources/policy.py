"""Explicit policies; unlisted tables never become tenant-accessible by default."""
from fastapi import HTTPException

# Migration bookkeeping, authentication challenges and immutable history are not
# mutable business records. Platform operators can inspect non-secret fields.
READ_ONLY = {'schema_migrations', 'user_otp_verifications', 'password_reset_tokens',
             'audit_logs', 'tenant_provisioning_history', 'patient_timeline_events',
             'consent_history', 'assessment_payment_history', 'assessment_access_audit',
             'assessment_retry_history', 'payment_events'}
# These have transactional account/profile creation APIs already.
PROFILE_TABLES = {'doctors', 'patients'}
# (read roles, write roles, permission prefix). None means role check suffices.
A, D, P = 'HOSPITAL_ADMIN', 'DOCTOR', 'PATIENT'
POLICIES = {
    'doctors': ({A, D}, {A}, 'DOCTOR'),
    'patients': ({A, D, P}, {D}, 'PATIENT'),
    'doctor_patients': ({A, D}, {D}, 'PATIENT'),
    'organization_profile': ({A, D}, {A}, None),
    'departments': ({A, D}, {A}, None),
    'doctor_departments': ({A, D}, {A}, None),
    'doctor_availability': ({A, D}, {D}, None),
    'assessment_assignments': ({A, D, P}, {D}, 'ASSESSMENT'),
    'assessment_attempts': ({D, P}, set(), 'ASSESSMENT'),
    'assessment_answers': ({D, P}, set(), 'ASSESSMENT'),
    'assessment_results': ({D}, set(), 'RESULT'),
    'assessment_result_dimensions': ({D}, set(), 'RESULT'),
    'assessment_reports': ({D}, set(), 'REPORT'),
    'assessment_access': ({D, P}, set(), 'ASSESSMENT'),
    'followups': ({A, D, P}, {D}, 'FOLLOWUP'),
    'appointments': ({A, D, P}, {D}, None),
    'clinical_notes': ({D}, {D}, None),
    'patient_documents': ({D}, {D}, None),
    'doctor_patient_messages': ({D, P}, {D, P}, None),
    'notifications': ({A, D, P}, set(), 'NOTIFICATION'),
    'consents': ({D, P}, {P}, 'CONSENT'),
    'user_settings': ({A, D, P}, {A, D, P}, 'PROFILE'),
    'notification_preferences': ({A, D, P}, {A, D, P}, 'PROFILE'),
    'tenant_settings': ({A}, {A}, None),
    'patient_timeline_events': ({D}, set(), None),
    'consent_history': ({D, P}, set(), 'CONSENT'),
    'assessment_payment_history': ({D, P}, set(), None),
    'assessment_access_audit': ({D}, set(), None),
    'assessment_retry_history': ({D, P}, set(), 'RETRY'),
}


def authorize(table, action, user, maintenance=False):
    if maintenance:
        if table in READ_ONLY and action not in ('list', 'get'):
            raise HTTPException(403, 'System-managed history or authentication data is read-only.')
        return
    policy = POLICIES.get(table)
    if policy is None:
        raise HTTPException(403, 'Platform administration required.')
    if user.role not in policy[0 if action in ('get', 'list') else 1]:
        raise HTTPException(403, 'Role cannot perform this operation.')
    if table in PROFILE_TABLES and action == 'create':
        raise HTTPException(403, 'Use the dedicated doctor or patient profile API.')
    if table == 'doctor_patients' and action == 'create':
        raise HTTPException(403, 'Patient creation assigns the authenticated doctor automatically.')


def permission_for(table, action, user):
    prefix = POLICIES[table][2]
    if table == 'doctors' and user.role == D: return 'PROFILE_VIEW'
    if table == 'patients' and user.role == P: return 'PROFILE_VIEW'
    if prefix is None: return None
    if action in ('list', 'get'): return prefix + '_VIEW'
    if prefix == 'ASSESSMENT': return 'ASSESSMENT_ASSIGN'
    if prefix == 'CONSENT': return 'CONSENT_MANAGE'
    if prefix == 'PROFILE': return 'PROFILE_UPDATE'
    return prefix + ('_CREATE' if action == 'create' else '_UPDATE')
