# car_manager/routes_auth.py
from __future__ import annotations

from functools import wraps
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash

from .models import User


def _safe_next_url(default: str = "/") -> str:
    nxt = (request.args.get("next") or request.form.get("next") or "").strip()
    if not nxt:
        return default

    p = urlparse(nxt)
    if p.scheme or p.netloc:
        return default
    if not nxt.startswith("/"):
        return default
    return nxt


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            flash("Brak uprawnień admina.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def init_routes(app: Flask) -> None:

    @app.get("/login")
    def login():
        if current_user.is_authenticated:
            return redirect(_safe_next_url(default=url_for("dashboard")))
        return render_template("login.html", next=_safe_next_url(default=url_for("dashboard")))

    @app.post("/login")
    def login_post():
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Podaj login i hasło.", "danger")
            return redirect(url_for("login", next=_safe_next_url(default=url_for("dashboard"))))

        u = User.query.filter_by(username=username).first()

        if not u or not u.is_active:
            flash("Nieprawidłowy login albo konto nieaktywne.", "danger")
            return redirect(url_for("login", next=_safe_next_url(default=url_for("dashboard"))))

        if not check_password_hash(u.password_hash, password):
            flash("Nieprawidłowy login lub hasło.", "danger")
            return redirect(url_for("login", next=_safe_next_url(default=url_for("dashboard"))))

        login_user(u)  # <- Flask-Login przejmuje stery sesji
        flash("Zalogowano ✅", "success")
        return redirect(_safe_next_url(default=url_for("dashboard")))

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Wylogowano.", "info")
        return redirect(url_for("login"))
