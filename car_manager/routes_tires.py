from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from .access import get_car_or_404, get_owned_entry_or_404
from .extensions import db
from .helpers import parse_date, parse_decimal
from .models import TireEvent, TireSet


SEASONS = {"summer": "Letnie", "winter": "Zimowe", "all_season": "Całoroczne"}
TIRE_ACTIONS = {"installed": "Założono", "removed": "Zdjęto", "inspection": "Pomiar"}


def _int(name):
    raw = (request.form.get(name) or "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _set_values():
    season = (request.form.get("season") or "").strip()
    values = {
        "name": (request.form.get("name") or "").strip(),
        "season": season,
        "manufacturer": (request.form.get("manufacturer") or "").strip() or None,
        "model": (request.form.get("model") or "").strip() or None,
        "width": _int("width"),
        "aspect_ratio": _int("aspect_ratio"),
        "diameter": _int("diameter"),
        "dot": (request.form.get("dot") or "").strip() or None,
        "rim": (request.form.get("rim") or "").strip() or None,
        "recommended_pressure": (request.form.get("recommended_pressure") or "").strip() or None,
        "storage_location": (request.form.get("storage_location") or "").strip() or None,
        "note": (request.form.get("note") or "").strip() or None,
        "active": request.form.get("active", "1") == "1",
    }
    errors = []
    if not values["name"]:
        errors.append("Podaj nazwę kompletu.")
    if season not in SEASONS:
        errors.append("Wybierz rodzaj opon.")
    return values, errors


def _event_values():
    action = (request.form.get("action") or "").strip()
    km = _int("km")
    values = {
        "date": parse_date(request.form.get("date")),
        "km": km,
        "action": action,
        "tread_fl": parse_decimal(request.form.get("tread_fl")),
        "tread_fr": parse_decimal(request.form.get("tread_fr")),
        "tread_rl": parse_decimal(request.form.get("tread_rl")),
        "tread_rr": parse_decimal(request.form.get("tread_rr")),
        "pressure": (request.form.get("pressure") or "").strip() or None,
        "note": (request.form.get("note") or "").strip() or None,
    }
    errors = []
    if values["date"] is None:
        errors.append("Podaj prawidłową datę.")
    if action not in TIRE_ACTIONS:
        errors.append("Wybierz rodzaj zdarzenia.")
    if km is not None and km < 0:
        errors.append("Przebieg nie może być ujemny.")
    return values, errors


def init_routes(app):
    @app.route("/cars/<int:car_id>/tires/new", methods=["GET", "POST"])
    def tire_set_new(car_id):
        car = get_car_or_404(car_id)
        if request.method == "POST":
            values, errors = _set_values()
            if not errors:
                db.session.add(TireSet(car_id=car.id, **values))
                db.session.commit()
                flash("Dodano komplet opon ✅", "success")
                return redirect(url_for("car_detail", car_id=car.id, tab="tires"))
            for message in errors:
                flash(message, "danger")
        return render_template("tire_set_form.html", car=car, tire_set=None, seasons=SEASONS)

    @app.route("/tires/<int:set_id>/edit", methods=["GET", "POST"])
    def tire_set_edit(set_id):
        tire_set = get_owned_entry_or_404(TireSet, set_id)
        if request.method == "POST":
            values, errors = _set_values()
            if not errors:
                for field, value in values.items():
                    setattr(tire_set, field, value)
                db.session.commit()
                flash("Zapisano komplet opon ✅", "success")
                return redirect(url_for("car_detail", car_id=tire_set.car_id, tab="tires"))
            for message in errors:
                flash(message, "danger")
        return render_template("tire_set_form.html", car=tire_set.car, tire_set=tire_set, seasons=SEASONS)

    @app.post("/tires/<int:set_id>/delete")
    def tire_set_delete(set_id):
        tire_set = get_owned_entry_or_404(TireSet, set_id)
        car_id = tire_set.car_id
        db.session.delete(tire_set)
        db.session.commit()
        flash("Usunięto komplet opon 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id, tab="tires"))

    @app.route("/tires/<int:set_id>/events/new", methods=["GET", "POST"])
    def tire_event_new(set_id):
        tire_set = get_owned_entry_or_404(TireSet, set_id)
        if request.method == "POST":
            values, errors = _event_values()
            if not errors:
                db.session.add(TireEvent(tire_set_id=tire_set.id, **values))
                db.session.commit()
                flash("Dodano zdarzenie opon ✅", "success")
                return redirect(url_for("car_detail", car_id=tire_set.car_id, tab="tires"))
            for message in errors:
                flash(message, "danger")
        return render_template("tire_event_form.html", tire_set=tire_set, event=None, actions=TIRE_ACTIONS)

    @app.route("/tire-events/<int:event_id>/edit", methods=["GET", "POST"])
    def tire_event_edit(event_id):
        event = get_owned_entry_or_404(TireEvent, event_id)
        if request.method == "POST":
            values, errors = _event_values()
            if not errors:
                for field, value in values.items():
                    setattr(event, field, value)
                db.session.commit()
                flash("Zapisano zdarzenie opon ✅", "success")
                return redirect(url_for("car_detail", car_id=event.car.id, tab="tires"))
            for message in errors:
                flash(message, "danger")
        return render_template("tire_event_form.html", tire_set=event.tire_set, event=event, actions=TIRE_ACTIONS)

    @app.post("/tire-events/<int:event_id>/delete")
    def tire_event_delete(event_id):
        event = get_owned_entry_or_404(TireEvent, event_id)
        car_id = event.car.id
        db.session.delete(event)
        db.session.commit()
        flash("Usunięto zdarzenie opon 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id, tab="tires"))
