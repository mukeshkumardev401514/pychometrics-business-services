import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from tests.test_doctors import app
from fastapi import HTTPException
from app.assessment_payments import confirm_payment, consent, PaymentConfirmation, AssessmentConsent


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(role='PATIENT', user_id=uuid4(), tenant=SimpleNamespace(tenant_id=uuid4()))
        self.assignment = dict(id=uuid4(), patient_id=uuid4(), doctor_id=uuid4(),
                               assessment_id=uuid4(), assessment_version_id=uuid4(),
                               expired=False, assignment_status='PENDING_PAYMENT')
        self.payment = dict(self.assignment, assignment_id=self.assignment['id'], status='PAID',
                            paid_at=datetime.now(timezone.utc), razorpay_order_id='order_test',
                            razorpay_payment_id='pay_test', amount=100, currency='INR')
        self.request = PaymentConfirmation(payment_id=uuid4())
        self.platform_patch = patch('app.assessment_payments.get_platform_connection')
        self.tenant_patch = patch('app.assessment_payments.get_tenant_connection')
        self.platform = self.platform_patch.start().return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.tenant_connection = self.tenant_patch.start()
        self.cur = self.tenant_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.addCleanup(self.platform_patch.stop)
        self.addCleanup(self.tenant_patch.stop)
        self.platform.fetchone.return_value = self.payment
        self.cur.fetchone.return_value = self.assignment
        self.cur.fetchall.return_value = []

    def test_unpaid_payment_cannot_unlock(self):
        self.payment['status'] = 'PENDING'
        with self.assertRaises(HTTPException) as error:
            confirm_payment(self.assignment['id'], self.request, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.tenant_connection.assert_not_called()

    def test_foreign_assignment_denied(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(HTTPException) as error:
            confirm_payment(self.assignment['id'], self.request, self.user)
        self.assertEqual(error.exception.status_code, 404)

    def test_mismatched_payment_denied(self):
        self.payment['patient_id'] = uuid4()
        with self.assertRaises(HTTPException) as error:
            confirm_payment(self.assignment['id'], self.request, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(any(call.args[0].lstrip().startswith('UPDATE') for call in self.cur.execute.call_args_list))

    def test_paid_confirmation_records_once_on_retry(self):
        with patch('app.assessment_payments.refresh_access', return_value={'payment_status': 'PAID'}):
            self.assertEqual(confirm_payment(self.assignment['id'], self.request, self.user)['payment_status'], 'PAID')
            self.assertTrue(any('INSERT INTO assessment_payment_history' in c.args[0] for c in self.cur.execute.call_args_list))
            self.cur.execute.reset_mock()
            self.cur.fetchall.return_value = [{'platform_payment_id': self.request.payment_id}]
            confirm_payment(self.assignment['id'], self.request, self.user)
            self.assertFalse(any('INSERT INTO assessment_payment_history' in c.args[0] for c in self.cur.execute.call_args_list))

    def test_closed_assignment_denied(self):
        self.assignment['assignment_status'] = 'CANCELLED'
        with self.assertRaises(HTTPException) as error:
            confirm_payment(self.assignment['id'], self.request, self.user)
        self.assertEqual(error.exception.status_code, 409)

    def test_doctor_cannot_consent_for_patient(self):
        self.user.role = 'DOCTOR'
        with self.assertRaises(HTTPException) as error:
            consent(self.assignment['id'], AssessmentConsent(granted=True, consent_version='1', consent_text='I agree'), self.user)
        self.assertEqual(error.exception.status_code, 403)
        self.tenant_connection.assert_not_called()

    def test_payment_cannot_be_claimed_in_request(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PaymentConfirmation(payment_id=uuid4(), status='PAID')
