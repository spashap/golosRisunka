"""Flask-приложение «Голос рисунка». Один процесс, серверный HTML (spec §2)."""
from flask import Flask, render_template

from config import settings


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(settings.BASE_DIR / "static"),
        template_folder=str(settings.BASE_DIR / "templates"),
    )
    app.config["MAX_CONTENT_LENGTH"] = settings.UPLOAD_MAX_BYTES * 3 + 1_000_000

    from app.routes import bp
    app.register_blueprint(bp)

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
                "site_name": settings.SITE_NAME}

    return app
