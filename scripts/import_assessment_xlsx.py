"""Import the first two sheets of each XLSX in a folder; see docs/import-assessment-xlsx.md."""

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import os
from pathlib import Path
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

if __package__:
    from .import_assessments import normalize, upsert, money
else:
    from import_assessments import normalize, upsert, money

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_sheets(path):
    """Read only the first two worksheet parts, preserving literal 'None' labels."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in item.findall('.//m:t', NS))
                       for item in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        relationships = {r.attrib['Id']: r for r in ET.fromstring(
            archive.read('xl/_rels/workbook.xml.rels'))}
        sheets = list(workbook.find('m:sheets', NS))[:2]
        if len(sheets) != 2:
            raise ValueError('At least two worksheets required')
        result = []
        for sheet in sheets:
            rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            relationship = relationships[rid]
            if relationship.attrib.get('TargetMode') == 'External':
                raise ValueError('External worksheet links are unsupported')
            target = relationship.attrib['Target']
            target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
            root = ET.fromstring(archive.read(target))
            rows = []
            for row in root.findall('m:sheetData/m:row', NS):
                values = {}
                for cell in row.findall('m:c', NS):
                    if cell.find('m:f', NS) is not None:
                        raise ValueError(f'{sheet.attrib["name"]} {cell.attrib["r"]}: formulas unsupported; use values')
                    kind = cell.attrib.get('t')
                    node = cell.find('m:v', NS)
                    value = node.text if node is not None else None
                    if kind == 's' and value is not None:
                        value = strings[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
                    elif kind == 'b':
                        value = value == '1'
                    elif kind == 'e':
                        raise ValueError(f'Excel error at {cell.attrib["r"]}')
                    elif value is not None and kind not in ('str', 's'):
                        number = Decimal(value)
                        value = int(number) if number == number.to_integral_value() else float(number)
                    values[re.sub(r'\d', '', cell.attrib['r'])] = value
                if any(v is not None and str(v).strip() for v in values.values()):
                    rows.append((row.attrib['r'], values))
            if len(rows) < 2:
                raise ValueError(f'{sheet.attrib["name"]}: missing headers/data')
            headers = {col: str(v).strip() for col, v in rows[0][1].items() if v is not None and str(v).strip()}
            if len(set(headers.values())) != len(headers):
                raise ValueError('Duplicate column headers')
            records = []
            for row_number, values in rows[1:]:
                if any(col not in headers and v is not None for col, v in values.items()):
                    raise ValueError(f'Row {row_number}: data without header')
                records.append({name: values.get(col) for col, name in headers.items()})
            result.append(records)
        return result


def required_text(value, label, limit=None):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}: nonempty text required')
    value = value.strip()
    if limit and len(value) > limit:
        raise ValueError(f'{label}: maximum length {limit}')
    return value


def normalize_questions(records):
    questions, seen = [], set()
    for row in records:
        number = row.get('sr_no')
        if type(number) is not int or not 1 <= number <= 2147483647 or number in seen:
            raise ValueError(f'sr_no {number}: unique positive integer required')
        seen.add(number)
        unknown = [k for k in row if k not in {'sr_no', 'domain', 'sub_domain', 'question', 'image'}
                   and not re.fullmatch(r'(option|weightage)_[1-9]\d*', k)]
        if unknown:
            raise ValueError(f'Question {number}: unknown columns {unknown}')
        if row.get('image') is not None and str(row['image']).strip():
            raise ValueError(f'Question {number}: images require a schema extension')
        options = []
        indices = sorted({int(k.rsplit('_', 1)[1]) for k in row
                          if re.fullmatch(r'(option|weightage)_[1-9]\d*', k)})
        for i in indices:
            label, weight = row.get(f'option_{i}'), row.get(f'weightage_{i}')
            blank_label = label is None or (isinstance(label, str) and not label.strip())
            blank_weight = weight is None or (isinstance(weight, str) and not weight.strip())
            if blank_label and blank_weight:
                continue
            if blank_label or blank_weight:
                raise ValueError(f'Question {number}: option_{i} and weightage_{i} must both be supplied')
            if isinstance(label, (int, float)) and not isinstance(label, bool):
                label = str(label)
            label = required_text(label, f'Question {number} option_{i}', 500)
            try:
                score = Decimal(str(weight))
                valid = score.is_finite() and abs(score) <= Decimal('99999999.99') and score == score.quantize(Decimal('.01'))
            except InvalidOperation:
                valid = False
            if not valid:
                raise ValueError(f'Question {number} weightage_{i}: finite number with at most 2 decimals required')
            if i > 2147483647:
                raise ValueError('Option index exceeds database integer range')
            options.append((i, label, score))
        if not options:
            raise ValueError(f'Question {number}: at least one option required')
        questions.append(dict(number=number, domain=required_text(row.get('domain'), 'domain', 255),
                              sub_domain=required_text(row.get('sub_domain'), 'sub_domain', 255),
                              text=required_text(row.get('question'), 'question'), options=options))
    if not questions:
        raise ValueError('No questions found')
    return sorted(questions, key=lambda q: q['number'])


def load_workbook(path):
    bio, rows = read_sheets(path)
    if len(bio) != 1:
        raise ValueError('Bio sheet must contain exactly one assessment')
    return normalize(bio[0]), normalize_questions(rows)


def sync_rows(conn, table, parent_column, parent_id, key_column, records):
    """Keep IDs stable; refuse removal of existing rows rather than leave stale data."""
    from psycopg import sql
    existing = conn.execute(sql.SQL('SELECT {} FROM {} WHERE {} = %s').format(
        sql.Identifier(key_column), sql.Identifier(table), sql.Identifier(parent_column)), (parent_id,)).fetchall()
    expected = {r[key_column] for r in records}
    if any(row[0] not in expected for row in existing):
        raise ValueError(f'{table}: existing rows absent from input; use a new assessment version')
    result = {}
    for record in records:
        values = {parent_column: parent_id, **record}
        columns = list(values)
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}, {}) DO UPDATE SET {}, updated_at = NOW() RETURNING id').format(
            sql.Identifier(table), sql.SQL(', ').join(map(sql.Identifier, columns)),
            sql.SQL(', ').join(sql.Placeholder() for _ in columns),
            sql.Identifier(parent_column), sql.Identifier(key_column),
            sql.SQL(', ').join(sql.SQL('{} = EXCLUDED.{}').format(sql.Identifier(c), sql.Identifier(c))
                               for c in columns if c not in (parent_column, key_column)))
        result[record[key_column]] = conn.execute(query, list(values.values())).fetchone()[0]
    return result


def import_workbook(conn, item, questions, version, doctor):
    # Share the lock with the existing metadata importer.
    conn.execute('SELECT pg_advisory_xact_lock(1340134)')
    current = conn.execute('SELECT v.status FROM assessment_versions v JOIN assessments a ON a.id=v.assessment_id '
                           'WHERE a.code=%s AND v.version_number=%s FOR UPDATE OF v', (item[0]['code'], version)).fetchone()
    if current and current[0] != 'DRAFT':
        raise ValueError('Question imports require a DRAFT version; select a new version')
    upsert(conn, item, version, doctor)
    version_id = conn.execute('SELECT v.id FROM assessment_versions v JOIN assessments a ON a.id=v.assessment_id '
                              'WHERE a.code=%s AND v.version_number=%s', (item[0]['code'], version)).fetchone()[0]
    domains = list(dict.fromkeys(q['domain'] for q in questions))
    pairs = list(dict.fromkeys((q['domain'], q['sub_domain']) for q in questions))
    existing_sections = conn.execute(
        'SELECT display_order, name FROM assessment_sections WHERE assessment_version_id=%s',
        (version_id,),
    ).fetchall()
    for order, name in existing_sections:
        if order > len(domains) or domains[order - 1] != name:
            raise ValueError('Existing domain names/order differ; use a new assessment version')
    sections = sync_rows(conn, 'assessment_sections', 'assessment_version_id', version_id, 'display_order',
                         [dict(display_order=i, name=name) for i, name in enumerate(domains, 1)])
    # Scoped codes distinguish equal sub-domain labels belonging to different domains.
    codes = {pair: 'XLSX_' + hashlib.sha256(('\0'.join(pair)).encode()).hexdigest() for pair in pairs}
    dimensions = sync_rows(conn, 'assessment_dimensions', 'assessment_version_id', version_id, 'code',
                           [dict(code=codes[pair], name=pair[1], description=pair[0], display_order=i)
                            for i, pair in enumerate(pairs, 1)])
    for section_order, domain in enumerate(domains, 1):
        group = [q for q in questions if q['domain'] == domain]
        question_ids = sync_rows(conn, 'questions', 'assessment_section_id', sections[section_order], 'display_order',
                                [dict(display_order=q['number'], question_text=q['text'], question_type='SINGLE_CHOICE') for q in group])
        for q in group:
            option_ids = sync_rows(conn, 'question_options', 'question_id', question_ids[q['number']], 'display_order',
                                   [dict(display_order=i, option_text=label, option_value=str(i)) for i, label, _ in q['options']])
            for i, _, score in q['options']:
                sync_rows(conn, 'question_option_scores', 'question_option_id', option_ids[i], 'dimension_id',
                          [dict(dimension_id=dimensions[codes[(q['domain'], q['sub_domain'])]], score=score)])


def run_files(paths, process, continue_on_error=False):
    failures = 0
    seen = set()
    for path in paths:
        try:
            item, questions = load_workbook(path)
            code = item[0]['code']
            if code in seen:
                raise ValueError(f'Duplicate assessment code in folder: {code}')
            seen.add(code)
            process(item, questions)
            print(f'OK {path.name}: {code}, {len(questions)} questions, {sum(len(q["options"]) for q in questions)} options')
        except Exception as exc:
            failures += 1
            print(f'FAILED {path.name}: {exc}', file=sys.stderr)
            if not continue_on_error:
                break
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--version', type=int, default=1)
    parser.add_argument('--doctor-percentage')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--validate-only', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    parser.add_argument('--continue-on-error', action='store_true')
    args = parser.parse_args()
    try:
        if args.version < 1:
            raise ValueError('--version must be positive')
        if not args.folder.is_dir():
            raise ValueError('Supply an existing folder')
        paths = sorted(p for p in args.folder.iterdir() if p.is_file() and p.suffix.lower() == '.xlsx' and not p.name.startswith('~$'))
        if not paths:
            raise ValueError('No XLSX files found in folder')
        doctor = None if args.doctor_percentage is None else money(args.doctor_percentage, '--doctor-percentage', Decimal(100))
        def process(item, questions):
            if args.validate_only:
                return
            import psycopg
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[1] / '.env')
            with psycopg.connect(host=os.getenv('PLATFORM_DB_HOST', 'localhost'),
                                 port=os.getenv('PLATFORM_DB_PORT', '5432'),
                                 dbname=os.getenv('PLATFORM_DB_NAME', 'psychometric_platform'),
                                 user=os.getenv('PLATFORM_DB_USER', 'psych_platform_app'),
                                 password=os.getenv('PLATFORM_DB_PASSWORD', ''), connect_timeout=10) as conn:
                import_workbook(conn, item, questions, args.version, doctor)
                if args.dry_run:
                    conn.rollback()
        failures = run_files(paths, process, args.continue_on_error)
        print(f'Mode: {"validation only (no DB)" if args.validate_only else "dry run (rolled back)" if args.dry_run else "import (committed per file)"}; failures: {failures}')
        return 1 if failures else 0
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Import failed: {exc}\n')


if __name__ == '__main__':
    sys.exit(main())
