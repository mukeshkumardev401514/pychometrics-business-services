"""Import one assessment JSON object or a list; see docs/import-assessments.md."""

import argparse
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


FIELD_MAP = {
    'assessment_id': 'code',
    'assessment_name': 'name',
    'assessment_full_name': 'full_name',
    'copyright': 'copyright',
    'description': 'description',
    'min_age': 'min_age',
    'max_age': 'max_age',
    'typical_groups': 'typical_groups',
    'charts': 'charts',
    'domain_charts': 'domain_charts',
    't_score': 't_score',
    'domain_t_score': 'domain_t_score',
}
FLAGS = {'domain_charts', 't_score', 'domain_t_score'}


def money(value, label, maximum):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f'{label}: expected a number') from None
    if not result.is_finite() or not 0 <= result <= maximum:
        raise ValueError(f'{label}: must be between 0 and {maximum}')
    if result != result.quantize(Decimal('0.01')):
        raise ValueError(f'{label}: at most two decimal places allowed')
    return result


def normalize(record):
    if not isinstance(record, dict):
        raise ValueError('Each assessment must be a JSON object')
    unknown = set(record) - set(FIELD_MAP) - {
        'assessment_category', 'assessment_duration', 'assessment_cost',
    }
    if unknown:
        raise ValueError(f'Unknown fields: {", ".join(sorted(unknown))}')
    for key in ('assessment_id', 'assessment_name', 'assessment_category'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f'{key}: nonempty text required')
    for key in ('min_age', 'max_age', 'assessment_duration'):
        if type(record.get(key)) is not int:
            raise ValueError(f'{key}: integer required')
    if not 0 <= record['min_age'] <= record['max_age']:
        raise ValueError('Age range must satisfy 0 <= min_age <= max_age')
    if record['assessment_duration'] <= 0:
        raise ValueError('assessment_duration must be positive (minutes)')
    data = {}
    for source, target in FIELD_MAP.items():
        if source not in record:
            continue  # Missing optional fields preserve existing values.
        value = record[source]
        if source in FLAGS:
            if isinstance(value, str) and value.strip().upper() in ('Y', 'N'):
                value = value.strip().upper() == 'Y'
            if value is not None and type(value) is not bool:
                raise ValueError(f'{source}: expected Y, N, boolean or null')
        elif source == 'charts':
            if isinstance(value, str):
                value = [part.strip() for part in value.split(',') if part.strip()]
            if value is not None:
                if not isinstance(value, list) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    raise ValueError('charts: expected comma-separated text or a text array')
                value = [item.strip() for item in value]
        elif source not in ('min_age', 'max_age'):
            if value is not None and not isinstance(value, str):
                raise ValueError(f'{source}: expected text or null')
            value = value.strip() or None if isinstance(value, str) else value
        data[target] = value
    for key, limit in (('code', 100), ('name', 255), ('full_name', 500)):
        if data.get(key) and len(data[key]) > limit:
            raise ValueError(f'{key}: maximum length is {limit}')
    category = record['assessment_category'].strip()
    category_code = re.sub(r'[^A-Z0-9]+', '_', category.upper()).strip('_')
    if len(category) > 255 or not category_code or len(category_code) > 100:
        raise ValueError('assessment_category: invalid name or generated code')
    price = record.get('assessment_cost')
    if price is not None:
        price = money(price, 'assessment_cost', Decimal('9999999999.99'))
    return data, category, category_code, record['assessment_duration'], price


def upsert(conn, item, version, doctor_percentage):
    from psycopg import sql
    from psycopg.types.json import Jsonb

    data, category, category_code, duration, price = item
    matches = conn.execute(
        'SELECT id FROM assessment_categories WHERE lower(name) = lower(%s)',
        (category,),
    ).fetchall()
    if len(matches) > 1:
        raise ValueError(f'Ambiguous category name: {category}')
    if matches:
        category_id = matches[0][0]
    else:
        category_id = conn.execute(
            'INSERT INTO assessment_categories (code, name) VALUES (%s, %s) '
            'ON CONFLICT (code) DO UPDATE SET name = assessment_categories.name '
            'WHERE lower(assessment_categories.name) = lower(EXCLUDED.name) RETURNING id',
            (category_code, category),
        ).fetchone()
        if category_id is None:
            raise ValueError(f'Category code collision: {category_code}')
        category_id = category_id[0]
    values = dict(data, category_id=category_id)
    if values.get('charts') is not None:
        values['charts'] = Jsonb(values['charts'])
    columns = list(values)
    query = sql.SQL(
        'INSERT INTO assessments ({}) VALUES ({}) ON CONFLICT (code) '
        'DO UPDATE SET {}, updated_at = NOW() RETURNING id'
    ).format(
        sql.SQL(', ').join(map(sql.Identifier, columns)),
        sql.SQL(', ').join(sql.Placeholder() for _ in columns),
        sql.SQL(', ').join(
            sql.SQL('{} = EXCLUDED.{}').format(sql.Identifier(c), sql.Identifier(c))
            for c in columns if c != 'code'
        ),
    )
    assessment_id = conn.execute(query, list(values.values())).fetchone()[0]
    version_id = conn.execute(
        'INSERT INTO assessment_versions (assessment_id, version_number, duration_minutes) '
        'VALUES (%s, %s, %s) ON CONFLICT (assessment_id, version_number) '
        'DO UPDATE SET duration_minutes = EXCLUDED.duration_minutes, updated_at = NOW() '
        'RETURNING id', (assessment_id, version, duration),
    ).fetchone()[0]
    if price is not None:
        rows = conn.execute(
            "SELECT id, price, currency, doctor_percentage, platform_percentage "
            "FROM assessment_pricing WHERE assessment_version_id = %s "
            "AND status = 'ACTIVE' AND (effective_to IS NULL OR effective_to > NOW()) "
            "FOR UPDATE", (version_id,),
        ).fetchall()
        if len(rows) > 1:
            raise ValueError(f'{data["code"]}: multiple active/scheduled prices; resolve first')
        if rows:
            current = rows[0]
            doctor = current[3] if doctor_percentage is None else doctor_percentage
            platform = Decimal('100') - doctor
            if (current[1], current[2], current[3], current[4]) != (price, 'INR', doctor, platform):
                # Preserve historical rows rather than changing a previously charged price.
                future = conn.execute(
                    'SELECT effective_from >= NOW() FROM assessment_pricing WHERE id = %s',
                    (current[0],),
                ).fetchone()[0]
                if future:
                    raise ValueError(f'{data["code"]}: scheduled price exists; resolve first')
                conn.execute(
                    "UPDATE assessment_pricing SET status = 'INACTIVE', effective_to = NOW(), "
                    'updated_at = NOW() WHERE id = %s', (current[0],),
                )
            else:
                return
        else:
            if doctor_percentage is None:
                raise ValueError(f'{data["code"]}: new price requires --doctor-percentage')
            doctor = doctor_percentage
            platform = Decimal('100') - doctor
        conn.execute(
            'INSERT INTO assessment_pricing '
            '(assessment_version_id, price, currency, doctor_percentage, platform_percentage) '
            "VALUES (%s, %s, 'INR', %s, %s)", (version_id, price, doctor, platform),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json_file', type=Path)
    parser.add_argument('--version', type=int, default=1, help='Target version number (default: 1)')
    parser.add_argument('--doctor-percentage', help='Required for new non-null prices; platform gets remainder')
    parser.add_argument('--dry-run', action='store_true', help='Perform DB checks and upserts, then roll back')
    parser.add_argument('--validate-only', action='store_true', help='Validate JSON without connecting to DB')
    args = parser.parse_args()
    try:
        if args.version < 1:
            raise ValueError('--version must be positive')
        doctor = None if args.doctor_percentage is None else money(
            args.doctor_percentage, '--doctor-percentage', Decimal('100'),
        )
        raw = json.loads(args.json_file.read_text(encoding='utf-8-sig'))
        records = raw if isinstance(raw, list) else [raw]
        if not records:
            raise ValueError('Input must contain at least one assessment')
        items = []
        seen = set()
        for index, record in enumerate(records, 1):
            try:
                item = normalize(record)
                if item[0]['code'] in seen:
                    raise ValueError('Duplicate assessment_id in input')
                seen.add(item[0]['code'])
                items.append(item)
            except ValueError as exc:
                raise ValueError(f'Record {index}: {exc}') from exc
        if args.validate_only:
            print(f'Validated {len(items)} assessment(s); no DB connection made.')
            return
        import psycopg
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / '.env')
        with psycopg.connect(
            host=os.getenv('PLATFORM_DB_HOST', 'localhost'),
            port=os.getenv('PLATFORM_DB_PORT', '5432'),
            dbname=os.getenv('PLATFORM_DB_NAME', 'psychometric_platform'),
            user=os.getenv('PLATFORM_DB_USER', 'psych_platform_app'),
            password=os.getenv('PLATFORM_DB_PASSWORD', ''),
            connect_timeout=10,
        ) as conn:
            # Serialize runs of this importer across the complete batch.
            conn.execute('SELECT pg_advisory_xact_lock(1340134)')
            for item in items:
                upsert(conn, item, args.version, doctor)
            if args.dry_run:
                conn.rollback()
        print(f'{"Dry run rolled back" if args.dry_run else "Imported"}: {len(items)} assessment(s).')
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Import failed: {exc}\n')


if __name__ == '__main__':
    main()
