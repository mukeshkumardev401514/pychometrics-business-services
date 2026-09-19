import asyncio
import unittest
from unittest.mock import patch

from tests.test_doctors import request
from app.auth.tenant_host import login_tenant
from fastapi import HTTPException, Request


class TenantLoginTests(unittest.TestCase):
    def resolve(self, host='localhost:8000', origin=None, supplied=None):
        headers = [(b'host', host.encode())]
        if origin:
            headers.append((b'origin', origin.encode()))
        req = Request({'type': 'http', 'scheme': 'http', 'path': '/auth/login',
                       'query_string': b'', 'headers': headers})
        return login_tenant(req, supplied)

    def test_origin_host_and_legacy_body(self):
        self.assertEqual(self.resolve(origin='http://test01.localhost:3001'), 'TEST01')
        self.assertEqual(self.resolve(host='test02.localhost:8000'), 'TEST02')
        self.assertEqual(self.resolve(supplied='test03'), 'TEST03')

    def test_invalid_or_conflicting_tenants(self):
        for kwargs in ({}, {'origin': 'http://test01.evil.com'},
                       {'origin': 'null'}, {'origin': 'http://test01.localhost.evil.com'},
                       {'origin': 'http://test01.localhost:3001', 'supplied': 'test02'},
                       {'origin': 'http://test01.localhost:3001', 'host': 'test02.localhost'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(HTTPException):
                self.resolve(**kwargs)

    def test_login_without_body_tenant(self):
        from app.auth.service import InvalidCredentialsError
        with patch('app.auth.router.authenticate_user', side_effect=InvalidCredentialsError) as auth:
            status = asyncio.run(request('POST', '/auth/login',
                {'username': 'doctor@example.com', 'password': 'password123'},
                headers=[(b'origin', b'http://test01.localhost:3001')]))
            self.assertEqual(status, 401)
            auth.assert_called_once_with(tenant_code='TEST01', email='doctor@example.com', password='password123')

    def test_browser_preflight(self):
        status = asyncio.run(request('OPTIONS', '/auth/login', headers=[
            (b'origin', b'http://test01.localhost:3001'),
            (b'access-control-request-method', b'POST'),
            (b'access-control-request-headers', b'content-type,authorization')]))
        self.assertEqual(status, 200)
