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
**Solution:** flip the DNS records to **DNS-only (grey cloud)**, then issue a **Let's Encrypt** cert with the certbot **nginx plugin**, ECDSA, both apex+www — identical to shepotzvezd: `certbot --nginx -d golosrisunka.ru -d www.golosrisunka.ru --key-type ecdsa --redirect`. certbot rewrites the vhost's `ssl_certificate` to `/etc/letsencrypt/live/...` and registers auto-renewal (`certbot.timer`, `installer=nginx` → reloads nginx on renew). Verify public trust from OUTSIDE the box: `openssl s_client ... | grep "Verify return code"` must be `0 (ok)` and `curl` (no `-k`) must succeed. **Prereqs for issuance:** both names resolve directly to the server, port 80 open (HTTP-01). **Repo:** `go_live.sh` / `setup_letsencrypt.sh` now do LE; the old CF-Origin `install_cert.sh` is gitignored (private key) and obsolete. `deploy.sh` does NOT touch nginx, so updating these scripts in git does not auto-change live TLS — the cert swap is a one-time manual `certbot` run on the server.
