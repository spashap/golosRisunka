# Use Cases — problems met & solved

Knowledge base: problem → cause → solution. Searchable reference, one entry per case.
Chronological build log lives in `DevelopmentStatus.md`.

---

## #1 · google-webfonts-helper API returns 403 to Python urllib
**Problem:** `urllib.request.urlopen("https://gwfh.mranftl.com/api/fonts/…")` → HTTP 403, while the same URL works in curl/browser.
**Cause:** the API blocks Python's default `User-Agent: Python-urllib/3.x`.
**Solution:** send a browser-like UA header: `urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 …"})`. Applies to fonts.gstatic.com downloads too.

## #2 · Subsetted Google fonts are missing the ₽ ruble sign (U+20BD)
**Problem:** PDF render embedded a stray Verdana fallback; bisection showed ₽ was the missing glyph. NONE of the gwfh `cyrillic_latin` files (Rubik/Inter/Caveat) contain U+20BD — Google's standard latin/cyrillic subset ranges exclude it.
**Cause:** ₽ lives in Currency Symbols block (U+20A0–20BF), which standard subsets strip.
**Solution:** build our own subsets — `scripts/build_fonts.py`: download variable TTFs from raw.githubusercontent.com/google/fonts, pin weights with `fontTools.varLib.instancer`, subset with `fontTools.subset` using explicit unicodes `U+0000-00FF,U+0131,U+0400-04FF,U+2010-205F,U+20A0-20BF,U+2116,U+2122`, save as woff2 (needs `pip install brotli`) + ttf.
**Detection recipe (reusable):** render PDF → list `/BaseFont` per page via pypdf → any non-project font = some glyph fell back; bisect by rendering suspect strings per family.

## #3 · Windows console (cp1252) crashes Python printing Cyrillic/₽
**Problem:** `print('… ₽')` or printing extracted PDF text → `UnicodeEncodeError: 'charmap' codec can't encode character`.
**Cause:** stdout on this Windows box defaults to cp1252.
**Solution:** either (a) keep script console output ASCII-only (chosen for project scripts), or (b) run with `PYTHONIOENCODING=utf-8 python …`, or (c) write output to a UTF-8 file instead of stdout (used for PDF text extraction).

## #4 · WeasyPrint on Windows: GLib-GIO-WARNING spam
**Problem:** every WeasyPrint run prints `GLib-GIO-WARNING **: Unexpectedly, UWP app … supports N extensions but has no verbs`.
**Cause:** GTK's GIO enumerating Windows UWP app registrations; cosmetic, unrelated to rendering.
**Solution:** ignore (filter with `grep -v GLib-GIO-WARNING` in terminal). Rendering verified correct. Prod is Linux — warning won't exist there.

## #6 · `font-style: italic` in report CSS pulls in Segoe-UI-Italic fallback
**Problem:** report PDF embedded `Segoe-UI-Italic` although all text families are self-hosted.
**Cause:** we host no italic faces; WeasyPrint resolves `font-style: italic` via system fonts (Windows → Segoe). On Linux prod the same CSS would pick a *different* random font — silent inconsistency.
**Solution:** don't use italics anywhere in report/site CSS; distinguish notes with color/size. (Alternative if italics ever needed: host italic woff2/ttf faces.)

## #7 · Characters like → (U+2192) silently fall back to system fonts
**Problem:** sample report text contained «ствол → ветви → листва»; the → glyph isn't in our latin+cyrillic subsets → Segoe-UI crept into the PDF again.
**Cause:** LLM-generated text loves arrows/checkmarks; standard subsets don't include them.
**Solution:** extended `build_fonts.py` UNICODES with `U+2190-2193` (arrows) and `U+2713-2714` (checkmarks), rebuilt fonts. **Rule: after ANY font/subset change, re-run the embedded-font check from UseCase #2.** Phase 3 prompt should also instruct "no emojis/exotic symbols" like the old prompt did.

## #8 · Prompt rules alone can't fully stop "inner-state language" drift → linter + repair pass
**Problem:** prompt v1.0/v1.1 explicitly bans conclusions about the child's inner states, yet Gemini 2.5 Pro kept producing «желание добавить своё», «интерес к людям», «отсутствие страха перед листом», «смелость» (~3-6 spots per report). Strengthening instructions reduced but did not eliminate — sampling drift is inherent.
**Solution (belt and suspenders):** `pipeline/lint.py` — regex patterns for banned trait-words with allowed-context exceptions (activities are NOT linted: «передать настроение сцены» is a legit assignment). On hits, `gemini.py` runs a cheap text-only **repair call** (temp 0.2): rewrite only flagged spots in skill-language, return full JSON, re-validate + re-lint; accept only if violations decreased; max 2 rounds; failed repair never spoils an already-valid report. Result on all 3 test drawings: 1 repair round → 0 hits.
**Reusable principle:** for any "LLM must not say X" requirement, add a programmatic post-check + targeted repair instead of trusting the prompt.

## #9 · Crop-based synthetic test can't validate multi-drawing consolidation
**Problem:** to test the consolidated (2-image) report we paired a drawing with its own crop. The report came back describing ONE work with no per-drawing citations — looked like the consolidation prompt failed.
**Cause:** it didn't fail — Gemini correctly recognized the crop as part of the same drawing and merged them (the crop's content appears inside the single description). The model was more perceptive than the test.
**Solution:** consolidation quality can only be tested with genuinely different drawings of the same child (user to provide). Crop/duplicate synthetic sets are invalid for this purpose — though they usefully confirm the model doesn't hallucinate differences between near-identical inputs.

## #10 · Browsers silently rejected our subsetted fonts (serif fallback) while WeasyPrint accepted them
**Problem:** user screenshot showed the whole landing in Times-like serif — woff2 fonts not applied. PDFs were fine, so the fonts "worked" in all our machine checks.
**Cause:** `fontTools.varLib.instancer` pins axes and removes `fvar`, but leaves the `STAT` table behind. Chrome/Firefox run fonts through the OTS sanitizer, which rejects a font with STAT referencing non-existent axes — silently, falling back to system serif. WeasyPrint doesn't sanitize, hence PDF worked.
**Solution:** in `build_fonts.py` after instancing, delete leftover variable-font tables: `STAT, avar, fvar, gvar, cvar, MVAR, HVAR, VVAR`. Verified via headless Chrome screenshot (`chrome --headless --screenshot=ABS_PATH url` — note: the path must be absolute on Windows).
**Reusable principle:** webfont checks must include a real browser engine (headless Chrome screenshot), not only the PDF renderer — they validate fonts differently.

## #11 · Naive sentence split breaks on Russian initials («Никиты Н.»)
**Problem:** landing quotes extracted as «В рисунке Никиты Н.» — `conclusion.split('. ')[0]` saw the initial's period as a sentence end.
**Solution:** sentence boundary = period preceded by a lowercase letter/quote/paren: `re.search(r"^(.*?[а-яёa-z»\)])\.(?=\s|$)", text)` (`app/samples.py::_first_sentence`).

## #12 · Two Phase-5 form gotchas: MultiDict→dict gives lists; curl mangles Cyrillic multipart
**Problem A:** re-rendered form after validation errors didn't preserve values: `dict(request.form)` (Werkzeug MultiDict) yields LIST values → `['ж'] == 'ж'` false in templates. **Fix:** `request.form.to_dict()`.
**Problem B:** even after the fix, curl-based tests showed gender not re-selected. The app was correct — Git-bash curl on Windows sends Cyrillic `-F` values as cp1252 bytes, breaking comparisons server-side. **Rule:** test Cyrillic form submissions with Flask test client (`app.test_client()`), not curl; curl is fine for ASCII/status/flow checks.

## #13 · lru_cache на инлайн-CSS лендинга «замораживает» правки стилей
**Problem:** мобильные CSS-правки не появлялись на лендинге — страница инлайнит tokens+components через `@lru_cache`, а werkzeug-reloader перезапускает процесс только при изменении .py, не .css.
**Solution:** кэш по mtime файлов (`_inline_css` в app/routes.py) — правки видны сразу. Правило: любые серверные кэши контента — только с mtime/версией.

## #14 · Headless Chrome на этой машине врёт про мобильную вёрстку (Windows DPI 125%)
**Problem:** скриншоты `--window-size=375` выглядели как горизонтальный overflow (обрезанные заголовки/шапка); часы ушли на «починку» несуществующего бага.
**Cause:** системный масштаб Windows 125% — headless рендерит CSS-вьюпорт 469px и отдаёт левый кроп 375px. `--force-device-scale-factor=1` в старом headless не работает.
**Solution/ground truth:** DOM-проба (`document.documentElement.scrollWidth == clientWidth` → overflow нет). Правило: мобильную вёрстку проверяет ЗАКАЗЧИК на реальном телефоне; headless-скриншоты здесь — только по явной просьбе и с поправкой на кроп.

## #15 · Правки .claude/settings.local.json не действуют в живой сессии
**Problem:** широкие permissions записаны в файл, но промпты продолжались, а каждое одобрение ПЕРЕЗАПИСЫВАЛО файл старым накопленным списком (война за файл, deny-список с защитой .env терялся).
**Cause:** сессия читает permissions при старте и держит в памяти; файл-вотчер не следит за .claude/ этого проекта; при одобрении сессия пишет свой stale-снимок поверх.
**Solution:** восстановить файл и НЕ воевать с ним до перезапуска сессии; активация — только рестарт Claude Code или /permissions reload. После рестарта война прекращается (промптов нет — нечего дописывать).

## #5 · gwfh variant id for weight 400 is "regular", not "400"
**Problem:** `KeyError: '400'` when picking Inter variants from gwfh API JSON.
**Cause:** the API names the normal-weight variant `regular` (and italic `italic`), numeric ids only for other weights.
**Solution:** map `regular → 400` when indexing variants. (Script later superseded by build_fonts.py, see #2.)

## #16 · Ubuntu: `python3 -m venv` fails ("ensurepip is not available") though `import venv` works
**Problem:** on the VPS, `python3 -m venv venv` aborted with *"ensurepip is not available … install the python3.12-venv package"*, even though a recon check of `import venv` had reported OK.
**Cause:** Debian/Ubuntu split venv: the `venv` module imports fine, but `ensurepip` (needed to bootstrap pip into a new venv) ships in a separate `python3.X-venv` apt package that isn't installed by default. A bare `import venv` check is a false positive.
**Solution:** `apt-get install -y python3.12-venv`, then `rm -rf` the half-built venv dir and recreate. **Recon rule:** to test real venv capability, check the apt package / try `python3 -m venv` in a temp dir, not just `import venv`.

## #17 · `.gitignore` inline `#` comments don't work — almost leaked a private key
**Problem:** lines like `scripts/deploy/install_cert.sh      # private CF key` failed to ignore the file; `git add -A` staged the private Cloudflare Origin key + a tarball of private drawings.
**Cause:** in `.gitignore`, `#` only starts a comment at the **beginning of a line**. An inline `#` after a pattern becomes part of the pattern (`install_cert.sh      # private CF key`), which matches nothing → file not ignored.
**Solution:** put comments on their **own lines**. Verify with `git check-ignore <path>`. **Process rule:** before every commit, run a safety grep over `git diff --cached --name-only` for secret/generated patterns (`install_cert|\.tar\.gz|/samples/|^\.env$|\.webp$`) — this is what caught it. Confirmed via `git log --all -- <path>` the secrets were never in history.

## #18 · Cloudflare proxy silently overrides robots.txt and 403s crawlers (breaks SEO)
**Problem:** after deploy, live `robots.txt` showed a Cloudflare-managed block (`Content-Signal: ai-train=no`, `Disallow: /` for GPTBot/ClaudeBot) **above** our allow-rules; and `/`, `/blog`, `/sitemap.xml` returned **403** to non-browser clients while `robots.txt` returned 200. Origin (Flask) was correct in all local tests.
**Cause:** orange-cloud proxy means Cloudflare can rewrite/serve content at the edge. **"Block AI Scrapers and Crawlers" / Content-Signals** prepends anti-AI rules to robots.txt; **Bot Fight Mode** challenges/403s automated clients (would block Yandex fetching the sitemap). Both are dashboard toggles, invisible from the codebase.
**Solution:** disable both in Cloudflare (Security → Bots), then **purge the CF cache for `/robots.txt`** (edge-cached). Re-verify with a cache-busting query (`?cb=…`). **Verification rule:** what crawlers actually see = Yandex Webmaster «Проверка ответа сервера» (fetches as YandexBot through CF), NOT a normal browser — browsers pass CF, bots may not.

## #19 · grep mangles Cyrillic in Git Bash on this box → false "clean" on banned-word scans
**Problem:** a grep-based banned-word scan of Russian blog content reported "clean", but a later check found `«Энергия темперамента»` (a banned token) it had missed; grep output also showed mojibake (`предсказ�`).
**Cause:** Git Bash grep on this Windows box has a locale/encoding mismatch with UTF-8 Cyrillic — matches are unreliable (false negatives).
**Solution:** scan Russian text with **Python (UTF-8)**, not grep: `low = path.read_text(encoding="utf-8").lower(); if token in low`. Don't `print()` the Cyrillic context (cp1252 console crashes, UseCase #3) — **write findings to a UTF-8 file and open it with the Read tool**. Reusable for any Cyrillic content audit.

## #20 · WeasyPrint doesn't resolve CSS `var()` inside SVG presentation attributes
**Problem:** rendering the inline-SVG blog doodles (which use `fill="var(--accent)"`) to a PDF montage for visual QA produced black/unstyled shapes.
**Cause:** browsers inherit CSS custom properties into SVG, but WeasyPrint's SVG renderer (and most rasterizers) don't resolve `var()` in SVG presentation attributes.
**Solution:** for offline rasterization/QA only, string-replace `var(--x)` with concrete hex before rendering. In the live site it's a non-issue — real browsers resolve `var()`, so the doodles recolor correctly across all 4 palettes. Don't "fix" the SVGs to hex (that would break theming).

## #21 · Cloudflare orange-cloud hurt Russian reachability → DNS-only (grey) + Let's Encrypt
**Problem:** golosrisunka.ru behind Cloudflare orange-cloud (proxy) + CF Origin cert was poorly reachable from Russia. shepotzvezd.ru on the SAME server works fine — it's DNS-only.
**Cause:** Cloudflare's proxy edge IPs are unreliable/throttled for RU users (and add the SEO gotchas of UseCase #18). The CF Origin cert is ONLY trusted by Cloudflare's edge, so the moment you go grey-cloud (direct traffic), browsers see an untrusted cert → you MUST swap to a publicly-trusted cert.
**Solution:** flip the DNS records to **DNS-only (grey cloud)**, then issue a **Let's Encrypt** cert with the certbot **nginx plugin**, ECDSA, both apex+www — identical to shepotzvezd: `certbot --nginx -d golosrisunka.ru -d www.golosrisunka.ru --key-type ecdsa --redirect`. certbot rewrites the vhost's `ssl_certificate` to `/etc/letsencrypt/live/...` and registers auto-renewal (`certbot.timer`, `installer=nginx` → reloads nginx on renew). Verify public trust from OUTSIDE the box: `openssl s_client ... | grep "Verify return code"` must be `0 (ok)` and `curl` (no `-k`) must succeed. **Prereqs for issuance:** both names resolve directly to the server, port 80 open (HTTP-01). **Repo:** `go_live.sh` / `setup_letsencrypt.sh` now do LE; the old CF-Origin `install_cert.sh` is gitignored (private key) and obsolete. `deploy.sh` does NOT touch nginx, so updating these scripts in git does not auto-change live TLS — the cert swap is a one-time manual `certbot` run on the server. **Footgun:** don't end a deploy/setup script with `certbot renew --dry-run` — it hits LE *staging* and can hang for minutes with no output, blocking the run (hit us in setup_letsencrypt.sh; replaced with a non-blocking expiry+timer check).

## #22 · First-party admin analytics drowned in bot traffic (uptime monitors, scanners, tools)
**Problem:** the `/admin` analytics (own `events` table) was ~61% bots — `PingAdmin.Ru` (a RU uptime monitor) alone was 37% of all events, plus `l9scan/leakix`, `TLM-Audit-Scanner`, `rust_sniffer`, `curl`, `Claude-User` agent fetches. They inflated visitor/funnel/action counts and were counted as real `desktop` users.
**Cause:** `parse_device()` only flagged UAs containing `bot/crawler/spider/headless/slurp/monitor`. Modern bots either self-identify with a `+http(s)://…` URL (PingAdmin, leakix, Claude-User) or are non-browser tools whose UA lacks `Mozilla` (curl, `*-Audit-Scanner`, greedyhand) — neither matched, so they landed in `desktop`. The JS beacon doesn't help here because the funnel's server-side `landing_view` fires for every request, bot or not.
**Solution:** three-layer fix. (1) Broaden `parse_device()`: UA with `+http` → bot; UA without `mozilla` → bot (tools); plus a marker list (scanners, http libs, AI/SEO/social bots). **Keep YandexBrowser as a human** — it sends a normal Mozilla UA with no `+http` (don't blanket-match "yandex"). (2) Filter `device='bot'` out of every human-facing admin query via a shared `NOT_BOT = "(device IS NULL OR device <> 'bot')"` (NULL = worker/system events → keep), and show a "ботов отфильтровано: N" count for transparency. (3) Backfill historical rows with `scripts/reclassify_devices.py` (recompute device from `user_agent`; **skip null-UA rows** so worker events stay untouched; `--dry-run` first). Run the backfill **as www-data** (`sudo -u www-data venv/bin/python …`) so the SQLite WAL/SHM files keep correct ownership. Filtering is heuristic — a bot with a real browser UA + residential IP is unfilterable, but this removed the vast majority (138 → 39 human visitors).

## #23 · Measuring "engaged" visits (vs instant bounces) in first-party analytics
**Problem:** the owner wanted to see only *engaged* visitors in the admin panel and drop "bounced, didn't even scroll, left" sessions. First instinct was "duration < 1s = bot/bounce" — but we only record a single server-side `landing_view` per visit, so a visit has ONE timestamp → duration is always 0s for both bots AND humans who read for 30s and left without clicking. Duration is unmeasurable here, and "fast bounce = bot" over-deletes real people.
**Cause:** no client-side engagement/dwell signal existed; the server beacon only captured page loads and UI clicks.
**Solution:** add a GA4-style "engaged session" signal (positive flag, not deletion). `_metrika.html` fires ONE `engaged` beacon to `/t/e?engaged=1` on the FIRST of: scroll / click / keydown / touchstart, OR **15s of *visible* dwell** (1s timer gated by `document.visibilityState`, so background/prerender tabs don't accrue time). 15s matches Yandex Metrika's «отказ» threshold so the two dashboards agree. `/t/e` maps `engaged=1` → event type `engaged`. Admin **Визиты** then shows engaged = `COUNT(DISTINCT visitor_id WHERE type='engaged')`, bounce% = `1 - engaged/total`, a per-visitor «Вовлечён ✓» flag, and an "Вовлёкся" funnel step. **Don't include bare `mousemove`** in the interaction set (incidental cursor presence over the page isn't intent; the 15s arm already catches no-scroll readers). Layers on the UA bot filter (#22): JS-less bots never fire `engaged`; instant no-scroll bounces don't either. Verified live by POSTing `engaged=1` with a browser UA → event recorded as `device=desktop`. Note: this first-party beacon lives inside the Metrika `{% if metrika_id %}` gate (prod has it set) — if Metrika is ever removed, first-party tracking stops too.

## #24 · Inlined critical CSS broke when it contained quotes/`>` (Jinja auto-escape)
**Problem:** after the redesign, the hero `background-image: url("/static/img/hero.jpg")` 404'd with the quotes IN the request path (`/"/static/img/hero.jpg"`), console showed `&#34;`. The image existed and served fine directly; only the CSS reference broke.
**Cause:** the landing inlines critical CSS via `<style>{{ inline_css }}</style>`. Flask auto-escapes `.html`, so Jinja turned every `"` → `&#34;`, `>` → `&gt;`, `&` → `&amp;` inside the stylesheet — silently mangling `url("…")`, `font-family:"Rubik"`, and child-combinator selectors (`.carousel > *`). Unnoticed for ages because the OLD inline CSS had no `url()` to make a visible 404 — fonts had just been quietly falling back.
**Solution:** mark trusted inlined CSS safe: `<style>{{ inline_css | safe }}</style>` (our own files, no XSS risk). Belt-and-suspenders: prefer **unquoted** CSS urls (`url(/static/img/hero.jpg)`) and **absolute `/static/…` paths** (relative `../img/…` breaks when CSS is inlined into a page served at `/`). This also un-breaks the inlined `font-family` and `>` selectors — ships whenever the landing is next deployed.

## #25 · Web binary assets must be built on the host, not in the agent sandbox
**Problem:** images generated in the agent's Linux sandbox (PIL) never appeared on the site — blank hero / missing logo even though "the files were created".
**Cause:** the agent's shell sandbox is isolated from the Windows host; it writes text via the file tools but **binary writes don't reach the real project**, and its mount serves **stale reads** (reported `tokens.css` as 1 brace; truncated templates). So sandbox-built JPG/PNG/WebP and sandbox `git` are not trustworthy for delivery.
**Solution:** ship a **build script** the owner runs in their own venv: `scripts/build_hero_image.py` (Hero.png → static/img/hero.{jpg,webp}+800) and `scripts/build_logos.py` (stripLogo/logo.png → static/img/logo-{strip,icon}.{png,webp}). Sources live in gitignored `data/Images/` (local-only); the **optimized outputs in `static/img/` ARE committed** and served directly (server needs no rebuild). Verify file/CSS state with the **Read/Grep tools (authoritative), not bash**. Same isolation reason: the agent can't `git push` — use `release.bat` on the host (bump → export dist → commit → push).
