"""Execute every assessment Postman request over HTTP against disposable databases."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg

from tests.test_resource_integration import BIN, ROOT, ResourceIntegrationTests
from app.core.security import hash_password


@unittest.skipUnless((BIN / 'initdb').exists(), 'PostgreSQL test binaries not available')
class AssessmentCollectionTests(unittest.TestCase):
    setUpClass = classmethod(ResourceIntegrationTests.setUpClass.__func__)
    stop_cluster = classmethod(ResourceIntegrationTests.stop_cluster.__func__)

    def test_every_collection_request_over_http(self):
        collection = json.loads((ROOT / 'postman/assessment-browser.postman_collection.json').read_text())
        variables = {v['key']: v['value'] for v in collection['variable']}
        password = 'CollectionTest-' + str(uuid4())
        hashed = hash_password(password)
        variables.update(tenant_code='TEST', doctor_email='doctor@example.com', doctor_password=password,
                         owner_email='owner@example.com', owner_password=password,
                         patient_email='patient@example.com', patient_password=password,
                         assessment_code='COLLECTION-TEST')
        with psycopg.connect(self.base + ' dbname=platform_test') as conn:
            tenant_id = conn.execute("""INSERT INTO tenants
                (tenant_code,tenant_name,tenant_type,status,database_name)
                VALUES('TEST','Collection test','INDIVIDUAL_DOCTOR','ACTIVE','tenant_test') RETURNING id""").fetchone()[0]
            conn.execute("""INSERT INTO tenant_database_config(tenant_id,database_name,host,username)
                VALUES(%s,'tenant_test',%s,'postgres')""", (tenant_id, str(self.root)))
            conn.execute("INSERT INTO platform_users(email,password_hash,first_name) VALUES(%s,%s,'Owner')",
                         (variables['owner_email'], hashed))
            category = conn.execute("INSERT INTO assessment_categories(code,name) VALUES('TEST','Test Category') RETURNING id").fetchone()[0]
            subcategory = conn.execute("""INSERT INTO assessment_subcategories(category_id,code,name)
                VALUES(%s,'TEST','Test Subcategory') RETURNING id""", (category,)).fetchone()[0]
            assessment = conn.execute("""INSERT INTO assessments(code,name,category_id,subcategory_id,status)
                VALUES(%s,'Collection Assessment',%s,%s,'PUBLISHED') RETURNING id""",
                (variables['assessment_code'], category, subcategory)).fetchone()[0]
            version = conn.execute("""INSERT INTO assessment_versions(assessment_id,version_number,duration_minutes,status)
                VALUES(%s,1,30,'PUBLISHED') RETURNING id""", (assessment,)).fetchone()[0]
            section = conn.execute("INSERT INTO assessment_sections(assessment_version_id,name,display_order) VALUES(%s,'Domain',1) RETURNING id", (version,)).fetchone()[0]
            dimension = conn.execute("INSERT INTO assessment_dimensions(assessment_version_id,code,name,display_order) VALUES(%s,'SUB','Subdomain',1) RETURNING id", (version,)).fetchone()[0]
            question = conn.execute("INSERT INTO questions(assessment_section_id,question_text,question_type,display_order) VALUES(%s,'Test question','SINGLE_CHOICE',1) RETURNING id", (section,)).fetchone()[0]
            for order, weight in [(1, 0), (2, -2)]:
                option = conn.execute("INSERT INTO question_options(question_id,option_text,option_value,display_order) VALUES(%s,%s,%s,%s) RETURNING id", (question, f'Choice {order}', str(order), order)).fetchone()[0]
                conn.execute('INSERT INTO question_option_scores(question_option_id,dimension_id,score) VALUES(%s,%s,%s)', (option, dimension, weight))
        with psycopg.connect(self.base + ' dbname=tenant_test') as conn:
            users = {}
            for role, email in [('DOCTOR', variables['doctor_email']), ('PATIENT', variables['patient_email']), ('PATIENT', 'other@example.com')]:
                uid = conn.execute("INSERT INTO users(email,password_hash,first_name) VALUES(%s,%s,'Test') RETURNING id", (email, hashed)).fetchone()[0]
                conn.execute('INSERT INTO user_roles(user_id,role_id) SELECT %s,id FROM roles WHERE code=%s', (uid, role))
                users[email] = uid
            doctor = conn.execute("INSERT INTO doctors(user_id,doctor_code) VALUES(%s,'DOC-TEST') RETURNING id", (users[variables['doctor_email']],)).fetchone()[0]
            patient = conn.execute("INSERT INTO patients(user_id,patient_code) VALUES(%s,'PAT-TEST') RETURNING id", (users[variables['patient_email']],)).fetchone()[0]
            conn.execute('INSERT INTO doctor_patients(doctor_id,patient_id) VALUES(%s,%s)', (doctor, patient))
        variables.update(doctor_id=str(doctor), patient_id=str(patient))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        variables['base_url'] = f'http://127.0.0.1:{port}'
        env = dict(os.environ, PLATFORM_DB_HOST=str(self.root), PLATFORM_DB_PORT='5432',
                   PLATFORM_DB_NAME='platform_test', PLATFORM_DB_USER='postgres', PLATFORM_DB_PASSWORD='',
                   TENANT_DB_PASSWORD='', JWT_SECRET='isolated-collection-secret-at-least-32-characters')
        log = (self.root / 'api.log').open('w+')
        self.addCleanup(log.close)
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                                  cwd=ROOT, env=env, stdout=log, stderr=log)
        def stop_server():
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        self.addCleanup(stop_server)
        for _ in range(100):
            try:
                with urlopen(variables['base_url'] + '/health', timeout=1):
                    break
            except (URLError, TimeoutError):
                if server.poll() is not None:
                    log.seek(0)
                    self.fail(log.read())
                time.sleep(.1)
        else:
            self.fail('Disposable API server did not start')

        results = []
        def substitute(value):
            return re.sub(r'\{\{(\w+)\}\}', lambda m: str(variables[m[1]]), value)

        def run(item, expected=200, token_override=None, record=True):
            spec = item['request']
            auth = spec.get('auth', collection['auth'])
            headers = {h['key']: substitute(h['value']) for h in spec.get('header', [])}
            if auth['type'] == 'bearer':
                headers['Authorization'] = 'Bearer ' + (token_override or substitute(auth['bearer'][0]['value']))
            body = substitute(spec['body']['raw']).encode() if 'body' in spec else None
            req = Request(substitute(spec['url']), data=body, headers=headers, method=spec['method'])
            try:
                response = urlopen(req, timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                raw = response.read()
                data = json.loads(raw) if raw else {}
                self.assertEqual(response.status, expected, (item['name'], data))
            if record:
                results.append((item['name'], expected))
            return data

        auth_items = collection['item'][0]['item']
        for item, key, role in zip(auth_items, ['doctor_token', 'owner_token', 'patient_token'], ['DOCTOR', 'PLATFORM_ADMIN', 'PATIENT']):
            data = run(item)
            self.assertEqual(data['role'], role)
            variables[key] = data['access_token']
        browse = collection['item'][1]['item']
        for role in ['doctor_token', 'owner_token']:
            variables['browser_token'] = variables[role]
            for index, item in enumerate(browse):
                data = run(item)
                if index == 0:
                    variables['category_id'] = data['items'][0]['id']
                elif index == 2:
                    variables['subcategory_id'] = data['items'][0]['id']
                elif index == 6:
                    variables['assessment_id'] = data['items'][0]['id']
                elif index == 7:
                    variables['version_id'] = data['versions'][0]['id']
                elif index == 9:
                    variables['domain_id'] = data['items'][0]['id']
                elif index == 11:
                    variables['sub_domain_id'] = data['items'][0]['id']
                elif index >= 12:
                    self.assertEqual([o['scores'][0]['weightage'] for o in data['items'][0]['options']], [0, -2])
        assigned = run(collection['item'][2]['item'][0], expected=201)
        variables['assignment_id'] = assigned['id']
        patient_items = collection['item'][3]['item']
        self.assertEqual(run(patient_items[0])['items'][0]['assignment_id'], assigned['id'])
        run(patient_items[1], expected=403)
        with psycopg.connect(self.base + ' dbname=tenant_test') as conn:
            conn.execute("UPDATE assessment_assignments SET assignment_status='ASSIGNED',payment_completed_at=NOW() WHERE id=%s", (assigned['id'],))
            conn.execute("""INSERT INTO assessment_access(assignment_id,patient_id,status,payment_verified_at,consent_verified_at)
                VALUES(%s,%s,'ACTIVE',NOW(),NOW())""", (assigned['id'], patient))
        data = run(patient_items[1])
        self.assertEqual(len(data['items'][0]['options']), 2)
        self.assertNotIn('weightage', json.dumps(data))
        self.assertNotIn('scores', json.dumps(data))
        run(browse[0], expected=403, token_override=variables['patient_token'])
        other_login = json.loads(json.dumps(auth_items[2]))
        other_login['request']['body']['raw'] = json.dumps({'tenant_code':'TEST', 'email':'other@example.com', 'password':password})
        other_token = run(other_login, record=False)['access_token']
        run(patient_items[1], expected=404, token_override=other_token)
        with psycopg.connect(self.base + ' dbname=tenant_test') as conn:
            conn.execute("UPDATE assessment_access SET status='REVOKED',revoked_at=NOW() WHERE assignment_id=%s", (assigned['id'],))
        run(patient_items[1], expected=403)
        report = '# Assessment Postman collection verification\n\n'
        report += 'Executed against a disposable PostgreSQL cluster and a real HTTP API server.\n'
        report += 'All 22 collection requests covered; browser requests checked with doctor and owner tokens.\n'
        report += 'Passwords, JWT verification, roles, permissions and SQL were real; no authentication overrides.\n'
        report += 'Patient activation was simulated in the disposable DB after checking pending access is denied.\n'
        report += 'Localhost:8000 credentials were unavailable; this report does not claim that deployment passed.\n\n'
        report += '| Request | Expected/actual HTTP |\n|---|---|\n'
        report += ''.join(f'| {name} | {status} / {status} |\n' for name, status in results)
        (ROOT / 'docs/assessment-collection-test-results.md').write_text(report)
