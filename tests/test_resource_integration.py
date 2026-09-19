"""Real PostgreSQL checks using a disposable cluster, never the configured database."""
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from tests.test_doctors import app
from app.auth.platform import PlatformUser
from app.resources.models import CATALOG
from app.resources.service import execute

BIN = Path('/usr/lib/postgresql/18/bin')
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((BIN / 'initdb').exists(), 'PostgreSQL test binaries not available')
class ResourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='psychometric-crud-')
        cls.root = Path(cls.tmp.name)
        cls.data = cls.root / 'data'
        subprocess.run([str(BIN/'initdb'), '-D',str(cls.data),'-U','postgres','-A','trust','--no-locale','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            subprocess.run([str(BIN/'pg_ctl'),'-D',str(cls.data),'-l',str(cls.root/'postgres.log'),'-o',f"-k {cls.root} -c listen_addresses=''",'-w','start'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        except Exception:
            print((cls.root/'postgres.log').read_text())
            cls.tmp.cleanup()
            raise
        cls.addClassCleanup(cls.stop_cluster)
        cls.base = f'host={cls.root} user=postgres'
        with psycopg.connect(cls.base+' dbname=postgres',autocommit=True) as conn:
            conn.execute('CREATE DATABASE platform_test')
            conn.execute('CREATE DATABASE tenant_test')
        for scope,db in [('platform','platform_test'),('tenant','tenant_test')]:
            with psycopg.connect(cls.base+f' dbname={db}') as conn:
                for path in sorted((ROOT/'psychometric-db-models'/scope).glob('*.sql')):
                    conn.execute(path.read_text())
        cls.operator = PlatformUser(uuid4(),'operator@example.com')
        cls.tenant = SimpleNamespace(tenant_id=uuid4(),tenant_code='TEST',tenant_type='HOSPITAL_ORGANIZATION')

    @classmethod
    def stop_cluster(cls):
        subprocess.run([str(BIN/'pg_ctl'),'-D',str(cls.data),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
        cls.tmp.cleanup()

    def setUp(self):
        for target,db in [('app.resources.service.get_platform_connection','platform_test'),('app.resources.service.get_tenant_connection','tenant_test')]:
            p=patch(target,side_effect=lambda *a,_db=db: psycopg.connect(self.base+' dbname='+_db))
            p.start(); self.addCleanup(p.stop)

    def call(self,table,action,scope='tenant',**kwargs):
        return execute(scope,table,action,self.operator,maintenance=True,tenant=self.tenant,**kwargs)

    def create(self, table, **values):
        return self.call(table,'create',values=values)

    def user(self):
        # Raw hash omitted from response, but database permits a nullable hash.
        return self.create('users',email=f'{uuid4()}@example.com',first_name='Test')

    def doctor_patient(self):
        doctor=self.create('doctors',user_id=self.user()['id'],doctor_code=str(uuid4()))
        patient=self.create('patients',user_id=self.user()['id'],patient_code=str(uuid4()))
        self.create('doctor_patients',doctor_id=doctor['id'],patient_id=patient['id'],is_primary_doctor=True)
        return doctor,patient

    def assessment(self):
        assessment=self.call('assessments','create',scope='platform',values={'code':str(uuid4()),'name':'Test'})
        version=self.call('assessment_versions','create',scope='platform',values={'assessment_id':assessment['id'],'version_number':1,'duration_minutes':30})
        return assessment,version

    def test_catalog_matches_database_columns_and_primary_keys(self):
        for scope,db in [('platform','platform_test'),('tenant','tenant_test')]:
            with psycopg.connect(self.base+' dbname='+db) as conn:
                for table,spec in CATALOG[scope].items():
                    rows=conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",(table,)).fetchall()
                    self.assertEqual(set(spec['columns']),{r[0] for r in rows},(scope,table))
                    rows=conn.execute("""SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
                                         WHERE i.indrelid=%s::regclass AND i.indisprimary""",(table,)).fetchall()
                    self.assertEqual(set(spec['primary_key']),{r[0] for r in rows},(scope,table))

    def test_crud_nullable_patch_and_duplicate(self):
        row=self.create('departments',department_code=str(uuid4()),department_name='Psychiatry',description='Before')
        self.assertEqual(self.call('departments','get',key=str(row['id']))['id'],row['id'])
        result=self.call('departments','update',key=str(row['id']),values={'description':None})
        self.assertIsNone(result['description'])
        with self.assertRaises(HTTPException) as error:
            self.create('departments',department_code=row['department_code'],department_name='Duplicate')
        self.assertEqual(error.exception.status_code,409)
        self.call('departments','delete',key=str(row['id']))
        with self.assertRaises(HTTPException) as error: self.call('departments','get',key=str(row['id']))
        self.assertEqual(error.exception.status_code,404)

    def test_composite_key_and_delete_relationship_protection(self):
        doctor,_=self.doctor_patient()
        dept=self.create('departments',department_code=str(uuid4()),department_name='Psychiatry')
        row=self.create('doctor_departments',doctor_id=doctor['id'],department_id=dept['id'])
        key=f"{doctor['id']},{dept['id']}"
        self.assertEqual(self.call('doctor_departments','get',key=key)['doctor_id'],doctor['id'])
        self.call('doctor_departments','update',key=key,values={'is_primary':True})
        with self.assertRaises(HTTPException) as error: self.call('departments','delete',key=str(dept['id']))
        self.assertEqual(error.exception.status_code,409)
        self.call('doctor_departments','delete',key=key)
        self.call('departments','delete',key=str(dept['id']))

    def test_cross_database_version_consistency(self):
        doctor,patient=self.doctor_patient()
        a,v=self.assessment()
        other,_=self.assessment()
        values={'doctor_id':doctor['id'],'patient_id':patient['id'],'assessment_id':other['id'],'assessment_version_id':v['id']}
        with self.assertRaises(HTTPException) as error: self.create('assessment_assignments',**values)
        self.assertEqual(error.exception.status_code,422)
        values['assessment_id']=a['id']
        self.create('assessment_assignments',**values)

    def test_mismatched_patient_followup_rejected(self):
        doctor,patient=self.doctor_patient()
        other=self.create('patients',user_id=self.user()['id'],patient_code=str(uuid4()))
        self.create('doctor_patients',doctor_id=doctor['id'],patient_id=other['id'])
        followup=self.create('followups',doctor_id=doctor['id'],patient_id=patient['id'],title='Followup',scheduled_at=datetime.now(timezone.utc))
        with self.assertRaises(HTTPException) as error:
            self.create('appointments',doctor_id=doctor['id'],patient_id=other['id'],followup_id=followup['id'],title='Wrong patient',scheduled_start_at=datetime.now(timezone.utc),scheduled_end_at=datetime.now(timezone.utc))
        self.assertEqual(error.exception.status_code,422)

    def test_check_constraints_and_missing_foreign_key(self):
        with self.assertRaises(HTTPException) as error:
            self.call('assessment_versions','create',scope='platform',values={'assessment_id':uuid4(),'version_number':1,'duration_minutes':30})
        self.assertEqual(error.exception.status_code,422)
        assessment,_=self.assessment()
        with self.assertRaises(HTTPException) as error:
            self.call('assessment_versions','create',scope='platform',values={'assessment_id':assessment['id'],'version_number':2,'duration_minutes':-1})
        self.assertEqual(error.exception.status_code,422)

    def test_profile_status_sync(self):
        doctor,_=self.doctor_patient()
        self.call('doctors','update',key=str(doctor['id']),values={'status':'INACTIVE'})
        row=self.call('users','get',key=str(doctor['user_id']))
        self.assertEqual(row['status'],'INACTIVE')
        self.assertNotIn('password_hash',row)

    def test_unassigned_doctor_cannot_access_patient(self):
        doctor,patient=self.doctor_patient()
        other_doctor,_=self.doctor_patient()
        user=SimpleNamespace(user_id=other_doctor['user_id'],role='DOCTOR',tenant=self.tenant)
        with psycopg.connect(self.base+' dbname=tenant_test') as conn:
            role=conn.execute("SELECT id FROM roles WHERE code='DOCTOR'").fetchone()[0]
            conn.execute('INSERT INTO user_roles(user_id,role_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(user.user_id,role))
        with self.assertRaises(HTTPException) as error:
            execute('tenant','patients','get',user,key=str(patient['id']))
        self.assertEqual(error.exception.status_code,404)
        items=execute('tenant','patients','list',user)['items']
        self.assertNotIn(patient['id'],[p['id'] for p in items])

    def test_real_platform_login_and_crud_http(self):
        import asyncio
        from tests.test_doctors import request
        from app.core.security import hash_password
        email=f'{uuid4()}@example.com'
        with psycopg.connect(self.base+' dbname=platform_test') as conn:
            conn.execute('INSERT INTO platform_users(email,password_hash,first_name) VALUES(%s,%s,%s)',(email,hash_password('IntegrationPass123'),'Operator'))
        with patch('app.auth.platform.get_platform_connection',side_effect=lambda:psycopg.connect(self.base+' dbname=platform_test')):
            response={}
            self.assertEqual(asyncio.run(request('POST','/platform/auth/login',{'email':email,'password':'IntegrationPass123'},response_body=response)),200)
            headers=[(b'authorization',('Bearer '+response['access_token']).encode())]
            record={}
            path=f'/platform/tenants/{self.tenant.tenant_id}/data/departments'
            with patch('app.resources.router.resolve_tenant_by_id',return_value=self.tenant):
                self.assertEqual(asyncio.run(request('POST',path,{'department_code':str(uuid4()),'department_name':'HTTP department'},headers=headers,response_body=record)),201)
                detail={}
                self.assertEqual(asyncio.run(request('GET',path+'/'+record['id'],headers=headers,response_body=detail)),200)
                self.assertEqual(detail['department_name'],'HTTP department')
                self.assertEqual(asyncio.run(request('PATCH',path+'/'+record['id'],{'department_name':'Updated'},headers=headers)),200)
                self.assertEqual(asyncio.run(request('DELETE',path+'/'+record['id'],headers=headers)),204)
                self.assertEqual(asyncio.run(request('GET',path+'/'+record['id'],headers=headers)),404)
            # A platform bearer must not authenticate a tenant API.
            self.assertEqual(asyncio.run(request('GET','/auth/me',headers=headers)),401)

    def test_patient_message_ownership_and_actor(self):
        doctor,patient=self.doctor_patient()
        user=SimpleNamespace(user_id=patient['user_id'],role='PATIENT',tenant=self.tenant)
        message=execute('tenant','doctor_patient_messages','create',user,values={
            'doctor_id':doctor['id'],'patient_id':patient['id'],
            'sender_user_id':user.user_id,'sender_type':'PATIENT','message_text':'Hello'})
        self.assertEqual(message['sender_user_id'],user.user_id)
        other=self.create('patients',user_id=self.user()['id'],patient_code=str(uuid4()))
        with self.assertRaises(HTTPException):
            execute('tenant','doctor_patient_messages','create',user,values={'doctor_id':doctor['id'],'patient_id':other['id'],
            'sender_user_id':user.user_id,'sender_type':'PATIENT','message_text':'Not my conversation'})

    def test_deletion_archives_profile_and_audits(self):
        doctor,patient=self.doctor_patient()
        self.call('patients','delete',key=str(patient['id']))
        self.assertEqual(self.call('patients','get',key=str(patient['id']))['status'],'INACTIVE')
        self.assertEqual(self.call('users','get',key=str(patient['user_id']))['status'],'INACTIVE')
        with psycopg.connect(self.base+' dbname=tenant_test') as conn:
            log=conn.execute("SELECT description FROM audit_logs WHERE entity_id=%s AND action='DELETE'",(patient['id'],)).fetchone()
            self.assertIn(str(self.operator.user_id),log[0])

    def test_identity_foreign_keys_are_immutable(self):
        doctor,patient=self.doctor_patient()
        with self.assertRaises(HTTPException) as error:
            self.call('patients','update',key=str(patient['id']),values={'user_id':self.user()['id']})
        self.assertEqual(error.exception.status_code,422)
