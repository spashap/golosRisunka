"""Офлайн-лаборатория бесплатного разбора (фремиум-бета). Фаза 0.2 плана.

Гоняет пайплайн по тестовым рисункам БЕЗ веба и UI и складывает результат так, чтобы
заказчик мог прочитать его глазами. Здесь же снимается стоимость одного разбора: в
проекте нигде не читался usage_metadata, поэтому до этого скрипта цифра рубля была
догадкой, а §11.6 требует числа.

Использование:
  free_lab.py                       # все тестовые рисунки, тревога по умолчанию
  free_lab.py --concern black monsters --duration weeks
  free_lab.py --images path\\to.png --age 7 --address она
  free_lab.py --texts               # все сборки §5 + отдельно пары с оверрайдом
  free_lab.py --dry                 # без вызова модели: проверить обвязку

Выход: data/free_lab/<timestamp>/index.html + по файлу на прогон + raw JSON.
Консоль — ASCII (Windows cp1252, UseCase #3); всё русское уходит в файлы.
"""
import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import free_texts as T
from config import settings
from pipeline.free_gemini import FreeGenerationError, generate_free_analysis
from pipeline.free_schema import FreeInsufficient

# Прайс Gemini 2.5 Pro (список, <=200k контекста) на момент написания.
# Меняется у Google — держим здесь, чтобы цифра в отчёте не врала молча.
USD_PER_M_IN, USD_PER_M_OUT = 1.25, 10.00
USD_RUB = 90.0

# Известные тестовые рисунки: имя/возраст/обращение.
KNOWN = {
    "Draw-3_5yr-v1": ("Алексей", 3, "он"),
    "Draw-6yr-v1": ("Никита", 6, "он"),
    "Draw-8yr-v1": ("Алина", 8, "она"),
    "set1-img1": ("Алиса", 6, "она"),
    "set1-img2": ("Алиса", 6, "она"),
    "devtest-img1": ("Алиса", 4, "она"),
    "drawing-4yroldGirl": ("Катя", 4, "она"),
    "drawing-5yroldGirl-Scary": ("Даша", 5, "она"),
    "drawing-6yroldBoy": ("Алекс", 6, "он"),
    "drawing-10yroldGirl": ("Полина", 10, "она"),
    "coloringDrawing-4yroldBoy": ("Миша", 4, "он"),
    "scribble-4yearsold": ("Соня", 4, "она"),
    "_degraded": ("Катя", 4, "она"),
}
TEST_DIR = BASE_DIR / "projectSpec" / "testDrawings"
TEST_DIR2 = BASE_DIR / "projectSpec" / "fremium" / "testDraw"

# Расширенный прогон гейта: каждый файл встречается с той тревогой, ради которой он
# и нужен, а не со всеми восемью. Комментарий у пары = что именно проверяется.
MATRIX: list[tuple[str, str, str, str]] = [
    ("scribble-4yearsold", "neutral", "",
     "контракт скудного рисунка: ждём sparse и hypothesis=null"),
    ("scribble-4yearsold", "pressure", "weeks",
     "тот же контракт под тревогой"),
    ("coloringDrawing-4yroldBoy", "neutral", "",
     "перехват раскраски: ждём авторский абзац, а не разбор"),
    ("coloringDrawing-4yroldBoy", "black", "months",
     "перехват раскраски независимо от тревоги"),
    ("drawing-10yroldGirl", "neutral", "",
     "правка 3: трактовка про двойственность должна уйти"),
    ("drawing-10yroldGirl", "stopped", "months",
     "правка 2: correlate=null; оценки навыка нет"),
    ("drawing-5yroldGirl-Scary", "monsters", "weeks",
     "не сломалось ли главное после правок"),
    ("drawing-6yroldBoy", "repeat", "always",
     "правка 2: correlate=null"),
]


def make_degraded(src: Path, dst: Path) -> Path:
    """Испорченное фото из нормального: поворот, затемнение, обрезка ~40% листа.

    Не заменяет реальный кривой снимок, но прогоняет ветку отказа — в реальности
    это самая частая загрузка, и до сих пор она не проверялась ни разу.
    """
    from PIL import Image, ImageEnhance
    im = Image.open(src).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, int(w * 0.62), int(h * 0.60)))     # срезано ~40% листа
    im = im.rotate(-7, expand=True, fillcolor=(20, 20, 24))
    im = ImageEnhance.Brightness(im).enhance(0.34)          # снято в темноте
    im = ImageEnhance.Contrast(im).enhance(0.72)
    im = im.resize((int(im.width * 0.5), int(im.height * 0.5)))
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, quality=32)
    return dst


def _cost(p_tok: int, o_tok: int) -> tuple[float, float]:
    usd = p_tok / 1e6 * USD_PER_M_IN + o_tok / 1e6 * USD_PER_M_OUT
    return usd, usd * USD_RUB


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode()


def dump_texts(out_dir: Path) -> None:
    """Все сборки §5. Отдельным списком — пары, где сработал оверрайд длительности:
    их надо прочитать в первую очередь, а не искать среди двух сотен."""
    band_age = {"3-4": 3, "5-6": 5, "7-9": 8, "10-12": 11}
    blocks, overrides, n = [], [], 0
    for c in T.CONCERNS:
        ck = c["key"]
        durs = [None] if ck == "neutral" else [d["key"] for d in T.DURATIONS]
        for dk in durs:
            for band, age in band_age.items():
                for form in ("он", "она"):
                    n += 1
                    r = T.assemble_summary(concern_key=ck, duration_key=dk, age=age,
                                           address_form=form, name="Соня")
                    head = (f"{ck} | {dk} | {band} (возраст {age}) | {form} "
                            f"| просьба={r['ask_variant']}")
                    body = "\n\n".join(r["paragraphs"])
                    entry = f"=== {head} ===\n{body}\n"
                    blocks.append(entry)
                    if r["override_used"]:
                        overrides.append(entry)

    (out_dir / "summaries-all.txt").write_text("\n".join(blocks), encoding="utf-8")
    (out_dir / "summaries-overrides.txt").write_text(
        "ПАРЫ С ПЕРЕОПРЕДЕЛЁННЫМ МОДИФИКАТОРОМ ДЛИТЕЛЬНОСТИ\n"
        "(общий модификатор давал бы успокоение по умолчанию — читать в первую очередь)\n\n"
        + "\n".join(overrides), encoding="utf-8")
    print(f"texts: {n} combos -> summaries-all.txt, "
          f"{len(overrides)} overridden -> summaries-overrides.txt")


def run_one(img: Path, *, name: str, age: int, address: str, concern: str,
            duration: str, out_dir: Path, dry: bool) -> dict:
    rec = {"image": img.name, "concern": concern, "duration": duration,
           "age": age, "address": address, "name": name}
    summary = T.assemble_summary(concern_key=concern,
                                 duration_key=None if concern == "neutral" else duration,
                                 age=age, address_form=address, name=name)
    rec["summary"] = summary["paragraphs"]
    rec["ask_variant"] = summary["ask_variant"]
    rec["wait_hint"] = T.wait_hint(concern, address)
    if dry:
        rec["status"] = "dry"
        return rec

    dur_label = ("" if concern == "neutral"
                 else T.duration_label(concern, duration, address))
    try:
        res = generate_free_analysis(
            img, child_name=name, age=age, address_form=address,
            concern_key=concern, duration_label=dur_label,
            raw_dump_dir=out_dir / "raw" / f"{img.stem}_{concern}")
    except FreeGenerationError as e:
        rec["status"] = "FAILED"
        rec["error"] = "; ".join(e.attempts_log)
        return rec

    usd, rub = _cost(res.prompt_tokens, res.output_tokens)
    rec.update(status="ok", elapsed=round(res.elapsed_s, 1),
               attempts=res.attempts_used, repairs=res.repair_rounds,
               dropped=res.hypothesis_dropped, tok_in=res.prompt_tokens,
               tok_out=res.output_tokens, usd=round(usd, 4), rub=round(rub, 2))
    a = res.analysis
    if isinstance(a, FreeInsufficient):
        rec["status"] = "insufficient"
        rec["reason_key"] = a.reason_key
        rec["reason"] = a.insufficient_reason
        return rec
    rec.update(words=a.word_count(), opening=a.opening, detail=a.detail,
               portrait_hint=a.portrait_hint,
               question=a.question_to_child, unknown=a.unknown_next,
               flags=a.flags,
               correlate=a.concern_correlate_visible,
               correlate_note=a.concern_correlate_note,
               hypothesis=(None if a.hypothesis is None else {
                   "phrase": a.hypothesis.phrase,
                   "attribution": a.hypothesis.attribution,
                   "key": a.hypothesis.key,
                   "age_scope": a.hypothesis.age_scope,
                   "new_key_description": a.hypothesis.new_key_description}))
    # Абзац несовпадения эмитит СЕРВЕР по единственному источнику правды — здесь
    # воспроизводим ровно то, что увидит родитель на странице.
    # На раскраске абзац несовпадения ПОДАВЛЯЕМ: печатный контур по определению не может
    # показать названный родителем признак, и два дисклеймера подряд до первого слова
    # по существу читаются как отписка. Абзаца про раскраску здесь достаточно.
    if "coloring" in a.flags:
        rec["coloring_paragraph"] = T.g(T.COLORING_PARAGRAPH, address)
    elif a.concern_correlate_visible is False:
        rec["mismatch_paragraph"] = T.MISMATCH_PARAGRAPH
    if "sparse" in a.flags:
        rec["sparse_paragraphs"] = [p.replace("{name}", name)
                                    for p in T.SPARSE_PARAGRAPHS]
    return rec


def write_index(recs: list[dict], out_dir: Path) -> None:
    e = html.escape
    ok = [r for r in recs if r.get("status") == "ok"]
    tot_rub = sum(r.get("rub", 0) for r in recs)
    avg_s = (sum(r.get("elapsed", 0) for r in ok) / len(ok)) if ok else 0
    p = ["<meta charset='utf-8'><title>free_lab</title>",
         "<style>body{font:16px/1.55 system-ui;max-width:900px;margin:24px auto;"
         "padding:0 16px;color:#222}h2{margin-top:34px;border-top:2px solid #eee;"
         "padding-top:14px}.m{color:#666;font-size:14px}blockquote{margin:8px 0;"
         "padding:8px 14px;border-left:3px solid #ccc;background:#fafafa}"
         "code{background:#f2f2f2;padding:1px 4px}.bad{color:#b00}"
         ".hyp{background:#fff8e5;padding:8px 12px;border-left:3px solid #e0a800}"
         "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:4px 8px;"
         "font-size:14px;text-align:left}"
         ".rep{border:1px solid #e3d8c2;background:#FFFCF4;padding:16px 20px;"
         "border-radius:14px;margin:10px 0}.rep p{margin:0 0 12px}"
         ".rep hr{border:0;border-top:1px dashed #ddd;margin:16px 0}</style>",
         "<h1>free_lab</h1>",
         f"<p class='m'>прогонов: {len(recs)} · успешных: {len(ok)} · "
         f"среднее время: {avg_s:.0f} c · суммарно ≈ {tot_rub:.1f} ₽ · "
         f"модель {e(settings.FREE_GEMINI_MODEL)}</p>"]

    if ok:
        avg_rub = tot_rub / len(ok)
        p.append(f"<p><b>Стоимость одного разбора ≈ {avg_rub:.2f} ₽</b> "
                 f"<span class='m'>(курс {USD_RUB:.0f} ₽/$, прайс "
                 f"${USD_PER_M_IN}/M вход, ${USD_PER_M_OUT}/M выход)</span></p>")

    # §12: шесть блоков «Что видно» рядом — так и проверяется, что разбор не мог бы
    # быть написан про другой рисунок.
    p.append("<h2>Открытия — все прогоны рядом</h2>")
    p.append("<p class='m'>Критерий §12: каждый абзац должен быть написан про ЭТОТ "
             "рисунок и не подходить ни к какому другому.</p>")
    for r in ok:
        if r.get("opening"):
            p.append(f"<p><b>{e(r['image'])}</b> <span class='m'>({e(r['concern'])})"
                     f"</span><br>{e(r['opening'])}</p>")

    # §4.4: гипотеза может быть законной и при этом пустой — пересказом видимой детали
    # чуть более абстрактными словами. Линтер такое не поймает и не должен; поэтому
    # выносим все кандидаты отдельным списком, чтобы это было видно глазами.
    p.append("<h2>Кандидаты интерпретаций — читать глазами</h2>")
    p.append("<p class='m'>Вопрос к каждой строке ровно один: <b>узнаёт ли родитель "
             "что-то, чего не увидел сам?</b> Если гипотеза только пересказывает "
             "видимую деталь более абстрактными словами — это кандидат на даунгрейд "
             "наравне с незаконной, хотя нарушения в ней нет. Второй вопрос: уместна "
             "ли трактовка для этого возраста.</p>")
    any_hyp = False
    for r in ok:
        h = r.get("hypothesis")
        if not h:
            continue
        any_hyp = True
        scope = h.get("age_scope") or "—"
        warn = ""
        nums = [int(x) for x in re.findall(r"\d+", scope)]
        if nums and r.get("age") is not None and r["age"] < min(nums):
            warn = (f" <span class='bad'>⚠ ребёнку {r['age']}, "
                    f"а заявленная область — {e(scope)}</span>")
        p.append(f"<div class='hyp'><b>{e(r['image'])} · {e(r['concern'])} · "
                 f"ребёнку {r.get('age')}</b>{warn}<br>"
                 f"<i>{e(h['phrase'])}</i><br>"
                 f"<span class='m'>ключ <code>{e(h['key'])}</code> · атрибуция: "
                 f"{e(h['attribution'])} · возрастная область: {e(scope)}</span><br>"
                 f"<span class='m'>опирается на: {e((r.get('opening') or '')[:180])}…"
                 f"</span></div>")
    if not any_hyp:
        p.append("<p class='m'>Гипотез не было ни в одном прогоне.</p>")

    p.append("<h2>Сводка</h2><table><tr><th>рисунок</th><th>тревога</th><th>статус</th>"
             "<th>слов</th><th>c</th><th>попыток</th><th>repair</th><th>гипотеза</th>"
             "<th>флаги</th><th>₽</th></tr>")
    for r in recs:
        hyp = "—" if not r.get("hypothesis") else e(r["hypothesis"]["key"])
        if r.get("dropped"):
            hyp = "снята (даунгрейд)"
        p.append(f"<tr><td>{e(r['image'])}</td><td>{e(r['concern'])}</td>"
                 f"<td>{e(str(r.get('status')))}</td><td>{r.get('words','')}</td>"
                 f"<td>{r.get('elapsed','')}</td><td>{r.get('attempts','')}</td>"
                 f"<td>{r.get('repairs','')}</td><td>{hyp}</td>"
                 f"<td>{e(','.join(r.get('flags') or []))}</td>"
                 f"<td>{r.get('rub','')}</td></tr>")
    p.append("</table>")

    p.append(keys_summary_html())

    p.append("<h2>Полные отчёты — так, как их увидит родитель</h2>")
    for r in recs:
        p.append(f"<h2>{e(r['image'])} · тревога «{e(r['concern'])}» · "
                 f"{e(str(r['age']))} лет · {e(r['address'])}</h2>")
        if r.get("why"):
            p.append(f"<p class='m'>проверяет: {e(r['why'])}</p>")
        if r.get("status") == "FAILED":
            p.append(f"<p class='bad'>ПРОВАЛ: {e(r.get('error',''))}</p>")
            continue

        p.append("<div class='rep'>")
        # 1. вывод после вопросов целиком
        for para in r["summary"]:
            p.append(f"<p>{e(para)}</p>")
        p.append("<hr>")
        if r.get("status") == "insufficient":
            p.append(f"<p class='bad'>{e(r['reason'])}</p></div>")
            p.append(f"<p class='m'>[тех] ОТКАЗ · {e(r['reason_key'])} · "
                     f"{r.get('elapsed')} c · {r.get('rub')} ₽</p>")
            continue
        if not r.get("opening"):          # --dry: модель не вызывалась
            p.append("<p class='m'>(dry-run: разбор не запрашивался)</p></div>")
            continue
        # 2. блок 1 — тёплое открытие
        p.append(f"<p>{e(r['opening'])}</p>")
        # 3. служебные абзацы — ПОСЛЕ открытия: документ не начинается с отрицания
        for key in ("coloring_paragraph", "mismatch_paragraph"):
            if r.get(key):
                p.append(f"<p><b>{e(r[key])}</b></p>")
        for para in r.get("sparse_paragraphs") or []:
            p.append(f"<p>{e(para)}</p>")
        # 4. деталь, портрет, вопрос, зазор
        p.append(f"<p>{e(r['detail'])}</p>")
        if r.get("portrait_hint"):
            p.append(f"<p>{e(r['portrait_hint'])}</p>")
        p.append(f"<p><b>Спросите {e(T.accusative(r.get('name',''), r.get('address','он')))} сегодня:</b> "
                 f"<i>{e(r['question'])}</i></p>")
        p.append(f"<p><b>Чего этот лист не показывает.</b> {e(r['unknown'])}</p>")
        # 5. финал. На раскраске — перенаправление, а не продажа: родитель в одном шаге
        # от того, чтобы дать нам нормальный материал.
        sell = (T.coloring_cta(r.get("name", ""), r.get("address", "он"))
                if "coloring" in (r.get("flags") or [])
                else T.selling_block(r.get("name", ""), r.get("address", "он")))
        p.append(f"<p><b>{e(sell['title'])}</b> {e(sell['body'])}</p>")
        p.append("<p><span style='display:inline-block;background:#3E4E78;color:#fff;"
                 "padding:10px 18px;border-radius:99px;font-weight:600'>"
                 f"{e(sell['button'])}</span></p>")
        p.append("</div>")
        # кандидат на «фразу, которую мама перескажет» — критерий приёмки шага 4
        if r.get("portrait_hint"):
            p.append(f"<p class='m'>[фраза на пересказ — кандидат] "
                     f"<b>{e(r['portrait_hint'][:200])}</b></p>")

        # техническая сноска
        h = r.get("hypothesis")
        hyp = "—"
        if h:
            hyp = (f"<code>{e(h['key'])}</code> (scope {e(h.get('age_scope') or '—')})"
                   f"{' <b class=bad>NEW: ' + e(h.get('new_key_description','')) + '</b>' if h['key'] == 'new' else ''}")
        if r.get("dropped"):
            hyp += " · <b>даунгрейд: гипотеза снята</b>"
        p.append(f"<p class='m'>[тех] ключ: {hyp} · флаги: "
                 f"{e(','.join(r.get('flags') or []) or '—')} · correlate: "
                 f"{e(str(r.get('correlate')))} · длительность: "
                 f"{e(str(r.get('duration') or '—'))} · слов в блоке 3: "
                 f"{len(re.findall(r'[^ЁёА-Яа-яA-Za-z]*([A-Za-zЁёА-Яа-я]+)', r['unknown']))}"
                 f" · {r.get('elapsed')} c · токены {r.get('tok_in')}/{r.get('tok_out')}"
                 f" · {r.get('rub')} ₽ · линтер: чисто, repair {r.get('repairs')}</p>")
        if r.get("correlate") is False:
            p.append(f"<p class='m'>заметка модели о несовпадении: "
                     f"{e(r.get('correlate_note',''))}</p>")
    (out_dir / "index.html").write_text("\n".join(p), encoding="utf-8")


def keys_summary_html() -> str:
    """Сводка ключей трактовок по ВСЕМ прогонам с начала: консолидируется словарь
    или растёт. Ради этого §1 и вводился."""
    e = html.escape
    counts: dict[str, list] = {}
    for f in sorted(settings.FREE_LAB_DIR.glob("*/runs.json")):
        try:
            for r in json.loads(f.read_text(encoding="utf-8")):
                h = r.get("hypothesis")
                if not h:
                    continue
                counts.setdefault(h["key"], []).append(r.get("age"))
        except (OSError, ValueError):
            continue
    rows = sorted(counts.items(), key=lambda kv: -len(kv[1]))
    out = ["<h2>Ключи трактовок по всем прогонам</h2>",
           "<p class='m'>Вопрос: словарь консолидируется или растёт? Ключи вне "
           "закрытого словаря теперь невозможны — модель обязана взять ключ из списка "
           "либо вернуть <code>new</code> с описанием.</p>",
           "<table><tr><th>ключ</th><th>раз</th><th>возрасты</th></tr>"]
    for k, ages in rows:
        out.append(f"<tr><td><code>{e(k)}</code></td><td>{len(ages)}</td>"
                   f"<td>{e(', '.join(str(a) for a in sorted(x for x in ages if x)))}"
                   f"</td></tr>")
    out.append("</table>")
    out.append(f"<p class='m'>всего разных ключей: {len(rows)}</p>")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="*", type=Path, default=None)
    ap.add_argument("--concern", nargs="*", default=["black"],
                    choices=T.CONCERN_KEYS + ["all"])
    ap.add_argument("--duration", default="weeks",
                    choices=[d["key"] for d in T.DURATIONS])
    ap.add_argument("--age", type=int, default=None)
    ap.add_argument("--address", default=None, choices=["он", "она"])
    ap.add_argument("--name", default=None)
    ap.add_argument("--texts", action="store_true", help="только сборки §5, без модели")
    ap.add_argument("--matrix", action="store_true",
                    help="расширенный прогон гейта: пары файл x тревога из MATRIX")
    ap.add_argument("--dry", action="store_true", help="без вызова модели")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = settings.FREE_LAB_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"out: {out_dir}")

    if args.texts:
        dump_texts(out_dir)
        return 0

    if args.matrix:
        degraded = make_degraded(TEST_DIR2 / "drawing-4yroldGirl.png",
                                 settings.FREE_LAB_DIR / "_degraded.png")
        print(f"degraded photo built: {degraded.name}")
        pairs = []
        for stem, concern, dur, why in MATRIX:
            src = degraded if stem == "_degraded" else TEST_DIR2 / f"{stem}.png"
            if not src.exists():
                print("MISSING:", _ascii(str(src)))
                continue
            pairs.append((src, concern, dur or args.duration, why))
    else:
        images = args.images or sorted(TEST_DIR.glob("*.png"))
        if not images:
            print("ERROR: no images found in", TEST_DIR)
            return 1
        concerns = T.CONCERN_KEYS if "all" in args.concern else args.concern
        pairs = [(img, c, args.duration, "") for img in images for c in concerns]

    recs = []
    for img, concern, duration, why in pairs:
        known = KNOWN.get(img.stem, ("Ребёнок", 6, "он"))
        name = args.name or known[0]
        age = args.age or known[1]
        address = args.address or known[2]
        print(f"-> {_ascii(img.name)} | {concern} | age {age} ...")
        rec = run_one(img, name=name, age=age, address=address, concern=concern,
                      duration=duration, out_dir=out_dir, dry=args.dry)
        rec["why"] = why
        recs.append(rec)
        print(f"   {rec.get('status')} "
              f"words={rec.get('words','-')} s={rec.get('elapsed','-')} "
              f"hyp={'yes' if rec.get('hypothesis') else 'no'} "
              f"corr={rec.get('correlate','-')} flags={rec.get('flags','-')} "
              f"rub={rec.get('rub','-')}")

    (out_dir / "runs.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(recs, out_dir)

    ok = [r for r in recs if r.get("status") == "ok"]
    failed = [r for r in recs if r.get("status") == "FAILED"]
    if ok:
        print(f"\nOK {len(ok)}/{len(recs)} | avg {sum(r['elapsed'] for r in ok)/len(ok):.0f}s"
              f" | avg cost {sum(r['rub'] for r in ok)/len(ok):.2f} RUB"
              f" | no-hypothesis {sum(1 for r in ok if not r.get('hypothesis'))}")
    if failed:
        print(f"FAILED: {len(failed)}")
    print(f"open: {out_dir / 'index.html'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
