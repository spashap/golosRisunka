# CLAUDE.md — Голос рисунка (golosrisunka.ru)

Сервис анализа детских рисунков: родитель загружает 1–3 рисунка + контекст, оплачивает,
получает PDF-отчёт (Gemini 2.5 Pro → JSON → Jinja2 → WeasyPrint). Русскоязычный. MVP к **25.06.2026**.

## Ключевые документы (читать при возобновлении работы)
- `projectSpec/golosrisunka-tech-spec.md` — ТЗ (но см. «Модель продукта» ниже — она новее спеки!)
- `projectSpec/development-plan.md` — план по фазам с милстоунами
- `DevelopmentStatus.md` — **append-only журнал**: что сделано, текущее состояние, чего ждём
- `UseCasesData.md` — база решённых проблем (проблема → причина → решение); пополнять при каждой новой
- **`projectSpec/brand-book.md` — ДИЗАЙН-СИСТЕМА (источник истины для всего визуала сайта, утв. 18.06.2026).**
  Любой UI-элемент строится ТОЛЬКО по нему. Старый мокап `projectSpec/golosrisunka-hybrid-2.html` — архив.

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
venv\Scripts\python.exe scripts\build_hero_image.py             # оптимизир. hero из data/Images/Hero.png -> static/img/hero.{jpg,webp}
venv\Scripts\python.exe scripts\build_logos.py                  # оптимизир. лого из data/Images/{StripLogo,logo}.png -> static/img/logo-{strip,icon}.{png,webp}
venv\Scripts\python.exe scripts\build_geoip.py CSV.gz           # сборка гео-базы data/geoip.db из DB-IP City Lite (строить НА сервере)
venv\Scripts\python.exe scripts\hello_pdf.py                    # smoke-тест WeasyPrint+кириллица
venv\Scripts\python.exe scripts\bump_version.py                 # минор +1 (ПЕРЕД каждым git push)
venv\Scripts\python.exe scripts\bump_version.py --major         # мажор +1 (ТОЛЬКО по команде заказчика)
release.bat "msg"                                               # релиз одной командой: bump -> export dist -> commit -> push (в PowerShell: .\release.bat)
```

## Деплой (прод: golosrisunka.ru, Ubuntu VPS 31.172.67.220 — провайдер Fornex, fornex.com)
- Ресурсы (апгрейд 14.06): 40 ГБ диск (~23 ГБ free), 3 vCPU, 3.8 ГБ RAM (НЕ апгрейдили), swap НЕТ.
  Бокс делит с shepotzvezd.ru. SSH/доступы — `C:\projects\serverdata.txt` (root, пароль).
- Код в `/var/www/golosrisunka` (git clone, www-data владеет только `data/` + `static/img/`),
  gunicorn+worker как systemd (`golosrisunka-web`, `golosrisunka-worker`), nginx-vhost,
  **DNS-only (Cloudflare grey cloud) + Let's Encrypt** (certbot nginx-plagin, ключ ECDSA,
  автопродление `certbot.timer`, reload nginx при renew) — как shepotzvezd.ru. Переход с
  Cloudflare orange + Origin-cert сделан 13.06 ради доступности из РФ (UseCase #21). Скрипты
  первичной установки: `scripts/deploy/` (`setup_letsencrypt.sh` выдаёт/чинит cert;
  `install_cert.sh` — устаревший CF-Origin, в .gitignore из-за приватного ключа).
- Обновление прода: на сервере `cd /var/www/golosrisunka && ./deploy.sh` (git pull + deps + restart);
  только перезапуск — `./restart.sh`. Оба в корне репо (eol=lf, +x в git).
- ЮKassa встроена (TEST-стадия, см. «Состояние на 22.06»). Stub удалён. Перед боем добавить
  `YUKASSA_MODE`/`YUKASSA_SHOP_ID_LIVE`/`YUKASSA_SECRET_KEY_LIVE` в СЕРВЕРНЫЙ `.env`, затем `./deploy.sh`.

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
- **ДИЗАЙН САЙТА — ТОЛЬКО по бренд-буку (`projectSpec/brand-book.md`). ЖЁСТКО.** Один глобальный
  CSS-источник: `static/css/tokens.css` (значения) + `static/css/components.css` (компоненты).
  ЛЮБОЙ новый/изменённый элемент сайта обязан: (1) брать цвета ТОЛЬКО из токенов (никаких хардкод-hex
  в шаблонах/инлайн-стилях), (2) брать размеры ТОЛЬКО из 7-ступенчатой шкалы (`--fs-*`), (3) быть
  композицией существующих компонентов — не хватает компонента, добавляешь его в `components.css`,
  а НЕ инлайнишь стиль в страницу, (4) рукописный Caveat — только «голос» (`.hand`) и логотип,
  (5) Rubik — только веса 800/900. Палитра «Золотой час» (тёплая бумага + эспрессо-текст + джинсовый
  синий = действие + медовый янтарь = голос). Меняешь токен → меняется весь сайт; «отдельных
  контролов» под страницу быть НЕ должно. Hero — кино-фото `static/img/hero.jpg` + матовая карточка.
  Исключение: PDF-отчёт (`report.html`/`report.css`) — отдельная система, бренд-бук на него НЕ распространяется.
- **Промпт-философия — ФИЛОСОФИЯ 2.3 «ПОРТРЕТ РЕБЁНКА КАК ЛИЧНОСТИ» (PROMPT_VERSION 4.0, разворот 23.06.2026).**
  ⚠️ ЭТО ОТМЕНЯЕТ старую «только навыки» спеку §7.4. Отчёт читает РЕБЁНКА (характер, темы, внутренний мир,
  настроение, интересы) ЧЕРЕЗ рисунок; навыки рисования — ПОДДЕРЖКА, не суть. Эмоц./псих. интерпретация
  (зона 3) РАЗРЕШЕНА, но ТОЛЬКО в 4-условной оправе: **атрибуция к традиции/автору + гипотезный оборот +
  привязка к видимой детали + возврат к ребёнку** («лучше спросить саму [имя]…»). Всегда запрещено (оправа
  не спасает): голый диагноз-факт, «исправить/вылечить», «скрытые травмы», гадание по цветам/символам,
  командный тон, прогноз-таланта-факт. Рынок РФ допускает бóльшую глубину; англо-версия — строже (см.
  `projectSpec/pipe-change/HANDOFF-english-philosophy-2.3.md`). Память: [[report-person-pivot-2-3]].
- Для «LLM не должен говорить X» — промпт + **программный линтер + repair-вызов** (UseCase #8), не только
  промпт. Линтер 2.3: HARD-баны ВЕЗДЕ + проверка ОПРАВЫ только на интерпретационных полях (intro/about_child/
  conclusion/observation/specialists.reason), НЕ на списках-идеях (рекомендации/направления/context_summary);
  repair = «ДОБАВЬ оправу / смягчи, НЕ удаляй смысл». Hedge-словарь широкий (могут/можем/предположить…).
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
- **АНАЛИТИКА / Я.Метрика (обязательно)**: счётчик стоит на ВСЕХ страницах сайта, кроме `/admin*`
  (`templates/_metrika.html`, гейт `metrika_id and not request.path.startswith('/admin')`;
  ID из `YANDEX_METRIKA_ID` в `.env`). КАЖДАЯ новая кнопка/CTA/ссылка-действие получает уникальный
  `data-ym-goal="page_action"` (форма — `data-ym-goal-submit="..."`); делегированный трекер в
  `_metrika.html` сам шлёт `reachGoal` — JS дописывать не нужно. Имя цели уникальное, по схеме
  `<страница>_<действие>` (напр. `order_submit`, `cabinet_download_pdf`). Админку НЕ трекать.

## Состояние на 23.06.2026 — РАЗВОРОТ ПРОДУКТА К ФИЛОСОФИИ 2.3 «ПОРТРЕТ РЕБЁНКА» (V1.037)
**Полный пивот ядра продукта: отчёт + лендинг + позиционирование переписаны с «только навыки рисования»
на «портрет ребёнка как личности через рисунок». Детали — [[report-person-pivot-2-3]], журнал
DevelopmentStatus.md (23.06), хендофф для англо-версии `projectSpec/pipe-change/HANDOFF-english-philosophy-2.3.md`.**
- **Пайплайн отчёта (PROMPT_VERSION 4.0):** новая рамка (ребёнок как личность), зона-3 в 4-условной оправе,
  нарративный блок `about_child` (сердце отчёта), 7 НОВЫХ направлений (4 личностных ведут: world_and_themes/
  character_in_line_color/mood_and_expression/story_and_characters + 3 навыковых: creativity/
  technique_and_materials/fine_motor), раздельные рекомендации (understanding_/art_), `specialists` (тип спеца
  как ресурс, неарт-вариант), `development_directions` = «куда растить ПО ЖИЗНИ» (3 слоя, профессии «как
  пример»), честный разброс оценок (не стена девяток), меньше суперлативов. Схема: `pipeline/schema.py`.
- **Линтер переписан** (`pipeline/lint.py`): «бан слов» → «проверка ОПРАВЫ». HARD-баны везде + frame-check
  только на интерпретационных полях; repair = «добавь оправу, не удаляй смысл»; широкий hedge-словарь;
  артефакт-исключение («тревожное небо»≠ребёнок). Тюнинг по ложным срабатываниям (Задачи 1.1/1.2).
- **Админ-тексты в конце отчёта** (pass-through): `config/report_texts.json` + `get_report_texts()` +
  раздел `/admin/report-texts` — апсейл по числу рисунков (1/2/3) + дисклеймеры + свободный блок.
- **Лендинг переписан** (`templates/landing.html`, `app/routes.py`): hero сохранён; новые блоки «Больше чем
  рисунок» + «Например, такие ситуации» (иллюстративные кейсы, явно НЕ реальные клиенты); «Без мифов» →
  «Бережно и по методикам, не гадание»; FAQ/мета/JSON-LD под новый голос (SEO-ключи сохранены, «диагноз»
  только мягко-негативно); отзывы — реальные, 2 «навыковых» убраны; дисклеймеры = позитивная идентичность.
  Затем фьюент-правка текста (ревью ChatGPT, 37 блоков). Память: [[landing-positioning]].
- **Примеры отчётов** перегенерированы пайплайном 4.0 (4 шт, источники `projectSpec/testDrawings/`), карточка
  ведёт КРУПНЫМ полароидом рисунка + цитата из about_child + мелкие оценки; сводный по 2 рисункам — два
  полароида веером. Карточка → прямой переход на полный отчёт (`/r/<token>`, минуя обёртку `/primer`).
  Образцы (data/test_reports, gitignored) → на прод тарболом `golos_samples.tar.gz` + `install_samples.sh`.
- **Операционные фиксы:** Gemini-вызов получил per-request таймаут (`GEMINI_TIMEOUT_MS`=180с — зависший
  вызов больше НЕ блокирует воркера навсегда) + пошаговый трейс в worker.log + `scripts/gemini_ping.py`
  (проба связи в обход воркера). Email: `custom_backend_id` для Unisender (Return-Path=click.golosrisunka.ru,
  чинит DKIM-выравнивание/спам — нужен `UNISENDER_GO_CUSTOM_BACKEND_ID=31525` в СЕРВЕРНОМ .env).
  Комбобоксы формы заказа (тема/материалы): нативный `<datalist>` на мобильных не давал выбрать вариант →
  свой комбобокс (`order.js`, выбор по mousedown). Прод-500 от root-owned миниатюр → `_thumb_file` не
  перезаписывает существующие. Память: [[ops-gotchas-23-06]].
- **Заказчик одобрил отчёт Лизы и лендинг.** ⏳ ЧЕГО ЖДЁМ / pending: (1) задеплоить хвост (V1.037 комбобокс +
  линтер-тюн + Gemini-таймаут/трейс + тарбол образцов) — `./deploy.sh` + tarball; (2) добавить
  `UNISENDER_GO_CUSTOM_BACKEND_ID` в серверный .env; (3) ответ посредника по СБП-диплинку на мобильном
  (виджет embedded даёт только QR, без перехода в банк-апп — возможно нужен redirect-флоу); (4) 3 правки
  feature-копий в products.json — заказчик через /admin/settings.

## Состояние на 22.06.2026 — PHASE 8: ЮKassa ОПЛАТА (разработка завершена, TEST-стадия)
- **Оплата ЮKassa встроена — разработка ЗАВЕРШЕНА, сейчас на стадии тестирования.** Stub-оплата
  УДАЛЕНА. Встроенный виджет (`confirmation=embedded`) в модалке на нашей странице — без редиректа,
  порт проверенной схемы из `C:\projects\shepotZvezd`, адаптирован под одиночный заказ.
- **Код:** `app/yookassa.py` (новый клиент API v3 на stdlib `urllib` — без новой зависимости),
  `app/routes.py` (`GET /pay/<id>` + `POST /pay/yookassa/create` + `POST /pay/yookassa/webhook` +
  `GET /pay/yookassa/status`), `templates/checkout.html` (новый; `checkout_stub.html` удалён),
  компонент `.modal` в `components.css`. `mark_paid()` (идемпотентная точка оплаты) НЕ менялся —
  ЮKassa встала перед ним; воркер по-прежнему забирает `status='paid'`.
- **Без ложных оплат (UseCase #26):** подтверждаем оплату ТОЛЬКО при `succeeded` + точное совпадение
  суммы; подлинность webhook — перезапросом платежа через API (ЮKassa не подписывает); `canceled` —
  no-op; идемпотентность через `mark_paid`. Сумма из копеек точно (купоны дают копейки).
- **Конфиг:** `config/settings.py` — режимный сплит `YUKASSA_MODE` + `YUKASSA_SHOP_ID_{TEST,LIVE}` /
  `YUKASSA_SECRET_KEY_{TEST,LIVE}`, `yukassa_enabled()`. Боевые ключи — в локальном `.env` (live).
- **Ещё НЕ задеплоено в прод.** Перед боем (детали — DevelopmentStatus.md 22.06): (1) добавить
  `YUKASSA_*` в **серверный** `.env`; (2) `release.bat` → на сервере `./deploy.sh`; (3) зарегистрировать
  webhook `https://golosrisunka.ru/pay/yookassa/webhook` (события `payment.succeeded`+`payment.canceled`)
  в ЛК ЮKassa; (4) проверить фискализацию 54-ФЗ (чек `vat_code=1`/`service`/`full_payment`) — иначе
  live-платёж с `receipt` отклонится. Поллинг status — страховка, если webhook опоздает.

## Состояние на 18.06.2026 — РЕДИЗАЙН САЙТА (детали в DevelopmentStatus.md, бренд — в brand-book.md)
- **Полный редизайн сайта по бренд-буку готов ЛОКАЛЬНО, ещё НЕ запушен.** Бренд «Голос рисунка»
  («Золотой час»): кино-герой (`static/img/hero.jpg`) + матовая карточка; палитра выведена из фото
  (бумага `#FCEFDF` = фон логотипа; эспрессо-текст; джинсовый = действие; янтарь = «голос»). Один
  глобальный CSS (`tokens.css`+`components.css`) перекрашивает ВЕСЬ сайт. `landing.html` переписан;
  кабинет/заказ/вход/блог наследуют автоматически.
- **Лого в шапке:** `_header.html` → `<picture>` (strip на десктопе, icon ≤560px, webp+png), SEO-alt.
  Картинки строятся скриптами на хосте (бинарь нельзя писать из агента — UseCase #25):
  `build_hero_image.py`, `build_logos.py`. Источники в gitignored `data/Images/`, оптимизир. выводы в
  `static/img/` коммитятся.
- **Карусели примеров/блога — бесконечные** (клон ×3, бесшовный сброс скролла) в `landing.html`-JS.
- **Фикс:** инлайн-CSS лендинга экранировался Jinja (ломал `url()`/шрифты) → `{{ inline_css | safe }}`
  (UseCase #24). Этот фикс улучшит и прод при деплое.
- **Публикация:** `release.bat "msg"` на хосте (bump → export dist → commit → push). В PowerShell —
  `.\release.bat`. Прод-сайт обновляется ОТДЕЛЬНО: на сервере `./deploy.sh` (data/ нет на сервере, но
  оптимизир. картинки закоммичены → отдаются как есть).

## Состояние на 14.06.2026 (детали в DevelopmentStatus.md)
- **🚀 СОФТ-ЗАПУЩЕНО В ПРОД (13.06): сайт ЖИВ на golosrisunka.ru, V1.010 (14.06).** Фазы 0–7 готовы,
  Phase 9 (деплой) сделан РАНЬШЕ Phase 8 — прод со stub-оплатой (публичный,
  индексируемый по решению заказчика). **TLS: DNS-only + Let's Encrypt** (13.06 ушли с CF
  orange ради доступности из РФ — UseCase #21). Следующий гейт — Phase 8 (ЮKassa + Unisender), ждём аккаунты.
- **Фазы 0–7 построены; 0–5 одобрены заказчиком (M5 ✅)**: дизайн-система; промпт v2.0 (M3R: сводный отчёт по
  2 реальным рисункам одного ребёнка — честные противоречия, ссылки на номера рисунков — sign-off);
  лендинг с 4 сэмплами (сводный по 2 рисункам — в центре карусели, стрелки ‹ ›, мобайл-адаптация);
  единая sticky-шапка с навигацией и «Войти» (заглушка /login до Phase 7);
  **Phase 5: полный флоу заказа** — SQLite (drawn_at/birth_ym/base_order_id + events/UTM-аналитика),
  форма (конфиг полей; комбобоксы; ym-селекты; черновик в localStorage 4ч; email-опечатки; промокоды
  со скидкой; guard кнопки добавления рисунка; защита от двойного сабмита; серверные проверки дат),
  оплата через идемпотентный mark_paid() (ЮKassa встроена 22.06, см. состояние выше), сессия при оплате.
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
- **Блог: 14 статей** (content/blog/) в философии §7.4 — 6 «тревожных» тем + 8 SEO-столпов/
  конверсионных (13.06): по одному целевому запросу на статью, перелинковка blog→лендинг+/primer,
  0 эзотерики. У КАЖДОЙ статьи свой инлайн-SVG дудл (_blog_thumb.html). Даты на витрине нет.
- **Админка /admin** (дизайн одобрен): вход по `ADMIN_PASS` из .env (отдельно от /login!),
  сайдбар: Аналитика/Заказы/Клиенты/Промокоды/Настройки сайта (редактор products.json
  живьём)/Письма (outbox). Лендинг: Цены → FAQ → Блог-карусель; отзывы — узкая лента-ротатор
  (6 ПЛЕЙСХОЛДЕРОВ в routes.TESTIMONIALS). Метрика: тег готов, ждёт YANDEX_METRIKA_ID в .env
  (webvisor выключен намеренно). Dev-чит: код входа виден на странице для spashap@gmail.com
  на localhost. Кабинет: группировка по детям + спящие CTA Development («скоро»).
  Сид кабинета: data/tmp/tmp_seed_cabinet.py (заказы 9/10/11).
- **Аналитика ЖИВА (13.06)**: Я.Метрика на всех страницах кроме /admin (webvisor=ON по решению
  заказчика), first-party трекинг кликов (data-ym-goal → reachGoal + beacon /t/e), админ-вкладки
  **Визиты** (устройства/UTM/origin/гео) и **Действия** (счётчик событий с фильтром); events получил
  device/user_agent/referer (миграция в init_db). `scripts/reset_analytics.py` — чистка тест-данных.
- **Аналитика V1.010 (14.06)**: «Визиты» по умолчанию показывают НЕвовлечённых (отказы) +
  тумблер «Все»; **гео** (страна всем, регион РФ) из своей офлайн-базы `data/geoip.db`
  (`scripts/build_geoip.py` ← DB-IP City Lite, CC BY 4.0; ~30 МБ — город выкинут, диапазоны
  слиты под маленький диск; строить НА сервере, обновлять раз в месяц + `./restart.sh`);
  **IP НЕ храним** — только производную метку (миграция events +geo_country/region/city, city=NULL).
  Inline drill-down посетителя (`<details>`, без JS): полная лента событий + заказы. `app/geoip.py`
  (graceful-degrade «—» без базы), забор IP из `X-Real-IP`. Привязка фавиконок (static/img/favico/).
- **SEO Yandex+AI (13.06)**: robots.txt (YandexBot/GPTBot/ClaudeBot/Perplexity allow; block
  admin/cabinet/r), sitemap (23 URL), OG+Twitter+canonical глобально, schema Org/WebSite/Product/
  FAQPage/Article, индексируемые `/primer/<token>` (приватные /r/ закрыты), OG-картинка
  (scripts/build_og_image.py), noindex на приватных. yandex-verification на лендинге.
  ⚠️ Cloudflare-гочи (UseCase #18) актуальны ТОЛЬКО при orange-cloud; сейчас DNS-only (grey),
  CF не в тракте запроса → robots.txt/Bot-Fight не вмешиваются. Вернутся, если включить orange.
- **Git**: https://github.com/spashap/golosRisunka (PUBLIC). **Прод-деплой = VPS** (см. «Деплой»);
  Vercel-экспорт dist/ — устаревший noindex-зеркало, НЕ продакшен (продакшен на VPS).
- **✅ Unisender Go email — ЖИВ в проде (с 15.06)**: транзакционные письма (коды/доставка)
  через `app/mailer.py` (backend `unisender`). **Доставляемость в Gmail починена 16.06**:
  письма больше НЕ в «Промоакциях», доходят во «Входящие» с уведомлением. Решило:
  `MAIL_SKIP_UNSUBSCRIBE=1` (убрал List-Unsubscribe) + Unisender выключил принудительный
  трекинг открытий на аккаунте (пиксель пустой). Аккаунт ОБЩИЙ с shepotzvezd (`8096698`) —
  заметка для них `projectSpec/unisender-deliverability-shepotzvezd.md`. Свой домен ссылок
  `click.golosrisunka.ru` заведён (NS в Cloudflare). Детали — memory `unisender-go-email`.
- **Phase 8 — ЮKassa: разработка ЗАВЕРШЕНА, TEST-стадия (22.06, см. состояние выше).** Боевые ключи
  получены и в локальном `.env`. Осталось: деплой + webhook в ЛК + проверка фискализации → M8/M9-гейт.
- **devtest-img1** (Алиса, 4 года, июль 2024) — зарезервирован для Development report (продукт 2).
- Кредензалы: Gemini ✅ · YANDEX_METRIKA_ID ✅ (109824945, в прод-.env) · TLS = Let's Encrypt
  (автопродление, ничего хранить не нужно; CF Origin-cert больше не используется) ·
  Unisender Go ✅ (транзакционные письма живут, общий аккаунт shepotzvezd) · ЮKassa ✅ (ключи live
  в .env; код готов, TEST-стадия — деплой/webhook/фискализация впереди).
- Тестовый купон в локальной БД: TEST20 (20%, multi-use).

## Watch list
- Первый экран ≈235KB (цель <200KB): caveat-700.woff2 = 93KB — решить на Lighthouse-пассе Phase 9.
- Отзывы на лендинге — placeholder до текстов заказчика; 6yr тест-рисунок — сток (заменит).
  OG-image есть (static/img/og-default.png, генератор scripts/build_og_image.py).
- Прод ВСЁ ЕЩЁ на stub-оплате, ПОКА не задеплоена ЮKassa (код готов локально, TEST-стадия 22.06):
  до деплоя любой посетитель получает бесплатные отчёты (риск Gemini-расходов) — закроется деплоем
  ЮKassa. После правок шаблонов/CSS: на сервере `./deploy.sh` (nginx/TLS он НЕ
  трогает). Если когда-нибудь снова включат Cloudflare orange — «Block AI bots»/Bot Fight Mode
  держать ВЫКЛ + purge (UseCase #18); при grey-cloud это неактуально.
- `python -` heredoc и `&&`-цепочки: падение по encoding обрывает цепочку — файлы писать Write-тулом.
- Headless-скриншоты на этой машине КРОПЯТСЯ (Windows DPI 125%, UseCase #14) — мобильную вёрстку
  проверяет заказчик на телефоне; fast-сессии = правка → отдать на проверку, без скриншот-циклов.
- dist/ пересобирать после правок лендинга/CSS (`scripts/export_static.py`) и коммитить — Vercel
  деплоит из него. После правок report-шаблона: `scripts/rerender_reports.py`.
