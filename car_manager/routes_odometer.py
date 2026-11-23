from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash
from .extensions import db
from .models import OdometerEntry
from .helpers import parse_date
from .validators import validate_odometer
from .access import get_car_or_404, get_owned_entry_or_404


def init_routes(app):
    # -------------------
    # ODOMETER
    # -------------------

    @app.post("/cars/<int:car_id>/odometer/new")
    def odometer_new(car_id):
        car = get_car_or_404(car_id)
        when = parse_date(request.form.get("date"))
        km = int(request.form.get("km") or 0)

        ok, msg = validate_odometer(car.id, when, km, None)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        entry = OdometerEntry(
            car_id=car.id,
            date=when,
            km=km,
            note=(request.form.get("note") or "").strip() or None,
        )
        db.session.add(entry)
        db.session.commit()
        flash("Dodano wpis przebiegu ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.route("/odometer/<int:entry_id>/edit", methods=["GET", "POST"])
    def odometer_edit(entry_id):
        entry = get_owned_entry_or_404(OdometerEntry, entry_id)
        car = entry.car

        if entry.source_type:
            flash("Ten przebieg jest zarządzany przez powiązane tankowanie albo serwis.", "warning")
            return redirect(url_for("car_detail", car_id=car.id))

        if request.method == "POST":
            when = parse_date(request.form.get("date"))
            km = int(request.form.get("km") or 0)

            ok, msg = validate_odometer(car.id, when, km, entry.id)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("odometer_edit", entry_id=entry.id))

            entry.date = when
            entry.km = km
            entry.note = (request.form.get("note") or "").strip() or None
            db.session.commit()

            flash("Zaktualizowano wpis przebiegu ✅", "success")
            return redirect(url_for("car_detail", car_id=car.id))

        return render_template("odometer_form.html", car=car, entry=entry)

    @app.post("/odometer/<int:entry_id>/delete")
    def odometer_delete(entry_id):
        entry = get_owned_entry_or_404(OdometerEntry, entry_id)
        car_id = entry.car_id
        if entry.source_type:
            flash("Automatyczny wpis usuń razem z powiązanym tankowaniem albo serwisem.", "warning")
            return redirect(url_for("car_detail", car_id=car_id))
        db.session.delete(entry)
        db.session.commit()
        flash("Usunięto wpis przebiegu 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))
