"""Flask-приложение «Голос рисунка». Один процесс, серверный HTML (spec §2)."""
from flask import Flask, g, render_template

from app import track
from app.db import init_db
from config import settings


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(settings.BASE_DIR / "static"),
        template_folder=str(settings.BASE_DIR / "templates"),
    )
    app.config["MAX_CONTENT_LENGTH"] = settings.UPLOAD_MAX_BYTES * 3 + 1_000_000

    init_db()
    app.before_request(track.before_request)
    app.after_request(track.after_request)

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    from app.routes import bp
    app.register_blueprint(bp)
    from app.admin import bp_admin
    app.register_blueprint(bp_admin)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="Такой страницы нет"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500,
                               message="Что-то пошло не так. Мы уже разбираемся."), 500

    @app.context_processor
    def inject_globals():
        return {"static": "/static", "palette": settings.PALETTE,
                "site_name": settings.SITE_NAME,
                "site_domain": settings.SITE_DOMAIN,
                "metrika_id": settings.YANDEX_METRIKA_ID}

    return app
