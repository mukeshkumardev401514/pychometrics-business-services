"""Create test patients through the API and save credentials locally."""
import argparse
import csv
from datetime import datetime, timezone
from getpass import getpass
import json
import os
from pathlib import Path
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def api(base_url, path, token, body=None):
    request = Request(
        base_url.rstrip('/') + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.count < 1:
        parser.error('--count must be positive')
    token = getpass('Doctor access token: ').strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    try:
        doctor = api(args.base_url, '/auth/me', token)
    except (HTTPError, URLError, TimeoutError):
        raise SystemExit('Doctor token verification failed. Check API URL and use a fresh login token.')
    if doctor.get('role') != 'DOCTOR':
        raise SystemExit('A DOCTOR access token is required.')

    batch = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + secrets.token_hex(3)
    output = args.output or Path('test-credentials') / f'patients-{batch}.csv'
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting an earlier batch's credentials.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created = 0
    with os.fdopen(fd, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=[
            'tenant_code', 'username', 'password', 'patient_code', 'patient_id', 'status'])
        writer.writeheader()
        for index in range(1, args.count + 1):
            email = f'patient-{batch}-{index:03d}@example.com'
            password = 'Test@' + secrets.token_urlsafe(12)
            code = f'PAT-{batch}-{index:03d}'
            row = dict(tenant_code=doctor['tenant_code'], username=email,
                       password=password, patient_code=code, patient_id='', status='')
            try:
                patient = api(args.base_url, '/patients', token, {
                    'email': email, 'password': password, 'first_name': f'Test{index}',
                    'last_name': 'Patient', 'patient_code': code,
                    'date_of_birth': '1995-01-15', 'gender': 'FEMALE', 'country': 'India',
                    'address_line1': f'Flat {index}, Test Residency',
                    'address_line2': 'Sample Street',
                    'city': 'New Delhi', 'state': 'Delhi', 'postal_code': '110001',
                    'emergency_contact_name': f'Test Guardian {index}',
                    'emergency_contact_mobile': '0000000000',
                    'emergency_contact_relation': 'Parent',
                    'notes': f'Synthetic test patient, batch {batch}, record {index}.',
                })
                row.update(patient_id=patient['id'], status='CREATED')
                created += 1
            except HTTPError as error:
                row['status'] = f'HTTP_{error.code}'
            except (URLError, TimeoutError, ValueError, KeyError, OSError):
                # A timeout may happen after the server commits. Preserve the
                # attempted credentials and stop rather than retrying blindly.
                row['status'] = 'UNKNOWN_CHECK_SERVER'
            writer.writerow(row)
            file.flush()
            os.fsync(file.fileno())
            print(f'{index}/{args.count}: {code} {row["status"]}', flush=True)
            if row['status'] != 'CREATED':
                print('Stopped on error; inspect CSV status before retrying.')
                break
    print(f'Created {created}/{args.count}. Credentials: {output.resolve()}')
    return 0 if created == args.count else 1


if __name__ == '__main__':
    raise SystemExit(main())
