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

### Баги из projectSpec/errors/ (скриншоты заказчика 11.06)
1. **Шрифты не грузились в браузере** (всё serif): instancer оставлял STAT-таблицу при удалённом fvar → Chrome OTS тихо отвергал woff2. WeasyPrint не санитайзит — поэтому PDF были ок и мы не заметили. Фикс: build_fonts.py дропает STAT/avar/gvar/…; проверка headless-Chrome скриншотом. **UseCase #10.** Правило: проверки шрифтов — и PDF, и браузер.
2. **Цитаты карточек обрывались на инициалах** («В рисунке Никиты Н.»): наивный split по '. '. Фикс: `_first_sentence()` — конец предложения только после строчной буквы. **UseCase #11.**
- Отступ CTA↔заметка в hero был починен ранее (22px) — скриншот заказчика был до фикса.
