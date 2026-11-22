from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=48)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Введите корректный email")
        return value


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class CreateSaveIn(BaseModel):
    club_source_id: str = Field(min_length=1, max_length=80)
    save_name: str = Field(default="Моя карьера", min_length=2, max_length=48)


class TacticIn(BaseModel):
    formation: str = Field(
        default="4-3-3",
        pattern=r"^(?:3-1-4-2|3-4-1-2|3-4-2-1|3-4-3|3-4-3 Flat|3-5-2|4-1-2-1-2|4-1-2-1-2 \(2\)|4-1-2-1-2 Narrow|4-1-2-1-2 Wide|4-1-3-2|4-1-4-1|4-2-1-3|4-2-2-2|4-2-3-1|4-2-3-1 \(2\)|4-2-3-1 Narrow|4-2-3-1 Wide|4-2-4|4-3-1-2|4-3-2-1|4-3-3|4-3-3 \(2\)|4-3-3 \(3\)|4-3-3 \(4\)|4-3-3 Attack|4-3-3 Defend|4-3-3 Flat|4-3-3 Holding|4-4-1-1 Midfield|4-4-2|4-4-2 \(2\)|4-4-2 Flat|4-4-2 Holding|4-5-1|4-5-1 \(2\)|4-5-1 Attack|4-5-1 Flat|5-2-1-2|5-2-3|5-3-2|5-3-2 Holding|5-4-1|5-4-1 Flat)$",
    )
    mentality: str = Field(default="balanced", pattern=r"^(defensive|balanced|positive|attacking)$")
    style: dict = Field(default_factory=dict)
    starting_xi: list[str] = Field(default_factory=list, max_length=11)
    bench: list[str] = Field(default_factory=list, max_length=9)
