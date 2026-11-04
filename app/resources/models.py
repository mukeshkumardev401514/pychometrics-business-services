import json
import re
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, create_model, model_validator

CATALOG = json.loads(Path(__file__).with_name('catalog.json').read_text())
SECRETS = {'password_hash', 'token_hash', 'otp_code', 'access_token_hash', 'razorpay_signature', 'secret_reference'}
SERVER_FIELDS = {'id', 'created_at', 'updated_at', 'last_login_at'}


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def validate_values(self):
        if self.__class__.__name__.endswith('Update') and not self.model_fields_set:
            raise ValueError('At least one field is required.')
        for key in self.model_fields_set:
            if getattr(self, key) is None and self.__class__.model_fields[key].json_schema_extra.get('not_null', False):
                raise ValueError(f'{key} cannot be null.')
        return self


class AssessmentInputModel(InputModel):
    @model_validator(mode='before')
    @classmethod
    def normalize_metadata(cls, values):
        import math
        if not isinstance(values, dict):
            return values
        values = dict(values)
        for key, value in values.items():
            if key in cls.model_fields and cls.model_fields[key].json_schema_extra.get('not_null') is False:
                if isinstance(value, float) and math.isnan(value):
                    values[key] = None
            if isinstance(values[key], str):
                values[key] = values[key].strip()
        if isinstance(values.get('charts'), str):
            values['charts'] = [part.strip() for part in values['charts'].split(',') if part.strip()]
        return values

    @model_validator(mode='after')
    def validate_age_range(self):
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValueError('min_age cannot exceed max_age.')
        return self


def field_type(info):
    dtype = info['type']
    if 'enum' in info:
        return Literal[tuple(info['enum'])]
    if dtype.startswith('numeric'): return Decimal
    return {'uuid': UUID, 'integer': int, 'bigint': int, 'boolean': bool, 'date': date,
            'time': time, 'timestamptz': datetime, 'timestamp with time zone': datetime,
            'jsonb': Any}.get(dtype, str)


def input_model(scope, table, update=False):
    spec = CATALOG[scope][table]
    fields = {}
    for name, info in spec['columns'].items():
        if name in SERVER_FIELDS | SECRETS or (update and name in spec['primary_key']):
            continue
        annotation = EmailStr if name == 'email' else field_type(info)
        kwargs = {'json_schema_extra': {'not_null': not info['nullable']}}
        if scope == 'platform' and table == 'assessments':
            if name == 'charts': annotation = list[str]
            if name in {'min_age', 'max_age'}: kwargs['ge'] = 0
        size = re.search(r'(?:varchar|character varying)\((\d+)\)', info['type'])
        if size: kwargs['max_length'] = int(size[1])
        numeric = re.fullmatch(r'numeric\((\d+),(\d+)\)', info['type'])
        if numeric: kwargs.update(max_digits=int(numeric[1]), decimal_places=int(numeric[2]))
        if update or info['nullable'] or info['default']:
            annotation = annotation | None
            default = None
        else:
            default = ...
        fields[name] = (annotation, Field(default=default, **kwargs))
    if table in ('users', 'platform_users'):
        fields['password'] = (SecretStr | None if update else SecretStr,
                              Field(default=None if update else ..., min_length=8, max_length=128,
                                    json_schema_extra={'not_null': True}))
    return create_model(f'{scope.title()}{"".join(x.title() for x in table.split("_"))}{"Update" if update else "Create"}',
                        __base__=AssessmentInputModel if scope == 'platform' and table == 'assessments' else InputModel, **fields)


def public_record(row):
    if isinstance(row, dict):
        return {key: public_record(value) for key, value in row.items() if key not in SECRETS}
    if isinstance(row, list):
        return [public_record(value) for value in row]
    return row
