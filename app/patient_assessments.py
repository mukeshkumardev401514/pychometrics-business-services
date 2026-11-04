"""Assignment-scoped patient content; scoring keys stay in the doctor/owner APIs."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row

from app.assessment_browser import fetch
from app.auth.dependencies import require_permission
from app.db.tenant import get_tenant_connection


def patient_user(user=Depends(require_permission('ASSESSMENT_VIEW'))):
    if user.role != 'PATIENT':
        raise HTTPException(403, 'Patient account required.')
    return user


router = APIRouter(prefix='/patient/assessments', tags=['Patient assessment content'])


@router.get('')
def assignments(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
                user=Depends(patient_user)):
    with get_tenant_connection(user.tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('''SELECT a.id AS assignment_id, a.assessment_id, a.assessment_version_id,
                a.assignment_status, a.assigned_at, a.expires_at, a.payment_required,
                a.payment_completed_at,
                CASE WHEN NOT a.payment_required THEN 'NOT_REQUIRED'
                     WHEN a.payment_completed_at IS NOT NULL THEN 'PAID'
                     ELSE 'PENDING' END AS payment_status,
                x.status AS access_status,
                x.consent_verified_at IS NOT NULL AS consent_completed
                FROM assessment_assignments a JOIN patients p ON p.id = a.patient_id
                LEFT JOIN assessment_access x ON x.assignment_id=a.id AND x.patient_id=a.patient_id
                WHERE p.user_id = %s AND p.status = 'ACTIVE'
                ORDER BY a.assigned_at DESC, a.id LIMIT %s OFFSET %s''', (user.user_id, limit, offset))
            return {'items': cur.fetchall(), 'limit': limit, 'offset': offset}


def accessible_assignment(user, assignment_id):
    with get_tenant_connection(user.tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('''SELECT a.assessment_id, a.assessment_version_id,
                (a.assignment_status IN ('ASSIGNED', 'IN_PROGRESS')
                 AND (a.expires_at IS NULL OR a.expires_at > NOW())
                 AND (NOT a.payment_required OR a.payment_completed_at IS NOT NULL)
                 AND x.status = 'ACTIVE' AND x.revoked_at IS NULL
                 AND x.payment_verified_at IS NOT NULL AND x.consent_verified_at IS NOT NULL
                 AND (x.access_granted_at IS NULL OR x.access_granted_at <= NOW())
                 AND (x.access_expires_at IS NULL OR x.access_expires_at > NOW())) IS TRUE AS allowed
                FROM assessment_assignments a JOIN patients p ON p.id = a.patient_id
                LEFT JOIN assessment_access x ON x.assignment_id = a.id AND x.patient_id = a.patient_id
                WHERE a.id = %s AND p.user_id = %s AND p.status = 'ACTIVE' ''',
                (assignment_id, user.user_id))
            item = cur.fetchone()
    if item is None:
        raise HTTPException(404, 'Assigned assessment not found.')
    if not item['allowed']:
        raise HTTPException(403, 'Assessment access is pending, revoked, expired or closed.')
    return item


@router.get('/{assignment_id}/questions')
def questions(assignment_id: UUID, limit: int = Query(100, ge=1, le=100),
              offset: int = Query(0, ge=0), user=Depends(patient_user)):
    assignment = accessible_assignment(user, assignment_id)
    # Bind both IDs: a stale/mismatched tenant reference cannot select another assessment.
    version = fetch('''SELECT v.id, a.name AS assessment_name, v.duration_minutes
        FROM assessment_versions v JOIN assessments a ON a.id = v.assessment_id
        WHERE v.id = %s AND a.id = %s AND v.status = 'PUBLISHED' AND a.status = 'PUBLISHED' ''',
        (assignment['assessment_version_id'], assignment['assessment_id']), one=True)
    if version is None:
        raise HTTPException(404, 'Published assessment version not found.')
    items = fetch('''SELECT q.id, q.display_order AS sr_no, q.question_text, q.question_type,
        q.is_required, s.id AS domain_id, s.name AS domain,
        COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'id', o.id, 'text', o.option_text, 'option_number', o.display_order)
            ORDER BY o.display_order, o.id)
            FROM question_options o WHERE o.question_id = q.id), '[]'::jsonb) AS options
        FROM questions q JOIN assessment_sections s ON s.id = q.assessment_section_id
        WHERE s.assessment_version_id = %s
        ORDER BY q.display_order, s.display_order, q.id LIMIT %s OFFSET %s''',
        (assignment['assessment_version_id'], limit, offset))
    return {'assignment_id': assignment_id, 'assessment': version,
            'items': items, 'limit': limit, 'offset': offset}
