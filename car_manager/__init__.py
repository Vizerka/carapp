import os
from flask import Flask
from .extensions import db
from .helpers import days_left_filter

def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cars.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config["UPLOAD_FOLDER"] = os.path.join(base_dir, "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    db.init_app(app)

    # MODELE muszą być zaimportowane zanim create_all
    from . import models  # noqa

    # Template filters
    app.add_template_filter(days_left_filter, name="days_left")

    # ROUTES
    from .routes_core import init_routes as init_core
    from .routes_odometer import init_routes as init_odo
    from .routes_insurance import init_routes as init_oc
    from .routes_inspection import init_routes as init_ti
    from .routes_service import init_routes as init_svc
    from .routes_fuel import init_routes as init_fuel
    from .routes_documents import init_routes as init_docs
    from .routes_intervals import init_routes as init_iv
    from .routes_backup import init_routes as init_backup

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

    return app
