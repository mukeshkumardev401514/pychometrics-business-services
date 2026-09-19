import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from tests.test_doctors import app, get_current_user, request
from app.patients import service


class PatientTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(user_id=uuid4(), role='DOCTOR', tenant=object())
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.addCleanup(app.dependency_overrides.clear)
        permission = patch('app.auth.dependencies.get_tenant_connection')
        self.permission = permission.start().return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.addCleanup(permission.stop)
        self.permission.fetchone.return_value = (1,)
        connection = patch.object(service, 'get_tenant_connection')
        self.connection = connection.start()
        self.addCleanup(connection.stop)
        self.cur = self.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        hashing = patch.object(service, 'hash_password', return_value='hashed-secret')
        self.hashing = hashing.start()
        self.addCleanup(hashing.stop)
        self.body = {'email': 'Patient@example.com', 'password': 'Patient@123', 'first_name': 'Test', 'patient_code': 'PAT-1'}
        self.doctor_id, self.patient_id, self.user_id, self.role_id = uuid4(), uuid4(), uuid4(), uuid4()
        self.cur.fetchone.side_effect = [
            {'id': self.doctor_id}, {'id': self.role_id}, None, {'id': self.user_id},
            {'id': self.patient_id, 'status': 'ACTIVE', 'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc)},
        ]

    def call(self, body=None, response=None):
        return asyncio.run(request('POST', '/patients', self.body if body is None else body, response_body=response))

    def test_create_and_primary_assignment(self):
        response = {}
        self.assertEqual(self.call(response=response), 201)
        self.assertEqual(response['primary_doctor_id'], str(self.doctor_id))
        self.assertEqual(response['email'], 'patient@example.com')
        self.assertNotIn('password', response)
        self.assertNotIn('password_hash', response)
        self.connection.assert_called_once_with(self.user.tenant)
        calls = self.cur.execute.call_args_list
        self.assertEqual(calls[0].args[1], (self.user.user_id,))
        self.assertIn('hashed-secret', calls[3].args[1])
        self.assertEqual(calls[4].args[1], (self.user_id, self.role_id))
        self.assertEqual(calls[-1].args[1], (self.doctor_id, self.patient_id))
        self.assertIn('TRUE', calls[-1].args[0])
        self.assertEqual(self.permission.execute.call_args.args[1][1], 'PATIENT_CREATE')
        self.connection.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_admin_denied_even_with_permission(self):
        self.user.role = 'HOSPITAL_ADMIN'
        self.assertEqual(self.call(), 403)
        self.connection.assert_not_called()

    def test_missing_permission(self):
        self.permission.fetchone.return_value = None
        self.assertEqual(self.call(), 403)
        self.connection.assert_not_called()

    def test_missing_authentication(self):
        app.dependency_overrides.clear()
        self.assertEqual(self.call(), 401)

    def test_invalid_or_injected_fields(self):
        for extra in ({'doctor_id': str(uuid4())}, {'database_name': 'other'}, {'date_of_birth': '2999-01-01'}, {'gender': 'INVALID'}, {'patient_code': ' '}, {'password': 'short'}):
            with self.subTest(extra=extra):
                self.assertEqual(self.call({**self.body, **extra}), 422)
        self.connection.assert_not_called()

    def test_missing_active_doctor(self):
        self.cur.fetchone.side_effect = [None]
        self.assertEqual(self.call(), 403)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_missing_patient_role(self):
        self.cur.fetchone.side_effect = [{'id': self.doctor_id}, None]
        self.assertEqual(self.call(), 503)

    def test_duplicate_email(self):
        self.cur.fetchone.side_effect = [{'id': self.doctor_id}, {'id': self.role_id}, {'id': uuid4()}]
        self.assertEqual(self.call(), 409)
        self.assertEqual(self.cur.execute.call_count, 3)

    def test_assignment_failure_rolls_back(self):
        from psycopg.errors import UniqueViolation
        self.cur.execute.side_effect = [None] * 6 + [UniqueViolation('internal details')]
        response = {}
        self.assertEqual(self.call(response=response), 409)
        self.assertNotIn('internal details', str(response))
        self.assertIs(self.connection.return_value.__exit__.call_args.args[0], UniqueViolation)

    def test_database_error_hidden(self):
        from psycopg import OperationalError
        self.cur.execute.side_effect = OperationalError('private database details')
        response = {}
        self.assertEqual(self.call(response=response), 503)
        self.assertNotIn('private database', str(response))
