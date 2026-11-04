import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from tests.test_doctors import app, request
from app.auth.dependencies import get_current_user
from app.assessment_browser import browser_identity
from app.auth.platform import PlatformUser


class AssessmentBrowserTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(role='DOCTOR', user_id=uuid4(), tenant=object())
        app.dependency_overrides[browser_identity] = lambda: self.user
        self.addCleanup(app.dependency_overrides.clear)
        permission = patch('app.auth.dependencies.get_tenant_connection')
        self.permission = permission.start().return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.permission.fetchone.return_value = (1,)
        self.addCleanup(permission.stop)
        connection = patch('app.assessment_browser.get_platform_connection')
        self.connection = connection.start()
        self.addCleanup(connection.stop)
        self.cur = self.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        self.cur.fetchone.return_value = {'id': str(uuid4())}
        self.cur.fetchall.return_value = []

    def test_all_routes_require_authentication(self):
        app.dependency_overrides.clear()
        version = uuid4()
        for path in ['/categories', '/sub-categories', '/assessments', f'/assessments/{uuid4()}',
                     f'/versions/{version}', f'/versions/{version}/domains',
                     f'/versions/{version}/sub-domains', f'/versions/{version}/questions']:
            with self.subTest(path=path):
                self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser' + path)), 401)
        self.connection.assert_not_called()

    def test_platform_owner_can_browse_without_tenant_permission(self):
        app.dependency_overrides[browser_identity] = lambda: PlatformUser(uuid4(), 'owner@example.com')
        self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/categories')), 200)
        self.permission.execute.assert_not_called()

    def test_non_doctors_and_missing_permission_are_denied(self):
        for role in ['PATIENT', 'HOSPITAL_ADMIN', 'PLATFORM_ADMIN']:
            self.user.role = role
            self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/categories')), 403)
        self.user.role = 'DOCTOR'
        self.permission.fetchone.return_value = None
        self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/categories')), 403)
        self.connection.assert_not_called()

    def test_scoped_questions_preserve_scores_and_pagination(self):
        version, domain, dimension = uuid4(), uuid4(), uuid4()
        self.cur.fetchall.return_value = [{'options': [{'scores': [{'weightage': 0}, {'weightage': -2}]}]}]
        response = {}
        status = asyncio.run(request('GET', f'/platform/assessment-browser/versions/{version}/questions',
            query=f'domain_id={domain}&sub_domain_id={dimension}&limit=10&offset=20'.encode(),
            response_body=response))
        self.assertEqual(status, 200)
        query, params = self.cur.execute.call_args.args
        self.assertEqual(params, (version, domain, domain, dimension, dimension, 10, 20))
        self.assertIn('s.assessment_version_id = %s', query)
        self.assertEqual(response['items'][0]['options'][0]['scores'][1]['weightage'], -2)
        self.assertEqual(response['offset'], 20)

    def test_missing_version_or_domain_returns_404(self):
        self.cur.fetchone.return_value = None
        for suffix in ['', '/domains', '/sub-domains', '/questions']:
            self.assertEqual(asyncio.run(request('GET',
                f'/platform/assessment-browser/versions/{uuid4()}{suffix}')), 404)
        self.cur.fetchone.side_effect = [{'id': str(uuid4())}, None]
        self.assertEqual(asyncio.run(request('GET',
            f'/platform/assessment-browser/versions/{uuid4()}/questions',
            query=f'domain_id={uuid4()}'.encode())), 404)

    def test_invalid_uuid_and_pagination(self):
        for path, query in [('/versions/invalid/questions', b''),
                            ('/categories', b'limit=101'), ('/assessments', b'offset=-1')]:
            self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser' + path,
                                                query=query)), 422)
        self.connection.assert_not_called()

    def test_assessment_lookup_and_categories(self):
        category = uuid4()
        self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/assessments',
            query=f'category_id={category}&code=PSY-0134'.encode())), 200)
        self.assertEqual(self.cur.execute.call_args.args[1],
                         (category, category, 'PSY-0134', 'PSY-0134', None, None, 100, 0))
        self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/categories')), 200)

    def test_separate_subcategories_and_assessment_filter(self):
        category, subcategory = uuid4(), uuid4()
        self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/sub-categories',
            query=f'category_id={category}'.encode())), 200)
        self.assertEqual(self.cur.execute.call_args.args[1], (category, category, 100, 0))
        self.assertEqual(asyncio.run(request('GET', '/platform/assessment-browser/assessments',
            query=f'subcategory_id={subcategory}'.encode())), 200)
        self.assertEqual(self.cur.execute.call_args.args[1],
                         (None, None, None, None, subcategory, subcategory, 100, 0))


if __name__ == '__main__':
    unittest.main()
