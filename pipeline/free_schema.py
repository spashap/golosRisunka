"""JSON-контракт БЕСПЛАТНОГО разбора одного рисунка (фремиум-бета).

Отдельный контракт, а не урезанная платная схема: у бесплатного разбора другая
задача и другие запреты (task-fremium-beta.md §7). Здесь НЕТ и никогда не будет
блока о самом ребёнке, оценок, направлений, специалистов и талантов — есть ровно
три блока: что видно -> одна деталь (и максимум ОДНА гипотеза) -> что пока неизвестно.

Ключевое отличие от платной схемы: гипотеза отдаётся ОТДЕЛЬНЫМ объектом
(фраза + атрибуция + ключ), а не растворена в прозе. Это требование §8: библиотека
допустимых трактовок должна собираться из того, что модель реально пишет на реальных
рисунках, и заказчик потом размечает накопленные ключи. Побочный выигрыш — линтер
может сверить фразу с текстом и механически удержать правило «ровно одна гипотеза».

`hypothesis = None` — ЗАКОННЫЙ и уважаемый исход (§7): «если законной гипотезы нет —
её нет». Тогда блок 2 работает как видимая деталь -> нейтральное наблюдение -> вопрос
ребёнку. Это не ошибка генерации и не повод для ретрая.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from config.free_keys import ALLOWED_KEYS, NEW_KEY

FREE_SCHEMA_VERSION = "1.0"

# Объём (§7): «170–230 слов обычно, до ~300 только если на рисунке есть материал».
# Потолок с запасом — превышение считаем неудачной попыткой (модель расписалась).
# Нижняя граница низкая намеренно: на скудной каляке разбор ОБЯЗАН быть короче (§9),
# и наказывать за честную краткость нельзя.
# ШАГ 4: разворот на продажу. Прежние 170–230 слов отменены — эмоциональный удар в них
# не помещается (в платном отчёте один только about_child занимает 110–170).
#
# ВАЖНО ПРО КАЛИБРОВКУ: цель «300–380 слов» относится ко ВСЕМУ документу, который видит
# родитель, а продающий финал (~80 слов) пишет сервер, а не модель. Эталон из задания,
# посчитанный по словам, даёт ~235 слов авторского текста + ~80 серверных. Поэтому
# потолок и пол здесь — на МОДЕЛЬНУЮ часть, и они ниже 300 не по недосмотру.
# Сумма целевых объёмов блоков: 60-90 + 80-120 + 50-70 + 25-40 + ~40 = 255-360.
FREE_MAX_WORDS = 370
FREE_MIN_WORDS = 190
# На раскраске портретного блока нет, поэтому пол ниже: короткий служебный абзац,
# одно наблюдение, один вопрос — и дальше просьба принести рисунок с чистого листа.
FREE_MIN_WORDS_COLORING = 130
# Честный зазор — по-прежнему два предложения. Продающий финал за ним пишет НЕ модель,
# а сервер (там цена и оглавление направлений — их нельзя доверять генерации).
FREE_UNKNOWN_MAX_WORDS = 60

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_KEY_CLEAN_RE = re.compile(r"[^a-z0-9_]+")


def count_words(*texts: str) -> int:
    return sum(len(_WORD_RE.findall(t or "")) for t in texts)


def _keep_one_question(text: str) -> str:
    """Оставляет ПЕРВЫЙ вопрос и все невопросительные предложения после него.

    «Кто это? Что он делает? Куда идёт?» -> «Кто это?»
    Фраза про то, что ответ ребёнка точнее догадки взрослого, остаётся: она не вопрос.
    """
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    out, seen_q = [], False
    for p in parts:
        if p.rstrip().endswith("?"):
            if seen_q:
                continue
            seen_q = True
        out.append(p)
    return " ".join(out).strip()


class Hypothesis(BaseModel):
    """Одна интерпретирующая фраза в полной оправе — и её «паспорт» для §8.

    phrase хранится ДОСЛОВНО так, как стоит в detail: линтер сверяет вхождение,
    и только это делает накопленную библиотеку достоверной, а не параллельной
    выдумкой рядом с текстом для родителя.
    """

    phrase: str = Field(min_length=1)
    attribution: str = Field(min_length=1)   # к какой традиции/автору отнесено
    # Ключ ТОЛЬКО из закрытого словаря config/free_keys.py либо "new".
    # Свободное имя запрещено: разброс имён убивает разметку библиотеки (см. шапку
    # free_keys.py). Нормализация ниже мягкая, но членство в словаре — строгое.
    key: str = Field(min_length=1)
    # Заполняется ТОЛЬКО при key="new": трактовка одной фразой, чтобы заказчик мог
    # решить — добавить в словарь или отклонить.
    new_key_description: str = ""
    # Возрастная область применимости трактовки, как её оценивает сама модель
    # («5-12», «7+», «любой»). Нужна библиотеке §8: одна и та же трактовка бывает
    # осмысленной для схематического возраста и сомнительной для доschematического
    # (размер фигуры у трёхлетки определяется контролем руки, а не значимостью).
    # Пишем в лог ВСЕГДА, даже когда трактовка спорна — это и есть кандидат на
    # разметку «только в узком контексте» или «фольклор».
    age_scope: str = ""

    @field_validator("key")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = _KEY_CLEAN_RE.sub("_", v.strip().lower()).strip("_")
        if not v:
            raise ValueError("hypothesis.key пуст после нормализации")
        if v not in ALLOWED_KEYS:
            raise ValueError(
                f"hypothesis.key='{v}' не из словаря. Допустимы только: "
                f"{', '.join(sorted(ALLOWED_KEYS))}. Если подходящей трактовки в "
                f"словаре нет — верни hypothesis=null ЛИБО key='new' с "
                f"new_key_description")
        return v

    @model_validator(mode="after")
    def _new_needs_description(self) -> "Hypothesis":
        if self.key == NEW_KEY and not self.new_key_description.strip():
            raise ValueError("key='new' требует new_key_description — иначе строку "
                             "невозможно разметить")
        return self


# Особые случаи §9. Несовпадения с тревогой здесь НЕТ и быть не должно: оно живёт
# ровно в одном поле — concern_correlate_visible (см. ниже). Не заводить сюда
# 'mismatch' ни в каком виде.
FreeFlag = Literal[
    "sparse",     # скудная каляка 3–4 лет: гипотеза ЗАПРЕЩЕНА (§9)
    "coloring",   # раскраска/обводка: работа в чужих границах
    "thin",       # мало материала: гипотеза остаётся, но переносится на линию/расположение
]


class FreeAnalysis(BaseModel):
    # Блок 1 (60–90 слов): тёплое конкретное открытие — ОДИН образ, привязанный к
    # видимому, а не опись. Поле называлось visible, пока задачей была инвентаризация;
    # переименовано вместе со сменой контракта, чтобы имя не тянуло обратно к протоколу.
    opening: str = Field(min_length=1)
    detail: str = Field(min_length=1)             # блок 2 (80–120): одна деталь в полной оправе
    hypothesis: Hypothesis | None = None
    # Блок 3 (50–70) — то, ради чего мама читает: что ЭТОТ лист говорит о ребёнке.
    # Оправа обязательна, диагноза нет, но прохладный тон здесь — брак.
    # ПУСТОЙ на раскраске: там портрета быть не должно (см. _contracts).
    portrait_hint: str = ""
    question_to_child: str = Field(min_length=1)  # блок 4 (25–40): открытый вопрос + фраза про ответ ребёнка
    unknown_next: str = Field(min_length=1)       # блок 5а (2 предложения): честный зазор

    flags: list[FreeFlag] = Field(default_factory=list)
    # ЕДИНСТВЕННЫЙ источник правды про несовпадение с названной тревогой.
    #   False -> сервер подставит авторский абзац §9; сама модель его не пишет;
    #   None  -> неприменимо (нейтральный путь — тревоги нет вообще).
    # Метки 'mismatch' в flags СОЗНАТЕЛЬНО НЕТ: два представления одного факта уже
    # разъехались однажды (модель отдавала flags=[] при correlate=false), и
    # возвращать её нельзя — читатели должны смотреть ровно сюда.
    concern_correlate_visible: bool | None = None
    concern_correlate_note: str = ""

    insufficient_input: bool = False

    @field_validator("flags")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for f in v:
            if f not in seen:
                seen.append(f)
        return seen

    @model_validator(mode="after")
    def _contracts(self) -> "FreeAnalysis":
        # ШАГ 4 отменил прежний запрет «sparse => hypothesis is None». Появление первого
        # узнаваемого символа среди каракулей — лучший эмоциональный материал во всей
        # партии, и хоронить его под отказом от трактовки было ошибкой. У него есть
        # свой ключ: symbol_emerging_from_scribble.
        # Раскраска — это не разбор, а перенаправление: её единственная задача —
        # получить настоящий рисунок. Портрет здесь противоречил бы служебному абзацу
        # («чтобы увидеть характер, нужен чистый лист») и делал бы две работы сразу,
        # из-за чего оба прогона раскраски и вышли средними.
        if "coloring" in self.flags:
            if self.portrait_hint.strip():
                raise ValueError(
                    "coloring: портретного блока быть не должно — раскраска это "
                    "перенаправление, а не разбор. Верни portrait_hint пустым")
        elif not self.portrait_hint.strip():
            raise ValueError("portrait_hint обязателен: это то, ради чего мама читает")

        # Ровно один вопрос ребёнку — но НЕ ценой сожжённой попытки: лишние вопросы
        # срезаются механически. Три-четыре подряд превращают разбор в домашнее задание,
        # а ронять из-за этого весь разбор (и платить за три попытки) — глупость.
        if self.question_to_child.count("?") != 1:
            object.__setattr__(self, "question_to_child",
                               _keep_one_question(self.question_to_child))
        if "?" not in self.question_to_child:
            raise ValueError("question_to_child должен содержать вопрос ребёнку")

        u = count_words(self.unknown_next)
        if u > FREE_UNKNOWN_MAX_WORDS:
            raise ValueError(
                f"unknown_next {u} слов при потолке {FREE_UNKNOWN_MAX_WORDS}: нужно два "
                f"предложения — какой вопрос рисунок оставляет открытым и что на него "
                f"ответят другие работы")
        n = self.word_count()
        floor = (FREE_MIN_WORDS_COLORING if "coloring" in self.flags
                 else FREE_MIN_WORDS)
        if n > FREE_MAX_WORDS:
            raise ValueError(f"разбор длиннее {FREE_MAX_WORDS} слов ({n}) — сократи")
        if n < floor:
            raise ValueError(
                f"разбор короче {floor} слов ({n}) — нужны тёплое открытие, деталь "
                f"в оправе, вопрос и честный зазор")
        return self

    def word_count(self) -> int:
        # hypothesis.phrase считается тоже: с тех пор как трактовка живёт отдельным
        # объектом и показывается своим блоком, это такой же текст для родителя,
        # как и остальные. Не учитывать её — занижать реальный объём разбора.
        return count_words(self.opening, self.detail, self.portrait_hint,
                           self.question_to_child, self.unknown_next,
                           self.hypothesis.phrase if self.hypothesis else "")


class FreeInsufficient(BaseModel):
    """Непригодный вход. reason_key — чтобы §8 мог считать отказы по типам,
    а страница показала родителю разный текст (переснять / это не детский
    рисунок / пустой лист). Лимит на ребёнка такой разбор НЕ расходует."""

    insufficient_input: Literal[True]
    reason_key: Literal["photo_poor", "not_a_drawing", "blank", "other"] = "other"
    insufficient_reason: str = Field(min_length=1)


def validate_free(data: dict) -> FreeAnalysis | FreeInsufficient:
    """Валидирует сырой JSON от Gemini. Бросает pydantic.ValidationError.
    Дискриминация по insufficient_input — как в платной validate_report()."""
    if data.get("insufficient_input"):
        return FreeInsufficient.model_validate(data)
    return FreeAnalysis.model_validate(data)
