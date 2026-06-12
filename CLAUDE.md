# CLAUDE.md — Голос рисунка (golosrisunka.ru)

Сервис анализа детских рисунков: родитель загружает 1–3 рисунка + контекст, оплачивает,
получает PDF-отчёт (Gemini 2.5 Pro → JSON → Jinja2 → WeasyPrint). Русскоязычный. MVP к **25.06.2026**.

## Ключевые документы (читать при возобновлении работы)
- `projectSpec/golosrisunka-tech-spec.md` — ТЗ (но см. «Модель продукта» ниже — она новее спеки!)
- `projectSpec/development-plan.md` — план по фазам с милстоунами
- `DevelopmentStatus.md` — **append-only журнал**: что сделано, текущее состояние, чего ждём
- `UseCasesData.md` — база решённых проблем (проблема → причина → решение); пополнять при каждой новой
- Мокап-дизайн: `projectSpec/golosrisunka-hybrid-2.html` (палитра «Синий» = дефолт)

## Модель продукта (коррекция заказчика, ОВЕРРАЙДИТ spec §1)
1. **snapshot** — до 3 рисунков → ОДИН сводный отчёт; цена НЕ зависит от числа рисунков. 2999 ₽ (зачёркнуто 4900 ₽).
2. **development** — сравнение 2 наборов с интервалом ≥6 мес. 4999 ₽ (от 6900 ₽). Может не войти в MVP — на лендинге «скоро».
- **ВСЕ цены/цифры — из `config/products.json`** (будущая админка). Хардкод цен в шаблонах/коде ЗАПРЕЩЁН.

## Команды
```
venv\Scripts\python.exe run.py                                  # dev-сервер :5000
venv\Scripts\python.exe scripts\generate_report.py IMG [IMG2] --context C1.txt [C2.txt] [--common X.txt] [-o DIR]
venv\Scripts\python.exe scripts\render_sample.py                # отчёт из fake JSON (шаблон)
venv\Scripts\python.exe scripts\render_gallery.py [dk|pu|cl]    # галерея компонентов
venv\Scripts\python.exe scripts\build_fonts.py                  # пересборка шрифтов (subsets)
venv\Scripts\python.exe scripts\hello_pdf.py                    # smoke-тест WeasyPrint+кириллица
```

## Архитектура
- `app/` — Flask (routes, samples лендинга, blog-скелет). `run.py` — dev-вход.
- `pipeline/` — генерация отчёта: `prompt.py` (системный промпт, PROMPT_VERSION), `gemini.py`
  (вызов + 5 ретраев + **lint+repair цикл**), `lint.py` (линтер запрещённого языка),
  `schema.py` (pydantic-контракт §7.3), `images.py` (resize/heic), `render.py` (JSON→HTML→PDF).
- `config/settings.py` — всё конфигурируемое; `.env` — секреты (GEMINI_API_KEY есть; читать .env запрещено permissions).
- `templates/` + `static/css/{tokens,components,report,fonts}.css` — дизайн-система:
  токены + переиспользуемые компоненты. Новый блок = композиция компонентов; одноразовые стили запрещены (закон спеки §3).
- `data/` — drawings/, reports/, test_reports/ (вне будущего git).

## Жёсткие правила проекта
- **Промпт-философия (§7.4)**: БЕЗ Барнума, БЕЗ чтения эмоций/состояний по рисунку; каждое наблюдение
  привязано к видимой детали. Язык навыков, не черт («уверенно работает крупным масштабом», НЕ «не боится листа»).
  Старые сэмплы в `projectSpec/reportSamples/` — референс структуры/тона, НЕ философии (они нарушают правила).
- Для «LLM не должен говорить X» — промпт + **программный линтер + repair-вызов** (UseCase #8), не только промпт.
- Пол ребёнка — только из поля «пол» (текст родителя may содержать намеренный грамматический мусор).
  Имя в отчётах: «Имя Ф.» (первая буква фамилии). На лендинге — только имя.
- Шрифты self-hosted, свои subsets (₽ U+20BD обязателен!). После ЛЮБОГО изменения шрифтов/CSS отчёта —
  проверка embedded-fonts PDF (UseCase #2): никаких Segoe/Verdana fallback. Italics в отчётах запрещены (#6).
- Windows-консоль cp1252: НЕ print'ить кириллицу/₽ из python-скриптов — ASCII или запись в файл (#3).
- WeasyPrint-вёрстка отчёта: таблицы/блоки/float, без сложного flex/grid; GLib-warnings игнорировать (#4).
- `.claude/settings.local.json` — широкий allow-list от пользователя; permission-система иногда
  перезаписывает его старым аккумулированным списком — восстанавливать широкую версию.

## Состояние на вечер 11.06.2026 (детали в DevelopmentStatus.md)
- **Фазы 0–4 построены**: дизайн-система, шаблон отчёта, промпт v2.0 + Gemini-пайплайн (M3 протестирован
  на 3 реальных рисунках: gender traps passed, insufficient input works), лендинг на :5000 с реальными
  сэмплами, 2 продукта со скидочным дизайном.
- **Phase 3R (консолидация 2–3 рисунков)**: код готов, регрессия пройдена.
  **⛔ ЖДЁМ ОТ ЗАКАЗЧИКА: 2–3 разных рисунка ОДНОГО ребёнка + история по каждому** → `projectSpec/testDrawings/`
  (синтетический тест кропом невалиден — Gemini распознал кроп как ту же работу, UseCase #9).
- **Ждут проверки заказчика**: M4 re-test (лендинг после правок цен/UI), M3R (после реального набора).
- **Дальше по плану**: Phase 5 (форма заказа: общий блок ребёнка + история per-drawing, загрузка,
  SQLite, stub-оплата) → Phase 6 (воркер) → 7 (auth/кабинет) → 8 (ЮKassa+Unisender) → 9 (деплой).
- Кредензалы: Gemini ✅ (.env); Unisender — аккаунт есть, домен не добавлен; ЮKassa — вопрос
  «старый аккаунт или новый» открыт. Git: repo https://github.com/spashap/golosRisunka (был PUBLIC —
  советовали сделать private), init запланирован в Phase 9; `.env`, `data/`, `venv/` — в .gitignore с первого коммита.

## Watch list
- Первый экран ≈235KB (цель <200KB): caveat-700.woff2 = 93KB — решить на Lighthouse-пассе Phase 9.
- Отзывы на лендинге — placeholder до текстов заказчика; OG-image нет; 6yr тест-рисунок — сток (заменит).
- `python -` heredoc и `&&`-цепочки: падение по encoding обрывает цепочку — файлы писать Write-тулом.
