from __future__ import annotations

from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for

from .access import get_owned_entry_or_404
from .extensions import db
from .helpers import parse_decimal
from .models import ServiceEntry, ServiceItem


ITEM_TYPES = {
    "part": "Część",
    "labor": "Robocizna",
    "fluid": "Płyn / materiał",
    "other": "Inne",
}


def _values():
    item_type = (request.form.get("item_type") or "part").strip()
    name = (request.form.get("name") or "").strip()
    quantity = parse_decimal(request.form.get("quantity")) or Decimal("1")
    unit_price = parse_decimal(request.form.get("unit_price"))
    values = {
        "item_type": item_type,
        "name": name,
        "manufacturer": (request.form.get("manufacturer") or "").strip() or None,
        "part_number": (request.form.get("part_number") or "").strip() or None,
        "quantity": quantity,
        "unit_price": unit_price,
        "note": (request.form.get("note") or "").strip() or None,
    }
    errors = []
    if item_type not in ITEM_TYPES:
        errors.append("Nieprawidłowy typ pozycji.")
    if not name:
        errors.append("Podaj nazwę pozycji.")
    if quantity <= 0:
        errors.append("Ilość musi być większa od zera.")
    if unit_price is not None and unit_price < 0:
        errors.append("Cena nie może być ujemna.")
    return values, errors


def _sync_total(service):
    totals = [
        item.total_cost
        for item in ServiceItem.query.filter_by(service_id=service.id).all()
        if item.total_cost is not None
    ]
    if totals:
        service.cost = sum(totals, Decimal("0"))
    else:
        service.cost = None


def init_routes(app):
    @app.post("/service/<int:service_id>/items/new")
    def service_item_new(service_id):
        service = get_owned_entry_or_404(ServiceEntry, service_id)
        values, errors = _values()
        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            db.session.add(ServiceItem(service_id=service.id, **values))
            db.session.flush()
            _sync_total(service)
            db.session.commit()
            flash("Dodano pozycję serwisową ✅", "success")
        return redirect(url_for("service_edit", service_id=service.id))

    @app.route("/service-items/<int:item_id>/edit", methods=["GET", "POST"])
    def service_item_edit(item_id):
        item = get_owned_entry_or_404(ServiceItem, item_id)
        if request.method == "POST":
            values, errors = _values()
            if errors:
                for message in errors:
                    flash(message, "danger")
            else:
                for field, value in values.items():
                    setattr(item, field, value)
                _sync_total(item.service)
                db.session.commit()
                flash("Zapisano pozycję serwisową ✅", "success")
                return redirect(url_for("service_edit", service_id=item.service_id))
        return render_template("service_item_form.html", item=item, item_types=ITEM_TYPES)

    @app.post("/service-items/<int:item_id>/delete")
    def service_item_delete(item_id):
        item = get_owned_entry_or_404(ServiceItem, item_id)
        service = item.service
        db.session.delete(item)
        db.session.flush()
        _sync_total(service)
        db.session.commit()
        flash("Usunięto pozycję serwisową 🗑️", "success")
        return redirect(url_for("service_edit", service_id=service.id))
