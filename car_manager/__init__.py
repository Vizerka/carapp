# car_manager/__init__.py
import os
from flask import Flask, request, redirect, url_for
from flask_login import current_user

from .extensions import db, login_manager
from .helpers import days_left_filter
from .cli import register_cli


def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )

    # --- config ---
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")

    # jak chcesz absolutną ścieżkę do DB (polecam, mniej cyrków z cwd):
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(base_dir, "cars.db")

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(base_dir, "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    # --- extensions ---
    db.init_app(app)
    login_manager.init_app(app)

    # opcjonalnie (ale przyjemne)
    login_manager.login_view = "login"
    login_manager.login_message = "Zaloguj się, żeby wejść dalej."
    login_manager.login_message_category = "warning"

    # MODELE muszą być zaimportowane zanim create_all
    from . import models  # noqa: F401

    register_cli(app)

    # Template filters
    app.add_template_filter(days_left_filter, name="days_left")

    # --- globalna blokada dla niezalogowanych ---
    @app.before_request
    def _require_login():
        # statyki zostaw w spokoju
        if request.path.startswith("/static/"):
            return None

        # pozwól na logowanie/wylogowanie + ewentualnie stronę "about" jeśli chcesz publiczną
        public_paths = {
            "/login",
            "/logout",
        }
        if request.path in public_paths:
            return None

        # wszystko inne wymaga logowania
        if not current_user.is_authenticated:
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=nxt))

        return None

    # --- ROUTES (Twoja architektura init_routes) ---
    from .routes_auth import init_routes as init_auth
    from .routes_admin import init_routes as init_admin

    from .routes_core import init_routes as init_core
    from .routes_odometer import init_routes as init_odo
    from .routes_insurance import init_routes as init_oc
    from .routes_inspection import init_routes as init_ti
    from .routes_service import init_routes as init_svc
    from .routes_fuel import init_routes as init_fuel
    from .routes_documents import init_routes as init_docs
    from .routes_intervals import init_routes as init_iv
    from .routes_backup import init_routes as init_backup

    init_auth(app)
    init_admin(app)

    init_core(app)
    init_odo(app)
    init_oc(app)
    init_ti(app)
    init_svc(app)
    init_fuel(app)
    init_docs(app)
    init_iv(app)
    init_backup(app)

    with app.app_context():
        db.create_all()
        from .mqtt_discovery import publish_safely
        publish_safely()

    @app.after_request
    def _publish_mqtt_after_change(response):
        if request.method == "POST" and request.path != "/login" and response.status_code < 400:
            from .mqtt_discovery import publish_safely
            publish_safely()
        return response

    return app
