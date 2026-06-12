"""JSON-контракт отчёта (spec §7.3 + опциональный development_directions).

Модель отдаёт ДАННЫЕ, шаблон владеет всем видом. Невалидный JSON от Gemini =
неудачная попытка (spec §7.2) — поэтому валидация строгая.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# 8 направлений спецификации; решение задач + логическое мышление можно
# объединять при нехватке данных => допустимо 7 или 8 элементов.
DIMENSIONS_MIN = 7
DIMENSIONS_MAX = 8


class Child(BaseModel):
    name: str = Field(min_length=1)
    age_display: str = Field(min_length=1)  # «5 лет 6 мес.»


class Dimension(BaseModel):
    key: str = Field(min_length=1)            # "creativity", ...
    title: str = Field(min_length=1)          # «Креативность»
    score: int = Field(ge=1, le=10)
    observation: str = Field(min_length=1)    # привязка к конкретным деталям рисунка
    research_note: str = ""                   # общая ссылка на исследование
    activities: list[str] = Field(default_factory=list)


class DevelopmentDirection(BaseModel):
    """Опциональный блок «Возможные направления развития» — для интереса, не прогноз."""
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Report(BaseModel):
    child: Child
    context_summary: str = ""
    introduction: str = Field(min_length=1)
    dimensions: list[Dimension]
    recommendations: list[str] = Field(default_factory=list)
    development_directions: list[DevelopmentDirection] | None = None
    conclusion: str = Field(min_length=1)
    insufficient_input: bool = False
    insufficient_reason: str | None = None

    @field_validator("dimensions")
    @classmethod
    def _dimensions_count(cls, v: list[Dimension]) -> list[Dimension]:
        if not (DIMENSIONS_MIN <= len(v) <= DIMENSIONS_MAX):
            raise ValueError(
                f"dimensions: expected {DIMENSIONS_MIN}-{DIMENSIONS_MAX}, got {len(v)}"
            )
        return v


class InsufficientReport(BaseModel):
    """Когда insufficient_input=true, остальное может отсутствовать — отчёт не рендерится."""
    insufficient_input: bool
    insufficient_reason: str = Field(min_length=1)


def validate_report(data: dict) -> Report | InsufficientReport:
    """Валидирует сырой JSON от Gemini. Бросает pydantic.ValidationError."""
    if data.get("insufficient_input"):
        return InsufficientReport.model_validate(data)
    return Report.model_validate(data)
