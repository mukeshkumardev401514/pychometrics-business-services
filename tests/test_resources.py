import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from tests.test_doctors import app, request, get_current_user
from app.auth.platform import get_platform_user
from app.resources.models import CATALOG, input_model, public_record
from app.resources.policy import authorize
from app.resources.service import execute, key_values, row_scope
from scripts.build_resource_catalog import compile_catalog


class ResourceTests(unittest.TestCase):
    def test_patient_reads_preserve_nullable_user_fields(self):
        user = SimpleNamespace(role='DOCTOR', user_id=uuid4())
        fields = {'email': None, 'first_name': None, 'last_name': None, 'mobile': None}
        patient = {'id': uuid4(), 'user_id': uuid4(), **fields}
        for action in ('list', 'get'):
            with self.subTest(action=action), patch('app.resources.service.connection') as connection:
                cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
                cur.fetchone.return_value = patient
                if action == 'list':
                    cur.fetchone.side_effect = [patient, {'total_patients': 1, 'active': 1,
                                                        'in_progress': 0, 'not_started': 0}]
                cur.fetchall.return_value = [patient]
                result = execute('tenant', 'patients', action, user, key=str(patient['id']))
                query, params = cur.execute.call_args.args
                query = query.as_string()
                self.assertIn('LEFT JOIN users u ON u.id = r.user_id', query)
                self.assertIn('d.user_id = %s', query)
                self.assertIn(user.user_id, params)
                record = result['items'][0] if action == 'list' else result
                for field in fields:
                    self.assertIn(f'u.{field}', query)
                    self.assertIn(field, record)
                    self.assertIsNone(record[field])
                self.assertNotIn('password', query)

    def test_patient_counts_are_scoped_and_independent_of_page(self):
        user = SimpleNamespace(role='DOCTOR', user_id=uuid4())
        for total, offset in ((101, 0), (101, 200), (0, 0)):
            with self.subTest(total=total, offset=offset), patch('app.resources.service.connection') as connection:
                cur = connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
                counts = {'total_patients': total, 'active': total, 'in_progress': 0, 'not_started': 0}
                cur.fetchone.side_effect = [{'allowed': 1}, counts]
                cur.fetchall.return_value = []
                result = execute('tenant', 'patients', 'list', user, limit=20, offset=offset)
                self.assertEqual(result['counts'], counts)
                self.assertEqual(result['pagination'], {'limit': 20, 'offset': offset,
                                                       'total': total, 'total_pages': 6 if total else 0})
                query, params = cur.execute.call_args_list[1].args
                query = query.as_string()
                self.assertIn('d.user_id = %s', query)
                self.assertEqual(params, (user.user_id,))
                self.assertNotIn('LIMIT', query)
                self.assertIn('pending AND NOT started', query)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_catalog_matches_every_migration_table(self):
        self.assertEqual(CATALOG, compile_catalog())
        self.assertEqual(len(CATALOG['platform']), 25)
        self.assertEqual(len(CATALOG['tenant']), 38)

    def test_all_tables_have_read_routes(self):
        paths = app.openapi()['paths']
        for scope, tables in CATALOG.items():
            prefix = '/platform/data' if scope == 'platform' else '/platform/tenants/{tenant_id}/data'
            for table in tables:
                self.assertIn('get', paths[prefix + '/' + table.replace('_', '-')])
                self.assertIn('get', paths[prefix + '/' + table.replace('_', '-') + '/{key}'])

    def test_generated_models_types_enums_unknown_and_nulls(self):
        Create = input_model('tenant', 'departments')
        with self.assertRaises(ValidationError): Create(department_code='D')
        with self.assertRaises(ValidationError): Create(department_code='D', department_name='Name', injected='x')
        Update = input_model('tenant', 'departments', True)
        with self.assertRaises(ValidationError): Update(department_name=None)
        with self.assertRaises(ValidationError): Update()
        self.assertEqual(Update(description=None).model_dump(exclude_unset=True), {'description': None})
        with self.assertRaises(ValidationError): input_model('tenant','appointments',True)(status='INVALID')
        with self.assertRaises(ValidationError): input_model('tenant','patients',True)(email='bad')

    def test_composite_keys(self):
        a,b = uuid4(),uuid4()
        spec=CATALOG['tenant']['doctor_departments']
        self.assertEqual(key_values(spec, f'{a},{b}'), {'doctor_id':a,'department_id':b})
        with self.assertRaises(HTTPException): key_values(spec, str(a))
        with self.assertRaises(HTTPException): key_values(spec, 'invalid,invalid')

    def test_secret_fields_never_returned(self):
        self.assertEqual(public_record({'id':1,'password_hash':'x','token_hash':'x','otp_code':'x','secret_reference':'x'}), {'id':1})

    def test_admin_cannot_modify_patient_or_results(self):
        user=SimpleNamespace(role='HOSPITAL_ADMIN')
        for table in ('patients','assessment_results','user_roles','role_permissions'):
            with self.assertRaises(HTTPException): authorize(table,'create',user)

    def test_history_read_only_even_platform(self):
        with self.assertRaises(HTTPException): authorize('audit_logs','delete',None,True)
        authorize('audit_logs','list',None,True)

    def test_patient_and_doctor_list_scopes_are_parameterized(self):
        for role in ('DOCTOR','PATIENT'):
            user=SimpleNamespace(role=role,user_id=uuid4())
            query, args=row_scope('assessment_answers',user)
            self.assertIn('assessment_attempts',query.as_string())
            self.assertIn('assessment_assignments',query.as_string())
            self.assertEqual(args,[user.user_id])
            self.assertNotIn(str(user.user_id),query.as_string())

    def test_unauthenticated_routes_blocked(self):
        for path in ('/data/departments','/platform/data/tenants',f'/platform/tenants/{uuid4()}/data/users'):
            self.assertEqual(asyncio.run(request('GET',path)),401)

    def test_permission_denial_precedes_resource_access(self):
        app.dependency_overrides[get_current_user]=lambda: SimpleNamespace(role='PATIENT',tenant=object(),user_id=uuid4())
        with patch('app.resources.service.connection') as conn:
            self.assertEqual(asyncio.run(request('POST','/data/departments',{'department_code':'D','department_name':'N'})),403)
            conn.assert_not_called()

    def test_platform_and_tenant_tokens_are_separate(self):
        from app.auth.platform import get_platform_user
        from app.core.security import create_access_token
        from fastapi.security import HTTPAuthorizationCredentials
        token=create_access_token(user_id=uuid4(),tenant_id=uuid4(),role='HOSPITAL_ADMIN')
        with patch('app.auth.platform.get_platform_connection') as conn:
            with self.assertRaises(HTTPException) as error:
                get_platform_user(HTTPAuthorizationCredentials(scheme='Bearer',credentials=token))
            self.assertEqual(error.exception.status_code,401)
            conn.assert_not_called()

    def test_postman_collection_covers_all_business_routes(self):
        import re
        from pathlib import Path
        collection=json.loads(Path('postman/psychometrics-all-apis.postman_collection.json').read_text())
        defined={v['key'] for v in collection['variable']}
        covered=set()
        def visit(items):
            for item in items:
                if 'item' in item:
                    visit(item['item']); continue
                request=item['request']
                url=request['url'].replace('{{base_url}}','').split('?')[0]
                url=url.replace('{{maintenance_tenant_id}}','{tenant_id}').replace('{{doctor_id}}','{doctor_id}')
                url=re.sub(r'\{\{(?:platform|tenant)_\w+_key\}\}', '{key}', url)
                covered.add((request['method'].lower(),url))
                for name in re.findall(r'\{\{(\w+)\}\}',json.dumps(request)):
                    self.assertIn(name,defined)
                if 'body' in request:
                    json.loads(request['body']['raw'])
        visit(collection['item'])
        expected={(method,path) for path,methods in app.openapi()['paths'].items() for method in methods if method in {'get','post','patch','delete'}}
        self.assertFalse(expected-covered,expected-covered)

    def test_nested_secrets_are_redacted(self):
        self.assertEqual(public_record({'old_data':{'password_hash':'hidden','email':'a@example.com'}}),
                         {'old_data':{'email':'a@example.com'}})
