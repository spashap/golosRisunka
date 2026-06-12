# Голос рисунка — Development Plan (MVP)

**Created: 2026-06-11 · Launch deadline: 2026-06-25**
Companion to `golosrisunka-tech-spec.md`. Tasks are small and ordered; every phase ends with a **🧪 Milestone** you can test yourself on localhost. Nothing in a later phase starts until the milestone of the previous phase passes (exceptions noted).

Locked decisions reflected here: Gemini 2.5 Pro · report pipeline built first as standalone CLI · ЮKassa stubbed until account question is resolved · Unisender wired late (domain not added yet) · git set up at deploy time · optional `development_directions` JSON field · site fully in Russian · design source = `golosrisunka-hybrid-2.html`, palette «Синий», self-hosted fonts.

---

## Phase 0 — Project skeleton (~half a day)

- [ ] 0.1 Create project layout: `app/` (web app, empty for now), `pipeline/` (report generation), `templates/`, `static/` (`css/`, `fonts/`, `img/`), `config/`, `data/` (`drawings/`, `reports/` — gitignored later), `scripts/`, `content/blog/` (empty, reserved)
- [ ] 0.2 Python venv + `requirements.txt`: flask, jinja2, weasyprint, google-genai, pillow, pillow-heif, python-dotenv, pydantic (JSON validation)
- [ ] 0.3 Verify WeasyPrint installs and renders on **Windows** (it needs GTK/Pango — known friction point; resolve now, not later). Fallback decision if painful: render PDFs inside WSL during local dev (prod is Linux anyway)
- [ ] 0.4 `config/settings.py`: reads `.env` (GEMINI_API_KEY already present), holds prices, product codes, ADMIN_ALERT_EMAIL placeholder
- [ ] 0.5 Download Rubik, Inter, Caveat as woff2 → `static/fonts/` + `@font-face` CSS (self-hosted per spec §3.3)

**🧪 Milestone M0 — you test:** run `python scripts/hello_pdf.py` → opens a one-page PDF with Cyrillic text in all three fonts (Rubik bold heading, Inter body, Caveat handwritten note). If Cyrillic and fonts look right in the PDF, the riskiest technical unknown is retired.

---

## Phase 1 — Design system (1 day)

- [ ] 1.1 `static/css/tokens.css`: CSS variables from `golosrisunka-hybrid-2.html` — «Синий» default, Фиолет/Тёмный/Облака as commented palettes switchable by one class on `<html>`
- [ ] 1.2 `static/css/components.css`: `btn`/`btn--primary`, `card`, `polaroid` (+tilt modifiers, tape ::before, Caveat caption), `badge`, `score-bar`, `section`/`section--alt`, `carousel` (scroll-snap), `quote`, `step` — extracted and generalized from the mockups, no page-specific styles
- [ ] 1.3 `templates/_base.html` (Jinja2 layout: fonts preload, tokens+components, footer disclaimer block)
- [ ] 1.4 Component gallery page `templates/dev/components.html` — every component rendered once with dummy data (dev-only route or static file)

**🧪 Milestone M1 — you test:** open the component gallery in a browser. Check it matches the mockup look (polaroids with tape and tilt, badges, score bars, buttons with hard shadow). Switch palette by editing one class — whole page recolors. This gallery stays alive for the whole project as the design reference.

---

## Phase 2 — Report HTML/PDF template with fake data (1 day)

*Built BEFORE the prompt so prompt iteration (Phase 3) produces a finished-looking PDF from day one.*

- [ ] 2.1 Hand-write `sample_report.json` matching spec §7.3 schema + optional `development_directions` field (content adapted from `reportSamples/child.pdf`, cleaned of banned claims)
- [ ] 2.2 `templates/report.html`: cover (logo, name, age, date) → context → introduction → summary score-bar block (8 bars) → per-dimension sections (observation, research note, activities) → development directions (optional) → recommendations → conclusion → disclaimer. WeasyPrint-friendly markup (floats/blocks, `page-break` rules, no complex flex/grid)
- [ ] 2.3 `pipeline/render.py`: JSON → HTML (saved) → PDF (saved). Pure function, no Gemini yet
- [ ] 2.4 Pydantic models for the §7.3 contract: structure, score range 1–10, dimension count, `insufficient_input` handling

**🧪 Milestone M2 — you test:** run `python scripts/render_sample.py` → get `sample_report.html` (browser) and `sample_report.pdf`. Judge: does this look like something worth 990 ₽? Page breaks sane, Cyrillic clean, score bars correct widths. Your visual feedback here is cheap to apply; later it isn't.

---

## Phase 3 — System prompt + Gemini pipeline (2–3 days; the core)

**⛔ Needs from you before/while this phase runs: 3–5 real drawing photos (~ages 5/7/10) + short context for each (age, materials, what was asked). Place in `projectSpec/testDrawings/`.**

- [ ] 3.1 Write Russian system prompt v1 (`pipeline/prompt.py` or `.txt`): structure/tone from old `promptSample.txt`, philosophy inverted per spec §7.4 — no Barnum, no emotion/state-reading, every observation tied to a visible detail, strict JSON output, `insufficient_input` rule, honest strengths AND growth areas
- [ ] 3.2 `pipeline/gemini.py`: Gemini 2.5 Pro call — images + per-drawing context + prompt → JSON; response parsed and validated by the Phase 2 Pydantic models
- [ ] 3.3 Retry loop: up to 5 attempts, invalid JSON = failed attempt, pauses between; on exhaustion raise a typed error (worker will turn this into alerts later)
- [ ] 3.4 Image prep: jpg/png/heic → RGB jpg, long side ~2000px (Pillow)
- [ ] 3.5 `scripts/generate_report.py <image(s)> <context.json> [-o outdir]` — end-to-end CLI: images → Gemini → validated JSON (saved raw) → HTML → PDF. *This script later becomes the worker's core and `regenerate_report.py`.*
- [ ] 3.6 Prompt iteration rounds on your real drawings (expect 3–6 rounds). Each round: generate all test reports → review together → adjust prompt. Also test failure inputs: blank page photo, blurry photo, non-drawing photo → must yield `insufficient_input=true`, not an invented report
- [ ] 3.7 Multi-drawing orders: 1–3 drawings in one report — verify the prompt handles 2 and 3 drawings sensibly

**🧪 Milestone M3 — you test (the big one):** for each of your real drawings, run one command and read the finished PDF. Acceptance: observations reference details actually visible in the drawing; no emotion/psychology claims; scores feel explained, not flattering by default; «Как развивать» activities are concrete; garbage input refuses politely. **You sign off on report quality here — this gates everything else.** Side product: the best outputs become the landing-page sample reports (spec §4.1.3).

---

## Phase 3R — Multi-drawing consolidated report (INSERTED 11.06 after product-model correction)

*Product model corrected by заказчик: ONE product «snapshot» = up to 3 drawings → ONE consolidated report (price independent of count). Prompt v1.x was single-drawing-centric; consolidation needs explicit design.*

- [ ] 3R.1 Context restructure: per-drawing story data (image ↔ story pairing), common child block (name/gender/age) once. CLI accepts one context per image
- [ ] 3R.2 Prompt v2.0: consolidation rules — drawings are one child/one period; single unified report; observations cite drawing numbers («на рисунке 2…»); repeated evidence across drawings > single appearance; contradictions named honestly; scores reflect the aggregate picture
- [ ] 3R.3 Regression: 1-image reports must stay as good as M3
- [ ] 3R.4 Multi-image tests on synthetic set (8yr + crop) — mechanics + cross-referencing
- [ ] 3R.5 **⛔ USER INPUT: 2–3 real drawings of the SAME child (same period) + story per drawing** — the only honest test of consolidation quality
  - Naming: `set1-img1.png/.txt`, `set1-img2.png/.txt`, `set1-common.txt` (child data + birth month/year); each story includes month/year the drawing was made
  - The user's 1-year-old drawing of the same child = reserved Development-report test material (`devtest-*`), NOT for the snapshot test

**🧪 Milestone M3R — you test:** read the consolidated PDF from a real multi-drawing set: does it feel like ONE report about one child (not three glued summaries)? do observations reference specific drawings? does the score feel justified across works?

---

## Phase 4 — Web app skeleton + landing page (2 days)

- [ ] 4.1 Flask app: routes, error pages, static serving, `_base.html` wiring
- [ ] 4.2 Landing page per spec §4.1: nav, hero (headline + 3 polaroids + badges), sample-report carousel (linking to hosted HTML reports from M3), «Как это работает», testimonials (placeholder texts until заказчик provides), guarantee/trust block, FAQ (details/summary), final CTA + footer
- [ ] 4.3 Hosted report route `/r/{public_token}` serving the HTML reports (long random token)
- [ ] 4.4 SEO base: titles/descriptions, OpenGraph, Schema.org Product + FAQPage, `robots.txt`, `sitemap.xml` generator, ЧПУ urls
- [ ] 4.5 Performance pass: critical CSS inline, WebP images with width/height, lazy below fold, font preload, first screen < 200KB

**🧪 Milestone M4 — you test:** open `http://localhost:5000` — full landing in Russian, palette «Синий», sample reports clickable through to full HTML reports. Check on your phone (same wifi) for mobile layout. Run Lighthouse in Chrome DevTools: mobile ≥ 90 target already at this stage.

---

## Phase 5 — Order flow: form, upload, DB, payment-stub (2 days)

- [ ] 5.1 SQLite schema per spec §5 (customers, children, orders, drawings, reports, sessions, login_codes, coupons) + tiny migration/init script.
  **Upsell/Development groundwork (decided 12.06):** `drawings.drawn_at` (YYYY-MM, required), `children.birth_ym` (birth month/year — collected once, age per drawing computed), `orders.base_order_id` (nullable FK — Development order references the prior order whose stored report_json + drawings it builds on)
- [ ] 5.2 Context-form **config** (spec §5 flexibility rule): field list as Python/JSON config (key, label, type, required); form render + server validation generated from it
- [ ] 5.3 Order form page: product = snapshot (price from config/products.json) → email + child block (имя, пол, **дата рождения месяц/год** — вместо возраста) + per-drawing upload & story incl. **«когда нарисован» (месяц/год, required)**. Vanilla JS only for file picking/preview
- [ ] 5.4 Upload handling: client+server validation, 15MB limit, heic conversion, files → `/data/drawings/{order_id}/`
- [ ] 5.5 Payment abstraction with **stub provider**: "pay" button → fake checkout page → simulated webhook → order `created → paid`. Real ЮKassa drops into the same interface later (§ Phase 8)
- [ ] 5.6 Success page: «Отчёт придёт на почту в течение часа» + cabinet link; session cookie issued on payment (30 days)
- [ ] 5.7 **Analytics groundwork (decided 12.06, для будущей админки):** `events` table, anonymous visitor cookie, first-touch UTM capture (on visitor + on order), server-side `track()` at funnel steps: landing_view → sample_view → order_form_view → order_created → checkout_view → order_paid → report_delivered. No JS analytics libs.

**🧪 Milestone M5 — you test:** full purchase walk-through on localhost: pick product → fill form → upload your real photos (try a HEIC from an iPhone) → fake-pay → success page. Check `data/drawings/` and the DB rows. Try breaking it: oversized file, wrong type, missing required field.

---

## Phase 6 — Background worker + delivery statuses (1 day)

- [ ] 6.1 Worker (separate process / cron-style loop): polls `orders WHERE status='paid'` → runs the Phase 3 pipeline → `generating → delivered` (or `failed` after 5 attempts)
- [ ] 6.2 Failure path: `failed` status + admin alert (logged to console/file until Unisender is live), client-side shows «в обработке»
- [ ] 6.3 `scripts/regenerate_report.py <order_id>` — manual rerun CLI (reuses pipeline)
- [ ] 6.4 `insufficient_input` path: order flagged, alert logged, client email queued (template)

**🧪 Milestone M6 — you test:** place a stub order → watch worker pick it up → report appears in `data/reports/` and is reachable at `/r/{token}`. Then sabotage one (e.g. temporarily wrong API key) → status `failed`, alert logged, `regenerate_report.py` fixes it after restoring the key.

---

## Phase 7 — Auth + personal cabinet (1–1.5 days)

- [ ] 7.1 Login: email → 6-digit code (30 min TTL, single-use) → session 30 days, httpOnly cookie. Code delivery = console/log until Unisender is live
- [ ] 7.2 Rate limits: max 1 code request per email per 10 min («код уже отправлен»); N wrong attempts → code void
- [ ] 7.3 Cabinet page: orders list (date, product, status «в обработке»/«готов»), per ready order: drawing thumbnails, HTML report link, PDF download, logout. Nothing else
- [ ] 7.4 Auto-account + auto-session on purchase (already wired in 5.6 — verify end-to-end)

**🧪 Milestone M7 — you test:** buy with the stub on one browser → land in cabinet automatically. Open a *different* browser (= other device) → login by emailed code (read code from console) → same cabinet. Try: reusing a code, requesting twice in 10 min, 5 wrong codes.

---

## Phase 8 — Real integrations: ЮKassa + Unisender (1.5–2 days)

**⛔ Needs from you: (a) decision/credentials for ЮKassa (existing account usable for new site, or new shop); (b) golosrisunka.ru domain added & verified in Unisender.**

- [ ] 8.1 ЮKassa provider behind the Phase 5 abstraction: create payment → hosted checkout redirect → webhook (idempotent on `yookassa_payment_id`, signature/IP verification) → `paid`
- [ ] 8.2 Unisender transactional emails (Jinja2 → simple HTML, disclaimer + support contact in all): payment confirmation, report delivery (PDF attached + HTML link, **batched** if several reports finish in one window), login code, admin alert, insufficient-input request
- [ ] 8.3 Switch worker/auth alert+code delivery from console to Unisender

**🧪 Milestone M8 — you test:** test-mode ЮKassa payment from the real form → real confirmation email → report email with PDF attached → login code email on second device. (Can run on localhost via a tunnel for the webhook, or be folded into Phase 9 on the VPS.)

---

## Phase 9 — Legal, polish, deploy (1.5 days)

- [ ] 9.1 Legal pages: политика конфиденциальности, оферта, контакты (your placeholder texts); disclaimer present on landing + report + all emails — sweep check
- [ ] 9.2 git init (decisions: `.env`, `data/`, venv gitignored) + push to your private server remote
- [ ] 9.3 VPS deploy: nginx + systemd (app + worker), https (Let's Encrypt), domain golosrisunka.ru
- [ ] 9.4 Daily backup cron: SQLite dump + `data/` copy off-server
- [ ] 9.5 PageSpeed final pass on prod: mobile ≥ 90, desktop ≥ 95; sitemap/robots/schema validation
- [ ] 9.6 Full launch checklist from spec §13, item by item

**🧪 Milestone M9 — LAUNCH GATE, you test on production:** real (боевая) ЮKassa payment end-to-end: landing → pay → report by email within the hour → cabinet login from your phone by code. Plus the failed-order drill on prod (alert arrives, CLI rerun works).

---

## Phase 10 — Only if time remains before 25.06 (spec §11 order)

1. [ ] Blog: markdown files in `content/blog/` → `/blog`, `/blog/{slug}`, Article schema, sitemap (~half day)
2. [ ] Coupons + minimal admin (env-password login, coupon CRUD, orders list, regenerate button)
3. [ ] Development Report — explicitly post-launch unless everything above is done early.
   Design (decided 12.06): **builds on the client's EXISTING stored report** — input = prior order's report_json + prior drawings + new 1–3 drawing set; new prompt variant («тогда/сейчас», динамика по 8 направлениям); `orders.base_order_id` links the orders. Test material already reserved: user's `devtest-*` drawing (1 year older than set1).

4. [ ] **Upsell reminders (post-MVP, спроектировано 12.06):** cron job scans children whose latest `drawings.drawn_at` ≥ 5–6 months ago → email «добавьте свежий рисунок — увидите, как развился ребёнок» → Development report flow with base_order_id. Needs: drawn_at/birth_ym fields (Phase 5 ✓ planned), email-consent line in privacy policy (Phase 9), Unisender template. No architecture change — pure addition.

---

## Calendar fit (deadline 25.06, today 11.06)

| Dates | Phases |
|---|---|
| 11–12.06 | 0 + 1 (skeleton, fonts, WeasyPrint check, design system) |
| 12–13.06 | 2 (report template, fake data) |
| 13–16.06 | 3 (prompt + Gemini — **needs your drawings by ~12–13.06**) |
| 16–18.06 | 4 (landing) |
| 18–20.06 | 5 (order flow, stub payment) |
| 20–21.06 | 6 (worker) |
| 21–22.06 | 7 (auth + cabinet) |
| 22–23.06 | 8 (ЮKassa + Unisender — **needs your accounts ready by ~20.06**) |
| 23–24.06 | 9 (legal, deploy, launch gate) |
| 24–25.06 | Buffer / Phase 10 |

## Your inputs — deadlines

| What | Needed by | Blocks |
|---|---|---|
| 3–5 real drawing photos + context | ~13.06 | Phase 3 (core) |
| Testimonial texts (закрытое тестирование) | ~17.06 | Landing block 5 (placeholder until then) |
| ЮKassa: reuse account or new shop + credentials | ~20.06 | Phase 8 |
| Unisender: add golosrisunka.ru domain | ~20.06 | Phase 8 |
| Legal texts (политика, оферта, контакты) | ~22.06 | Phase 9 |
| VPS access + domain DNS | ~22.06 | Phase 9 |
