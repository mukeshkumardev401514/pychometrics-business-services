from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class PatientFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    email: EmailStr = Field(max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    mobile: str | None = Field(default=None, min_length=1, max_length=20)
    patient_code: str = Field(min_length=1, max_length=50)
    date_of_birth: date | None = None
    gender: Literal['MALE', 'FEMALE', 'OTHER', 'PREFER_NOT_TO_SAY'] | None = None
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default='India', max_length=100)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_mobile: str | None = Field(default=None, max_length=20)
    emergency_contact_relation: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=10000)


class PatientCreate(PatientFields):
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator('date_of_birth')
    @classmethod
    def validate_birth_date(cls, value):
        if value is not None and value > date.today():
            raise ValueError('Date of birth cannot be in the future.')
        return value


class PatientResponse(PatientFields):
    id: UUID
    user_id: UUID
    primary_doctor_id: UUID
    status: Literal['ACTIVE', 'INACTIVE', 'LOCKED']
    created_at: datetime
    updated_at: datetime
