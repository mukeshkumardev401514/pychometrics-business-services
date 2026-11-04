from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator

Status = Literal['ACTIVE', 'INACTIVE', 'LOCKED']


class DoctorFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    last_name: str | None = Field(default=None, max_length=100)
    mobile: str | None = Field(default=None, min_length=1, max_length=20)
    specialization: str | None = Field(default=None, max_length=255)
    qualification: str | None = Field(default=None, max_length=255)
    medical_registration_number: str | None = Field(default=None, max_length=100)
    registration_authority: str | None = Field(default=None, max_length=255)
    registration_year: int | None = Field(default=None, ge=1900, le=2100)
    designation: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    experience_years: Decimal | None = Field(default=None, ge=0, max_digits=5, decimal_places=2)
    bio: str | None = Field(default=None, max_length=10000)


class DoctorSelfCreate(DoctorFields):
    doctor_code: str = Field(min_length=1, max_length=50)


class DoctorCreate(DoctorFields):
    email: EmailStr = Field(max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=8, max_length=128)
    doctor_code: str = Field(min_length=1, max_length=50)


class DoctorUpdate(DoctorFields):
    email: EmailStr | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    status: Status | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('At least one field is required.')
        for field in ('email', 'first_name', 'status'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} cannot be null.')
        return self


class DoctorResponse(DoctorFields):
    id: UUID
    user_id: UUID
    doctor_code: str
    email: EmailStr
    first_name: str
    status: Status
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class DoctorListResponse(BaseModel):
    items: list[DoctorResponse]
    limit: int
    offset: int
