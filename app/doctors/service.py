from psycopg import sql
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from fastapi import HTTPException

from app.core.security import hash_password
from app.db.tenant import get_tenant_connection

USER_FIELDS = {'email', 'first_name', 'last_name', 'mobile'}
SELECT_DOCTOR = '''
    SELECT d.id, d.user_id, d.doctor_code, u.email, u.first_name,
           u.last_name, u.mobile, d.specialization, d.qualification,
           d.medical_registration_number, d.registration_authority,
           d.registration_year, d.designation, d.department,
           d.experience_years, d.bio, d.is_verified, d.status,
           d.created_at, d.updated_at
    FROM doctors d JOIN users u ON u.id = d.user_id
'''


def _insert(cur, table, values):
    cur.execute(
        sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING id').format(
            sql.Identifier(table),
            sql.SQL(', ').join(map(sql.Identifier, values)),
            sql.SQL(', ').join(sql.Placeholder() for _ in values),
        ),
        tuple(values.values()),
    )
    return cur.fetchone()['id']


def _update(cur, table, record_id, values):
    if not values:
        return
    cur.execute(
        sql.SQL('UPDATE {} SET {}, updated_at = NOW() WHERE id = %s').format(
            sql.Identifier(table),
            sql.SQL(', ').join(
                sql.SQL('{} = %s').format(sql.Identifier(key)) for key in values
            ),
        ),
        (*values.values(), record_id),
    )


def create_doctor(tenant, request):
    values = request.model_dump(exclude={'password'})
    values['email'] = str(values['email']).lower()
    user_values = {key: values.pop(key) for key in USER_FIELDS}
    user_values['password_hash'] = hash_password(request.password.get_secret_value())
    try:
        with get_tenant_connection(tenant) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id FROM roles WHERE code = 'DOCTOR'")
                role = cur.fetchone()
                if role is None:
                    raise HTTPException(503, 'Doctor role is not configured.')
                cur.execute('SELECT id FROM users WHERE LOWER(email) = %s', (user_values['email'],))
                if cur.fetchone():
                    raise HTTPException(409, 'Email already exists.')
                user_id = _insert(cur, 'users', user_values)
                cur.execute('INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)', (user_id, role['id']))
                doctor_id = _insert(cur, 'doctors', {**values, 'user_id': user_id})
                cur.execute(SELECT_DOCTOR + ' WHERE d.id = %s', (doctor_id,))
                return cur.fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'Email, mobile or doctor code already exists.') from None


def list_doctors(tenant, limit, offset):
    with get_tenant_connection(tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SELECT_DOCTOR + ' ORDER BY d.created_at DESC, d.id LIMIT %s OFFSET %s', (limit, offset))
            return {'items': cur.fetchall(), 'limit': limit, 'offset': offset}


def get_doctor(tenant, doctor_id):
    with get_tenant_connection(tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SELECT_DOCTOR + ' WHERE d.id = %s', (doctor_id,))
            doctor = cur.fetchone()
            if doctor is None:
                raise HTTPException(404, 'Doctor not found.')
            return doctor


def update_doctor(tenant, doctor_id, request):
    values = request.model_dump(exclude_unset=True)
    if 'email' in values:
        values['email'] = str(values['email']).lower()
    user_values = {key: values.pop(key) for key in USER_FIELDS if key in values}
    if 'status' in values:
        user_values['status'] = values['status']
    try:
        with get_tenant_connection(tenant) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute('SELECT user_id FROM doctors WHERE id = %s FOR UPDATE', (doctor_id,))
                doctor = cur.fetchone()
                if doctor is None:
                    raise HTTPException(404, 'Doctor not found.')
                if 'email' in user_values:
                    cur.execute('SELECT id FROM users WHERE LOWER(email) = %s AND id <> %s', (user_values['email'], doctor['user_id']))
                    if cur.fetchone():
                        raise HTTPException(409, 'Email already exists.')
                _update(cur, 'users', doctor['user_id'], user_values)
                _update(cur, 'doctors', doctor_id, values)
                if not values:
                    cur.execute('UPDATE doctors SET updated_at = NOW() WHERE id = %s', (doctor_id,))
                cur.execute(SELECT_DOCTOR + ' WHERE d.id = %s', (doctor_id,))
                return cur.fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'Email or mobile already exists.') from None


def get_own_profile(current_user):
    with get_tenant_connection(current_user.tenant) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SELECT_DOCTOR + ' WHERE d.user_id = %s', (current_user.user_id,))
            doctor = cur.fetchone()
            if doctor is None:
                raise HTTPException(404, 'Doctor profile not found.')
            return doctor


def create_own_profile(current_user, request):
    if current_user.role != 'DOCTOR' or current_user.tenant.tenant_type != 'INDIVIDUAL_DOCTOR':
        raise HTTPException(403, 'Individual doctor account required.')
    values = request.model_dump(exclude_unset=True)
    user_values = {key: values.pop(key) for key in USER_FIELDS if key in values}
    try:
        with get_tenant_connection(current_user.tenant) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Serialize profile creation for the same provisioned account.
                cur.execute('SELECT id FROM users WHERE id = %s FOR UPDATE', (current_user.user_id,))
                if cur.fetchone() is None:
                    raise HTTPException(401, 'User authentication is no longer valid.')
                cur.execute('SELECT id FROM doctors WHERE user_id = %s', (current_user.user_id,))
                if cur.fetchone() is not None:
                    raise HTTPException(409, 'Doctor profile already exists.')
                _update(cur, 'users', current_user.user_id, user_values)
                doctor_id = _insert(cur, 'doctors', {**values, 'user_id': current_user.user_id})
                cur.execute(SELECT_DOCTOR + ' WHERE d.id = %s', (doctor_id,))
                return cur.fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'Mobile, doctor code or profile already exists.') from None
