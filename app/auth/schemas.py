from pydantic import AliasChoices, BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    tenant_code: str | None = Field(default=None, min_length=2, max_length=50)
    email: EmailStr = Field(validation_alias=AliasChoices('email', 'username'))
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

    user_id: str
    tenant_id: str
    tenant_code: str
    role: str


class CurrentUserResponse(BaseModel):
    user_id: str
    tenant_id: str
    tenant_code: str
    email: EmailStr
    first_name: str
    last_name: str | None
    role: str
