"""JSON-контракт отчёта (философия 2.3 — портрет ребёнка как личности).

Модель отдаёт ДАННЫЕ, шаблон владеет всем видом. Невалидный JSON от Gemini =
неудачная попытка (spec §7.2) — поэтому валидация строгая.

v2.3: ведут личностно-смысловые направления, навыки — поддержка. Добавлены
about_child (нарративный портрет), раздельные рекомендации (понимание ребёнка /
творческие занятия), specialists (тип специалиста как ресурс «если захотите глубже»).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Набор из 7 направлений (4 личностно-смысловых ведут + 3 навыковых поддерживают);
# схема допускает 7–8 на случай расширения зоны 2.
DIMENSIONS_MIN = 7
DIMENSIONS_MAX = 8


class Child(BaseModel):
    name: str = Field(min_length=1)
    age_display: str = Field(min_length=1)  # «5 лет 6 мес.»


class Dimension(BaseModel):
    key: str = Field(min_length=1)            # "world_and_themes", ...
    title: str = Field(min_length=1)          # «Мир и темы рисунка»
    score: int = Field(ge=1, le=10)
    observation: str = Field(min_length=1)    # привязка к конкретным деталям рисунка
    research_note: str = ""                   # общая ссылка на исследование
    activities: list[str] = Field(default_factory=list)


class DevelopmentDirection(BaseModel):
    """Опциональный блок «Возможные направления развития» — для интереса, не прогноз."""
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Specialist(BaseModel):
    """Тип/область специалиста как полезный ресурс «если захотите глубже» (task §5),
    НЕ сигнал тревоги. Опциональный блок."""
    area: str = Field(min_length=1)   # «детский психолог, работающий с проективными методиками»
    reason: str = Field(min_length=1)  # за что зацепился отчёт (видимая деталь/направление)


class Report(BaseModel):
    child: Child
    context_summary: str = ""
    introduction: str = Field(min_length=1)
    about_child: str = Field(min_length=1)    # нарративный портрет ребёнка как личности (ведущий блок)
    dimensions: list[Dimension]
    # рекомендации раздельно: ~половина про понимание/связь с ребёнком, ~половина творческие занятия
    understanding_recommendations: list[str] = Field(default_factory=list)
    art_recommendations: list[str] = Field(default_factory=list)
    specialists: list[Specialist] | None = None
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
