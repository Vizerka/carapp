from __future__ import annotations

from datetime import date
from decimal import Decimal
from flask import render_template, request, redirect, url_for, flash

from .extensions import db
from .models import ServiceEntry, ServiceInterval, ServiceItem
from .helpers import (
    delete_source_odometer,
    parse_date,
    parse_decimal,
    source_odometer_id,
    sync_source_odometer,
)
from .validators import validate_odometer
from .access import get_car_or_404, get_owned_entry_or_404
from .document_links import delete_links_for_target
from .routes_service_items import ITEM_TYPES


def _items_from_create_form():
    fields = {
        "item_type": request.form.getlist("item_type[]"),
        "name": request.form.getlist("item_name[]"),
        "manufacturer": request.form.getlist("item_manufacturer[]"),
        "part_number": request.form.getlist("item_part_number[]"),
        "quantity": request.form.getlist("item_quantity[]"),
        "unit_price": request.form.getlist("item_unit_price[]"),
        "note": request.form.getlist("item_note[]"),
    }
    row_count = max((len(values) for values in fields.values()), default=0)
    items = []
    errors = []

    def value(field, index):
        values = fields[field]
        return values[index] if index < len(values) else ""

    for index in range(row_count):
        name = value("name", index).strip()
        if not name:
            continue
        item_type = value("item_type", index).strip() or "part"
        quantity = parse_decimal(value("quantity", index)) or Decimal("1")
        unit_price = parse_decimal(value("unit_price", index))
        row_number = index + 1
        if item_type not in ITEM_TYPES:
            errors.append(f"Pozycja {row_number}: nieprawidłowy typ.")
            continue
        if quantity <= 0:
            errors.append(f"Pozycja {row_number}: ilość musi być większa od zera.")
            continue
        if unit_price is not None and unit_price < 0:
            errors.append(f"Pozycja {row_number}: cena nie może być ujemna.")
            continue
        items.append(ServiceItem(
            item_type=item_type,
            name=name,
            manufacturer=value("manufacturer", index).strip() or None,
            part_number=value("part_number", index).strip() or None,
            quantity=quantity,
            unit_price=unit_price,
            note=value("note", index).strip() or None,
        ))
    return items, errors


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

        items, item_errors = _items_from_create_form()
        if item_errors:
            for message in item_errors:
                flash(message, "danger")
            return redirect(url_for("car_detail", car_id=car.id, tab="svc"))

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
        priced_totals = [item.total_cost for item in items if item.total_cost is not None]
        entry.cost = cost if cost is not None else (
            sum(priced_totals, Decimal("0")) if priced_totals else None
        )

        if km is not None:
            ok, msg = validate_odometer(car.id, when, km, None)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("car_detail", car_id=car.id))

        db.session.add(entry)
        db.session.flush()

        for item in items:
            item.service_id = entry.id
            db.session.add(item)

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
        return redirect(url_for("car_detail", car_id=car.id, tab="svc"))

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

        return render_template("service_form.html", car=car, s=s, item_types=ITEM_TYPES)

    @app.post("/service/<int:service_id>/delete")
    def service_delete(service_id):
        s = get_owned_entry_or_404(ServiceEntry, service_id)
        car_id = s.car_id
        delete_links_for_target("service", s.id)
        delete_source_odometer(source_type="service", source_id=s.id)
        db.session.delete(s)
        db.session.commit()
        flash("Usunięto wpis serwisowy 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))
