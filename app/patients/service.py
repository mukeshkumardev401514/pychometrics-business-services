from fastapi import HTTPException
from psycopg import Error, sql
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from app.auth.dependencies import CurrentUser
from app.core.security import hash_password
from app.db.tenant import get_tenant_connection
from app.patients.schemas import PatientCreate, PatientResponse


def create_patient(current_user: CurrentUser, request: PatientCreate) -> PatientResponse:
    if current_user.role != 'DOCTOR':
        raise HTTPException(403, 'Only doctors can create patients.')

    values = request.model_dump(exclude={'password'})
    user_values = {key: values.pop(key) for key in ('email', 'first_name', 'last_name', 'mobile')}
    user_values['email'] = str(user_values['email']).lower()

    try:
        with get_tenant_connection(current_user.tenant) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id FROM doctors WHERE user_id = %s AND status = 'ACTIVE' FOR SHARE",
                    (current_user.user_id,),
                )
                doctor = cur.fetchone()
                if doctor is None:
                    raise HTTPException(403, 'Active doctor profile required.')
                cur.execute("SELECT id FROM roles WHERE code = 'PATIENT'")
                role = cur.fetchone()
                if role is None:
                    raise HTTPException(503, 'Patient role is not configured.')
                cur.execute('SELECT id FROM users WHERE LOWER(email) = %s', (user_values['email'],))
                if cur.fetchone() is not None:
                    raise HTTPException(409, 'Email already exists.')

                cur.execute(
                    '''INSERT INTO users (email, first_name, last_name, mobile, password_hash)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id''',
                    (*user_values.values(), hash_password(request.password.get_secret_value())),
                )
                user_id = cur.fetchone()['id']
                cur.execute('INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)', (user_id, role['id']))
                values['user_id'] = user_id
                cur.execute(
                    sql.SQL('INSERT INTO patients ({}) VALUES ({}) RETURNING id, status, created_at, updated_at').format(
                        sql.SQL(', ').join(map(sql.Identifier, values)),
                        sql.SQL(', ').join(sql.Placeholder() for _ in values),
                    ),
                    tuple(values.values()),
                )
                patient = cur.fetchone()
                cur.execute(
                    '''INSERT INTO doctor_patients (doctor_id, patient_id, is_primary_doctor)
                       VALUES (%s, %s, TRUE)''',
                    (doctor['id'], patient['id']),
                )
                # Validate before the connection context commits all four writes.
                return PatientResponse(**user_values, **values, **patient, primary_doctor_id=doctor['id'])
    except UniqueViolation:
        raise HTTPException(409, 'Email, mobile or patient code already exists.') from None
    except Error:
        raise HTTPException(503, 'Unable to create patient at this time.') from None
