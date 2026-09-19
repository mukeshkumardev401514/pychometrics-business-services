"""Compile the repository's migration DDL into a reviewed API field allowlist.

Not a general SQL parser. Fail closed on unsupported column types or missing PKs.
The runtime never accepts table/column names or SQL from clients.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def split_columns(text):
    depth, quoted, start = 0, False, 0
    for i, char in enumerate(text):
        if char == "'":
            quoted = not quoted
        elif not quoted:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                yield text[start:i].strip()
                start = i + 1
    yield text[start:].strip()


def compile_catalog():
    catalog = {}
    for scope in ('platform', 'tenant'):
        files = sorted((ROOT / 'psychometric-db-models' / scope).glob('*.sql'))
        texts = [(p, re.sub(r'--[^\n]*', '', p.read_text())) for p in files]
        enums = {}
        for _, text in texts:
            for name, values in re.findall(r'CREATE TYPE (\w+) AS ENUM\s*\((.*?)\);', text, re.S | re.I):
                enums[name.lower()] = re.findall(r"'([^']*)'", values)
        tables = {}
        for path, text in texts:
            for match in re.finditer(r'CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?(\w+)\s*\(', text, re.I):
                start, depth, quoted = match.end(), 1, False
                end = start
                while depth:
                    c = text[end]
                    if c == "'": quoted = not quoted
                    if not quoted:
                        depth += (c == '(') - (c == ')')
                    end += 1
                body = text[start:end-1]
                table = {'source': str(path.relative_to(ROOT)), 'columns': {}, 'primary_key': [], 'foreign_keys': []}
                for entry in split_columns(body):
                    if re.match(r'(CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK)\b', entry, re.I):
                        pk = re.search(r'PRIMARY KEY\s*\(([^)]+)\)', entry, re.I)
                        if pk: table['primary_key'] = [x.strip() for x in pk[1].split(',')]
                        continue
                    m = re.match(r'(\w+)\s+(character varying\(\d+\)|timestamp with time zone|varchar\(\d+\)|numeric(?:\(\d+(?:,\d+)?\))?|\w+)', entry, re.I)
                    if not m: raise ValueError(entry)
                    name, dtype = m[1], m[2].lower()
                    info = {'type': dtype, 'nullable': not bool(re.search(r'NOT NULL|PRIMARY KEY', entry, re.I)), 'default': bool(re.search(r'\bDEFAULT\b', entry, re.I))}
                    if dtype in enums: info['enum'] = enums[dtype]
                    elif not re.match(r'^(uuid|text|boolean|integer|bigint|date|time|timestamptz|timestamp with time zone|inet|jsonb|varchar\(\d+\)|character varying\(\d+\)|numeric(?:\(\d+(?:,\d+)?\))?)$', dtype):
                        raise ValueError((name, dtype))
                    table['columns'][name] = info
                    if 'PRIMARY KEY' in entry.upper(): table['primary_key'].append(name)
                    inline = re.search(r'REFERENCES\s+(?:public\.)?(\w+)\s*\((\w+)\)', entry, re.I)
                    if inline: table['foreign_keys'].append({'column': name, 'table': inline[1], 'target': inline[2]})
                for col, target, target_col in re.findall(r'FOREIGN KEY\s*\(\s*(\w+)\s*\)\s*REFERENCES\s+(?:public\.)?(\w+)\s*\(\s*(\w+)\s*\)', body, re.I):
                    table['foreign_keys'].append({'column': col, 'table': target, 'target': target_col})
                assert table['primary_key'], match[1]
                tables[match[1]] = table
        # V019 adds the only column/FK via ALTER TABLE in these migrations.
        if scope == 'platform':
            tables['assessments']['columns']['category_id'] = {'type': 'uuid', 'nullable': True, 'default': False}
            tables['assessments']['foreign_keys'].append({'column': 'category_id', 'table': 'assessment_categories', 'target': 'id'})
        catalog[scope] = tables
    return catalog


if __name__ == '__main__':
    catalog = compile_catalog()
    (ROOT / 'app/resources/catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    print({scope: len(tables) for scope, tables in catalog.items()})
