from __future__ import annotations

from datetime import date
from flask import render_template, request, redirect, url_for, flash

from .extensions import db
from .models import ServiceEntry, ServiceInterval
from .helpers import (
    delete_source_odometer,
    parse_date,
    parse_decimal,
    source_odometer_id,
    sync_source_odometer,
)
from .validators import validate_odometer
from .access import get_car_or_404, get_owned_entry_or_404


def init_routes(app):
    # -------------------
    # SERVICE
    # -------------------

    @app.post("/cars/<int:car_id>/service/new")
    def service_new(car_id):
        car = get_car_or_404(car_id)

        when = parse_date(request.form.get("date"))
        km = int(request.form.get("km") or 0) or None

        interval_id_raw = (request.form.get("interval_id") or "").strip()
        interval_id = int(interval_id_raw) if interval_id_raw else None

        entry = ServiceEntry(
            car_id=car.id,
            date=when,
            km=km,
            title=(request.form.get("title") or "").strip(),
            description=(request.form.get("description") or "").strip() or None,
            vendor=(request.form.get("vendor") or "").strip() or None,
            note=(request.form.get("note") or "").strip() or None,
        )
        cost = parse_decimal(request.form.get("cost"))
        entry.cost = cost if cost is not None else None

        if km is not None:
            ok, msg = validate_odometer(car.id, when, km, None)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("car_detail", car_id=car.id))

        db.session.add(entry)
        db.session.flush()

        if km is not None:
            sync_source_odometer(
                car_id=car.id,
                when=when,
                km=km,
                source_type="service",
                source_id=entry.id,
                note=f"Serwis: {entry.title}",
            )

        if interval_id:
            iv = ServiceInterval.query.get(interval_id)
            if iv and iv.car_id == car.id:
                iv.last_done_date = when or date.today()
                if km is not None:
                    iv.last_done_km = km

        db.session.commit()
        flash("Dodano wpis serwisowy ✅", "success")
        if km is not None:
            flash("Przebieg zaktualizowany na podstawie serwisu ✅", "info")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.route("/service/<int:service_id>/edit", methods=["GET", "POST"])
    def service_edit(service_id):
        s = get_owned_entry_or_404(ServiceEntry, service_id)
        car = s.car

        if request.method == "POST":
            when = parse_date(request.form.get("date"))
            km = int(request.form.get("km") or 0) or None
            title = (request.form.get("title") or "").strip()

            if km is not None:
                odo_id = source_odometer_id(source_type="service", source_id=s.id)
                ok, msg = validate_odometer(car.id, when, km, odo_id)
                if not ok:
                    flash(msg, "danger")
                    return redirect(url_for("service_edit", service_id=s.id))

            s.date = when
            s.km = km
            s.title = title
            s.description = (request.form.get("description") or "").strip() or None
            s.vendor = (request.form.get("vendor") or "").strip() or None
            s.note = (request.form.get("note") or "").strip() or None
            s.cost = parse_decimal(request.form.get("cost"))

            if km is None:
                delete_source_odometer(source_type="service", source_id=s.id)
            else:
                sync_source_odometer(
                    car_id=car.id,
                    when=when,
                    km=km,
                    source_type="service",
                    source_id=s.id,
                    note=f"Serwis: {title}",
                )

            db.session.commit()
            flash("Zapisano serwis ✅", "success")
            return redirect(url_for("car_detail", car_id=car.id))

        return render_template("service_form.html", car=car, s=s)

    @app.post("/service/<int:service_id>/delete")
    def service_delete(service_id):
        s = get_owned_entry_or_404(ServiceEntry, service_id)
        car_id = s.car_id
        delete_source_odometer(source_type="service", source_id=s.id)
        db.session.delete(s)
        db.session.commit()
        flash("Usunięto wpis serwisowy 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))
