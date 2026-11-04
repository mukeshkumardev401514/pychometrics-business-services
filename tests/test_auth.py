import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from tests.test_doctors import app
from app.auth.dependencies import get_current_user
from app.auth.service import authenticate_user
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, InvalidAccessTokenError, TokenExpiredError


class AuthTests(unittest.TestCase):
    def token(self, role='DOCTOR'):
        return create_access_token(user_id=uuid4(), tenant_id=uuid4(), role=role)

    def test_roles_and_unique_tokens(self):
        for role in ('HOSPITAL_ADMIN', 'DOCTOR', 'PATIENT'):
            claims = decode_access_token(self.token(role))
            self.assertEqual(claims['role'], role)
            self.assertEqual(claims['exp'] - claims['iat'], settings.jwt_access_token_expire_minutes * 60)
        user_id, tenant_id = uuid4(), uuid4()
        self.assertNotEqual(create_access_token(user_id=user_id, tenant_id=tenant_id, role='DOCTOR'),
                            create_access_token(user_id=user_id, tenant_id=tenant_id, role='DOCTOR'))

    def test_invalid_and_expired_claims(self):
        base = decode_access_token(self.token())
        for changes, error in [({'exp': datetime.now(timezone.utc) - timedelta(seconds=1)}, TokenExpiredError),
                               ({'tenant_id': 123}, InvalidAccessTokenError),
                               ({'role': 'SUPERADMIN'}, InvalidAccessTokenError),
                               ({'type': 'refresh'}, InvalidAccessTokenError)]:
            with self.subTest(changes=changes), self.assertRaises(error):
                decode_access_token(jwt.encode({**base, **changes}, settings.jwt_secret, algorithm=settings.jwt_algorithm))
        with self.assertRaises(InvalidAccessTokenError):
            decode_access_token(jwt.encode(base, 'wrong-signing-key-that-is-long-enough', algorithm=settings.jwt_algorithm))

    def test_invalid_bearer_returns_401_without_database(self):
        with patch('app.auth.dependencies.resolve_tenant_by_id') as resolve:
            with self.assertRaises(HTTPException) as error:
                get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials='invalid'))
            self.assertEqual(error.exception.status_code, 401)
            resolve.assert_not_called()

    def test_revoked_role_and_inactive_user(self):
        for row, status in [(None, 401), ((uuid4(), 'a@example.com', 'A', None, 'INACTIVE', 'DOCTOR'), 403)]:
            with patch('app.auth.dependencies.resolve_tenant_by_id'), patch('app.auth.dependencies.get_tenant_connection') as connection:
                connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = row
                with self.assertRaises(HTTPException) as error:
                    get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=self.token()))
                self.assertEqual(error.exception.status_code, status)

    def test_login_uses_configured_expiry_for_every_role(self):
        tenant = SimpleNamespace(tenant_id=uuid4(), tenant_code='TEST')
        for role in ('HOSPITAL_ADMIN', 'DOCTOR', 'PATIENT'):
            with patch('app.auth.service.resolve_tenant', return_value=tenant), patch('app.auth.service.get_tenant_connection') as connection, patch('app.auth.service.verify_password', return_value=True), patch('app.auth.service.settings', jwt_access_token_expire_minutes=17):
                cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
                cur.fetchall.return_value = [(uuid4(), 'a@example.com', 'hash', 'A', None, 'ACTIVE', role)]
                doctor_id = uuid4()
                cur.fetchone.return_value = (doctor_id,)
                response = authenticate_user(tenant_code='TEST', email='a@example.com', password='password')
                self.assertEqual(response['expires_in'], 1020)
                self.assertEqual(decode_access_token(response['access_token'])['role'], role)
                claims = decode_access_token(response['access_token'])
                self.assertEqual(claims['email'], 'a@example.com')
                self.assertEqual(claims['sub'], str(cur.fetchall.return_value[0][0]))
                if role == 'DOCTOR':
                    self.assertEqual(claims['doctor_id'], str(doctor_id))
                    self.assertNotEqual(claims['doctor_id'], claims['sub'])
                else:
                    self.assertNotIn('doctor_id', claims)

    def test_doctor_without_profile_can_login_for_onboarding(self):
        tenant = SimpleNamespace(tenant_id=uuid4(), tenant_code='TEST')
        with patch('app.auth.service.resolve_tenant', return_value=tenant), patch('app.auth.service.get_tenant_connection') as connection, patch('app.auth.service.verify_password', return_value=True):
            cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchall.return_value = [(uuid4(), 'doc@example.com', 'hash', 'A', None, 'ACTIVE', 'DOCTOR')]
            cur.fetchone.return_value = None
            response = authenticate_user(tenant_code='TEST', email='doc@example.com', password='password')
            self.assertIsNone(decode_access_token(response['access_token'])['doctor_id'])
