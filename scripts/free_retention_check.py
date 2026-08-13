"""Проверка механизма удаления фото по сроку хранения (фремиум-бета).

Обещание «храним 90 дней, потом удаляем» стоит на публичной странице, поэтому механизм
должен быть не только написан, но и проверяем. Этот скрипт создаёт временную строку с
датой на день старше срока и настоящим файлом, гоняет уборщик и проверяет, что:
  1. файл и превью удалены с диска;
  2. deleted_at проставлен;
  3. текст разбора и строка в БД целы (удаляется фотография, а не данные беты);
  4. повторный вызов не падает (идемпотентность).

Тестовые строки удаляются из БД в конце. Консоль ASCII (Windows cp1252, UseCase #3).
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db import connect, init_db, new_token, now  # noqa: E402
from app.free_retention import sweep_expired  # noqa: E402
from config import settings  # noqa: E402

MARKER = "retention-selftest"


def main() -> int:
    init_db()
    conn = connect()
    ok = True
    tmp_dir = settings.FREE_DIR / "_selftest"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    img = tmp_dir / "drawing.jpg"
    thumb = tmp_dir / "thumb_drawing.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0 fake jpeg for retention test")
    thumb.write_bytes(b"\xff\xd8\xff\xe0 fake thumb")
    rel = img.relative_to(settings.BASE_DIR).as_posix()

    old = "2000-01-01T00:00:00+00:00"          # заведомо старше любого TTL
    cur = conn.execute(
        "INSERT INTO free_analyses (token, child_name, child_name_norm, child_age,"
        " status, file_path, parent_text, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (new_token(8), MARKER, MARKER, 5, "done", rel, MARKER, old))
    rid = cur.lastrowid
    conn.commit()
    print(f"created test row id={rid}, file exists={img.exists()}")

    n = sweep_expired(conn)
    row = conn.execute("SELECT deleted_at, parent_text, status FROM free_analyses"
                       " WHERE id = ?", (rid,)).fetchone()

    checks = [
        ("swept at least one row", n >= 1),
        ("image file removed", not img.exists()),
        ("thumbnail removed", not thumb.exists()),
        ("deleted_at set", bool(row["deleted_at"])),
        ("analysis row kept", row["status"] == "done"),
        ("analysis text kept", row["parent_text"] == MARKER),
    ]
    n2 = sweep_expired(conn)                    # идемпотентность
    checks.append(("second sweep is a no-op", n2 == 0))

    for label, passed in checks:
        print(("  ok   " if passed else "  FAIL ") + label)
        ok = ok and passed

    conn.execute("DELETE FROM free_analyses WHERE child_name = ?", (MARKER,))
    conn.commit()
    conn.close()
    for p in (img, thumb):
        if p.exists():
            p.unlink()
    try:
        tmp_dir.rmdir()
    except OSError:
        pass
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
