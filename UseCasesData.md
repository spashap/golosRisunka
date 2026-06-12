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
