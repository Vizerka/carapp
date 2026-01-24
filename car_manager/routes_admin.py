# car_manager/routes_admin.py
from __future__ import annotations

from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User


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

    @app.get("/admin/users")
    @admin_required
    def admin_users():
        users = User.query.order_by(User.username).all()
        return render_template("admin/users_list.html", users=users)

    @app.route("/admin/users/new", methods=["GET", "POST"])
    @admin_required
    def admin_user_new():
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            email = (request.form.get("email") or "").strip() or None
            password = request.form.get("password") or ""
            is_admin = bool(request.form.get("is_admin"))
            is_active = bool(request.form.get("is_active"))

            if not username:
                flash("Username jest wymagany.", "danger")
                return redirect(url_for("admin_user_new"))

            if User.query.filter_by(username=username).first():
                flash("Taki username już istnieje.", "danger")
                return redirect(url_for("admin_user_new"))

            if email and User.query.filter_by(email=email).first():
                flash("Taki email już istnieje.", "danger")
                return redirect(url_for("admin_user_new"))

            if len(password) < 6:
                flash("Hasło min 6 znaków.", "danger")
                return redirect(url_for("admin_user_new"))

            u = User(
                username=username,
                email=email,
                is_admin=is_admin,
                is_active=is_active,
                password_hash=generate_password_hash(password),
            )
            db.session.add(u)
            db.session.commit()
            flash("Użytkownik dodany ✅", "success")
            return redirect(url_for("admin_users"))

        return render_template("admin/user_form.html", mode="new", u=None)

    @app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_user_edit(user_id: int):
        u = User.query.get_or_404(user_id)

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            email = (request.form.get("email") or "").strip() or None
            password = request.form.get("password") or ""
            is_admin = bool(request.form.get("is_admin"))
            is_active = bool(request.form.get("is_active"))

            if not username:
                flash("Username jest wymagany.", "danger")
                return redirect(url_for("admin_user_edit", user_id=user_id))

            # unikalność username/email (z wykluczeniem siebie)
            q = User.query.filter(User.username == username, User.id != u.id).first()
            if q:
                flash("Taki username już istnieje.", "danger")
                return redirect(url_for("admin_user_edit", user_id=user_id))

            if email:
                q2 = User.query.filter(User.email == email, User.id != u.id).first()
                if q2:
                    flash("Taki email już istnieje.", "danger")
                    return redirect(url_for("admin_user_edit", user_id=user_id))

            # nie pozwól sobie odciąć gałęzi (wyłączanie siebie / zabieranie admina)
            if u.id == current_user.id:
                is_active = True
                is_admin = True

            u.username = username
            u.email = email
            u.is_admin = is_admin
            u.is_active = is_active

            if password:
                if len(password) < 6:
                    flash("Hasło min 6 znaków.", "danger")
                    return redirect(url_for("admin_user_edit", user_id=user_id))
                u.password_hash = generate_password_hash(password)

            db.session.commit()
            flash("Zapisano ✅", "success")
            return redirect(url_for("admin_users"))

        return render_template("admin/user_form.html", mode="edit", u=u)

    @app.post("/admin/users/<int:user_id>/delete")
    @admin_required
    def admin_user_delete(user_id: int):
        u = User.query.get_or_404(user_id)
        if u.id == current_user.id:
            flash("Nie możesz usunąć samej siebie.", "danger")
            return redirect(url_for("admin_users"))

        db.session.delete(u)
        db.session.commit()
        flash("Użytkownik usunięty 🗑️", "success")
        return redirect(url_for("admin_users"))
