"""Allowlisted, parameterized CRUD with tenant ownership and relationship checks."""
from contextlib import contextmanager
from uuid import UUID

from fastapi import HTTPException
from psycopg import DataError, Error, sql
from psycopg.errors import CheckViolation, ForeignKeyViolation, NotNullViolation, UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.security import hash_password
from app.db.platform import get_platform_connection
from app.db.tenant import get_tenant_connection
from app.db.tenant_resolver import resolve_tenant_by_id
from app.resources.models import CATALOG, public_record
from app.resources.policy import authorize, permission_for

# References crossing the physical database boundary cannot have PostgreSQL FKs.
EXTERNAL = {
    'assessment_id': 'assessments', 'assessment_version_id': 'assessment_versions',
    'question_id': 'questions', 'selected_option_id': 'question_options',
    'dimension_id': 'assessment_dimensions', 'platform_payment_id': 'platform_payments',
}
ACTORS = {'created_by', 'updated_by', 'uploaded_by', 'sender_user_id', 'performed_by', 'generated_by', 'action_by', 'requested_by'}
SELF_TABLES = {'user_settings', 'notification_preferences', 'notifications', 'consents', 'consent_history'}
CONTEXT_TABLES = {'doctors': 'doctor_id', 'patients': 'patient_id', 'assessment_assignments': 'assignment_id',
                  'assessment_attempts': 'attempt_id', 'assessment_results': 'result_id', 'assessments': 'assessment_id',
                  'assessment_versions': 'assessment_version_id', 'questions': 'question_id'}
# History references may legitimately point at distinct attempts.
CONTEXT_SKIP = {'previous_attempt_id', 'new_attempt_id'}
CATALOG_TABLES = {'assessments', 'assessment_versions', 'assessment_sections', 'questions', 'question_options',
                  'assessment_dimensions', 'question_option_scores', 'scoring_rules', 'assessment_pricing'}


@contextmanager
def connection(scope, user, tenant=None):
    try:
        with (get_platform_connection() if scope == 'platform' else get_tenant_connection(tenant or user.tenant)) as conn:
            yield conn
    except UniqueViolation:
        raise HTTPException(409, 'A record with these unique values already exists.') from None
    except ForeignKeyViolation:
        raise HTTPException(409, 'Referenced record is missing or this record is still in use.') from None
    except (CheckViolation, NotNullViolation, DataError):
        raise HTTPException(422, 'Values violate a database constraint.') from None
    except Error:
        raise HTTPException(503, 'Database operation unavailable.') from None


def row_scope(table, user, alias='r', depth=0):
    """Return SQL and bind values; list/detail/write all use the same predicate."""
    if depth > 8: raise HTTPException(403, 'Ownership could not be established.')
    if table in {'user_settings', 'notification_preferences', 'notifications'}:
        return sql.SQL('{} = %s').format(sql.Identifier(alias, 'user_id')), [user.user_id]
    if user.role == 'HOSPITAL_ADMIN': return sql.SQL('TRUE'), []
    col = lambda name: sql.Identifier(alias, name)
    if table == 'doctors' and user.role == 'PATIENT':
        return sql.SQL("EXISTS (SELECT 1 FROM doctor_patients dp JOIN patients p ON p.id=dp.patient_id WHERE dp.doctor_id={} AND p.user_id=%s AND dp.status='ACTIVE' AND dp.unassigned_at IS NULL)").format(col('id')), [user.user_id]
    if table == 'doctors':
        return sql.SQL('{} = %s').format(col('user_id')), [user.user_id]
    if table == 'patients':
        if user.role == 'PATIENT':
            return sql.SQL('{} = %s').format(col('user_id')), [user.user_id]
        return sql.SQL("EXISTS (SELECT 1 FROM doctor_patients dp JOIN doctors d ON d.id = dp.doctor_id WHERE dp.patient_id = {} AND d.user_id = %s AND d.status = 'ACTIVE' AND dp.status = 'ACTIVE' AND dp.unassigned_at IS NULL)").format(col('id')), [user.user_id]
    if table == 'users':
        return sql.SQL('{} = %s').format(col('id')), [user.user_id]
    if table in SELF_TABLES:
        # Doctors may see linked patient consent, but not another user's settings.
        if table not in {'consents', 'consent_history'} or user.role == 'PATIENT':
            return sql.SQL('{} = %s').format(col('user_id')), [user.user_id]
    columns = CATALOG['tenant'][table]['columns']
    if 'doctor_id' in columns and user.role == 'DOCTOR':
        return sql.SQL("EXISTS (SELECT 1 FROM doctors d WHERE d.id = {} AND d.user_id = %s AND d.status = 'ACTIVE')").format(col('doctor_id')), [user.user_id]
    if 'patient_id' in columns:
        condition, values = row_scope('patients', user, 'owned', depth+1)
        return sql.SQL('EXISTS (SELECT 1 FROM patients owned WHERE owned.id = {} AND {})').format(col('patient_id'), condition), values
    for field, parent in [('assignment_id', 'assessment_assignments'), ('attempt_id', 'assessment_attempts'), ('result_id', 'assessment_results')]:
        if field in columns:
            parent_alias = f'owner{depth}'
            condition, values = row_scope(parent, user, parent_alias, depth+1)
            return sql.SQL('EXISTS (SELECT 1 FROM {} {} WHERE {} = {} AND {})').format(
                sql.Identifier(parent), sql.Identifier(parent_alias), sql.Identifier(parent_alias, 'id'), col(field), condition), values
    if table in {'departments', 'organization_profile'}:
        return sql.SQL('TRUE'), []
    raise HTTPException(403, 'No ownership policy for this resource.')


def key_values(table_spec, key):
    parts = key.split(',')
    keys = table_spec['primary_key']
    if len(parts) != len(keys): raise HTTPException(422, 'Incorrect number of record key components.')
    try:
        return {name: UUID(value) if table_spec['columns'][name]['type'] == 'uuid' else value for name, value in zip(keys, parts)}
    except ValueError:
        raise HTTPException(422, 'Record key must contain valid UUIDs.') from None


def predicate(keys):
    return sql.SQL(' AND ').join(sql.SQL('{} = %s').format(sql.Identifier('r', key)) for key in keys)


def fetch(cur, scope, table, record_id, user, maintenance=False, lock=False, target='id'):
    condition, params = (sql.SQL('TRUE'), []) if maintenance or scope == 'platform' else row_scope(table, user)
    cur.execute(sql.SQL('SELECT r.* FROM {} r WHERE {} = %s AND {}{}').format(
        sql.Identifier(table), sql.Identifier('r', target), condition, sql.SQL(' FOR SHARE' if lock else '')),
        (record_id, *params))
    row = cur.fetchone()
    if row is None: raise HTTPException(422, 'Related record does not exist or is not accessible.')
    return row


def relation_checks(cur, scope, table, row, user, maintenance, tenant=None):
    """Validate all declared FKs and repeated ownership context across parents."""
    contexts, seen = {}, set()
    def add(name, value):
        if value is None: return
        if name in contexts and contexts[name] != value:
            raise HTTPException(422, f'Inconsistent relationship: {name}.')
        contexts[name] = value

    def walk(cursor, db_scope, name, record, level=0):
        if level > 10: raise HTTPException(422, 'Relationship depth exceeded.')
        marker = (db_scope, name, str(record.get('id')))
        if marker in seen: return
        seen.add(marker)
        if name in CONTEXT_TABLES and record.get('id'):
            add(CONTEXT_TABLES[name], record['id'])
        if db_scope == 'platform' and record.get('tenant_id'):
            add('tenant_id', record['tenant_id'])
        if db_scope == 'platform' and name == 'platform_payments':
            for field, parent in [('assessment_id', 'assessments'), ('assessment_version_id', 'assessment_versions')]:
                related = fetch(cursor, db_scope, parent, record[field], user, True, lock=True)
                walk(cursor, db_scope, parent, related, level+1)
        for field in ('doctor_id', 'patient_id', 'assignment_id', 'attempt_id', 'assessment_id', 'assessment_version_id', 'question_id'):
            if record.get(field) is not None: add(field, record[field])
        for fk in CATALOG[db_scope][name]['foreign_keys']:
            value = record.get(fk['column'])
            if value is None: continue
            related = fetch(cursor, db_scope, fk['table'], value, user, maintenance or fk['table'] in {'users', 'roles', 'permissions'}, lock=True, target=fk['target'])
            if fk['column'] not in CONTEXT_SKIP and fk['table'] not in {'users', 'roles', 'permissions', 'tenants', 'platform_users'}:
                walk(cursor, db_scope, fk['table'], related, level+1)
        if db_scope == 'tenant':
            with get_platform_connection() as platform_conn:
                with platform_conn.cursor(row_factory=dict_row) as platform_cur:
                    for field, parent in EXTERNAL.items():
                        if record.get(field) is None: continue
                        related = fetch(platform_cur, 'platform', parent, record[field], user, True)
                        if field == 'platform_payment_id':
                            expected_tenant = (tenant or user.tenant).tenant_id
                            if related['tenant_id'] != expected_tenant or related.get('assignment_id') != record.get('assignment_id'):
                                raise HTTPException(422, 'Payment belongs to another tenant or assignment.')
                        else:
                            walk(platform_cur, 'platform', parent, related, level+1)
        elif db_scope == 'platform' and name in {'platform_payments', 'doctor_payout_accounts', 'doctor_payouts'}:
            tenant_config = resolve_tenant_by_id(record['tenant_id'])
            with get_tenant_connection(tenant_config) as tenant_conn:
                with tenant_conn.cursor(row_factory=dict_row) as tenant_cur:
                    for field, parent in [('doctor_id','doctors'), ('patient_id','patients'), ('assignment_id','assessment_assignments')]:
                        if record.get(field) is not None:
                            related = fetch(tenant_cur, 'tenant', parent, record[field], user, True)
                            # Only ownership facts here; avoid platform↔tenant recursion.
                            add(field, related['id'])
                            for key in ('doctor_id','patient_id','assessment_id','assessment_version_id'):
                                add(key, related.get(key))
        if db_scope == 'platform' and name == 'doctor_payouts':
            account = fetch(cursor, db_scope, 'doctor_payout_accounts', record['payout_account_id'], user, True)
            if account['tenant_id'] != record['tenant_id'] or account['doctor_id'] != record['doctor_id']:
                raise HTTPException(422, 'Payout account must belong to the same tenant and doctor.')
    walk(cur, scope, table, row)
    if scope == 'tenant' and table != 'doctor_patients' and row.get('doctor_id') and row.get('patient_id'):
        cur.execute("SELECT 1 FROM doctor_patients WHERE doctor_id = %s AND patient_id = %s AND status = 'ACTIVE' AND unassigned_at IS NULL FOR SHARE", (row['doctor_id'], row['patient_id']))
        if cur.fetchone() is None: raise HTTPException(422, 'Doctor is not assigned to this patient.')


def adapt(spec, values):
    return {name: Jsonb(value) if spec['columns'].get(name, {}).get('type') == 'jsonb' and value is not None else value for name, value in values.items()}


def audit(cur, table, action, user, old, new, maintenance=False):
    cur.execute('INSERT INTO audit_logs (user_id, action, entity_type, entity_id, old_data, new_data, description) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (None if maintenance else user.user_id, action.upper(), table, (new or old).get('id'),
                 Jsonb(public_record(old), dumps=json_dump) if old else None,
                 Jsonb(public_record(new), dumps=json_dump) if new else None,
                 f'Platform operator {user.user_id}' if maintenance else None))


def json_dump(value):
    import json
    return json.dumps(value, default=str)


def execute(scope, table, action, user, *, key=None, values=None, limit=20, offset=0, maintenance=False, tenant=None):
    authorize(table, action, user, maintenance)
    spec = CATALOG[scope][table]
    values = dict(values or {})
    if not maintenance:
        if table == 'assessment_assignments':
            forbidden = set(values) & {'payment_completed_at', 'payment_required', 'retry_count', 'started_at', 'completed_at'}
            if forbidden: raise HTTPException(403, 'Payment and assessment progress are system-managed.')
            if 'assignment_status' in values and (action != 'update' or values['assignment_status'] != 'CANCELLED'):
                raise HTTPException(403, 'Only cancellation is allowed; other progress is system-managed.')
        if table == 'doctor_patient_messages':
            values['sender_user_id'] = user.user_id
            values['sender_type'] = user.role
        for field in ACTORS & set(spec['columns']):
            if field in values and values[field] != user.user_id:
                raise HTTPException(403, 'Actor must be the authenticated user.')
        if table in {'user_settings', 'notification_preferences', 'consents'}:
            if values.get('user_id', user.user_id) != user.user_id: raise HTTPException(403, 'Own account required.')
            if action == 'create': values['user_id'] = user.user_id
    if 'password' in values:
        values['password_hash'] = hash_password(values.pop('password').get_secret_value())
    if 'email' in values: values['email'] = str(values['email']).lower()
    with connection(scope, user, tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if not maintenance:
                permission = permission_for(table, action, user)
                if permission:
                    cur.execute('''SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                                   JOIN role_permissions rp ON rp.role_id=r.id JOIN permissions p ON p.id=rp.permission_id
                                   WHERE ur.user_id=%s AND r.code=%s AND p.code=%s''', (user.user_id, user.role, permission))
                    if cur.fetchone() is None: raise HTTPException(403, 'Permission denied.')
            condition, params = (sql.SQL('TRUE'), []) if maintenance or scope == 'platform' else row_scope(table, user)
            if action == 'list':
                cur.execute(sql.SQL('SELECT r.* FROM {} r WHERE {} ORDER BY {} LIMIT %s OFFSET %s').format(
                    sql.Identifier(table), condition, sql.SQL(', ').join(sql.Identifier('r', name) for name in spec['primary_key'])), (*params, limit, offset))
                return {'items': [public_record(row) for row in cur.fetchall()], 'limit': limit, 'offset': offset}
            old = None
            if action != 'create':
                keys = key_values(spec, key)
                cur.execute(sql.SQL('SELECT r.* FROM {} r WHERE {} AND {}{}').format(sql.Identifier(table), predicate(keys), condition,
                    sql.SQL(' FOR UPDATE' if action != 'get' else '')), (*keys.values(), *params))
                old = cur.fetchone()
                if old is None: raise HTTPException(404, 'Record not found.')
                if action == 'get': return public_record(old)
                if not maintenance and table == 'assessment_assignments' and values.get('assignment_status') == 'CANCELLED' and old['assignment_status'] == 'COMPLETED':
                    raise HTTPException(409, 'Completed assignments cannot be cancelled.')
                if not maintenance and table == 'doctor_patient_messages' and old['sender_user_id'] != user.user_id:
                    raise HTTPException(403, 'Only the sender can modify or delete a message.')
                if action == 'delete':
                    if scope == 'tenant' and table in {'doctors', 'patients'}:
                        cur.execute(sql.SQL("UPDATE {} SET status='INACTIVE', updated_at=NOW() WHERE id=%s").format(sql.Identifier(table)), (old['id'],))
                        cur.execute("UPDATE users SET status='INACTIVE', updated_at=NOW() WHERE id=%s", (old['user_id'],))
                        audit(cur, table, action, user, old, {**old, 'status': 'INACTIVE'}, maintenance)
                        return None
                    if scope == 'tenant' and table == 'assessment_assignments':
                        raise HTTPException(409, 'Cancel the assignment instead; payment records may reference it.')
                    if scope == 'platform' and table in CATALOG_TABLES | {'tenants', 'platform_payments'}:
                        raise HTTPException(409, 'Archive or deactivate this record; cross-database references prevent hard deletion.')
                    # Refuse cascading/set-null deletion too, preserving all existing relations.
                    for child, child_spec in CATALOG[scope].items():
                        for fk in child_spec['foreign_keys']:
                            if fk['table'] != table: continue
                            cur.execute(sql.SQL('SELECT 1 FROM {} WHERE {} = %s LIMIT 1').format(sql.Identifier(child), sql.Identifier(fk['column'])), (old[fk['target']],))
                            if cur.fetchone(): raise HTTPException(409, 'Record has related records; remove the relationship first.')
                    cur.execute(sql.SQL('DELETE FROM {} r WHERE {}').format(sql.Identifier(table), predicate(keys)), tuple(keys.values()))
                    if scope == 'tenant': audit(cur, table, action, user, old, None, maintenance)
                    return None
                immutable = {fk['column'] for fk in spec['foreign_keys']} | set(EXTERNAL) | {'tenant_id', 'doctor_id', 'patient_id'}
                for field in immutable & values.keys():
                    if old.get(field) != values[field]: raise HTTPException(422, f'{field} cannot be reassigned; create a new relationship.')
            combined = {**(old or {}), **values}
            relation_checks(cur, scope, table, combined, user, maintenance, tenant)
            # Validate new row ownership even where parents were admin-visible.
            if not maintenance and action == 'create':
                if 'doctor_id' in combined and user.role == 'DOCTOR': fetch(cur, scope, 'doctors', combined['doctor_id'], user)
                if 'patient_id' in combined: fetch(cur, scope, 'patients', combined['patient_id'], user)
            bound = adapt(spec, values)
            if action == 'create':
                query = sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING *').format(sql.Identifier(table),
                        sql.SQL(', ').join(map(sql.Identifier, bound)), sql.SQL(', ').join(sql.Placeholder() for _ in bound)) if bound else sql.SQL('INSERT INTO {} DEFAULT VALUES RETURNING *').format(sql.Identifier(table))
                cur.execute(query, tuple(bound.values()))
            else:
                assignments = [sql.SQL('{} = %s').format(sql.Identifier(name)) for name in bound]
                if 'updated_at' in spec['columns']: assignments.append(sql.SQL('updated_at = NOW()'))
                if not assignments: raise HTTPException(422, 'No mutable fields provided.')
                cur.execute(sql.SQL('UPDATE {} r SET {} WHERE {} RETURNING r.*').format(sql.Identifier(table), sql.SQL(', ').join(assignments), predicate(keys)), (*bound.values(), *keys.values()))
            result = cur.fetchone()
            if scope == 'tenant' and table in {'doctors', 'patients'} and action == 'create':
                role_code = 'DOCTOR' if table == 'doctors' else 'PATIENT'
                cur.execute('SELECT id FROM roles WHERE code=%s', (role_code,))
                role = cur.fetchone()
                if role is None: raise HTTPException(503, 'Required profile role is not configured.')
                cur.execute('INSERT INTO user_roles(user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (result['user_id'], role['id']))
            if scope == 'tenant' and table in {'doctors','patients'} and 'status' in values:
                cur.execute('UPDATE users SET status=%s, updated_at=NOW() WHERE id=%s', (values['status'], result['user_id']))
            if scope == 'tenant': audit(cur, table, action, user, old, result, maintenance)
            return public_record(result)
