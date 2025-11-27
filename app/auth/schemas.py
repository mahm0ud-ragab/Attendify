# app/auth/schemas.py

from pydantic import BaseModel, EmailStr, field_validator
from typing import Literal


class RegisterSchema(BaseModel):
    name: str
    email: EmailStr
    password: str
    confirm_password: str
    # Allow all three roles in input, but we’ll block 'admin' later
    role: Literal["student", "lecturer", "admin"]

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty.")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        password = info.data.get("password")  # <-- correct way in Pydantic v2
        if password and v != password:
            raise ValueError("Passwords do not match.")
        return v



class LoginSchema(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Password cannot be empty.")
        return v
