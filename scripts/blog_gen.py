"""Генерация и расширение статей блога через Gemini (философия 2.3, SEO-структура).

  venv\\Scripts\\python.exe scripts\\blog_gen.py --plan            # что будет сделано
  venv\\Scripts\\python.exe scripts\\blog_gen.py --all             # все статьи из PLAN
  venv\\Scripts\\python.exe scripts\\blog_gen.py --slug <slug>     # одна статья
  venv\\Scripts\\python.exe scripts\\blog_gen.py --all --only-new  # только новые

Существующие статьи РАСШИРЯЮТСЯ (исходный текст подаётся модели как материал:
сохранить факты и голос, переписать под текущую философию продукта, дописать разделы).
Каждая статья проходит линтер: HARD-баны из pipeline/lint.py, длина, размер title/description,
обязательные разделы, внутренние ссылки только на известные адреса. При провале — один
repair-вызов с замечаниями. Результат — content/blog/<slug>.md (frontmatter + markdown).
Консоль cp1252: печатаем только ASCII. Отчёт — data/tmp/blog_gen_report.txt.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from google import genai                      # noqa: E402
from google.genai import types                # noqa: E402

from config import settings                   # noqa: E402
from pipeline.lint import HARD_BANNED         # noqa: E402

BLOG = BASE / "content" / "blog"
REPORT = BASE / "data" / "tmp" / "blog_gen_report.txt"
TODAY = datetime.date.today().isoformat()
MODEL = "gemini-2.5-pro"

# Возраст -> образец отчёта (ссылка «посмотрите пример»)
SAMPLES = {"3": "/primer/primer-3-goda", "6": "/primer/primer-6-let", "8": "/primer/primer-8-let",
           "2": "/primer/primer-2-risunka"}
FREE = "/free/#name"

CATEGORIES = {
    "worry": "Тревоги родителей", "age": "По возрастам", "reading": "Как читать рисунок",
    "tests": "Тесты и расшифровки", "activities": "Занятия", "product": "О сервисе",
}

# (slug, mode, category, target query, retarget/notes, related slugs, min words)
PLAN: list[dict] = [
    # --- существующие: расширить ---
    dict(slug="rebenok-risuet-chernym", mode="extend", cat="worry",
         query="ребёнок рисует чёрным цветом", note="", related="temnye-cveta-v-detskih-risunkah,zlye-risunki-silnyj-nazhim,rebenok-zakrashivaet-lica", words=1100),
    dict(slug="temnye-cveta-v-detskih-risunkah", mode="extend", cat="reading",
         query="значение цветов в детском рисунке",
         note="ПЕРЕНАЦЕЛИТЬ: статья теперь про ЗНАЧЕНИЕ ЦВЕТОВ ВООБЩЕ (красный, синий, розовый, зелёный, жёлтый, чёрный, фиолетовый), а не только про тёмные. Заголовок вида «Значение цветов в детском рисунке: что говорит выбор цвета — и что нет». Про чёрный — кратко, со ссылкой на отдельную статью.",
         related="rebenok-risuet-chernym,kak-ponyat-risunok-rebenka-bez-psihologa,chto-risuet-rebenok-v-4-goda", words=1300),
    dict(slug="strashnye-risunki-monstry", mode="extend", cat="worry",
         query="ребёнок рисует монстров и страшное", note="", related="zlye-risunki-silnyj-nazhim,rebenok-risuet-chernym,chto-risuet-rebenok-v-5-let", words=1100),
    dict(slug="zlye-risunki-silnyj-nazhim", mode="extend", cat="worry",
         query="ребёнок сильно давит на карандаш и рвёт рисунки", note="", related="strashnye-risunki-monstry,rebenok-risuet-chernym,rebenok-perestal-risovat", words=1100),
    dict(slug="rebenok-risuet-sebya-odnogo", mode="extend", cat="worry",
         query="ребёнок рисует себя одного", note="", related="risunok-semi-rebenka,test-risunok-semi-rasshifrovka,rebenok-ne-risuet-litso-ruki", words=1100),
    dict(slug="rebenok-ne-risuet-litso-ruki", mode="extend", cat="worry",
         query="ребёнок рисует людей без лица и рук", note="", related="rebenok-zakrashivaet-lica,chto-risuet-rebenok-v-4-goda,test-narisuj-cheloveka-rasshifrovka", words=1100),
    dict(slug="pochemu-rebenok-risuet-odno-i-to-zhe", mode="extend", cat="worry",
         query="ребёнок рисует одно и то же", note="", related="rebenok-ne-risuet-litso-ruki,analiz-detskogo-risunka-7-priznakov,chto-risuet-rebenok-v-5-let", words=1100),
    dict(slug="risunok-semi-rebenka", mode="extend", cat="reading",
         query="что означает рисунок семьи ребёнка",
         note="Это ОБЪЯСНЯЮЩАЯ статья (что видно в рисунке семьи и чего не видно). Пошаговая расшифровка теста — отдельная статья test-risunok-semi-rasshifrovka, ссылайтесь на неё.",
         related="test-risunok-semi-rasshifrovka,rebenok-risuet-sebya-odnogo,kak-ponyat-risunok-rebenka-bez-psihologa", words=1100),
    dict(slug="chto-uznat-po-risunku-rebenka", mode="extend", cat="reading",
         query="что можно узнать по рисунку ребёнка",
         note="ПИЛЛАР. Старый ответ «характер по рисунку понять НЕЛЬЗЯ» заменить на честную рамку 2.3: по рисунку видны этап развития (надёжно) и ТЕМЫ, ИНТЕРЕСЫ, МАНЕРА, НАСТРОЕНИЕ МОМЕНТА (как гипотезы, по видимым деталям, проверяемые в разговоре с ребёнком). Не диагноз, не тест личности.",
         related="kak-ponyat-risunok-rebenka-bez-psihologa,analiz-detskogo-risunka-7-priznakov,analiz-detskogo-risunka-onlajn-besplatno", words=1500),
    dict(slug="kak-ponyat-risunok-rebenka-bez-psihologa", mode="extend", cat="reading",
         query="как понять рисунок ребёнка", note="ГЛАВНЫЙ ПИЛЛАР. Пошаговая инструкция родителю: что смотреть, что спросить у ребёнка, что записать, когда стоит идти к специалисту.",
         related="chto-uznat-po-risunku-rebenka,analiz-detskogo-risunka-7-priznakov,temnye-cveta-v-detskih-risunkah", words=1500),
    dict(slug="analiz-detskogo-risunka-7-priznakov", mode="extend", cat="reading",
         query="на что смотреть в рисунке ребёнка чек-лист",
         note="ПЕРЕНАЦЕЛИТЬ: заголовок вида «На что смотреть в рисунке ребёнка: чек-лист из 7 пунктов». Не «анализ» как у пилларов, а практический чек-лист.",
         related="kak-ponyat-risunok-rebenka-bez-psihologa,razvivayushchie-zadaniya-risovanie,pochemu-rebenok-risuet-odno-i-to-zhe", words=1200),
    dict(slug="analiz-risunka-ne-diagnoz", mode="extend", cat="tests",
         query="насколько точны тесты по детскому рисунку",
         note="ПЕРЕНАЦЕЛИТЬ: заголовок вида «Насколько точны тесты по детскому рисунку». Честно про надёжность проективных методик (Lilienfeld, Wood, Garb 2000), что из них полезно родителю как язык наблюдения, а что — нет.",
         related="test-risunok-semi-rasshifrovka,test-narisuj-cheloveka-rasshifrovka,chto-uznat-po-risunku-rebenka", words=1200),
    dict(slug="razvivayushchie-zadaniya-risovanie", mode="extend", cat="activities",
         query="упражнения по рисованию для детей 4 5 6 лет", note="Игры по возрастам (3–4, 5–6, 7–9), по 3–4 на возраст, каждая с целью.",
         related="analiz-detskogo-risunka-7-priznakov,chto-risuet-rebenok-v-4-goda,rebenok-perestal-risovat", words=1200),
    dict(slug="pdf-otchet-po-detskomu-risunku", mode="extend", cat="product",
         query="отчёт по детскому рисунку что внутри",
         note="ИСПРАВИТЬ список направлений: сейчас их 7 — «Мир и темы рисунка», «Характер в линии и цвете», «Настроение и выразительность», «История и герои», «Креативность и воображение», «Техника и владение материалом», «Моторика и детализация». Четыре первых — про ребёнка как личность (ведут), три — про навыки (поддерживают). Отчёт: до 3 рисунков, PDF + онлайн-версия, в течение часа, возврат 7 дней. Бесплатный разбор одного рисунка — отдельный вход.",
         related="analiz-detskogo-risunka-onlajn-besplatno,chto-uznat-po-risunku-rebenka,analiz-risunka-ne-diagnoz", words=1000),
    # --- новые ---
    dict(slug="rebenok-perestal-risovat", mode="new", cat="worry",
         query="ребёнок перестал рисовать что делать", note="Причины по возрастам (3–4: интерес ушёл; 5–7: «некрасиво», сравнение с другими; 8+: реализм, критика), что делать и чего не делать, когда это повод присмотреться.",
         related="razvivayushchie-zadaniya-risovanie,zlye-risunki-silnyj-nazhim,chto-risuet-rebenok-v-6-7-let", words=1200),
    dict(slug="malenkie-risunki-v-uglu-lista", mode="new", cat="worry",
         query="ребёнок рисует маленькие рисунки в углу листа", note="Размер и расположение на листе: что об этом говорит традиция (как гипотеза), будничные причины (лист, материал, привычка, моторика), что спросить у ребёнка.",
         related="rebenok-risuet-sebya-odnogo,zlye-risunki-silnyj-nazhim,kak-ponyat-risunok-rebenka-bez-psihologa", words=1100),
    dict(slug="rebenok-zakrashivaet-lica", mode="new", cat="worry",
         query="ребёнок закрашивает лица на рисунке зачёркивает людей", note="Закрашивание лиц, зачёркивание фигур, «испорченные» рисунки: игра, недовольство результатом, сюжет, и когда это повод спросить.",
         related="rebenok-ne-risuet-litso-ruki,rebenok-risuet-chernym,strashnye-risunki-monstry", words=1100),
    dict(slug="chto-risuet-rebenok-v-3-goda", mode="new", cat="age",
         query="что рисует ребёнок в 3 года норма", note="Каракули → первые формы → «головоног». Что типично, что не повод для тревоги, как поддержать. Ссылка на пример отчёта для 3 лет.",
         related="chto-risuet-rebenok-v-4-goda,rebenok-ne-risuet-litso-ruki,razvivayushchie-zadaniya-risovanie", words=1200),
    dict(slug="chto-risuet-rebenok-v-4-goda", mode="new", cat="age",
         query="что рисует ребёнок в 4 года головоног это нормально", note="Головоног, первые человечки с туловищем, дома, солнце; разброс нормы огромный; что спросить у ребёнка о рисунке.",
         related="chto-risuet-rebenok-v-3-goda,chto-risuet-rebenok-v-5-let,rebenok-ne-risuet-litso-ruki", words=1200),
    dict(slug="chto-risuet-rebenok-v-5-let", mode="new", cat="age",
         query="рисунок ребёнка 5 лет норма что должен рисовать", note="Сюжет, персонажи, «базовая линия» земли, первые истории; почему «не умеет рисовать человека в 5 лет» обычно нормально.",
         related="chto-risuet-rebenok-v-4-goda,chto-risuet-rebenok-v-6-7-let,pochemu-rebenok-risuet-odno-i-to-zhe", words=1200),
    dict(slug="chto-risuet-rebenok-v-6-7-let", mode="new", cat="age",
         query="рисунок ребёнка 6 7 лет норма плохо рисует", note="Схематическая стадия, стремление к «правильности», сравнение с одноклассниками, почему многие бросают рисовать в 7–9; ссылка на пример отчёта для 6 и 8 лет.",
         related="chto-risuet-rebenok-v-5-let,rebenok-perestal-risovat,razvivayushchie-zadaniya-risovanie", words=1200),
    dict(slug="test-risunok-semi-rasshifrovka", mode="new", cat="tests",
         query="тест рисунок семьи расшифровка для родителей", note="Как проводится «Рисунок семьи» дома, на что смотрят в традиции (порядок, размер, расстояние, кто пропущен, детали) — КАЖДЫЙ пункт как гипотеза с оговоркой, что домашняя расшифровка ≠ диагностика; что спросить у ребёнка; чего не делать.",
         related="risunok-semi-rebenka,analiz-risunka-ne-diagnoz,test-narisuj-cheloveka-rasshifrovka", words=1400),
    dict(slug="test-narisuj-cheloveka-rasshifrovka", mode="new", cat="tests",
         query="тест нарисуй человека расшифровка для детей", note="Гудинаф–Харрис как оценка ЭТАПА развития (не личности): что считают, по возрастам; Маховер — как традиция интерпретации с низкой надёжностью; что видно родителю.",
         related="rebenok-ne-risuet-litso-ruki,chto-risuet-rebenok-v-5-let,analiz-risunka-ne-diagnoz", words=1300),
    dict(slug="test-dom-derevo-chelovek-nesushchestvuyushchee-zhivotnoe", mode="new", cat="tests",
         query="тест дом дерево человек и несуществующее животное расшифровка для детей", note="Две популярные методики: как проводятся, что в них смотрят (гипотезы), где границы, как использовать дома как повод для разговора, а не как приговор.",
         related="test-risunok-semi-rasshifrovka,test-narisuj-cheloveka-rasshifrovka,strashnye-risunki-monstry", words=1300),
    dict(slug="analiz-detskogo-risunka-onlajn-besplatno", mode="new", cat="product",
         query="анализ детского рисунка онлайн бесплатно", note="Коммерческая страница-объяснение: что можно получить онлайн бесплатно (наш бесплатный разбор одного рисунка: как работает, что внутри, ограничения), чем отличается полный отчёт, чего онлайн-анализ не может (диагностика). Честно, без обещаний. Главный призыв — бесплатный разбор.",
         related="pdf-otchet-po-detskomu-risunku,chto-uznat-po-risunku-rebenka,analiz-risunka-ne-diagnoz", words=1100),
]
KNOWN = {p["slug"] for p in PLAN}

SYSTEM = """Ты пишешь статьи для блога сервиса «Голос рисунка» (golosrisunka.ru) — для родителей детей 3–12 лет в России.
Сервис: родитель загружает фото рисунка, получает бережный разбор: что видно в рисунке о ребёнке — темы, интересы, манера, настроение момента, этап развития. Есть БЕСПЛАТНЫЙ разбор одного рисунка (/free/#name) и платный полный отчёт по 1–3 рисункам.

ФИЛОСОФИЯ (обязательна):
- Рисунок читают КАК ОКНО В РЕБЁНКА: что его увлекает, какие темы выбирает, как ведёт линию, какое настроение в этой работе. Это разрешено — но ТОЛЬКО как гипотеза: с привязкой к видимой детали, с указанием традиции («в традиции анализа детского рисунка это часто связывают с…»), с оговоркой «по одному рисунку это не проверить» и с возвратом к ребёнку («лучше спросить самого ребёнка»).
- Этап развития (моторика, схема человека, композиция по возрастам) читается надёжно — об этом можно говорить уверенно.
- ВСЕГДА запрещено: диагноз как факт («ребёнок тревожен», «у него низкая самооценка»), слова «травма», «депрессия», «невроз», «тревожность» в утверждениях о ребёнке, «скрытые проблемы», «срочно к психологу», гадание по цветам/символам как правило («красный = агрессия»), командный тон («обязательно», «купите»), обещания талантов («станет художником»), катастрофизация. Про цвет и символы — только как «в традиции это связывают с…, но надёжных данных нет».
- Не отрицай продукт: НЕЛЬЗЯ писать «по рисунку нельзя понять характер/эмоции». Правильно: «по одному рисунку не поставишь диагноз и не сделаешь вывод о характере, но видно, что ребёнка увлекает, как он работает с листом, каким было настроение этой работы — и это стоит обсудить с ним самим».

ГОЛОС: спокойный, тёплый, конкретный, взрослый разговор с родителем, без сюсюканья и без нагнетания. Короткие абзацы. Активный залог. Примеры с именами детей (Маша, 5 лет) допустимы как иллюстрации, помеченные как примеры.

СТРУКТУРА (обязательна, markdown):
1) Первый абзац: узнаваемая ситуация родителя + что будет в статье. Без H1 (заголовок идёт в frontmatter).
2) Абзац «**Коротко:** …» — ответ в 2–3 предложениях.
3) 5–8 разделов H2, заголовки — ВОПРОСЫ родителя своими словами (например «Почему ребёнок рисует только чёрным?»). Внутри — списки, где уместно; 1 таблица, если есть что сравнить.
4) Обязательный раздел H2 «Что типично по возрастам» (3–4, 5–6, 7–9, 10+), если тема позволяет.
5) Обязательный раздел H2 «Что сделать сегодня» — чек-лист из 4–6 пунктов, включая 1–2 конкретных вопроса ребёнку.
6) Раздел H2 «Когда стоит показать специалисту» — спокойно, без запугивания, признаки в ПОВЕДЕНИИ, а не в рисунке.
7) Раздел H2 «Частые вопросы» — 3–4 пары: вопрос жирным (**Вопрос?**) и абзац ответа сразу под ним.
8) Раздел H2 «Источники» — 3–5 пунктов списка: реальные книги/работы (Lowenfeld & Brittain «Creative and Mental Growth»; Rhoda Kellogg «Analyzing Children's Art»; Maureen Cox «Children's Drawings»; Выготский «Воображение и творчество в детском возрасте»; Lilienfeld, Wood & Garb (2000) «The scientific status of projective techniques»; Goodenough–Harris Drawing Test; Piaget). Только реальные, без выдумок, без ссылок-URL.

ССЫЛКИ (внутренние, markdown [текст](путь)): вплетай в текст естественно, 4–7 штук на статью, ТОЛЬКО из списка разрешённых адресов ниже. Одна из ссылок обязательно на бесплатный разбор {FREE} в середине статьи (в подходящем месте, как совет: «можно загрузить рисунок и получить бесплатный разбор»), и одна — на подходящий пример отчёта (/primer/…). Ссылки на другие статьи — по смыслу, из списка related в первую очередь. Никаких внешних ссылок.

ДЛИНА: минимум {WORDS} слов основного текста (без frontmatter), максимум примерно {WORDS_MAX}.

ФОРМАТ ОТВЕТА — ровно один файл markdown:
---
title: <до 60 символов, с целевым запросом в начале, без названия сайта>
description: <120–155 символов, с целевым запросом в первых 50, обещание пользы>
date: {DATE}
updated: {TODAY}
category: {CAT}
related: {RELATED}
---
<тело статьи>
Никаких пояснений до или после файла, никаких ``` ограждений."""

ALLOWED_LINKS_HEAD = "РАЗРЕШЁННЫЕ АДРЕСА:\n- /free/#name — бесплатный разбор одного рисунка\n- /order — заказать полный отчёт\n" + \
    "".join(f"- {v} — пример отчёта, ребёнок {k} лет\n" for k, v in SAMPLES.items() if k != "2") + \
    "- /primer/primer-2-risunka — пример сводного отчёта по двум рисункам\n"


def _titles() -> dict[str, str]:
    out = {}
    for p in PLAN:
        f = BLOG / f"{p['slug']}.md"
        title = ""
        if f.exists():
            m = re.search(r"^title:\s*(.+)$", f.read_text(encoding="utf-8"), re.M)
            title = m.group(1).strip() if m else ""
        out[p["slug"]] = title or p["query"]
    return out


def _allowed_links(p: dict, titles: dict) -> str:
    lines = [ALLOWED_LINKS_HEAD]
    for q in PLAN:
        if q["slug"] != p["slug"]:
            lines.append(f"- /blog/{q['slug']} — статья: {titles[q['slug']]}")
    return "\n".join(lines)


def _existing(slug: str) -> tuple[str, str]:
    f = BLOG / f"{slug}.md"
    if not f.exists():
        return "", TODAY
    text = f.read_text(encoding="utf-8")
    m = re.search(r"^date:\s*(\S+)", text, re.M)
    return text, (m.group(1) if m else TODAY)


def build_prompt(p: dict, titles: dict, repair: list[str] | None = None) -> tuple[str, str]:
    body, date = _existing(p["slug"])
    words = p["words"]
    system = SYSTEM.replace("{FREE}", FREE).replace("{WORDS}", str(words)) \
        .replace("{WORDS_MAX}", str(int(words * 1.5))).replace("{DATE}", date) \
        .replace("{TODAY}", TODAY).replace("{CAT}", p["cat"]).replace("{RELATED}", p["related"])
    user = [f"ЦЕЛЕВОЙ ЗАПРОС: «{p['query']}»", f"КАТЕГОРИЯ: {CATEGORIES[p['cat']]}"]
    if p["note"]:
        user.append("ЗАМЕЧАНИЯ РЕДАКТОРА: " + p["note"])
    user.append(_allowed_links(p, titles))
    if p["mode"] == "extend" and body:
        user.append("ЗАДАЧА: РАСШИРИТЬ и ПЕРЕПИСАТЬ существующую статью ниже под требования выше. "
                    "Сохрани полезные факты и примеры, убери утверждения, противоречащие философии "
                    "(например «по рисунку нельзя понять характер»), доведи до нужной длины, "
                    "добавь обязательные разделы. Дата публикации остаётся прежней.\n\n"
                    "=== СУЩЕСТВУЮЩАЯ СТАТЬЯ ===\n" + body)
    else:
        user.append("ЗАДАЧА: НАПИСАТЬ новую статью под целевой запрос.")
    if repair:
        user.append("ПРЕДЫДУЩИЙ ВАРИАНТ НЕ ПРОШЁЛ ПРОВЕРКУ. Исправь ВСЕ замечания, сохранив остальное:\n- "
                    + "\n- ".join(repair))
    return system, "\n\n".join(user)


LINK_RE = re.compile(r"\]\(([^)]+)\)")


def autofix(text: str) -> str:
    """Механические поправки до линтера: ограждения, относительные ссылки, длина description."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    text = re.sub(r"\]\((?:https?://golosrisunka\.ru)?/?(blog/|primer/|free/|order\b)", r"](/\1", text)
    text = text.replace("](/free/)", "](/free/#name)").replace("](/free)", "](/free/#name)")
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    if m and len(m.group(1)) > 155:
        d = m.group(1)[:155]
        cut = max(d.rfind(". "), d.rfind(", "), d.rfind(" "))
        d = d[:cut].rstrip(" ,;:—-") if cut > 90 else d.rstrip()
        if not d.endswith("."):
            d += "."
        text = text[:m.start(1)] + d + text[m.end(1):]
    return text


def lint(p: dict, text: str) -> list[str]:
    errs = []
    if not text.startswith("---"):
        return ["файл должен начинаться с frontmatter ---"]
    try:
        _, fm, body = text.split("---", 2)
    except ValueError:
        return ["frontmatter не закрыт"]
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    t, d = meta.get("title", ""), meta.get("description", "")
    if not 25 <= len(t) <= 62:
        errs.append(f"title: {len(t)} символов, нужно 25–60")
    if not 110 <= len(d) <= 158:
        errs.append(f"description: {len(d)} символов, нужно 120–155")
    if "Голос рисунка" in t:
        errs.append("в title не должно быть названия сайта")
    for k in ("date", "updated", "category", "related"):
        if k not in meta:
            errs.append(f"нет поля {k} в frontmatter")
    n = len(re.findall(r"\w+", body))
    if n < p["words"] * 0.9:
        errs.append(f"слишком коротко: {n} слов, нужно не меньше {p['words']}")
    for sec in ("Что сделать сегодня", "Частые вопросы", "Источники"):
        if sec not in body:
            errs.append(f"нет раздела «{sec}»")
    h2 = re.findall(r"^## (.+)$", body, re.M)
    if len(h2) < 5:
        errs.append(f"мало разделов H2: {len(h2)}")
    if "# " in body.split("\n", 1)[0] or re.search(r"^# ", body, re.M):
        errs.append("H1 в теле недопустим (заголовок только в frontmatter)")
    links = LINK_RE.findall(body)
    if FREE not in links:
        errs.append(f"нет ссылки на бесплатный разбор {FREE}")
    if not any(l.startswith("/primer/") for l in links):
        errs.append("нет ссылки на пример отчёта /primer/…")
    for l in links:
        ok = l in (FREE, "/order") or l.startswith("/primer/") or \
            (l.startswith("/blog/") and l[6:] in KNOWN)
        if not ok:
            errs.append(f"недопустимая ссылка: {l}")
    for pattern, why in HARD_BANNED:
        m = re.search(pattern, body, re.I)
        if m:
            errs.append(f"запрещённая формулировка «{m.group(0)[:50]}» ({why})")
    for bad in ("нельзя понять характер", "не читаются эмоции", "не показывает характер"):
        if bad in body.lower():
            errs.append(f"противоречит продукту: «{bad}»")
    if "```" in text:
        errs.append("ограждения ``` недопустимы")
    return errs


def generate(client, p: dict, titles: dict, log) -> bool:
    repair = None
    for attempt in (1, 2, 3):
        system, user = build_prompt(p, titles, repair)
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.7,
                                          max_output_tokens=16000)
        t0 = time.time()
        text = ""
        for chunk in client.models.generate_content_stream(model=MODEL, contents=user, config=cfg):
            text += chunk.text or ""
        text = autofix(text)
        errs = lint(p, text)
        words = len(re.findall(r"\w+", text))
        log(f"{p['slug']}: attempt {attempt}, {words} words, {int(time.time()-t0)}s, errors={len(errs)}")
        if not errs:
            (BLOG / f"{p['slug']}.md").write_text(text + "\n", encoding="utf-8", newline="\n")
            return True
        for e in errs:
            log("   - " + e)
        repair = errs
        if attempt == 3:
            # сохраняем как черновик для ручного взгляда, не трогая рабочую статью
            (BASE / "data" / "tmp" / f"blog_draft_{p['slug']}.md").write_text(text, encoding="utf-8")
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only-new", action="store_true")
    ap.add_argument("--slug")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--skip-done", action="store_true", help="пропустить статьи с updated: сегодня")
    a = ap.parse_args()
    if a.plan:
        for p in PLAN:
            print(p["mode"], p["cat"], p["slug"], p["words"])
        return
    todo = [p for p in PLAN if (a.slug and p["slug"] == a.slug) or (a.all and (not a.only_new or p["mode"] == "new"))]
    if a.skip_done:
        def _done(slug):
            f = BLOG / f"{slug}.md"
            return f.exists() and f"updated: {TODAY}" in f.read_text(encoding="utf-8")
        todo = [p for p in todo if not _done(p["slug"])]
    if not todo:
        print("nothing to do"); return
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    rep = open(REPORT, "a", encoding="utf-8")

    def log(msg: str) -> None:
        rep.write(msg + "\n"); rep.flush()
        print(msg.encode("ascii", "replace").decode())

    kw = {"timeout": 300000}
    if settings.GOOGLE_GEMINI_BASE_URL if hasattr(settings, "GOOGLE_GEMINI_BASE_URL") else None:
        kw["base_url"] = settings.GOOGLE_GEMINI_BASE_URL
    client = genai.Client(api_key=settings.GEMINI_API_KEY, http_options=types.HttpOptions(**kw))
    titles = _titles()
    ok = fail = 0
    log(f"== blog_gen {datetime.datetime.now().isoformat(timespec='seconds')} model={MODEL} posts={len(todo)}")
    for p in todo:
        try:
            if generate(client, p, titles, log):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            log(f"{p['slug']}: EXCEPTION {type(e).__name__}: {str(e)[:200]}")
    log(f"== done ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
