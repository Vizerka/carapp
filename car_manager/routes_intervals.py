from __future__ import annotations

from datetime import date
from flask import request, redirect, url_for, flash, render_template

from .extensions import db
from .models import Car, ServiceInterval
from .helpers import parse_date


def init_routes(app):
    # -------------------
    # SERVICE INTERVALS
    # -------------------

    @app.post("/cars/<int:car_id>/intervals/new")
    def interval_new(car_id):
        car = Car.query.get_or_404(car_id)

        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Podaj nazwę interwału.", "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        def to_int(x):
            x = (x or "").strip()
            return int(x) if x else None

        iv = ServiceInterval(
            car_id=car.id,
            name=name,
            interval_km=to_int(request.form.get("interval_km")),
            interval_days=to_int(request.form.get("interval_days")),
            last_done_km=to_int(request.form.get("last_done_km")),
            last_done_date=parse_date(request.form.get("last_done_date")),
            note=(request.form.get("note") or "").strip() or None,
            active=True,
        )
        db.session.add(iv)
        db.session.commit()
        flash("Dodano interwał serwisowy ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.route("/intervals/<int:interval_id>/edit", methods=["GET", "POST"])
    def interval_edit(interval_id):
        iv = ServiceInterval.query.get_or_404(interval_id)
        car_id = iv.car_id

        def to_int(x):
            x = (x or "").strip()
            return int(x) if x else None

        if request.method == "POST":
            iv.name = (request.form.get("name") or "").strip() or iv.name
            iv.interval_km = to_int(request.form.get("interval_km"))
            iv.interval_days = to_int(request.form.get("interval_days"))
            iv.last_done_km = to_int(request.form.get("last_done_km"))
            iv.last_done_date = parse_date(request.form.get("last_done_date"))
            iv.note = (request.form.get("note") or "").strip() or None
            iv.active = (request.form.get("active") == "1")

            db.session.commit()
            flash("Zapisano interwał ✅", "success")
            return redirect(url_for("car_detail", car_id=car_id))

        return render_template("service_interval_form.html", iv=iv)

    @app.post("/intervals/<int:interval_id>/delete")
    def interval_delete(interval_id):
        iv = ServiceInterval.query.get_or_404(interval_id)
        car_id = iv.car_id
        db.session.delete(iv)
        db.session.commit()
        flash("Usunięto interwał 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))

    @app.post("/intervals/<int:interval_id>/mark_done")
    def interval_mark_done(interval_id):
        iv = ServiceInterval.query.get_or_404(interval_id)
        car = Car.query.get_or_404(iv.car_id)

        when = parse_date(request.form.get("date")) or date.today()
        km_raw = (request.form.get("km") or "").strip()
        km = int(km_raw) if km_raw else None

        iv.last_done_date = when
        if km is not None:
            iv.last_done_km = km

        db.session.commit()
        flash("Zaksięgowano wykonanie interwału ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))
