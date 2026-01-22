from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash

from .extensions import db
from .models import Car, FuelEntry
from .helpers import parse_date, parse_decimal, upsert_odometer_for_date
from .validators import validate_odometer


def init_routes(app):
    # -------------------
    # FUEL
    # -------------------

    @app.post("/cars/<int:car_id>/fuel/new")
    def fuel_new(car_id):
        car = Car.query.get_or_404(car_id)

        when = parse_date(request.form.get("date"))
        km = int(request.form.get("km") or 0)

        liters = parse_decimal(request.form.get("liters"))
        if liters is None:
            flash("Podaj litry (np. 42,5).", "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        total_cost = parse_decimal(request.form.get("total_cost"))
        price_per_l = parse_decimal(request.form.get("price_per_l"))
        station = (request.form.get("station") or "").strip() or None
        note = (request.form.get("note") or "").strip() or None

        full_raw = (request.form.get("full_tank") or "").strip().lower()
        full_tank = full_raw in ("1", "true", "on", "yes", "y")

        ok, msg = validate_odometer(car.id, when, km, None)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        fill = FuelEntry(
            car_id=car.id,
            date=when,
            km=km,
            liters=liters,
            total_cost=total_cost,
            price_per_l=price_per_l,
            station=station,
            full_tank=full_tank,
            note=note,
        )
        db.session.add(fill)

        upsert_odometer_for_date(
            car_id=car.id,
            when=when,
            km=km,
            note="Tankowanie",
        )

        db.session.commit()
        flash("Dodano tankowanie ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.route("/fuel/<int:fill_id>/edit", methods=["GET", "POST"])
    def fuel_edit(fill_id):
        f = FuelEntry.query.get_or_404(fill_id)
        car = f.car

        if request.method == "POST":
            when = parse_date(request.form.get("date"))
            km = int(request.form.get("km") or 0)

            liters = parse_decimal(request.form.get("liters"))
            if liters is None:
                flash("Podaj litry (np. 42,5).", "danger")
                return redirect(url_for("fuel_edit", fill_id=f.id))

            total_cost = parse_decimal(request.form.get("total_cost"))
            price_per_l = parse_decimal(request.form.get("price_per_l"))
            station = (request.form.get("station") or "").strip() or None
            note = (request.form.get("note") or "").strip() or None

            full_raw = (request.form.get("full_tank") or "").strip().lower()
            full_tank = full_raw in ("1", "true", "on", "yes", "y")

            ok, msg = validate_odometer(car.id, when, km, None)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("fuel_edit", fill_id=f.id))

            f.date = when
            f.km = km
            f.liters = liters
            f.total_cost = total_cost
            f.price_per_l = price_per_l
            f.station = station
            f.full_tank = full_tank
            f.note = note

            upsert_odometer_for_date(
                car_id=car.id,
                when=when,
                km=km,
                note="Tankowanie (edycja)",
            )

            db.session.commit()
            flash("Zapisano tankowanie ✅", "success")
            return redirect(url_for("car_detail", car_id=car.id))

        return render_template("fuel_form.html", car=car, f=f)

    @app.post("/fuel/<int:fill_id>/delete")
    def fuel_delete(fill_id):
        f = FuelEntry.query.get_or_404(fill_id)
        car_id = f.car_id
        db.session.delete(f)
        db.session.commit()
        flash("Usunięto tankowanie 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))
