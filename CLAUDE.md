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
venv\Scripts\python.exe worker.py [--once]                      # воркер отчётов (paid -> delivered)
venv\Scripts\python.exe scripts\regenerate_report.py ORDER_ID   # ручной перезапуск заказа
venv\Scripts\python.exe scripts\generate_report.py IMG [IMG2] --context C1.txt [C2.txt] [--common X.txt] [-o DIR]
venv\Scripts\python.exe scripts\render_sample.py                # отчёт из fake JSON (шаблон)
venv\Scripts\python.exe scripts\render_gallery.py [dk|pu|cl]    # галерея компонентов
venv\Scripts\python.exe scripts\build_fonts.py                  # пересборка шрифтов (subsets)
venv\Scripts\python.exe scripts\hello_pdf.py                    # smoke-тест WeasyPrint+кириллица
venv\Scripts\python.exe scripts\bump_version.py                 # минор +1 (ПЕРЕД каждым git push)
venv\Scripts\python.exe scripts\bump_version.py --major         # мажор +1 (ТОЛЬКО по команде заказчика)
```

## Деплой (прод: golosrisunka.ru, Ubuntu VPS 31.172.67.220)
- Код в `/var/www/golosrisunka` (git clone, www-data владеет только `data/` + `static/img/`),
  gunicorn+worker как systemd (`golosrisunka-web`, `golosrisunka-worker`), nginx-vhost,
  Cloudflare orange + Origin-cert (Full strict). Скрипты первичной установки: `scripts/deploy/`.
- Обновление прода: на сервере `cd /var/www/golosrisunka && ./deploy.sh` (git pull + deps + restart);
  только перезапуск — `./restart.sh`. Оба в корне репо (eol=lf, +x в git).
- ЮKassa ещё нет → оплата = stub (бесплатные отчёты), сайт публичный по решению заказчика.

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
- **ВЕРСИОНИРОВАНИЕ (обязательно)**: перед КАЖДЫМ `git push` поднимать минор —
  `python scripts\bump_version.py` (V1.001 → V1.002) и включать `VERSION` в тот же коммит.
  Мажор (`--major`, сброс минора в 000) — ТОЛЬКО по явной команде заказчика. Источник истины —
  файл `VERSION`; показывается в футере сайта (`config.settings.APP_VERSION` → `inject_globals`).

## Состояние на вечер 12.06.2026 (детали в DevelopmentStatus.md)
- **Фазы 0–7 построены; 0–5 одобрены заказчиком (M5 ✅), M6+M7 ждут проверки одной сессией**: дизайн-система; промпт v2.0 (M3R: сводный отчёт по
  2 реальным рисункам одного ребёнка — честные противоречия, ссылки на номера рисунков — sign-off);
  лендинг с 4 сэмплами (сводный по 2 рисункам — в центре карусели, стрелки ‹ ›, мобайл-адаптация);
  единая sticky-шапка с навигацией и «Войти» (заглушка /login до Phase 7);
  **Phase 5: полный флоу заказа** — SQLite (drawn_at/birth_ym/base_order_id + events/UTM-аналитика),
  форма (конфиг полей; комбобоксы; ym-селекты; черновик в localStorage 4ч; email-опечатки; промокоды
  со скидкой; guard кнопки добавления рисунка; защита от двойного сабмита; серверные проверки дат),
  stub-оплата через идемпотентный mark_paid() (ЮKassa воткнётся туда же в Phase 8), сессия при оплате.
- **Phase 6: фоновый воркер** — `worker.py` (поллер paid-заказов, `--once`; systemd в Phase 9),
  `app/jobs.py` (run_order: paid→generating→delivered/insufficient/failed; возраст на дату
  рисунка считаем сами; public_token живёт при regenerate), `app/mailer.py` (send_email —
  единая точка; backend 'outbox' = HTML-файлы в data/outbox/, Unisender = Phase 8),
  `scripts/regenerate_report.py ORDER_ID`. ⚠️ ЮKassa/Unisender аккаунтов всё ещё нет —
  всё строится «фундаментом»: заглушки за абстракциями, подключение = один backend.
- **Phase 7: auth + кабинет** — `app/auth.py` (email-код 6 цифр TTL 30 мин, rate limit 10 мин,
  5 попыток → void; код в outbox + консоль до Unisender; create_session общая с mark_paid),
  /login → /cabinet (статусы «в обработке»/«готов», превью рисунков thumb-JPEG, скачивание PDF,
  владельческие проверки). Заказ 8 оставлен в paid — воркер доставит при M6-тесте.
- **Блог: 6 статей** (content/blog/) по EN-образцам заказчика (projectSpec/blog/, gitignored) —
  НЕ калька: те же поисковые запросы, но ответы в философии §7.4. Ждут вычитки. Карточки-плитки
  с инлайн-SVG дудлами (_blog_thumb.html), дат на витрине нет.
- **Админка /admin** (дизайн одобрен): вход по `ADMIN_PASS` из .env (отдельно от /login!),
  сайдбар: Аналитика/Заказы/Клиенты/Промокоды/Настройки сайта (редактор products.json
  живьём)/Письма (outbox). Лендинг: Цены → FAQ → Блог-карусель; отзывы — узкая лента-ротатор
  (6 ПЛЕЙСХОЛДЕРОВ в routes.TESTIMONIALS). Метрика: тег готов, ждёт YANDEX_METRIKA_ID в .env
  (webvisor выключен намеренно). Dev-чит: код входа виден на странице для spashap@gmail.com
  на localhost. Кабинет: группировка по детям + спящие CTA Development («скоро»).
  Сид кабинета: data/tmp/tmp_seed_cabinet.py (заказы 9/10/11).
- **Git**: https://github.com/spashap/golosRisunka (PUBLIC — рекомендация private остаётся), запушено.
  **Vercel**: статический экспорт dist/ (scripts/export_static.py, noindex), деплой через дашборд.
- **⏸ ПРОЕКТ НА ПАУЗЕ (12.06 ночь)**: ждём от заказчика домен, ЮKassa, Unisender-домен,
  YANDEX_METRIKA_ID, тест M6+M7, вычитку блога/отзывов. Дальше: Phase 8 → 9.
- **devtest-img1** (Алиса, 4 года, июль 2024) — зарезервирован для Development report (продукт 2).
- Кредензалы: Gemini ✅ (.env); Unisender — домен не добавлен; ЮKassa — «старый или новый аккаунт» открыт.
- Тестовый купон в локальной БД: TEST20 (20%, multi-use).

## Watch list
- Первый экран ≈235KB (цель <200KB): caveat-700.woff2 = 93KB — решить на Lighthouse-пассе Phase 9.
- Отзывы на лендинге — placeholder до текстов заказчика; OG-image нет; 6yr тест-рисунок — сток (заменит).
- `python -` heredoc и `&&`-цепочки: падение по encoding обрывает цепочку — файлы писать Write-тулом.
- Headless-скриншоты на этой машине КРОПЯТСЯ (Windows DPI 125%, UseCase #14) — мобильную вёрстку
  проверяет заказчик на телефоне; fast-сессии = правка → отдать на проверку, без скриншот-циклов.
- dist/ пересобирать после правок лендинга/CSS (`scripts/export_static.py`) и коммитить — Vercel
  деплоит из него. После правок report-шаблона: `scripts/rerender_reports.py`.
