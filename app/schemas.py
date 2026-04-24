from __future__ import annotations

from pydantic import BaseModel, Field


class SearchOptions(BaseModel):
    top_k: int = Field(default=24, ge=1, le=100)
    group_by_person: bool = True
    target_type: str = Field(default="person")


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)
    invite_code: str = Field(min_length=1)
    display_name: str | None = None


class InviteCreateIn(BaseModel):
    code: str | None = None
    label: str | None = None
    max_uses: int = Field(default=1, ge=1, le=500)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


class TextSearchIn(SearchOptions):
    text: str = Field(min_length=1)


class AttributeSearchIn(SearchOptions):
    attributes: dict[str, str | None]


class ImageIdSearchIn(SearchOptions):
    image_id: int
