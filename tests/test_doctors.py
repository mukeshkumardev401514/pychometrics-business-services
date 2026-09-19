import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

os.environ.setdefault('JWT_SECRET', 'test-secret-that-is-at-least-32-characters')
with patch('psycopg_pool.ConnectionPool'):
    from app.main import app
    from app.auth.dependencies import get_current_user
    from app.doctors import service
    from app.doctors.schemas import DoctorCreate


async def request(method, path, body=None, query=b'', response_body=None, headers=None):
    messages = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {'type': 'http.disconnect'}
        received = True
        return {'type': 'http.request', 'body': json.dumps(body).encode() if body else b'', 'more_body': False}

    async def send(message):
        messages.append(message)

    await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
               'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
               'query_string': query, 'headers': [(b'content-type', b'application/json'), *(headers or [])],
               'client': ('127.0.0.1', 123), 'server': ('test', 80), 'root_path': ''}, receive, send)
    if response_body is not None:
        response_body.update(json.loads(b''.join(
            m.get('body', b'') for m in messages if m['type'] == 'http.response.body'
        )))
    return next(m['status'] for m in messages if m['type'] == 'http.response.start')


class DoctorTests(unittest.TestCase):
    def test_post_create_response(self):
        from datetime import datetime, timezone
        body = {'email': 'doc@example.com', 'password': 'password123',
                'first_name': 'Doctor', 'doctor_code': 'DOC-1'}
        doctor_id, user_id = uuid4(), uuid4()
        record = {key: value for key, value in body.items() if key != 'password'}
        record.update(id=doctor_id, user_id=user_id, status='ACTIVE',
                      is_verified=False, created_at=datetime.now(timezone.utc),
                      updated_at=datetime.now(timezone.utc))
        response = {}
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, 'hash_password', return_value='hashed'):
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [{'id': uuid4()}, None, {'id': user_id}, {'id': doctor_id}, record]
            self.assertEqual(asyncio.run(request('POST', '/doctors', body, response_body=response)), 201)
            connection.assert_called_once_with(self.user.tenant)
        self.assertEqual(response['id'], str(doctor_id))
        self.assertNotIn('password', response)
        self.assertNotIn('password_hash', response)
        self.assertEqual(self.cursor.execute.call_args.args[1][1], 'DOCTOR_CREATE')

    def test_post_missing_role(self):
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, 'hash_password', return_value='hashed'):
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = None
            body = {'email': 'doc@example.com', 'password': 'password123',
                    'first_name': 'Doctor', 'doctor_code': 'DOC-1'}
            self.assertEqual(asyncio.run(request('POST', '/doctors', body)), 503)
            self.assertEqual(cur.execute.call_count, 1)

    def setUp(self):
        self.user = SimpleNamespace(user_id=uuid4(), role='HOSPITAL_ADMIN', tenant=SimpleNamespace(tenant_type='HOSPITAL_ORGANIZATION'))
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.connection = patch('app.auth.dependencies.get_tenant_connection').start()
        self.cursor = self.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = (1,)

    def tearDown(self):
        app.dependency_overrides.clear()
        patch.stopall()

    def test_missing_authentication(self):
        app.dependency_overrides.clear()
        self.assertEqual(asyncio.run(request('GET', '/doctors')), 401)

    def test_forbidden_all_routes(self):
        self.cursor.fetchone.return_value = None
        with patch('app.doctors.router.service') as mocked:
            for method, path in [('GET', '/doctors'), ('POST', '/doctors'),
                                 ('GET', f'/doctors/{uuid4()}'), ('PATCH', f'/doctors/{uuid4()}')]:
                self.assertEqual(asyncio.run(request(method, path)), 403)
            self.assertFalse(mocked.mock_calls)

    def test_list_permission_and_tenant(self):
        with patch.object(service, 'list_doctors', return_value={'items': [], 'limit': 20, 'offset': 0}) as listing:
            self.assertEqual(asyncio.run(request('GET', '/doctors')), 200)
            listing.assert_called_once_with(self.user.tenant, 20, 0)
        self.assertEqual(self.cursor.execute.call_args.args[1], (self.user.user_id, 'DOCTOR_VIEW', 'HOSPITAL_ADMIN'))
        self.assertIn('r.code = %s', self.cursor.execute.call_args.args[0])

    def test_validation(self):
        for body in [{}, {'first_name': None}, {'status': None}, {'status': 'DELETED'}, {'password': 'new-password'}, {'experience_years': -1}]:
            self.assertEqual(asyncio.run(request('PATCH', f'/doctors/{uuid4()}', body)), 422)
        self.assertEqual(asyncio.run(request('GET', '/doctors', query=b'limit=101')), 422)
        self.assertEqual(asyncio.run(request('GET', '/doctors/invalid-id')), 422)

    def test_missing_doctor(self):
        with patch.object(service, 'get_tenant_connection') as connection:
            connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = None
            self.assertEqual(asyncio.run(request('GET', f'/doctors/{uuid4()}')), 404)

    def test_creation_hashes_password_and_assigns_role(self):
        user_id, doctor_id, role_id = uuid4(), uuid4(), uuid4()
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, 'hash_password', return_value='hashed') as hashing:
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [{'id': role_id}, None, {'id': user_id}, {'id': doctor_id}, {'id': doctor_id}]
            result = service.create_doctor(self.user.tenant, DoctorCreate(email='Doc@example.com', first_name='Doctor', password='password123', doctor_code='DOC-1'))
            self.assertEqual(result['id'], doctor_id)
            hashing.assert_called_once_with('password123')
            calls = cur.execute.call_args_list
            self.assertIn('hashed', calls[2].args[1])
            self.assertIn('doc@example.com', calls[2].args[1])
            self.assertEqual(calls[3].args[1], (user_id, role_id))
            connection.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_duplicate_rolls_back(self):
        from psycopg.errors import UniqueViolation
        from fastapi import HTTPException
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, 'hash_password', return_value='hashed'):
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [{'id': uuid4()}, None, {'id': uuid4()}]
            cur.execute.side_effect = [None, None, None, None, UniqueViolation('duplicate')]
            with self.assertRaises(HTTPException) as error:
                service.create_doctor(self.user.tenant, DoctorCreate(email='doc@example.com', first_name='Doctor', password='password123', doctor_code='DOC-1'))
            self.assertEqual(error.exception.status_code, 409)
            self.assertIs(connection.return_value.__exit__.call_args.args[0], UniqueViolation)

    def test_screenshot_permission_checks(self):
        from app.auth.dependencies import require_permission
        from fastapi import HTTPException
        self.assertIs(require_permission('PATIENT_CREATE')(self.user), self.user)
        self.cursor.fetchone.return_value = None
        with self.assertRaises(HTTPException) as error:
            require_permission('RESULT_VIEW')(self.user)
        self.assertEqual(error.exception.status_code, 403)

    def test_status_update_also_disables_login(self):
        from app.doctors.schemas import DoctorUpdate
        doctor_id, user_id = uuid4(), uuid4()
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, '_update') as update:
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [{'user_id': user_id}, {'id': doctor_id}]
            service.update_doctor(self.user.tenant, doctor_id, DoctorUpdate(status='INACTIVE', last_name=None))
            self.assertEqual(update.call_args_list[0].args[1:], ('users', user_id, {'last_name': None, 'status': 'INACTIVE'}))
            self.assertEqual(update.call_args_list[1].args[1:], ('doctors', doctor_id, {'status': 'INACTIVE'}))

    def test_hospital_creation_rejects_other_roles_and_tenants(self):
        body = {'email': 'doc@example.com', 'password': 'password123', 'first_name': 'Doctor', 'doctor_code': 'DOC-1'}
        with patch.object(service, 'create_doctor') as create:
            for role, tenant_type in [('DOCTOR', 'HOSPITAL_ORGANIZATION'), ('PATIENT', 'HOSPITAL_ORGANIZATION'), ('HOSPITAL_ADMIN', 'INDIVIDUAL_DOCTOR')]:
                self.user.role = role
                self.user.tenant.tenant_type = tenant_type
                self.assertEqual(asyncio.run(request('POST', '/doctors', body)), 403)
            create.assert_not_called()

    def test_individual_creation_only_uses_authenticated_user(self):
        from app.doctors.schemas import DoctorSelfCreate
        self.user.role = 'DOCTOR'
        self.user.tenant.tenant_type = 'INDIVIDUAL_DOCTOR'
        doctor_id = uuid4()
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, '_insert', return_value=doctor_id) as insert:
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [{'id': self.user.user_id}, None, {'id': doctor_id}]
            service.create_own_profile(self.user, DoctorSelfCreate(doctor_code='SELF-1'))
            self.assertEqual(insert.call_args.args[2], {'doctor_code': 'SELF-1', 'user_id': self.user.user_id})

    def test_self_registration_boundaries(self):
        body = {'doctor_code': 'SELF-1'}
        self.assertEqual(asyncio.run(request('POST', '/doctors/me', body)), 403)
        self.user.role = 'DOCTOR'
        self.assertEqual(asyncio.run(request('POST', '/doctors/me', body)), 403)
        self.user.tenant.tenant_type = 'INDIVIDUAL_DOCTOR'
        self.assertEqual(asyncio.run(request('POST', '/doctors/me', {**body, 'user_id': str(uuid4())})), 422)
        self.assertEqual(asyncio.run(request('PATCH', '/doctors/me', {'status': 'ACTIVE'})), 403)

    def test_individual_duplicate_profile_denied(self):
        from app.doctors.schemas import DoctorSelfCreate
        from fastapi import HTTPException
        self.user.role = 'DOCTOR'
        self.user.tenant.tenant_type = 'INDIVIDUAL_DOCTOR'
        with patch.object(service, 'get_tenant_connection') as connection, patch.object(service, '_insert') as insert:
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [{'id': self.user.user_id}, {'id': uuid4()}]
            with self.assertRaises(HTTPException) as error:
                service.create_own_profile(self.user, DoctorSelfCreate(doctor_code='SELF-1'))
            self.assertEqual(error.exception.status_code, 409)
            insert.assert_not_called()
