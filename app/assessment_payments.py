"""Unlock tenant assignments against trusted platform payment records."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_permission
from app.db.platform import get_platform_connection
from app.db.tenant import get_tenant_connection

router = APIRouter(prefix='/assessment-assignments', tags=['Assessment payments'])


class PaymentConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payment_id: UUID


class AssessmentConsent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    granted: bool
    consent_version: str = Field(min_length=1, max_length=50)
    consent_text: str = Field(min_length=1, max_length=10000)


def locked_assignment(cur, assignment_id, user):
    if user.role not in {'DOCTOR', 'PATIENT'}:
        raise HTTPException(403, 'Doctor or patient account required.')
    cur.execute('''SELECT a.*, (a.expires_at IS NOT NULL AND a.expires_at <= NOW()) AS expired
        FROM assessment_assignments a
        JOIN patients p ON p.id=a.patient_id
        JOIN doctors d ON d.id=a.doctor_id
        WHERE a.id=%s AND p.status='ACTIVE'
          AND ((%s='PATIENT' AND p.user_id=%s) OR
               (%s='DOCTOR' AND d.user_id=%s AND d.status='ACTIVE'))
        FOR UPDATE OF a''', (assignment_id, user.role, user.user_id, user.role, user.user_id))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(404, 'Assigned assessment not found.')
    if row['expired'] or row['assignment_status'] not in {'PENDING_PAYMENT', 'ASSIGNED', 'IN_PROGRESS'}:
        raise HTTPException(409, 'Assignment is expired or closed.')
    return row


def refresh_access(cur, assignment):
    # Never silently reactivate an explicitly revoked or expired access record.
    cur.execute('''INSERT INTO assessment_access (assignment_id, patient_id)
        VALUES (%s,%s) ON CONFLICT (assignment_id) DO NOTHING''',
        (assignment['id'], assignment['patient_id']))
    cur.execute('''UPDATE assessment_access x SET
        payment_verified_at=CASE WHEN NOT a.payment_required OR a.payment_completed_at IS NOT NULL
            THEN COALESCE(x.payment_verified_at,NOW()) ELSE NULL END,
        consent_verified_at=(SELECT CASE WHEN c.granted AND c.revoked_at IS NULL THEN c.granted_at END FROM consents c
            JOIN patients p ON p.id=c.patient_id AND p.user_id=c.user_id
            WHERE c.assignment_id=a.id AND c.patient_id=a.patient_id
              AND c.consent_type='ASSESSMENT_CONSENT'
            ORDER BY c.created_at DESC, c.id DESC LIMIT 1), updated_at=NOW()
        FROM assessment_assignments a WHERE x.assignment_id=a.id AND a.id=%s
          AND x.status IN ('PENDING','ACTIVE') AND x.revoked_at IS NULL''', (assignment['id'],))
    cur.execute('''UPDATE assessment_access SET status='ACTIVE',
        access_granted_at=COALESCE(access_granted_at,NOW()), updated_at=NOW()
        WHERE assignment_id=%s AND status='PENDING' AND revoked_at IS NULL
          AND payment_verified_at IS NOT NULL AND consent_verified_at IS NOT NULL
          AND (access_expires_at IS NULL OR access_expires_at>NOW())''', (assignment['id'],))
    cur.execute('''SELECT a.id AS assignment_id, a.assignment_status,
        CASE WHEN NOT a.payment_required THEN 'NOT_REQUIRED'
             WHEN a.payment_completed_at IS NOT NULL THEN 'PAID' ELSE 'PENDING' END AS payment_status,
        a.payment_completed_at, x.status AS access_status,
        x.consent_verified_at IS NOT NULL AS consent_completed
        FROM assessment_assignments a JOIN assessment_access x ON x.assignment_id=a.id
        WHERE a.id=%s''', (assignment['id'],))
    return cur.fetchone()


@router.post('/{assignment_id}/payment/confirm')
def confirm_payment(assignment_id: UUID, request: PaymentConfirmation,
                    user=Depends(require_permission('ASSESSMENT_VIEW'))):
    # Keep the trusted payment locked until the tenant transaction commits.
    with get_platform_connection() as platform:
        with platform.cursor(row_factory=dict_row) as payments:
            payments.execute('''SELECT * FROM platform_payments
                WHERE id=%s AND tenant_id=%s FOR UPDATE''', (request.payment_id, user.tenant.tenant_id))
            payment = payments.fetchone()
            if payment is None:
                raise HTTPException(404, 'Payment not found.')
            if payment['status'] != 'PAID' or payment['paid_at'] is None:
                raise HTTPException(409, 'Payment has not been confirmed as paid.')
            with get_tenant_connection(user.tenant) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    assignment = locked_assignment(cur, assignment_id, user)
                    for field in ('assignment_id', 'patient_id', 'doctor_id', 'assessment_id', 'assessment_version_id'):
                        expected = assignment['id'] if field == 'assignment_id' else assignment[field]
                        if payment[field] != expected:
                            raise HTTPException(409, 'Payment does not match this assignment.')
                    cur.execute('''SELECT platform_payment_id FROM assessment_payment_history
                        WHERE assignment_id=%s AND payment_event='PAYMENT_SUCCESSFUL' ''', (assignment_id,))
                    previous = cur.fetchall()
                    if any(row['platform_payment_id'] != request.payment_id for row in previous):
                        raise HTTPException(409, 'Assignment already has a different successful payment.')
                    if not previous:
                        cur.execute('''INSERT INTO assessment_payment_history
                            (assignment_id,payment_event,platform_payment_id,razorpay_order_id,
                             razorpay_payment_id,currency,amount,event_at)
                            VALUES (%s,'PAYMENT_SUCCESSFUL',%s,%s,%s,%s,%s,%s)''',
                            (assignment_id, request.payment_id, payment['razorpay_order_id'],
                             payment['razorpay_payment_id'], payment['currency'], payment['amount'], payment['paid_at']))
                    cur.execute('''UPDATE assessment_assignments SET
                        payment_completed_at=COALESCE(payment_completed_at,%s),
                        assignment_status=CASE WHEN assignment_status='PENDING_PAYMENT'
                            THEN 'ASSIGNED'::assignment_status ELSE assignment_status END,
                        updated_at=NOW() WHERE id=%s''', (payment['paid_at'], assignment_id))
                    return refresh_access(cur, assignment)


@router.post('/{assignment_id}/consent')
def consent(assignment_id: UUID, request: AssessmentConsent,
            user=Depends(require_permission('ASSESSMENT_VIEW'))):
    if user.role != 'PATIENT':
        raise HTTPException(403, 'Only the patient can give consent.')
    if not request.granted:
        raise HTTPException(422, 'Explicit consent is required to activate assessment access.')
    with get_tenant_connection(user.tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            assignment = locked_assignment(cur, assignment_id, user)
            cur.execute('''INSERT INTO consents
                (user_id,patient_id,consent_type,consent_version,granted,consent_text,granted_at,assignment_id)
                VALUES (%s,%s,'ASSESSMENT_CONSENT',%s,TRUE,%s,NOW(),%s)''',
                (user.user_id, assignment['patient_id'], request.consent_version, request.consent_text, assignment_id))
            return refresh_access(cur, assignment)
