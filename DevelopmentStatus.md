# Development Status — Голос рисунка

Append-only log: every step, current structure, decisions. Problems & solutions live in `UseCasesData.md`.
Plan reference: `projectSpec/development-plan.md`.

---

## 2026-06-11 — Phase 0: Project skeleton

### Steps done
1. Created directory layout (see Structure below).
2. Created venv (Python 3.13.1) + `requirements.txt`; installed: flask, jinja2, weasyprint 69.0, google-genai, pillow, pillow-heif, python-dotenv, pydantic (+ pypdf, brotli as dev/build helpers).
3. **WeasyPrint Windows check (task 0.3): PASSED out of the box** — GTK/Pango already on this machine. Harmless `GLib-GIO-WARNING` noise on every run (ignorable, see UseCase #4). WSL fallback NOT needed.
4. Fonts: first tried google-webfonts-helper downloads — rejected (missing ₽, UseCase #2). Final solution: `scripts/build_fonts.py` downloads official variable TTFs from github.com/google/fonts, pins weights (Rubik 800/900, Inter 400/500/600 @opsz14, Caveat 600/700), subsets to latin+cyrillic+punctuation+currency (`U+0000-00FF, U+0131, U+0400-04FF, U+2010-205F, U+20A0-20BF, U+2116, U+2122`), emits woff2 (web) + ttf (WeasyPrint). 7 faces × 2 formats in `static/fonts/`. Verified: all contain U+20BD (₽).
5. `static/css/fonts.css` — @font-face for all 7 faces, woff2 + ttf src, font-display: swap.
6. `config/settings.py` — reads `.env` (GEMINI_API_KEY verified loading), holds: products/prices (kopecks), paths, Gemini model `gemini-2.5-pro`, retry/auth/upload constants. Spec law #2: user-visible values live here, not in code.
7. `scripts/hello_pdf.py` — Milestone M0 script.

### 🧪 Milestone M0 — PASSED (machine-verified, awaiting user eyeball)
`venv/Scripts/python.exe scripts/hello_pdf.py` → `data/hello.pdf` (39 KB).
Machine checks: all 7 embedded faces are ours (Rubik-Heavy/Ultra-Bold, Inter/Medium/Semi-Bold, Caveat-Semi-Bold/Bold), **zero fallback fonts**, Cyrillic + ₽ render path clean.
**USER ACTION: open `data/hello.pdf` and visually confirm the three font families look right.**

### Structure as of now
```
GolosRisunka/
├── .env                  # GEMINI_API_KEY (never commit)
├── requirements.txt
├── DevelopmentStatus.md  # this file
├── UseCasesData.md       # problems → solutions knowledge base
├── app/                  # web app (Phase 4+)
├── config/
│   └── settings.py       # central config, reads .env
├── content/blog/         # reserved (spec §11.1)
├── data/                 # gitignored later; drawings/, reports/, hello.pdf
├── pipeline/             # report generation (Phase 2-3)
├── projectSpec/          # spec, mockups, samples, dev plan
├── scripts/
│   ├── build_fonts.py    # font build pipeline (rerunnable)
│   └── hello_pdf.py      # M0 test
├── static/
│   ├── css/fonts.css
│   ├── fonts/            # 7 faces × (woff2 + ttf)
│   └── img/
├── templates/dev/        # component gallery (Phase 1)
└── venv/
```

### Notes / watch list
- Caveat woff2 is heavy (~94 KB/face) because handwriting fonts have big glyphs; first-screen font budget will need care in Phase 4 (preload only rubik-900 + inter-400 + one caveat).
- pip 24.3.1 in venv nags about upgrade — harmless.

---

## 2026-06-11 — Phase 1: Design system

### Steps done
1. `static/css/tokens.css` — all design tokens (spec §3.2): palette «Синий» as `:root` default + Фиолет (`html.pu`) / Тёмный (`html.dk`) / Облака (`html.cl`) switchable by one class on `<html>` (= `settings.PALETTE`). Also typography tokens (`--font-head/body/hand`), geometry (radius, wrap width), shadow tokens incl. the signature hard shadow `5px 5px 0 var(--ink)`. Values taken 1:1 from `golosrisunka-hybrid-2.html` mockup.
2. `static/css/components.css` — reusable component library (spec §3.4), generalized from both mockups with BEM-ish naming: `btn`/`btn--primary`, `card`(+`--pad`), `polaroid`(+`--tilt-l/r/sl`, tape `::before`, `__img`, `__cap`), `badge`(+`--corner`, `--flat`), `score-bar`(`__track`/`__fill`, width = score×10%), `section`(+`--alt`), `carousel` (scroll-snap, no JS), `quote`(`__text`/`__who`), `step`/`steps`, `nav`+`logo`, `faq` (details/summary), `note`, `foot`, `wrap`, h1–h3 typography. Includes reset + mobile breakpoints.
3. `templates/_base.html` — Jinja2 base: lang=ru, palette class hook, font preloads (rubik-900/inter-400/caveat-700), css links, title/description/og/head/body/footer blocks, disclaimer footer default.
4. `templates/dev/components.html` — gallery: every component with dummy data (incl. ₽ and score bars driven by Jinja loop).
5. `scripts/render_gallery.py` — renders gallery to `component-gallery.html` in project root; optional palette arg (`pu`/`dk`/`cl`).

### 🧪 Milestone M1 — built, awaiting user eyeball
**USER ACTION: open `component-gallery.html` in a browser.** Check: polaroids with tape+tilt+handwritten captions, corner badges, hard-shadow CTA with hover shift, score bars, carousel scroll, FAQ accordion, ₽ sign everywhere.
To preview other palettes: `venv/Scripts/python.exe scripts/render_gallery.py dk` (or `pu`/`cl`) and reload.

> 2026-06-11: M0 + M1 **approved by user**.

---

## 2026-06-11 — Phase 2: Report HTML/PDF template (fake data)

### Steps done
1. `pipeline/schema.py` — Pydantic contract (spec §7.3): `Report` (child, context_summary, introduction, 7–8 dimensions with score 1–10 / observation / research_note / activities, recommendations, optional `development_directions`, conclusion, insufficient flags) + `InsufficientReport` + `validate_report()`. 7 dims allowed because spec permits merging problem-solving+logic.
2. `pipeline/samples/sample_report.json` — hand-written Russian sample (Лиза, дерево) adapted from old child.pdf but **cleaned per §7.4**: every observation tied to a visible detail, no emotion/color-psychology claims (the emotional_expression dimension explicitly debunks the color-mood myth), social dimension framed as "one drawing can't tell". This file = tone reference for the Phase 3 prompt.
3. `pipeline/samples/sample_drawing.svg` — fake child drawing (tree) for the cover polaroid.
4. `static/css/report.css` — WeasyPrint-safe report components on the same tokens: A4 @page with page-number footer + disclaimer, cover (logo/title/polaroid/disclaimer, page-break-after), score table (real `<table>`, not grid), dimension blocks (`page-break-inside: avoid`, floated score badge), context/conclusion panels, screen-vs-print backgrounds via `@media screen`.
5. `templates/report.html` — full §7.5 structure: cover → context → introduction → summary scores → 8 dimension sections → recommendations → development directions (optional, with "для интереса, не прогноз" note) → conclusion → footer disclaimer.
6. `pipeline/render.py` — `render_html()` (hosted `/static` prefix vs print `static` prefix), `render_pdf()` (WeasyPrint), `render_report_files()` (saves both), `drawing_to_data_uri()` — drawings embedded as data URIs so browser and PDF behave identically and no protected image route is needed.
7. `scripts/render_sample.py` — M2 script.
8. Two font-fallback bugs found by the embedded-font check and fixed (UseCases #6 italics→Segoe, #7 missing → arrow glyph; fonts rebuilt with arrows+checkmarks ranges).

### 🧪 Milestone M2 — built, machine-verified, awaiting user judgment
`data/reports/sample/report.html` (browser) + `report.pdf` (6 pages, 54 KB, zero font fallback).
**USER ACTION: read both and judge: does this look worth 990 ₽?** Feedback on layout/tone is cheapest to apply right now.

---

## 2026-06-11 — Phase 3: System prompt + Gemini pipeline (the core)

### Test data (user-provided, projectSpec/testDrawings/)
3 drawings + free-format context txts: 3.5yr (real, messy photo), 6yr (stock image — user will replace for landing), 8yr (real). Intentional traps: gender-grammar contradictions in texts. Agreed rules: gender from «пол» field only; display name = имя + first letter of фамилия.

### Steps done
1. `pipeline/prompt.py` — Russian system prompt v1.0→**v1.1** (PROMPT_VERSION versioned in file). Structure/warmth from old custom-GPT prompt, philosophy inverted per §7.4: hard bans (emotion/state reading, Barnum, invented details, invented sources, emojis, inner-trait language with rephrase-to-skill rule), 8 fixed dimensions with keys (merge rule → 7 allowed), honest scoring guidance (5-6 = age-typical), insufficient_input criteria, JSON format with field length targets.
2. `pipeline/images.py` — jpg/png/heic → RGB JPEG ≤2000px (white background for RGBA, pillow-heif registered).
3. `pipeline/gemini.py` — google-genai client: images+context → JSON (response_mime_type=application/json, temp 0.5), 5 attempts with backoff, raw responses dumped per attempt, markdown-fence stripper, pydantic validation. **Plus lint+repair loop** (see UseCase #8): `pipeline/lint.py` regex linter for inner-state language → text-only repair call (temp 0.2) → re-validate, max 2 rounds, accept only on improvement.
4. `scripts/generate_report.py` — end-to-end CLI (later becomes worker core + regenerate_report.py): images + context.txt → report_raw.json / report.json / report.html / report.pdf. Russian date formatting.
5. Template fix: cover now shows ALL drawings of an order (tilted polaroids), not just the first.

### Test results (gemini-2.5-pro, all on attempt 1)
| Test | Result |
|---|---|
| 8yr real drawing | clean report, honest scores 4-9, specific details (CAT lettering, nose from eye-line intersections) |
| 3.5yr real (messy photo) | clean, gender trap PASSED (male forms despite «сама» in text), голованог recognized, scores 4-8 |
| 6yr stock image | clean, gender trap PASSED; did not flag as stock (can't know — acceptable) |
| Blank page photo | `insufficient_input=true` + polite reason, no invented report ✓ |
| 2 drawings, one order | works, single coherent report ✓ |
| Lint/repair | every report: 1 repair round → 0 violations left |

### 🧪 Milestone M3 — READY FOR USER SIGN-OFF (the big one)
**USER ACTION: read the three final PDFs:**
- `data/test_reports/Draw-3_5yr-v1-final/report.pdf`
- `data/test_reports/Draw-6yr-v1-final/report.pdf`
- `data/test_reports/Draw-8yr-v1-final/report.pdf`

Judge: observations reference real visible details? scores feel explained, not flattering? «Как развивать» concrete? tone right? worth 990 ₽? **This sign-off gates Phase 4 (landing) — these reports become the landing samples.**

### Notes / watch list
- Each report ≈ 60-90 s Gemini time, 1 vision call + 1 repair text call.
- Multi-drawing cover re-render confirmed; production path embeds resized JPEGs (~220 KB PDF), not raw PNGs.

---

## 2026-06-11 — Phase 4: Flask app + landing page

### Steps done
1. `app/__init__.py` — create_app: static/templates wiring, 404/500 handlers, context globals (static prefix, palette, site name). `run.py` — dev server :5000.
2. `app/samples.py` — landing samples registry built from the M3 real reports (`data/test_reports/*-final`): first names only, top-3 scores, badge from top dimension, quote from conclusion, webp thumbnails auto-generated to `static/img/samples/` (480px, q72, width/height attrs). Replacing test drawings later = regenerate reports + edit `_SAMPLE_DEFS`.
3. `app/blog.py` — blog skeleton per spec §4.3/§11.1: md files with frontmatter in `content/blog/`, markdown lib added. Empty dir → «Статьи скоро».
4. `app/routes.py` — `/` (landing), `/r/<token>` (hosted reports; samples now, DB orders join same route in Phase 5), `/order` (stub until Phase 5), `/blog`, `/blog/<slug>`, `/privacy|/terms|/contacts` (placeholder texts), `/robots.txt` (Disallow /r/ and /order), `/sitemap.xml` (generated). FAQ texts configurable in routes.py.
5. `templates/landing.html` — full spec §4.1 structure: nav → hero (headline + 3 polaroids with REAL drawings + score badges) → sample-report carousel (real M3 reports) → 3 steps → testimonial (placeholder text until заказчик provides) → guarantee/trust → FAQ (details/summary) → pricing CTA (3 products from config) → footer with disclaimer + legal links.
6. New shared components (components.css): `hero`, `pol-table`, `report-card__*`, `price-card`.
7. SEO: unique title/description, OG tags, canonical, JSON-LD Product (3 offers) + FAQPage, robots, sitemap.
8. Performance: critical CSS (tokens+components) inlined (cached lru_cache), 3 font preloads, webp images with dimensions, lazy below fold. Landing HTML 113KB → **32KB** after switching thumbs from data URIs to static webp.

### Machine checks
All routes 200 (landing, sample reports, blog, legal, robots, sitemap; /r/unknown → 404). Content: 3 polaroids, 3 sample cards with real names (first names only — surnames verified absent), 6 FAQ items, prices 990/1490/1890, disclaimers, Schema Product+FAQPage present.

### 🧪 Milestone M4 — awaiting user
Dev server: `venv\Scripts\python.exe run.py` → http://localhost:5000 (already running in background).
**USER ACTIONS:**
1. Open http://localhost:5000 — full landing; click through sample reports, FAQ, all footer links.
2. Phone on same wifi: http://<PC-IP>:5000 — mobile layout.
3. Chrome DevTools → Lighthouse (mobile) — target ≥ 90 already now.

### Notes / watch list
- First-screen weight ≈ 235KB (slightly over 200KB target): caveat-700.woff2 is 93KB (cyrillic handwriting font is inherently heavy). Options for Phase 9 Lighthouse pass: drop caveat preload, or subset caveat to used-glyphs only.
- Testimonial block uses mockup placeholder text — заказчик заменит реальными цитатами (~17.06 per plan).
- OG image not set yet (needs a designed og.png) — Phase 9.

---

## 2026-06-11 — Phase 4.1: PRODUCT MODEL REWORK (user correction) + landing UI fixes

### ⚠️ Product model corrected by заказчик — overrides spec §1 pricing
- NOT 3 price tiers by drawing count (snap1/2/3 — отменено).
- **Product 1 «snapshot»**: до 3 рисунков → ОДИН сводный отчёт; цена не зависит от числа рисунков. 2999 ₽, дизайн «скидка от 4900 ₽».
- **Product 2 «development»**: сравнение ДВУХ наборов рисунков с интервалом ≥ 6 мес. 4999 ₽ (от 6900 ₽). Не факт что войдёт в MVP — на лендинге карточка «скоро» без кнопки покупки.
- **ВСЕ цифры — из будущей админки.** До неё: `config/products.json` (правится руками, mtime-кэш — без рестарта). `settings.get_products()` — единственный источник цен. Запрещено хардкодить цены в шаблонах.

### Steps done
1. `config/products.json` — оба продукта: enabled, title, subtitle, price_rub, old_price_rub, features[]. settings.PRODUCTS → `settings.get_products()` (mtime-кэш).
2. Landing pricing section redesign: 2 карточки `price-card` (новый дизайн: старая цена зачёркнута, фичи с галочками, кнопка прижата к низу). Development: бейдж «скоро», без кнопки. Hero CTA и meta: «2999 ₽» вместо «от 990 ₽».
3. JSON-LD offers: только enabled-продукты.
4. **UI fixes по фидбеку:** `.report-card` → flex column, `__link` margin-top:auto (кнопки карусели выровнены по низу); `.note` margin-top 22px (отступ текст↔кнопка в hero); step line-height; price-card паддинги.
5. Order stub обновлён под новую модель.

### Machine checks
2999/4900 + 4999/6900 рендерятся, старые цены (990/1490/1890) отсутствуют, development без кнопки покупки, schema = 1 offer, карточки flex.

### 🧪 Milestone M4 (re-test) — awaiting user
Перепроверить http://localhost:5000: секция цен (2 карточки со скидочным дизайном), кнопки карусели по низу, отступы.

---

## 2026-06-11 — Phase 3R: Multi-drawing consolidated report (по решению заказчика — пауза Phase 5, возврат к промпту)

### Rationale
Продукт «snapshot» = до 3 рисунков → ОДИН сводный отчёт. Промпт v1.x был одно-рисуночным; v2.0 добавляет явные правила консолидации.

### Steps done
1. **Prompt v2.0**: блок «НЕСКОЛЬКО РИСУНКОВ»: один ребёнок/один период; единый отчёт, не склейка; нумерованное описание каждого рисунка во введении; наблюдения цитируют номер рисунка; повторяемость навыка в нескольких работах > единичного появления; противоречия между рисунками называются честно; оценка = совокупная картина, не механическое среднее.
2. **Контекст по каждому рисунку**: `build_user_prompt(contexts: list, common_context)` — истории привязаны к изображениям по порядку + общий блок о ребёнке. `generate_report()` принимает список контекстов; CLI: `--context F1.txt F2.txt … [--common C.txt]`.
3. Тест механики (2 img): attempts 1, repair 1, lint 0 — pipeline работает.
4. **UseCase #9**: синтетический тест «рисунок + его кроп» НЕвалиден для оценки консолидации — Gemini корректно распознал кроп как часть той же работы и слил описания (модель внимательнее теста). Полезный side-эффект: модель не выдумывает различий между почти одинаковыми входами.
5. Регрессия 1 рисунок (v2.0): 8 направлений, оценки 5–7, ноль ложных ссылок на «рисунок 2/3» — одиночный режим не пострадал.

### ⛔ BLOCKED — нужен ввод заказчика (3R.5)
**Для честного теста консолидации нужны 2–3 РАЗНЫХ рисунка ОДНОГО ребёнка (один период) + короткая история по каждому.** Положить в `projectSpec/testDrawings/` (например `multi-set1-img1.png` + `multi-set1-img1.txt`, …).

### 🧪 Milestone M3R — ждёт реальный набор
Прочитать сводный PDF: ощущается как ЕДИН отчёт об одном ребёнке? наблюдения ссылаются на конкретные рисунки? противоречия названы честно?

---

## 2026-06-12 — Git push + временный Vercel-хостинг + 2 бага из скриншотов заказчика

### Git
- `.gitignore`: `.env`, `data/`, `venv/`, `.claude/`, **projectSpec/testDrawings/ и reportSamples/** (детские рисунки с ФИО и приватные материалы — НЕ в git).
- Initial commit (95 файлов) → push в https://github.com/spashap/golosRisunka (main). ⚠️ Репозиторий ПУБЛИЧНЫЙ — рекомендация сделать private остаётся в силе.

### Временный хостинг (до русского VPS)
- Полный Flask-стек на Vercel не работает (WeasyPrint/SQLite/воркер) — для витрины сделан **статический экспорт**: `scripts/export_static.py` → `dist/` (лендинг, 3 sample-отчёта, юр.страницы, static). Все страницы с `noindex`, robots.txt `Disallow: /` — временный домен не должен индексироваться (каноничный будет golosrisunka.ru).
- `vercel.json`: outputDirectory=dist, cleanUrls. dist/ закоммичен.
- Деплой: Vercel dashboard → Import Git Repository → spashap/golosRisunka → Framework "Other" → деплой (build command пустой). Адрес вида golos-risunka.vercel.app.

### Архитектурная проверка по запросу заказчика (12.06): дата рисунка + upsell + Development-на-базе-существующего-отчёта
Вердикт: архитектура выдерживает без переделок; три дешёвых поля закладываются в Phase 5 СРАЗУ:
`drawings.drawn_at` (YYYY-MM, обязательное), `children.birth_ym` (дата рождения раз на ребёнка вместо «возраста» в каждой заявке), `orders.base_order_id` (nullable — Development-заказ ссылается на прежний заказ; отчёт строится на его report_json + рисунках + новом наборе). Upsell-напоминания (drawn_at ≥ 5–6 мес.) — post-MVP cron, чистое дополнение. План (Phase 5, 11.3, новый 11.4) и память обновлены. Тестовые данные: set1 (2 рисунка этой недели) → M3R; devtest (рисунок годичной давности того же ребёнка) — зарезервирован для Development report.

### 12.06 — M3R: реальный набор получен, сводный отчёт сгенерирован
Заказчик загрузил set1 (Алиса, 6 лет: «Стич» + «Лабубу с натуры», июнь 2026) и devtest (та же Алиса, 4 года, июль 2024 — зарезервирован для Development report).
Результат `data/test_reports/set1-consolidated/` (attempts 1, repair 1, lint 0):
- ссылки на конкретные рисунки: 3× «рисунок 1», 4× «рисунок 2», 6× «в обоих» ✓
- **честное противоречие** (контроль движений, 6/10): «в рисунке 1 раскрашивание более аккуратное… в рисунке 2 штриховка размашистая, выходит за контуры» — названо прямо, объяснено в оценке ✓
- кросс-рисуночные наблюдения (глаза с бликами в обеих работах; рисование с натуры распознано как более сложная задача) ✓
- разброс оценок 6–9, единый отчёт (не склейка) ✓
**USER ACTION (gates M3R): прочитать `data/test_reports/set1-consolidated/report.pdf`.**

### 12.06 — M3R ПОДТВЕРЖДЁН заказчиком + фронтенд-дополнения
M3R sign-off: «looks great for MVP step» (сессия улучшений — после всех фаз). По фидбеку добавлено:
1. **Сводный отчёт set1 — на лендинге**: карточка `primer-2-risunka` ВТОРОЙ (центр карусели из 4), бейдж «пример · 2 рисунка». Hero-полароиды без изменений (флаг hero в _SAMPLE_DEFS).
2. **Единая шапка-полоса** `templates/_header.html` + `.site-header` (sticky): лого, Примеры/Как это работает/Цены/Блог, **Войти** (→ /login заглушка до Phase 7), CTA. Подключена на лендинге, всех страницах (_base) и hosted-отчётах.
3. **Hosted-отчёты с шапкой сайта**: report.html — условный site_header (в PDF шапки нет); `scripts/rerender_reports.py` перерендеривает hosted-HTML из сохранённых report.json без Gemini.
4. /login — страница-заглушка кабинета.
Проверено: headless-скриншоты лендинга и /r/primer-2-risunka; карусель: 3-goda → **2-risunka** → 6-let → 8-let; dist/ переэкспортирован (33 файла).

### 12.06 — Phase 5: Order flow построен (M5 ждёт проверки заказчика)
1. **БД** `app/db.py` (sqlite3 stdlib, без ORM): customers, children (gender/birth_ym), orders (child_json, base_order_id, visitor_id, utm_json), drawings (drawn_at, context_json), reports, sessions, login_codes, coupons, **events** + индексы. WAL, FK on. init_db() идемпотентен.
2. **Аналитика** (для будущей админки): `app/track.py` — visitor-cookie (httpOnly, 1 год), first-touch UTM cookie, серверный track(). Воронка: landing_view → sample_view → order_form_view → order_created → checkout_view → order_paid (только при реальном переходе статуса — дубль webhook не шумит). UTM заказа сохраняется в orders.utm_json — проверено (vk/june_test).
3. **Форма заказа** `config/form_fields.py` (поля = конфиг): блок ребёнка (имя/пол/месяц-год рождения) + до 3 блоков рисунка (фото, drawn_at, тема, материалы, настроение, время, «что бросилось в глаза», доп.) + email. `context_to_story()` → свободный текст для промпта (тот же формат, что в тестах M3). Рендер по конфигу (macro), сохранение значений при ошибках, server-side валидация всего.
4. **Загрузка**: jpg/png/heic/webp, ≤15МБ, до 3 файлов → data/drawings/{order_id}/; vanilla JS (order.js): динамические блоки 1–3, превью, клиентский лимит размера.
5. **Оплата за абстракцией** `app/payments.py`: create_payment() → stub-чекаут; **mark_paid() — единая идемпотентная точка** (стане webhook ЮKassa): customer find-or-create, child переиспользуется по имени (spec §5), сессия 30 дней (cookie gr_s httpOnly), status=paid. Дубль подтверждения безопасен (проверено).
6. Роуты: GET/POST /order, /pay/stub/<id> (+confirm), /order/success/<id>, /cabinet (заглушка до Phase 7); /r/<token> теперь ищет и в reports по public_token (готово для Phase 6).
7. Тесты пройдены: полный флоу (UTM-лендинг → форма → 2 рисунка → стаб-оплата → success, cookie сессии); БД-состояние (paid, 299900 коп., файлы на диске, drawn_at, воронка событий); ошибки валидации (400, поля подсвечены, значения сохранены); 16МБ файл отклонён; идемпотентность оплаты. UseCase #12 (MultiDict.to_dict + curl-кириллица).

### 🧪 Milestone M5 — USER ACTION
На http://localhost:5000: пройти покупку руками — лендинг → «Заказать» → форма (попробуйте добавить/убрать рисунки, отправить с ошибками, HEIC с телефона) → тест-оплата → success. Кабинет — заглушка (Phase 7).

### 12.06 — Fast-paced сессия: полировка формы заказа + мобильный лендинг (одобрено заказчиком)
**Форма заказа** (всё протестировано test client'ом):
- Поле имени без префилла; обязательные поля — голубая заливка в тон палитры, необязательные — бумажные + пометка «(необязательно)»; подсказки под каждым полем + title-тултипы.
- Textarea-«попапы»: слот фиксированной высоты, при hover/тапе раскрывается ПОВЕРХ контента (z-front, тень). Тема/материалы → комбобоксы (datalist: пресеты ИЛИ свой текст); время рисования → строгий селект (до 5 мин … больше часа). Поле «настроение» УДАЛЕНО по экспертной оценке (промпт не вправе использовать эмоции; обстоятельства покрыты временем/доп.контекстом). Порядок опциональных полей = по вкладу в анализ: материалы → время → «что бросилось в глаза» → доп.
- Черновик формы в localStorage (TTL 4 часа; файлы не кэшируются — браузер не даёт), очистка при сабмите; серверный ре-рендер с ошибками главнее черновика.
- Email: детектор опечаток домена (Левенштейн ≤2 к 18 популярным доменам) → попап «вы имели в виду …?» с Исправить/Оставить; сабмит блокируется до решения. Под email — поле промокода: валидация по таблице coupons, скидка применяется к цене заказа сразу (проверено: TEST20 → 239920 коп.), uses_count++ при оплате.
- Кнопка «+ Добавить рисунок»: отказ с пояснением, пока в предыдущем блоке не заполнены фото/тема/месяц/год (подсветка недостающего); год рисунка по умолчанию = текущий. Отступ кнопки от email-блока.
- Subgrid-выравнивание 2-колоночной сетки (label/hint/box на одних горизонталях). Двойной сабмит заблокирован («Отправляем…»), серверная проверка дат (рисунок не раньше рождения и не из будущего), HEIC-подтверждение именем файла, trust-строка у загрузки, маяк form_started в воронку.
**Лендинг (мобайл):** полароиды hero — НЕ карусель, три уменьшенных в ряд (мелкий скотч/бейджи); карусель примеров — карточка ~86vw со снапом + кнопки-стрелки ‹ › (и на десктопе); мобильная шапка ужата. UseCases #13 (lru_cache CSS), #14 (DPI-кроп headless), #15 (permissions в живой сессии).

### Баги из projectSpec/errors/ (скриншоты заказчика 11.06)
1. **Шрифты не грузились в браузере** (всё serif): instancer оставлял STAT-таблицу при удалённом fvar → Chrome OTS тихо отвергал woff2. WeasyPrint не санитайзит — поэтому PDF были ок и мы не заметили. Фикс: build_fonts.py дропает STAT/avar/gvar/…; проверка headless-Chrome скриншотом. **UseCase #10.** Правило: проверки шрифтов — и PDF, и браузер.
2. **Цитаты карточек обрывались на инициалах** («В рисунке Никиты Н.»): наивный split по '. '. Фикс: `_first_sentence()` — конец предложения только после строчной буквы. **UseCase #11.**
- Отступ CTA↔заметка в hero был починен ранее (22px) — скриншот заказчика был до фикса.

---

## 2026-06-12 — Phase 6: Background worker + delivery (M5 подтверждён заказчиком)

### Контекст-решение заказчика
ЮKassa-аккаунта для проекта и Unisender-домена ПОКА НЕТ — всё строим как «фундамент»:
рабочие заглушки за чистыми абстракциями, чтобы при получении аккаунтов подключение
свелось к реализации одного backend'а (Phase 8), без переделок вызывающего кода.

### Steps done
1. **`app/mailer.py`** — email за абстракцией: `send_email()` — единая точка отправки
   (Unisender в Phase 8 = смена MAIL_BACKEND, интерфейс тот же). Backend 'outbox':
   письмо → HTML-файл в `data/outbox/` (комментарий-шапка To/Subject/Attach, открывается
   в браузере) + ASCII-строка в лог. `send_admin_alert()` — алерты администратору туда же.
   Шаблоны: `templates/email/` (_email_base с дисклеймером и «ответьте на письмо» во ВСЕХ
   письмах, report_ready с кнопкой /r/<token>, insufficient с просьбой переснять/возвратом).
2. **`app/jobs.py`** — `run_order(conn, order_id)`: paid → generating → пайплайн →
   delivered | insufficient | failed. Без Flask (соединение явно) — общий код воркера и CLI.
   Детали: возраст на дату рисунка считаем САМИ (`_age_display`: birth_ym+drawn_at →
   «5 лет 11 месяцев», русские плюралы; модели арифметику дат не доверяем); пол в промпт
   словом («девочка»), не буквой; common_context = блок о ребёнке, contexts = истории по
   рисункам (`child_to_common`/`drawing_to_story` в form_fields.py — бывший context_to_story);
   failed: error.log + traceback + attempts_log в `data/reports/{id}/`, алерт админу,
   событие report_failed; insufficient: insufficient.json, письмо клиенту + алерт,
   событие order_insufficient; delivered: reports row (UPSERT — **public_token сохраняется
   при regenerate**, ссылка клиента не меняется), письмо с PDF-вложением, report_delivered.
3. **`worker.py`** (корень) — поллер `status='paid'` (ORDER BY paid_at), `--once` для
   тестов/cron; на старте сбрасывает зависшие 'generating'→'paid' (убитый воркер);
   лог: консоль ASCII + `data/worker.log` UTF-8; шумные либы (fontTools/weasyprint/httpx) →
   WARNING. На VPS станет systemd-юнитом (Phase 9).
4. **`scripts/regenerate_report.py ORDER_ID`** — ручной перезапуск из любого статуса
   кроме 'created' (тем же jobs.run_order).
5. Сопутствующее: `db.track(conn=...)` для процессов без Flask; `PRAGMA busy_timeout=5000`
   (воркер+веб пишут в одну БД); пути в БД — POSIX-слэши (`as_posix()` — переезд на VPS);
   `ru_date` переехал в pipeline/render.py (был дубль в CLI); settings: PUBLIC_BASE_URL
   (ссылки в письмах), WORKER_POLL_SECONDS, MAIL_BACKEND, OUTBOX_DIR, WORKER_LOG.

### Machine checks (29/29 passed + 2 live-прогона)
- Мок-пайплайн: delivered (файлы, reports row, /r/<token> 200, письмо с Attach и ссылкой,
  событие, возраст в контексте промпта, «девочка» в common); regenerate (token не сменился,
  reports row один); insufficient (статус, insufficient.json, письмо+алерт, причина в обоих);
  failed (статус, error.log, алерт, событие); guard на несуществующий/неоплаченный заказ;
  _age_display (5 кейсов с плюралами).
- **Live Gemini #1**: заказ 6 (failed) → `regenerate_report.py 6` → delivered (attempts 1, repair 1).
- **Live Gemini #2**: заказ 7 (2 рисунка set1, оплачен стабом) → `worker.py --once` подобрал →
  сводный отчёт delivered → письмо в outbox → выход по пустой очереди.

### 🧪 Milestone M6 — USER ACTION
1. Запустить в двух консолях: `venv\Scripts\python.exe run.py` и `venv\Scripts\python.exe worker.py`.
2. Пройти покупку на http://localhost:5000 → в течение ~2 минут заказ станет delivered,
   «письмо» появится в `data/outbox/` (открыть HTML, перейти по кнопке «Открыть отчёт»).
3. Саботаж: выключить интернет (или подложить битый файл рисунка) → заказ failed,
   алерт в outbox → `scripts/regenerate_report.py <id>` после починки → delivered, ссылка та же.

---

## 2026-06-12 — Phase 7: Вход по email-коду + личный кабинет

Заказчик занят M6-тестами → решение: строить Phase 7 сразу, M6+M7 проверить одной сессией.
Кабинет упрощает M6-проверку: статусы заказов и ссылки на отчёты видны на одной странице.

### Steps done
1. **`app/auth.py`**: `request_code()` (6 цифр, TTL 30 мин; rate limit — пока «живой» код
   моложе 10 мин, новый не выдаётся «код уже отправлен»; аннулированный по попыткам код
   НЕ блокирует повторный запрос); `verify_code()` (5 неверных вводов → код void; одноразовость;
   customer find-or-create — вход без покупок даёт пустой кабинет и не раскрывает, есть ли заказы);
   `create_session()` (общая с payments.mark_paid — auto-login при покупке, дубль-код убран);
   `current_customer()` (cookie gr_s, кэш в g); `destroy_session()`.
   Код уходит письмом (mailer → outbox) И ASCII-строкой в лог/консоль (до Unisender — план M7).
2. **Роуты**: GET/POST /login (шаги email→код, «прислать ещё раз»), POST /login/verify,
   POST /logout, GET /cabinet (заказы покупателя, кроме неоплаченных 'created'),
   GET /cabinet/drawing/<id> (превью: thumb-JPEG 480px кэшируется рядом с оригиналом — heic
   браузер не покажет; только владельцу: 403 аноним / 404 чужое),
   GET /cabinet/order/<id>/report.pdf (скачивание, владелец+delivered).
   Статусы для клиента: paid/generating/**failed** → «в обработке» (план 6.2), delivered →
   «готов», insufficient → «нужны другие фото». robots.txt += Disallow /login, /cabinet.
   События: login_view, login_code_requested, login_success, cabinet_view.
3. **Шаблоны**: login.html (код-инпут one-time-code/inputmode=numeric), cabinet.html
   (карточки заказов: продукт+имя ребёнка, статус-пилюля, превью рисунков, кнопки
   Открыть/Скачать PDF, логаут с email), email/login_code.html.
   login_stub.html устарел (не удалён: deny-list на Remove-Item) — удалить руками.
4. **CSS** (components.css, секция Phase 7): .login-notice, .code-input, .order-card
   (+__head/__thumbs/__actions), .thumb, .status-pill--wait/ready/warn.
5. dist/ переэкспортирован (инлайн-CSS лендинга вырос на ~1КБ — в Lighthouse-пасс Phase 9).

### Machine checks (27/27 passed)
Запрос кода (формат, страница шага 2); rate limit (повтор → «уже отправлен», новый код
не создан); 5 неверных вводов → void (верный код после — отказ; повторный запрос разрешён);
вход → redirect+cookie; кабинет: заказ 7 «готов» со ссылкой /r/ и превью; reuse кода — отказ;
thumb=JPEG, PDF скачивается; аноним 403/redirect, чужой покупатель 404/пустой кабинет;
auto-session при покупке (7.4: купил → кабинет без логина, заказ «в обработке»); логаут.

### 🧪 Milestone M6+M7 — USER ACTION (одной сессией)
1. Две консоли: `venv\Scripts\python.exe run.py` + `venv\Scripts\python.exe worker.py`.
   **Заказ 8 уже ждёт в paid** — воркер доставит его при старте (это и есть M6-проверка).
2. M6: письмо в `data/outbox/` (открыть HTML → кнопка «Открыть отчёт»); свой заказ с телефона/HEIC.
3. M7: /cabinet в том же браузере (auto-login после покупки) — статусы, превью, PDF.
   Другой браузер → /login → код из консоли run.py ИЛИ из data/outbox/.
   Попробовать сломать: неверный код 5 раз, повторный запрос < 10 мин, повторное использование кода.
4. Саботаж M6: отключить интернет → заказ → failed → алерт в outbox → regenerate_report.py.

---

## 2026-06-12 — Блог: 6 статей по образцам заказчика (EN → RU, SEO для Яндекса)

### Источник и редакторское решение
Заказчик дал 5 английских статей своего сайта DrawReport (projectSpec/blog/) на перевод
с обогащением. **Ключевое решение**: английские оригиналы местами читают эмоции по рисунку
(«dark palettes accompany strong emotions») — это противоречит философии продукта (§7.4)
и FAQ лендинга («принципиально не делаем выводов об эмоциях»). Поэтому статьи НЕ калька:
они целятся в ТЕ ЖЕ родительские поисковые запросы, но отвечают в духе бренда — спокойно
развенчивают цветовую поп-психологию (низкая надёжность проективных трактовок), показывают,
что в рисунке видно достоверно (навыки/этапы), а «когда тревожиться» переводят на ПОВЕДЕНИЕ
ребёнка, не на содержание рисунка. Каждая статья: дисклеймер «не диагностика» + мягкий CTA.

### 6 статей (content/blog/*.md; «angry drawings» разделена на 2 разных интента)
1. rebenok-risuet-chernym — «Ребёнок рисует только чёрным цветом» (запросы: ребёнок рисует чёрным)
2. temnye-cveta-v-detskih-risunkah — «Тёмные цвета: что значат на самом деле» (психология цвета — миф)
3. strashnye-risunki-monstry — «Монстры, война и страшное» (контент рисунков)
4. zlye-risunki-silnyj-nazhim — «Черкает, давит, рвёт бумагу» (ПРОЦЕСС: нажим/перфекционизм/разрядка)
5. rebenok-risuet-sebya-odnogo — «Рисует себя одного» (+развенчание теста «Рисунок семьи»)
6. rebenok-ne-risuet-litso-ruki — «Люди без лица/рук» (этапы рисунка человека, головоног)
Структура каждой: лид с запросом → блок «Коротко» (под быстрые ответы Яндекса) → H2-вопросы →
возрастные нормы → «когда присмотреться» (поведение!) → как говорить с ребёнком → FAQ →
перекрёстные ссылки. ~1200–1600 слов. Кросс-линки проверены (все резолвятся).

### Инфраструктура
- blog_post.html: h1 (class="h2"), canonical, OG article, расширенная Article-schema
  (mainEntityOfPage, author, inLanguage=ru, dateModified); site_domain в context_processor.
- components.css: компонент .prose (типографика markdown: таблицы, списки, hr, blockquote).
- export_static.py теперь экспортирует и посты блога (dist/blog/<slug>.html, 41 файл).
- Sitemap посты подхватывает автоматически (уже было).

### Machine checks (60/60)
6 постов парсятся; index перечисляет все; на каждом посте: 200, h1, meta description,
canonical+OG, Article-schema, нет сырого markdown, ссылка /order, дисклеймер, полный title
с двоеточием (frontmatter-парсер ок); md-таблица рендерится; sitemap содержит все посты;
перекрёстные /blog/-ссылки без 404.

### ⚠️ Для заказчика
- PNG-обложки образцов — с английским текстом, на русский сайт не пошли. OG-изображения
  статей — кандидат на Phase 9 (вместе с общим OG-image сайта).
- Статьи стоит вычитать: тон/факты — особенно блоки «что говорят исследования»
  (написаны осторожно, без ссылок на конкретные работы).
- Vercel: dist/ под noindex — для Яндекса блог заработает только на golosrisunka.ru (Phase 9).

---

## 2026-06-12 (поздний вечер) — Fast-сессия: блог-карточки, лендинг, отзывы, АДМИНКА, кабинет-концепт

Сессия до паузы проекта (ждём домен + аккаунты ЮKassa/Unisender/Metrika ID).

### Блог и лендинг (фронт, одобрено заказчиком по ходу)
1. /blog: сетка прямоугольных карточек (3/2/1 колонки) вместо текстовых полос; у каждой
   статьи концепт-миниатюра — **инлайн-SVG дудлы** (`templates/_blog_thumb.html`, цвета через
   var(--…) — перекрашиваются палитрами; дефолтный дудл для будущих статей). PNG заказчика
   не пошли (английский текст). Даты публикации скрыты (в schema/sitemap остались).
2. Лендинг, новый порядок: Примеры → Как работает → **Отзывы-лента** → Доверие → **Цены** →
   **FAQ** → **Блог-карусель** → футер. Совет-обоснование: FAQ = снятие возражений при цене;
   блог в самом низу (не уводит из воронки). Чередование --alt сохранено.
3. **Отзывы**: узкая лента (section--strip 30px, надзаголовок «ЧТО ГОВОРЯТ РОДИТЕЛИ»),
   ОДНА цитата за раз, автосмена 7с (data-interval), фейд, стрелки + точки, пауза на hover,
   фикс-высота без прыжков, мобайл ок. 6 цитат-ПЛЕЙСХОЛДЕРОВ в routes.py TESTIMONIALS.
4. Карусель-JS обобщён (шаг = ширина первого ребёнка; guard на не-карусели).

### Админка /admin (дизайн одобрен)
- **Отдельный вход**: пароль `ADMIN_PASS` из .env (НЕ смешан с клиентским /login по фидбеку);
  кука gr_a = HMAC(pass) — stateless, смена пароля = разлогин; пустой пароль = админка 404.
- **Сайдбар, раздел = экран**: Аналитика (KPI, воронка по уникальным посетителям с конверсиями,
  источники first-touch UTM с выручкой, события; фильтр периода 1/7/30/all) · Заказы (300, статусы
  цветом, источник, ссылка на отчёт) · Клиенты (дети, заказы, оплачено) · Промокоды (создание,
  вкл/выкл, счётчик использований) · **Настройки сайта** (редактор продуктов → пишет
  config/products.json, лендинг подхватывает без рестарта; защита: цены-числа, ≥1 продукт включён;
  статусы подключений Метрика/ЮKassa/Unisender) · Письма (outbox-вьювер: кому/тема/открыть;
  сюда же email-маркетинг после Phase 8). Мобайл: сайдбар → горизонтальные вкладки.
- Проверено: все разделы 200, аноним → пароль, create/toggle купона, roundtrip-сохранение
  products.json без потерь ключей.

### Метрика + dev-чит + кабинет-концепт
- **Яндекс.Метрика подготовлена**: `templates/_metrika.html` на всех страницах (включая лендинг);
  рендерится ТОЛЬКО при YANDEX_METRIKA_ID в .env. clickmap/trackLinks/accurateTrackBounce;
  **webvisor=false намеренно** (на сайт грузят детские рисунки). NB: это осознанный override
  старого «без JS-аналитики» (решение заказчика).
- **Dev-чит входа**: код логина показывается НА странице /login — только для
  DEV_LOGIN_CODE_EMAIL (spashap@gmail.com) И только host localhost/127.0.0.1 (проверено: на
  проде/чужих email не светится).
- **Кабинет — задел под будущее** (по запросу «design concept that will allow it»):
  профиль-блок (email + «изменить email · скоро»), заказы сгруппированы ПО ДЕТЯМ (ось
  Development-продукта), на готовых отчётах спящая кнопка «📈 Сравнить с новыми рисунками ·
  скоро», под группой — тизер: 1 отчёт → «через полгода сможете сравнить», ≥2 → «скоро выбор
  двух отчётов (≥6 мес) для отчёта о развитии». Путь активации: тизер → чекбоксы выбора пары
  (валидация по drawn_at) → форма development с base_order_id.
- **Сид-данные кабинета** spashap@gmail.com (data/tmp/tmp_seed_cabinet.py, идемпотентен,
  маркер-купон SEED): дети Вера/Марк, заказы №9 delivered (реальный отчёт set1, файлы
  скопированы) / №10 insufficient / №11 paid. ⚠️ Запуск воркера реально сгенерирует №11 (и №8).

### Watch list (добавлено)
- **index.html вырос 39→59KB** (инлайн-CSS тянет ВСЕ компоненты, включая админку) — на
  Lighthouse-пассе Phase 9 разделить components.css (база/админка) или собирать critical-CSS.
- templates/admin/dashboard.html и login_stub.html — мёртвые файлы (deny-list на удаление),
  заказчику удалить руками.

### ⏸ ПАУЗА. Чего ждём от заказчика
1. Тест M6+M7 (заказы 8 и 11 ждут воркера). 2. Вычитка 6 статей блога + 6 отзывов-плейсхолдеров.
3. Домен → VPS (Phase 9). 4. ЮKassa + Unisender домен (Phase 8). 5. YANDEX_METRIKA_ID в .env.

---

## 2026-06-13 — 🚀 СОФТ-ЗАПУСК В ПРОД + версионирование + аналитика + Yandex/AI SEO + 8 статей

Большая сессия: заказчик дал домен → развернули прод (Phase 9 РАНЬШЕ Phase 8), затем
версионирование, Я.Метрику с трекингом кликов, админ-аналитику, полный SEO-слой и 8 новых статей.
Сайт ЖИВ: **https://golosrisunka.ru, V1.003**. Оплата всё ещё stub (ЮKassa/Unisender ждём).

### Деплой (Phase 9, сделан вне очереди)
- VPS Fornex (Ubuntu 24.04, root@31.172.67.220) — уже хостит shepotzvezd/astro-api (nginx 1.24,
  certbot, MySQL, Next на :3000, python на :8000). Сначала read-only `scripts/server_recon.sh`
  (инвентаризация), потом план под существующее окружение.
- **WeasyPrint-либы уже стояли** (Pango/Cairo/GDK-Pixbuf — другой сайт юзает). Python 3.12 +
  `python3.12-venv` доставили (UseCase #16: `import venv` ок, но ensurepip отдельным пакетом).
- Код в `/var/www/golosrisunka` (git clone из публичного репо). Запуск как **www-data**, код
  root-owned (веб читает, не пишет); пишет только data/ + static/img/. **gunicorn на unix-сокете**
  `/run/golosrisunka/web.sock` (нет коллизии с :8000/:3000). systemd: `golosrisunka-web` +
  `golosrisunka-worker`. nginx-vhost рядом с чужими (явный server_name, не default).
- **SSL/Cloudflare**: домен на CF orange-proxy. Выбрали **Cloudflare Origin Certificate** (не
  Let's Encrypt — за оранжевым прокси LE-обновление хрупкое), SSL mode Full(strict). Cert/key в
  /etc/ssl/cloudflare/, валидация пары openssl modulus. nginx восстанавливает реальный IP из
  CF-Connecting-IP (диапазоны CF в конфиге).
- Скрипты: `scripts/deploy/{provision,go_live,install_cert,install_samples,update}.sh` (первичная
  установка; install_cert.sh + *.tar.gz — gitignored, содержат ключ/приватные рисунки). Рабочие
  команды в КОРНЕ репо: **`./deploy.sh`** (git pull + deps + restart) и **`./restart.sh`**.
- Сэмплы лендинга чинились отдельно: report.json/html + рисунки gitignored → не приехали клоном →
  пустая лента примеров. Залили тарболом (install_samples.sh) + chown static/img www-data.

### Версионирование (правило в CLAUDE.md)
- Файл `VERSION` (1.001) — единый источник, в футере «V{{version}}». `scripts/bump_version.py`
  (минор +1 / `--major`). **Правило: минор поднимать ПЕРЕД каждым git push.** Грабли: лендинг
  standalone (не наследует _base), футер у него отдельный — версию добавляли в оба места.

### Аналитика (Я.Метрика + first-party)
- `_metrika.html` переписан под боевой сниппет заказчика (**webvisor=ON** — осознанный override
  приватностного «выкл» из-за загрузки рисунков; зафиксировано). ID 109824945 из .env. Гейт:
  `metrika_id and not request.path.startswith('/admin')` — счётчик на всех страницах кроме админки.
- **Трекинг кликов**: делегированный листенер шлёт `data-ym-goal="page_action"` в Я.Метрику
  (reachGoal) И first-party beacon на `/t/e` → лог в events как `click:<goal>`. На КАЖДУЮ кнопку/
  CTA/ссылку проставлен уникальный goal (~42 имени по 12 шаблонам). Правило в CLAUDE.md.
- **events** получил `user_agent/device/referer` (идемпотентная миграция `_migrate` в init_db;
  `track()`/`track_event()` заполняют из request; воркер шлёт NULL). `parse_device()` по UA
  (mobile/tablet/desktop/bot; YaBrowser не путать с ботом).
- Админка: новые вкладки **Визиты** (устройства, UTM-источники, последние посетители с origin) и
  **Действия** (события с количеством + фильтр по имени, лента). `scripts/reset_analytics.py`
  (report по умолчанию, `--events/--orders/--all` + `--confirm`) — чистка пред-запускового мусора;
  на сервере гонять как `sudo -u www-data venv/bin/python ...`.

### SEO (Yandex + AI) — отдельной большой задачей
- **robots.txt**: явные allow-группы YandexBot/Yandex/Googlebot/Google-Extended/Bingbot/GPTBot/
  OAI-SearchBot/ChatGPT-User/ClaudeBot/Claude-SearchBot/anthropic-ai/PerplexityBot + `*`; Disallow
  admin/cabinet/login/logout/order-success/pay/r/t/track; Sitemap-строка.
- **sitemap.xml**: лендинг + блог (lastmod=дата) + сэмпл-страницы /primer (23 URL).
- **/primer/<token>** — НОВАЯ индексируемая страница-пример (sample.html, один H1, Article-schema,
  ссылка на полный отчёт /r/ с rel=nofollow). Приватные отчёты заказов на /r/ остаются закрыты
  (Disallow). Лендинг-карточки примеров теперь ведут на /primer.
- **Глобально в _base**: canonical, robots-блок, OG + Twitter cards, og:image, og:locale ru_RU;
  partial `_seo_jsonld.html` (Organization+WebSite на всех страницах). Лендинг: коммерческий
  title «Анализ детского рисунка по фото — образовательный PDF-отчёт без диагноза», schema
  Org/WebSite/Product(цены из config!)/FAQPage. blog_post: Article. noindex на приватных
  (кабинет/логин/чекаут/успех/стабы/админ-логин).
- **FAQ +3 пункта** (не диагноз / понять рисунок 4–5 лет / интерпретировать дома) — кормят FAQPage.
- **OG-картинка** `static/img/og-default.png` (1200×630, брендовая, `scripts/build_og_image.py`
  на PIL + проектные шрифты).
- Цены в schema — из products.json (2999/4999), НЕ из ТЗ-«990–1890» (закон «без хардкода цен»).

### Контент: 8 новых статей + дудлы
- 8 SEO-статей под высокочастотные запросы (столпы «что узнать по рисунку», «7 признаков», «не
  диагноз»-конверсия; + без психолога, PDF-отчёт, одно и то же, рисунок семьи, развивающие
  задания). Стиль = дом-шаблон (лид → **Коротко:** → ## → мифы/факты → ЧВ → дисклеймер → «Читайте
  также»), строго §7.4. Перелинковка blog→лендинг+/primer, два столпа — хабы.
- **0 запрещённой эзотерики** (Python-скан, не grep — UseCase #19): почистил «тайный смысл/магия/
  судьба/предсказания/эзотерика», в т.ч. в СУЩЕСТВУЮЩЕЙ статье «Энергия темперамента»→«Живость»
  (старый grep это пропустил из-за кириллицы). «расшифровка» в разоблачающем контексте — оставлено.
- **Уникальный инлайн-SVG дудл на каждую из 14 статей** (_blog_thumb.html): лупа/лампочка/«7»/
  3 домика/семья-палочки/карандаши/документ-с-графиком/перечёркнутый медкрест. Проверены визуально
  (рендер монтажа через WeasyPrint, var()→hex — WeasyPrint не резолвит var() в SVG, UseCase #20).

### Git/безопасность
- **.gitignore баг (чуть не утёк ключ!)**: inline `#`-комментарии в .gitignore НЕ комментарии —
  текст становится частью паттерна, файл не игнорился. install_cert.sh (приватный ключ CF) и
  golos_samples.tar.gz попали в stage. Поймал pre-commit safety-grep'ом. Исправил (комменты
  отдельными строками), проверил `git check-ignore` + историю (никогда не коммитились). UseCase #17.
- Три коммита: V1.001 (деплой-тулинг+версия), V1.002 (футер лендинга), **V1.003** (Метрика+
  аналитика+SEO+8 статей+дудлы+yandex-verification). Запушено, задеплоено.

### Cloudflare-гочи на проде (после деплоя)
- Прокси переписывал robots.txt: **«Block AI Scrapers»** допихивал `Content-Signal: ai-train=no` +
  `Disallow: /` для GPTBot/ClaudeBot — поверх наших allow. **Bot Fight Mode** отдавал 403 на /,
  /blog, /sitemap.xml (robots.txt проходил) — заблокировал бы Яндексу чтение sitemap.
- Заказчик выключил оба в CF-дашборде + purge кэша robots.txt. Перепроверено через WebFetch
  (cache-buster): /, /blog, /sitemap.xml → 200; robots.txt чистый (AI-боты Allow, без CF-секции).
  Зафиксировано в памяти + UseCase #18. Истина о том, что видят краулеры — Я.Вебмастер
  «Проверка ответа сервера», не браузер (браузер проходит CF, боты могут нет).

### Следующий шаг
**Phase 8 — ЮKassa + Unisender** (ждём аккаунты заказчика). Всё за абстракциями (payments.py,
mailer.py): подключение = один backend каждый. После — боевой платёж + рассылки, затем гейт M8/M9.
Заказчику: submit sitemap в Я.Вебмастер; по желанию — `seo-audit`/`seo-technical` по живому сайту.

---

## 2026-06-13 (вечер) — Прод TLS: Cloudflare Origin → Let's Encrypt (DNS-only)

**Контекст:** заказчик переключил golosrisunka.ru в Cloudflare на **DNS-only (grey cloud)** ради
доступности из РФ — как у работающего shepotzvezd.ru на этом же сервере. CF Origin-cert после этого
невалиден для прямого трафика (его доверяет только edge Cloudflare).

**Сделано на сервере (root@31.172.67.220):**
- Проверено: DNS обоих имён (apex+www) теперь указывает прямо на 31.172.67.220; firewall 80/443 open;
  certbot 2.9.0 стоит; certbot.timer enabled+active. Бэкап vhost → `/root/golosrisunka.vhost.bak.*`.
- Выпущен **Let's Encrypt** cert через nginx-плагин, ключ **ECDSA**, оба имени (как shepotzvezd):
  `certbot --nginx -d golosrisunka.ru -d www.golosrisunka.ru --key-type ecdsa --redirect`.
- certbot переписал vhost: `ssl_certificate` → `/etc/letsencrypt/live/golosrisunka.ru/{fullchain,privkey}.pem`;
  старые CF-Origin директивы убраны. `nginx -t` ок, reload. Renewal-conf: authenticator/installer=nginx,
  key_type=ecdsa (идентично shepotzvezd) → `certbot renew --dry-run` = success.
- **Проверка снаружи (публичный trust store, без `-k`):** apex и www → HTTP 200,
  `ssl_verify_result: 0`, `openssl ... Verify return code: 0 (ok)`, issuer = Let's Encrypt (CN=YE1),
  SAN покрывает оба имени, http→https 301. Истёк 2026-09-11, продлевается автоматически.
- Старые `/etc/ssl/cloudflare/golosrisunka.{pem,key}` оставлены на месте (не используются, безвредны).

**Репозиторий (синхронизация с реальностью, без bump версии — по команде заказчика):**
- `scripts/deploy/go_live.sh` — переписан под LE: bootstrap HTTP-vhost → `certbot certonly --nginx`
  (ECDSA, идемпотентно) → финальный HTTPS-vhost; убран CF real_ip-блок (DNS-only → IP клиента прямой);
  preflight теперь проверяет certbot + DNS, а не CF-cert.
- `scripts/deploy/setup_letsencrypt.sh` — новый committable скрипт выдачи/починки LE-cert
  (заменяет роль gitignored `install_cert.sh`, который держал приватный CF-ключ).
- `scripts/deploy/provision.sh` — финальные инструкции: DNS-only + certbot вместо CF Origin cert.
- `CLAUDE.md` (Деплой/Состояние/Watch list/кредензалы), `UseCasesData.md` (#21), память обновлены.
- ⚠️ `deploy.sh` nginx/TLS НЕ трогает — обновление этих скриптов в git не меняет живой TLS
  автоматически; смена cert была разовым ручным `certbot`-прогоном (уже сделан, прод уже на LE).

---

## 2026-06-14 — Бот-фильтр в админ-аналитике (V1.004)

**Проблема (заказчик):** в `/admin` аналитике почти всё — боты. Замер на проде: из 138 событий
**84 (61%) боты**, не люди. Главный шумовик — **PingAdmin.Ru** (RU-аптайм-монитор): 51 событие
(37% всего), всё `landing_view`; плюс `l9scan/leakix`, `TLM-Audit-Scanner`, `rust_sniffer`,
`curl`, `Claude-User` (агент-фетчи). Все они летели как `desktop` — `parse_device()` ловил только
UA с `bot/crawler/spider/headless/slurp/monitor`.

**Сделано (UseCase #22):**
- `app/track.py` — `parse_device()` расширен: UA с `+http(s)` → bot; UA без `mozilla` → bot
  (утилиты curl/wget/сканеры); список маркеров (сканеры, http-библиотеки, AI/SEO/соц-боты).
  Яндекс.Браузер остаётся человеком (обычный Mozilla-UA без `+http`); YandexBot → bot.
  Проверено юнит-тестом на реальных UA с прода (15/15, вкл. YaBrowser=desktop, YandexBot=bot).
- `app/admin.py` — общий фильтр `NOT_BOT = "(device IS NULL OR device <> 'bot')"` во ВСЕ
  человеко-запросы (Аналитика/Визиты/Действия: посетители, воронка, источники, лента, устройства).
  `device IS NULL` = серверные события воркера (оплата/доставка) — это не бот, оставляем.
  Каждая страница теперь отдаёт счётчик `bots` → в шаблонах «ботов отфильтровано: N».
- `scripts/reclassify_devices.py` — идемпотентный бэкфилл: пересчёт `device` из `user_agent`
  (пропускает строки без UA, чтобы не трогать NULL воркера; `--dry-run`). Запускать **под www-data**
  (`sudo -u www-data venv/bin/python …`), иначе WAL/SHM получат root-овнершип.
- Задеплоено (V1.004, `./deploy.sh`), бэкфилл применён на проде. Итог: 138 событий → **39 уникальных
  людей** (было ~122), боты (84) отсечены. БД/WAL/SHM остались `www-data`. Health: home 200, admin 302
  (редирект на логин — код не падает), https 200.

**Ограничение:** фильтрация эвристическая — бот с настоящим браузерным UA и резидентным IP
неотличим от человека; но основной мусор убран.

---

## 2026-06-14 — Вовлечённость (engaged sessions) + сброс аналитики (V1.006)

**Запрос заказчика:** в админке видеть только вовлечённых, отсеивать «зашёл, не скроллил, ушёл».
Идею «визит <1с = бот» отклонили: пишем одно серверное `landing_view` на визит → у визита одна
метка времени, длительность всегда 0с и у бота, и у человека (читал 30с и ушёл без кликов).
«Быстрый отказ ≠ бот». Вместо удаления — позитивный сигнал вовлечённости (модель GA4). UseCase #23.

**Сделано (V1.006):**
- `templates/_metrika.html` — один beacon `engaged` при ПЕРВОМ из: скролл/клик/клавиша/тач ИЛИ
  **15с видимого пребывания** (таймер 1с под `visibilityState` — фоновые/предзагруженные вкладки
  не копят время). 15с = порог «отказа» в Метрике (дашборды сходятся). Без голого `mousemove`
  (случайный курсор ≠ намерение; «читателя без скролла» ловит 15с-плечо).
- `app/routes.py` `/t/e` — `engaged=1` → событие `engaged` (рядом с `click:<goal>`).
- `app/admin.py` — Визиты: вовлечённые = DISTINCT visitor_id с `engaged`; отказы = 1−engaged/total;
  колонка «Вовлечён ✓» у посетителя; в воронку добавлен шаг «Вовлёкся». Всё под фильтром `NOT_BOT`.
- `templates/admin/visits.html` — шапка (вовлечённых/отказы) + колонка «Вовлечён».
- Проверено вживую: JS отдаётся на главной (порог 15с виден), POST `engaged=1` → 204, событие
  записалось как `device=desktop` (реальный браузерный UA не помечен ботом), Визиты считают верно.
- **Сброс аналитики (по разрешению заказчика):** `reset_analytics.py --events --confirm` — таблица
  events обнулена (была 137+ строк → 0). Заказы/клиенты не трогали. Старт «с чистого листа».
- Деплой на прод выполнен (V1.006). Заказчик попросил впредь деплоить ТОЛЬКО по явной команде —
  зафиксировано в памяти [[deploy-only-on-explicit-approval]]; разрешение на этот деплой было разовым.

---

## 2026-06-14 — Фавиконки + гео-аналитика + drill-down посетителей (V1.008–V1.010)

**Фавиконки (V1.008–V1.009):** набор из `data/favico` (ico/svg/96px/apple-touch/manifest+PWA)
скопирован в `static/img/favico/`, подключён в `_base.html`, `landing.html`, админ-каркасе;
корневой роут `/favicon.ico` для дефолтных запросов браузеров/ботов. `favicon.svg` оказался
PNG-в-обёртке (1254px, 1.2 МБ) → ужат до 256px = **76 КБ**.

**Аналитика — 3 улучшения по запросу заказчика (V1.010):**
1. **Фильтр вовлечённости.** `/admin/visits` по умолчанию показывает ТОЛЬКО невовлечённых
   (отказы) — `HAVING engaged=0`; тумблер «Не вовлечённые / Все» (`?show=all`). KPI-итоги
   остаются по всему периоду.
2. **Гео — своя офлайн-база, без сторонних API.** `scripts/build_geoip.py` строит `data/geoip.db`
   из **бесплатной DB-IP City Lite** (CC BY 4.0, атрибуция в подвале админки). По требованию
   («страна всем, регион для РФ») храним country для всех + region только для RU, **город
   выкинут**, и сливаем смежные диапазоны с одинаковым (country, region): 8.07M строк / 534 МБ
   CSV → **355K v4 + 348K v6 = 30.7 МБ** (важно: на VPS было всего 3.7 ГБ свободно). `app/geoip.py`
   — быстрый индексный lookup (v4 по int, v6 по 16-байт blob) с lru_cache; нет базы → `None` (гео
   «—», ничего не падает). IP берём из `X-Real-IP`/`X-Forwarded-For` (nginx уже шлёт), **сам IP
   НЕ сохраняем** — только производную метку (миграция `events` +geo_country/region/city; city
   зарезервирован, всегда NULL). Privacy-строка добавлена в `/privacy`.
3. **Drill-down посетителя.** Строка в «Визитах» раскрывается inline (`<details>`, без JS) —
   полная лента событий (время/тип/payload/устройство/гео), первый визит, origin, привязанные
   заказы. Плюс блок «География» (топ стран) рядом с «Устройства»/«Источники».

**Проверено вживую (test_client):** lookup RU→регион (v4+v6 Yandex), US/AU/CA по стране, приват→None;
событие пишет гео без IP-колонки; фильтр default vs ?show=all; drill-down рендерится; graceful
degrade без базы; все админ-страницы + воркерский `track()` (без гео-аргументов) — 200/OK.

**Деплой:** выполнен на прод по разовому явному разрешению заказчика (этот сеанс). На сервере:
git pull (V1.010, заодно подтянулись фавиконки 1.008–1.009), CSV закачан scp →`build_geoip.py`
собрал geoip.db (~30 МБ), `deploy.sh` (рестарт web+worker). geoip.db в `data/` (вне git) —
строится на сервере, обновлять раз в месяц.

---

## 2026-06-15 — MVP-спека: добавки к отчёту + перепозиционирование лендинга

Источник: `projectSpec/golos_risunka_homepage_report_mvp_spec.md`. Двигатель/скоринг/генерация
НЕ тронуты (диф только по шаблонам/CSS/данным).

### Part A — статические блоки в отчёт (PDF)
1. **Плашка «Как читать оценки»** сразу под таблицей «Сводные оценки» (`templates/report.html`,
   класс `.r-callout` в `report.css` — мягкий фон `--alt`, без красного/предупреждений).
2. **Приложение «Как читать оценки в отчёте»** отдельной страницей между «Заключением» и
   футер-дисклеймером (`.r-appendix` с `page-break-before: always`; футер `@bottom-center`
   наследуется автоматически).
   **Проверено:** `rerender_reports.py --pdf` → 4 отчёта; pypdf — страниц стало 7→8, плашка на
   стр.2 под оценками, приложение на отдельной последней странице; шрифты только наши сабсеты
   (Caveat/Inter/Rubik), без Segoe/Verdana; ₽ ок.

### Part B — лендинг (`templates/landing.html` + `components.css`)
Новый порядок: Hero → **Что внутри** → **Mini-logic** → Примеры → **Без мифов** → Как работает →
Отзывы → Доверие → Цены → FAQ → Блог. Первые 4 ценностных блока — до прайса.
- **Hero**: H1 «Поймите, что показывает рисунок ребёнка — спокойно и без диагнозов»; поэтичную
  строку понизили до бренд-акцента; лид/вторичный текст/микрокопия по спеке; чипы доверия;
  визуал — карточка-превью отчёта (`.report-preview`, реальные top_scores из sample) вместо
  только полароидов.
- Новые секции: «Что внутри персонального отчёта» (`.check-list`), «Как строится вывод»
  (`.flow` 3 карточки со стрелками), «Без мифов» (`.compare` две колонки, спокойно, без красного).
- Примеры/Как-работает/Доверие — копи по спеке; заметка про оценки под каруселью примеров.
- **Отзывы (B10):** перетасованы — «чёрной ручкой» первым; явная подпись «Отзывы из закрытого
  тестирования» (НЕ выдаём за отзывы платящих клиентов до подтверждения заказчиком — PENDING).
- **FAQ (B13):** `routes.FAQ_ITEMS` = набор B13 (9) + 2 SEO-якорных вопроса сохранены
  («keep useful existing»); FAQPage JSON-LD синхронен (читает FAQ_ITEMS) — visible=schema=11.

### Цена 2999 ₽ — без фейковой старой цены
`old_price_rub` сделана НЕОБЯЗАТЕЛЬНОЙ end-to-end: убрана из `products.json` (оба продукта),
гард `{% if p.old_price_rub %}` на лендинге/`order.html`/`order_stub.html`, `admin.py` не падает
без неё, `admin/settings.html` показывает пустое поле. На запуске: «Цена на запуске: 2999 ₽».
Фичи продукта приведены к B12 (с «около 8 страниц»).

### Решения заказчика (этот сеанс)
- «6–7 страниц» (спека) недостоверно: реальные отчёты 7–8 стр., с приложением 8–9 → копи
  везде **«около 8 страниц»**.
- «8 направлений» оставили (верно ~9/10; схема допускает 7, `DIMENSIONS_MIN=7`).
- Отзывы: оставить с пометкой «закрытое тестирование» до реальных.

### SEO-флаг (constraint #1)
B15-заголовок дропал ключ «анализ детского рисунка по фото» → **существующие `<title>`/
description/OG НЕ перезаписаны** (они уже несут интент B15). Репозиционирование — в видимом
H1/копи, не в `<title>`.

**Проверено вживую (test_client):** `/` 200, все новые блоки/копи присутствуют, отзыв «чёрной
ручкой» раньше «Сони», FAQ visible=schema=11, фейковой старой цены нет (`<span class="p-old">`
не рендерится, 4900/6900 отсутствуют, 2999 есть), `/order` и `/admin/settings` 200 без утечки
`None`. Диф: 10 файлов, `pipeline/` не тронут.

**НЕ сделано (намеренно):** version bump + пересборка `dist/` + деплой — это ПЕРЕД push по
явному разрешению заказчика (сейчас не пушим). Мобайл — проверяет заказчик на телефоне
(headless-кроп, UseCase #14).

---

## 2026-06-15 — Phase 8 (часть): Unisender Go — транзакционные письма

ЮKassa по-прежнему stub (аккаунт не готов, сайт без оплаты по решению заказчика). Подключён
ТОЛЬКО почтовый цикл (вход по коду, отчёт готов, insufficient, админ-алерты). Заказчик добавил
`UNISENDER_GO_API_KEY` в local.env и server.env; отправитель — **sales@golosrisunka.ru**;
DKIM в Unisender ещё настраивается (~1 ч), поэтому боевая отправка включается позже.

**Сделано:**
- `config/settings.py`: `UNISENDER_GO_API_KEY`, `UNISENDER_GO_API_URL`
  (**регион go2/EU** transactional `email/send.json` — go1 даёт 401 «User not found»;
  переопределяемо), `MAIL_FROM_EMAIL`
  (sales@golosrisunka.ru), `MAIL_FROM_NAME`, `UNISENDER_GO_TIMEOUT`. Старый `UNISENDER_API_KEY`
  помечен legacy.
- `app/mailer.py`: backend `'unisender'` реализован (`_unisender_send` через stdlib `urllib`,
  без новых зависимостей). JSON `{api_key, message{recipients, subject, from_email/name,
  body{html, plaintext}, track_links/read=0, attachments[base64]}}`. Вложения (PDF отчёта)
  base64. plaintext-фолбэк из HTML. **При сбое сети/не-success/failed_emails/пустом ключе —
  падаем в outbox + ERROR в лог, без исключения** (воркер и /login не падают). Интерфейс
  `send_email()` не менялся — `jobs.py`/`auth.py` не трогали.
- `scripts/send_test_email.py` — `--dry-run` (монкей-патч HTTP: собирает payload, api_key
  маскируется, пишет в `data/outbox/_dryrun_payload.json`) и боевая отправка после DKIM.
- Админка «Подключения»: строка почты показывает backend (outbox / Unisender Go + отправитель).

**Проверено (без реальной отправки):** dry-run payload корректен (endpoint go1, from=sales@,
html+plaintext, track=0); PDF-вложение base64 декодируется в валидный `%PDF`; все 3 сбойных
пути (нет сети / failed_emails / пустой ключ) → фолбэк в outbox, исключений нет.

**Активация (заказчик, после DKIM):** в local.env и server.env добавить `MAIL_BACKEND=unisender`,
затем `venv\Scripts\python.exe scripts\send_test_email.py you@example.com` — проверить инбокс.
На сервере после правок — `./restart.sh`. ЮKassa (8.1) — позже, когда будет аккаунт.

**Боевая проверка 15.06 (V1.014):** первый деплой дал 401. Две причины: (1) Unisender Go
аутентифицируется заголовком **`X-API-KEY`** (а не `api_key` в теле, как у старого Unisender);
(2) аккаунт в **регионе go2/EU** (go1 → 401 code 114 «User id … not found»). После правок
тест с дефолтным конфигом — `SENT (status=success)`, письмо доставлено на spashap@gmail.com.
Добавлен разбор тела HTTPError (видно причину 4xx в логе).

**Доставляемость (письмо упало в Gmail «Промоакции»):** главный сигнал — авто-блок «отписаться»,
который Unisender Go добавляет к письму. Убирается `skip_unsubscribe:1`, но аккаунту нужен флаг
`allow_skip_unsubscribe` (код 1588 без него) — включает поддержка Unisender Go. Подготовлено:
`MAIL_SKIP_UNSUBSCRIBE` (env, по умолчанию off) → после включения флага у Unisender ставим
`MAIL_SKIP_UNSUBSCRIBE=1` в .env. Шаблон писем (`_email_base.html`) упрощён до плоского
транзакционного вида (белый фон, без «карточки»/баннеров). Трекинг уже выключен (track=0).

---

> ⏪ **Бэкфилл 18.06.** Записи ниже (16–18.06) восстановлены задним числом из git-истории —
> журнал не пополнялся во время работы над промптом. Восстановлено по коммитам V1.016–V1.019.

## 2026-06-16 — Gmail-доставляемость починена (V1.016)

Письма транзакционки больше **НЕ** падают в «Промоакции» — доходят во «Входящие» Gmail с
уведомлением. Что решило (итог 15–16.06): `MAIL_SKIP_UNSUBSCRIBE=1` (Unisender включил флаг
`allow_skip_unsubscribe` на аккаунте → убрали авто-блок «отписаться» / List-Unsubscribe) +
Unisender выключил принудительный трекинг открытий на аккаунте (пиксель пустой). Аккаунт ОБЩИЙ
с shepotzvezd (`8096698`) — заметка для них `projectSpec/unisender-deliverability-shepotzvezd.md`.
Свой домен ссылок `click.golosrisunka.ru` заведён (NS в Cloudflare).

V1.016 сам по себе мелкий: `scripts/send_test_email.py` теперь шлёт реальную транзакционную
тему (убрали префикс «Test Unisender Go»), чтобы тест-письмо проверяло боевую доставляемость.

## 2026-06-17 — Админка: кнопка «выслать заново» на /admin/orders (V1.017)

Действие resend/regenerate для проблемных заказов. Если PDF отчёта существует (сбой
доставки/письма) — повторно шлём письмо `report_ready` с уже готовым PDF и public_token (БЕЗ
вызова Gemini). Если отчёта нет (сбой генерации) — переводим заказ обратно в `paid`, воркер
перегенерит и доставит.
- `jobs.report_pdf_path()` / `jobs.resend_report_email()`;
- `POST /admin/orders/<id>/resend` (гарды на created/paid/generating);
- кнопка на строках failed/insufficient/delivered + баннер результата.

## 2026-06-18 — V17 «golden-standard» промпт в прод + выравнивание сайта (V1.018)

A/B-победивший голос **V17** промоутнут в боевой отчёт; публичный сайт выровнен под то, что
отчёт реально отдаёт. Только продукт **snapshot** (один + несколько рисунков); продукт
development/progression остаётся вне scope.

**Промпт (`pipeline/prompt.py`, PROMPT_VERSION 3.0):**
- Тёплый/личный голос V17 (баланс 70/20/10 — открытие/практика/доверие), обобщён из
  лабораторного firebird-специфичного промпта; персонализация по каждому рисунку обязательна.
- **Возраст-относительная честная оценка** (нет фикс-планки 7–9): проверено на 3.5/6/8 лет +
  2-рисуночных сэмплах — у малыша оценки 5–7, 8-летка зарабатывает 9, мульти-рисунок
  консолидируется.
- **Зафиксирована таксономия art-7**: Креативность и воображение / Цвет и свет / Композиция и
  пространство / Техника и материалы / Мелкая моторика и детализация / Форма и пропорции /
  Сюжет и взаимодействие. Правила мульти-рисунка сохранены, перетонированы.

**Линтер (`pipeline/lint.py` + `gemini.py` `_REPAIR_INSTRUCTION`):**
- Переведён со старых анти-Барнум банов на рельсы V17 (запрещённые формулировки, командный тон,
  диагнозы/черты/talk о будущих талантах, линеры, символьные преувеличения). Золотой V17-отчёт →
  0 нарушений; плохие строки ловятся.

**Сэмплы + копи:**
- 4 демо-отчёта лендинга перегенерены новым промптом (`data/test_reports`, на VPS через tarball —
  gitignored), `dist/` пересобран для Vercel.
- Хоумпейдж/SEO/products/FAQ-schema/страница примера/письмо «отчёт готов» утеплены; везде
  «8 направлений» → **«7 направлений»**. Доверие-якоря (без диагнозов / по видимой детали /
  наука) сохранены. **Переписывание тела блога отложено в отдельную задачу.**
- Добавлен `scripts/prompt_lab.py` — A/B-харнесс, которым выведен V17.

## 2026-06-18 — Блог-копи под art-7 + допиленные «припаркованные» фичи (V1.019)

**Блог:** описывающая отчёт копи выровнена под V17 — «8 направлений» → «7» в 9 статьях, и
перечисление «Что внутри отчёта» переписано под зафиксированную таксономию art-7. `dist/`
пересобран. (**Более глубокое переписывание тела блога в тёплом тоне всё ещё отложено** —
отдельная задача.)

**Допилены припаркованные фичи:**
- Письмо «Оплата получена» (`app/payments.py` `mark_paid` + `templates/email/payment_received.html`):
  плоское, без вложений, шлётся в момент оплаты (stub + будущая ЮKassa), задаёт ожидание + ссылка
  на вход в кабинет.
- Админская кнопка «перегенерировать» (hard-regenerate) на `/admin/orders` (`app/admin.py` +
  `templates/admin/orders.html`): пере-ставит заказ в очередь на перегенерацию текущим промптом
  по тем же сохранённым изображениям, затем пере-отправляет.
- `.gitignore` теперь игнорит `*.tar.gz` где угодно (бандлы сэмплов); статус Unisender-live
  обновлён в CLAUDE.md.

---

## 2026-06-18 — СЛЕДУЮЩАЯ ЗАДАЧА: редизайн фронтенда (хоумпейдж)

Заказчик показал сайт другу-веб-дизайнеру. Вердикт: **«месиво»** — нет единой концепции, много
шрифтов и стилей, нет бренд-войса. Решение: **редизайн, в первую очередь главной страницы**
(`templates/landing.html`). Остальные страницы — ОК, их не трогаем (если не потребуется ради
единой системы). Работа начинается со следующего сеанса: аудит → концепция → редизайн.

---

## 2026-06-18 — РЕДИЗАЙН САЙТА: бренд-система «Голос рисунка» (НЕ запушено)

Полный редизайн фронтенда выполнен через итерации мокапов (`projectSpec/mockups/`). Заказчик
утвердил: кино-герой (фото на весь экран) + матовая карточка, палитра «Золотой час» (вариант
«светлое стекло»). Концепция выведена из hero-фото.

**Бренд-бук:** `projectSpec/brand-book.md` — единый источник истины для всего визуала сайта
(цвета/шрифты/шкала/компоненты/правила). CLAUDE.md получил ЖЁСТКОЕ правило: любой UI — только
по бренд-буку, через токены/компоненты, без хардкода.

**Один глобальный CSS** (минимальная правка меняет весь сайт, без отдельных контролов):
- `static/css/tokens.css` — переписан: палитра «Золотой час» (бумага `#FBF1DD`, эспрессо-текст
  `#3A2A1C`, джинсовый `#3E4E78` = действие, янтарь `#B9722A` = голос, шалфей, `--line`, `--bg-soft`),
  7-ступенчатая шкала шрифта (`--fs-*`), радиусы, мягкие тени. Темы `cl`/`dk` обновлены (старые
  `pu`/«Синий» убраны).
- `static/css/components.css` — ретюн всех атомов под бренд: кнопки джинсовые с мягким подъёмом
  (жёсткие чёрные тени убраны), Caveat ужат ДО «голос»+лого (полароид-капшен/метки/цитаты/номера/
  имена → Rubik/Inter), score-bar заливка джинсовая, step__n — число в круге, FAQ +/–, футер тёплый
  тёмный на всю ширину. Добавлены компоненты: кино-`.hero`+`.hero__card`, попап `.cta-zone/.cta-pop`
  «что входит» (тултип, не меняет размер карточки; клик-тоггл для мобайла), `.reveal` (появление
  при скролле, уважает reduce-motion), `.car-dots` (точки-индикатор каруселей). Старый
  двухколоночный hero-визуал удалён.

**Контент:**
- `templates/landing.html` — переписан под кино-герой + единый ритм секций; все секции на
  существующих компонентах; reveal-классы; JS: попап, точки каруселей, ротатор отзывов, IO-reveal.
  Все `data-ym-goal` сохранены, SEO-голова не тронута.
- `templates/_base.html` — футер на всю ширину (`.foot` + внутренний `.wrap` + бренд Caveat) →
  перекрашивает кабинет/заказ/блог/legal/ошибки автоматически.
- Кабинет/заказ/вход: правок функционала НЕ было — перекрашиваются через токены+компоненты.
  Убраны 2 хардкод-цвета (login dev-нотис, order error-рамка) → токены.

**Картинки/скорость:** `static/img/hero.{jpg,webp}` + `hero-800.*` (оптимизировано из
`data/Images/Hero.png`: jpg ~186 КБ / webp ~121 КБ); в CSS `image-set(webp,jpg)` по абсолютному
`/static`-пути (CSS лендинга инлайнится); hero preload `as=image fetchpriority=high`; контентные
img — lazy.

**Проверено:** jinja-компиляция `landing.html` — OK; `tokens.css`/`components.css` структурно
целы (Read-инспекция; брейсы сбалансированы); шаблоны кабинет/заказ/вход — `{% endblock %}` на
месте (Grep). ⚠️ Sandbox-маунт периодически отдавал устаревшие копии файлов — верифицировал
авторитетными Read/Grep, не bash. **НЕ запускал dev-сервер (Windows-сторона у заказчика).**

**НЕ сделано намеренно:** version bump + пересборка `dist/` + push — по правилу делаются ПЕРЕД
git push; заказчик просил не пушить. Мобайл и финальный вид проверяет заказчик (открыть сайт
локально `venv\Scripts\python.exe run.py` :5000). Мокапы-итерации лежат в `projectSpec/mockups/`.

## 22.06.2026 — PHASE 8 (оплата): ЮKassa встроенный платёж (модалка) вместо stub

**Что:** заменили stub-оплату на боевую ЮKassa (YooKassa API v3, `confirmation=embedded` — виджет
в модалке на нашей странице, без редиректа). Портировано с проверенной реализации соседнего проекта
`C:\projects\shepotZvezd` (тот же владелец/стиль), но адаптировано под Flask + одиночный заказ
(у нас НЕТ батчей/`group_id`; цена уже лежит в `orders.price_kopecks` со скидкой купона). Заказчик
положил боевые ключи в `.env` (`YUKASSA_MODE=live`, `YUKASSA_SHOP_ID_LIVE`, `YUKASSA_SECRET_KEY_LIVE`).

**Ключевое преимущество:** идемпотентная точка подтверждения `mark_paid(order_id)` в `app/payments.py`
уже была (создаёт customer/child, сессия 30 дней, `status='paid'`, инкремент купона, письмо «оплата
получена»). Воркер уже забирает `status='paid'`. Поэтому ЮKassa встала **перед** `mark_paid`, сам
`mark_paid` НЕ менялся.

**Файлы:**
- `config/settings.py` — слоты `YOOKASSA_*` (одиночные) заменены на режимный сплит test/live:
  `YUKASSA_MODE` + `YUKASSA_SHOP_ID_{TEST,LIVE}`/`YUKASSA_SECRET_KEY_{TEST,LIVE}`, `YUKASSA_API_URL`,
  хелпер `yukassa_enabled()` (оба ключа заданы → True).
- `app/yookassa.py` (НОВЫЙ) — клиент API v3 на stdlib `urllib` (в проекте нет `requests`; mailer.py
  уже так ходит). `create_payment(...)` → embedded + `Idempotence-Key` + Basic-Auth + `metadata={order_id}`
  + точная сумма из копеек (см. UseCase #26) + чек 54-ФЗ в live (`vat_code=1`, `service`, `full_payment`,
  как в shepotZvezd). `get_payment(id)` для проверки. Короткий ретрай на 429/5xx/таймаут.
- `app/payments.py` — `create_payment()` теперь ведёт на `main.checkout` (страница виджета). `mark_paid` без изменений.
- `app/routes.py` — удалены `/pay/stub/*`; добавлены: `GET /pay/<id>` (страница оплаты; если уже
  оплачен → редирект на success), `POST /pay/yookassa/create/<id>` (создаёт платёж → `confirmation_token`;
  переиспользует ещё «висящий» pending-платёж), `POST /pay/yookassa/webhook` (перезапрос платежа через
  API = подлинность; `mark_paid` ТОЛЬКО при `succeeded` И точном совпадении суммы; `canceled`/прочее —
  no-op, заказ остаётся `created` → ложных оплат нет; всегда 200), `GET /pay/yookassa/status/<id>`
  (поллинг с фронта; если webhook опоздал — проводит оплату здесь же + ставит сессионную куку).
  Общий хелпер `_settle_payment(payment_id)` для webhook и поллинга.
- `templates/checkout.html` (НОВЫЙ) + `templates/checkout_stub.html` (УДАЛЁН) — сводка заказа + кнопка
  «Оплатить» (`data-ym-goal="checkout_pay"`) открывает модалку с виджетом; чистый JS:
  загрузка `checkout-widget.js` → create → render → поллинг status каждые 2с (≤90 попыток) →
  редирект на success. Акцент виджета берётся из CSS-токена `--accent` (без хардкод-hex).
- `static/css/components.css` — добавлен переиспользуемый компонент `.modal/.modal__card/.modal__close`
  (цвета/размеры из токенов — по закону дизайн-системы, а не инлайн-стиль на странице).
- `scripts/deploy/provision.sh` — комментарий-шаблон `.env` обновлён на `YUKASSA_*`.

**Проверено локально (Windows, venv):** `create_app()` импортируется чисто; 4 роута `/pay/*`
зарегистрированы; `checkout.html` рендерится в enabled И disabled состояниях; `yukassa_enabled()=True`;
формат суммы из копеек верный (239920 → `2399.20`, 299900 → `2999.00`).

**НЕ сделано (ждём заказчика):** (1) регистрация webhook-URL `https://golosrisunka.ru/pay/yookassa/webhook`
в кабинете ЮKassa (события `payment.succeeded` + `payment.canceled`); (2) для локального теста —
`YUKASSA_SHOP_ID_TEST`/`_TEST` + `YUKASSA_MODE=test` (виджету нужен реальный домен/HTTPS; в live
создаются НАСТОЯЩИЕ платежи); (3) version bump + commit + deploy — ТОЛЬКО по явной команде заказчика
(правило: не пушить/деплоить автоматически). После деплоя — боевой M8/M9-гейт.


## Состояние на 23.06.2026 — РАЗВОРОТ ПАЙПЛАЙНА ОТЧЁТА К ФИЛОСОФИИ «2.3» (Задача 1, локально, НЕ задеплоено)
- **Причина:** старый отчёт (PROMPT_VERSION 3.0 «голос V17») провалился на реальных мамах ЦА — описывал
  ТОЛЬКО навыки рисования, ничего о ребёнке как личности («99% не хотят растить художника»). Разворот:
  продукт = ПОРТРЕТ РЕБЁНКА через рисунок; навыки → поддержка. План:
  `projectSpec/pipe-change/task1-pipeline-pivot-2.3.md`. ЗАДАЧА 1 трогает ТОЛЬКО пайплайн отчёта;
  лендинг/FAQ/мета/примеры — Задача 2 (после регенерации отчёта Лизы и утверждения заказчиком).
- **PROMPT_VERSION → 4.0** (`pipeline/prompt.py`): новая рамка (ребёнок как личность), зона-3 интерпретация
  разрешена ТОЛЬКО в 4-условной оправе (атрибуция к традиции/автору + гипотезный оборот + видимая деталь +
  возврат к ребёнку); новый блок `about_child` (нарративный портрет, сердце отчёта); 7 новых направлений
  (4 личностных ведут: world_and_themes/character_in_line_color/mood_and_expression/story_and_characters +
  3 навыковых поддерживают: creativity/technique_and_materials/fine_motor); раздельные рекомендации
  (understanding_recommendations / art_recommendations); specialists как ресурс «если захотите глубже»;
  механика «тумана» (1 рисунок честно оставляет открытый вопрос).
- **Линтер переписан с «бан слов» на «проверку оправы»** (`pipeline/lint.py`) — КРИТИЧНО: старый молча
  удалял бы всю новую глубину. Два класса: HARD_BANNED (голый диагноз-факт, командный тон, катастрофизация,
  предсказание-таланта, бренд-баны — всегда) + REQUIRES_FRAME (сенситивные термины НЕ баним: тяжёлые
  тревож/депресс/страх требуют гипотезы+атрибуции в окне; лёгкие характер/настроение/темперамент — гипотезы,
  либо артефакт-существительное сразу после термина = речь о работе, не о ребёнке). Репэйр-инструкция в
  `pipeline/gemini.py` переписана: «ДОБАВЬ оправу / смягчи, НЕ удаляй смысл».
- **Схема** (`pipeline/schema.py`): +about_child (обяз.), recommendations→understanding_/art_, +Specialist
  модель + specialists (опц.). Счётчик dimensions 7–8 не менялся.
- **Шаблон/CSS** (`templates/report.html`, `static/css/report.css`): секция-портрет «Что мы увидели о самом
  ребёнке» после введения; два блока рекомендаций; блок «Куда можно пойти глубже» (специалисты); админ-блоки
  в конце (апсейл/дисклеймер/свободный текст); приложение «Как читать отчёт» и дисклеймеры смягчены под 2.3
  (сохранён честный «не мед./псих. диагностика» + «серьёзно тревожит → к специалисту»). Новые классы
  r-portrait/r-specialists/r-upsell/r-admin-note.
- **Админ-тексты в конце отчёта (pass-through, без логики):** `config/report_texts.json` + `get_report_texts()`
  (mtime-кэш, как get_products) + раздел `/admin/report-texts` (`templates/admin/report_texts.html`).
  `app/jobs.py` выбирает апсейл-слот по числу рисунков (min(len(rows),3)), прокидывает upsell/дисклеймер/
  free-text в `render_report_files` (`pipeline/render.py` — новые опц. параметры, дефолты пустые).
- **Сэмпл** `pipeline/samples/sample_report.json` переписан под новый контракт (Лиза, дерево; зона-3 в оправе).
- **Локальная проверка (PASS):** схема валидна (7 направлений); линтер юнит-кейсы (framed→0, голый диагноз→hit,
  сенситив-без-оправы→hit, heavy без атрибуции→hit, командный тон→hit, «характер линии»→0); render_sample
  HTML+PDF ок; embedded-fonts PDF — только свои сабсеты (Caveat/Inter/Rubik), без Segoe/Verdana (UseCase #2);
  create_app + admin-роуты + jobs импортируются. Скрипт проверки: `data/tmp/verify_pivot.py`.
- **Линтер — тонкое место (тюнить на Лизе):** уже отловлены 2 ложных среза при разработке — «тревож» внутри
  «вс-тревож-ит» (тревога РОДИТЕЛЯ) → добавлен ; и слишком широкое окно WORK_REF (любой «рисунок» рядом
  оправдывал «характер Лизы») → сужено до lookahead 40 символов после термина.
- **НЕ задеплоено и НЕ запушено.** Следующий шаг (по плану §10): заказчик жмёт «перегенерировать» отчёт Лизы
  в админке (нужен запущенный worker), разбираем «душу»/оправу/линтер/админ-тексты, фиксируем — потом Задача 2.
- **ВНИМАНИЕ — обратная совместимость:** about_child и раздельные рекомендации теперь обязательны → старые
  сохранённые report.json БЕЗ этих полей не перерендерятся `scripts/rerender_reports.py`. Это ОК: Лиза
  регенерируется заново через админ-кнопку (полный прогон), а не перерендером.
