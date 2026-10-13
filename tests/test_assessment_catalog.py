import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from tests.test_doctors import app, get_current_user, request


class AssessmentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(user_id=uuid4(), role='DOCTOR', tenant=object())
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.addCleanup(app.dependency_overrides.clear)
        permission = patch('app.auth.dependencies.get_tenant_connection')
        self.permission = permission.start().return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.permission.fetchone.return_value = (1,)
        self.addCleanup(permission.stop)
        connection = patch('app.assessment_catalog.get_platform_connection')
        self.connection = connection.start()
        self.cur = self.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.cur.fetchall.return_value = []
        self.addCleanup(connection.stop)

    def test_published_only_and_paginated(self):
        response = {}
        self.assertEqual(asyncio.run(request('GET', '/assessment-catalog', query=b'limit=20&offset=100', response_body=response)), 200)
        query, params = self.cur.execute.call_args.args
        self.assertIn("a.status = 'PUBLISHED' AND v.status = 'PUBLISHED'", query)
        self.assertIn('ORDER BY a.name, a.id, v.version_number DESC, v.id', query)
        self.assertIn('LEFT JOIN assessment_categories c ON c.id = a.category_id', query)
        self.assertIn('c.name AS category_name', query)
        self.assertIn('effective_from <= NOW()', query)
        self.assertIn('effective_to > NOW()', query)
        self.assertIn('pricing.price::text AS price', query)
        self.assertIn('COUNT(*) FROM questions q', query)
        self.assertIn('section.assessment_version_id = v.id', query)
        self.assertEqual(params, (20, 100))
        self.assertEqual(response['items'], [])
        self.assertEqual(self.permission.execute.call_args.args[1][1], 'ASSESSMENT_ASSIGN')

    def test_empty_categories_are_returned_without_tests(self):
        category = {'id': str(uuid4()), 'name': 'Career Assessment', 'display_order': 2}
        self.cur.fetchall.side_effect = [[category], []]
        response = {}
        self.assertEqual(asyncio.run(request('GET', '/assessment-catalog', response_body=response)), 200)
        self.assertEqual(response['categories'], [category])
        self.assertEqual(response['items'], [])
        self.assertIn("status = 'ACTIVE'", self.cur.execute.call_args_list[0].args[0])

    def test_other_roles_cannot_read_catalog(self):
        self.user.role = 'PATIENT'
        self.assertEqual(asyncio.run(request('GET', '/assessment-catalog')), 403)
        self.connection.assert_not_called()

    def test_permission_required(self):
        self.permission.fetchone.return_value = None
        self.assertEqual(asyncio.run(request('GET', '/assessment-catalog')), 403)
        self.connection.assert_not_called()

    def test_authentication_required(self):
        app.dependency_overrides.clear()
        self.assertEqual(asyncio.run(request('GET', '/assessment-catalog')), 401)
        self.connection.assert_not_called()
