import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from tests.test_doctors import app, request
from app.patient_assessments import patient_user
from app.assessment_browser import browser_identity
from fastapi import HTTPException


class PatientAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(user_id=uuid4(), tenant=object(), role='PATIENT')
        app.dependency_overrides[patient_user] = lambda: self.user
        self.addCleanup(app.dependency_overrides.clear)
        connection = patch('app.patient_assessments.get_tenant_connection')
        self.connection = connection.start()
        self.addCleanup(connection.stop)
        self.cur = self.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        fetch = patch('app.patient_assessments.fetch')
        self.fetch = fetch.start()
        self.addCleanup(fetch.stop)

    def test_foreign_or_missing_assignment_denied_before_platform_read(self):
        self.cur.fetchone.return_value = None
        self.assertEqual(asyncio.run(request('GET', f'/patient/assessments/{uuid4()}/questions')), 404)
        self.assertEqual(self.cur.execute.call_args.args[1][1], self.user.user_id)
        self.fetch.assert_not_called()

    def test_locked_assignment_denied(self):
        self.cur.fetchone.return_value = {'allowed': False}
        self.assertEqual(asyncio.run(request('GET', f'/patient/assessments/{uuid4()}/questions')), 403)
        query = self.cur.execute.call_args.args[0]
        for check in ['x.consent_verified_at IS NOT NULL', "x.status = 'ACTIVE'", 'a.payment_completed_at IS NOT NULL',
                      'a.expires_at > NOW()', 'x.access_expires_at > NOW()', 'x.revoked_at IS NULL']:
            self.assertIn(check, query)
        self.fetch.assert_not_called()

    def test_assigned_content_has_no_scoring_keys(self):
        assessment, version = uuid4(), uuid4()
        self.cur.fetchone.return_value = {'allowed': True, 'assessment_id': assessment, 'assessment_version_id': version}
        self.fetch.side_effect = [{'id': str(version)}, [{'id': str(uuid4()), 'options': []}]]
        response = {}
        self.assertEqual(asyncio.run(request('GET', f'/patient/assessments/{uuid4()}/questions',
                                            response_body=response)), 200)
        self.assertEqual(self.fetch.call_args_list[0].args[1], (version, assessment))
        query = self.fetch.call_args.args[0]
        for forbidden in ['question_option_scores', 'weightage', 'option_value', 'scoring_rules']:
            self.assertNotIn(forbidden, query)

    def test_authentication_required(self):
        app.dependency_overrides.clear()
        self.assertEqual(asyncio.run(request('GET', '/patient/assessments')), 401)
        self.assertEqual(asyncio.run(request('GET', f'/patient/assessments/{uuid4()}/questions')), 401)
        self.connection.assert_not_called()

    def test_browser_authenticator_verifies_platform_or_tenant_token(self):
        credentials = object()
        with patch('app.assessment_browser.get_platform_user') as owner, patch('app.assessment_browser.get_current_user') as tenant:
            owner.return_value = 'owner'
            self.assertEqual(browser_identity(credentials), 'owner')
            tenant.assert_not_called()
            owner.side_effect = HTTPException(401, 'Invalid platform token')
            tenant.return_value = self.user
            self.assertEqual(browser_identity(credentials), self.user)
            tenant.assert_called_once_with(credentials)
