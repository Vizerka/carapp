from __future__ import annotations

from datetime import date

from flask import flash, redirect, render_template, request, url_for

from .access import get_car_or_404, get_owned_entry_or_404
from .document_links import delete_links_for_target
from .extensions import db
from .helpers import parse_date, parse_decimal
from .models import Modification, ModificationTask


STATUSES = {
    "planned": "Planowana",
    "parts_ordered": "Części zamówione",
    "in_progress": "W trakcie",
    "done": "Gotowa",
    "cancelled": "Anulowana",
}


def _values():
    status = (request.form.get("status") or "planned").strip()
    values = {
        "title": (request.form.get("title") or "").strip(),
        "description": (request.form.get("description") or "").strip() or None,
        "status": status,
        "started_date": parse_date(request.form.get("started_date")),
        "completed_date": parse_date(request.form.get("completed_date")),
        "estimated_cost": parse_decimal(request.form.get("estimated_cost")),
        "actual_cost": parse_decimal(request.form.get("actual_cost")),
        "note": (request.form.get("note") or "").strip() or None,
    }
    errors = []
    if not values["title"]:
        errors.append("Podaj nazwę modyfikacji.")
    if status not in STATUSES:
        errors.append("Wybierz prawidłowy status.")
    for field in ("estimated_cost", "actual_cost"):
        if values[field] is not None and values[field] < 0:
            errors.append("Koszt nie może być ujemny.")
    if status == "done" and values["completed_date"] is None:
        values["completed_date"] = date.today()
    return values, errors


def init_routes(app):
    @app.route("/cars/<int:car_id>/modifications/new", methods=["GET", "POST"])
    def modification_new(car_id):
        car = get_car_or_404(car_id)
        if request.method == "POST":
            values, errors = _values()
            if not errors:
                modification = Modification(car_id=car.id, **values)
                db.session.add(modification)
                db.session.commit()
                flash("Dodano projekt modyfikacji ✅", "success")
                return redirect(url_for("modification_edit", modification_id=modification.id))
            for message in errors:
                flash(message, "danger")
        return render_template("modification_form.html", car=car, modification=None, statuses=STATUSES)

    @app.route("/modifications/<int:modification_id>/edit", methods=["GET", "POST"])
    def modification_edit(modification_id):
        modification = get_owned_entry_or_404(Modification, modification_id)
        if request.method == "POST":
            values, errors = _values()
            if not errors:
                for field, value in values.items():
                    setattr(modification, field, value)
                db.session.commit()
                flash("Zapisano modyfikację ✅", "success")
                return redirect(url_for("car_detail", car_id=modification.car_id, tab="mods"))
            for message in errors:
                flash(message, "danger")
        return render_template(
            "modification_form.html",
            car=modification.car,
            modification=modification,
            statuses=STATUSES,
        )

    @app.post("/modifications/<int:modification_id>/delete")
    def modification_delete(modification_id):
        modification = get_owned_entry_or_404(Modification, modification_id)
        car_id = modification.car_id
        delete_links_for_target("modification", modification.id)
        db.session.delete(modification)
        db.session.commit()
        flash("Usunięto modyfikację 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id, tab="mods"))

    @app.post("/modifications/<int:modification_id>/tasks/new")
    def modification_task_new(modification_id):
        modification = get_owned_entry_or_404(Modification, modification_id)
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Podaj nazwę zadania.", "danger")
        else:
            position = max((task.position for task in modification.tasks), default=-1) + 1
            db.session.add(ModificationTask(
                modification_id=modification.id, title=title, position=position
            ))
            db.session.commit()
            flash("Dodano zadanie ✅", "success")
        return redirect(url_for("modification_edit", modification_id=modification.id))

    @app.post("/modification-tasks/<int:task_id>/toggle")
    def modification_task_toggle(task_id):
        task = get_owned_entry_or_404(ModificationTask, task_id)
        task.done = not task.done
        db.session.commit()
        return redirect(url_for("modification_edit", modification_id=task.modification_id))

    @app.post("/modification-tasks/<int:task_id>/delete")
    def modification_task_delete(task_id):
        task = get_owned_entry_or_404(ModificationTask, task_id)
        modification_id = task.modification_id
        db.session.delete(task)
        db.session.commit()
        flash("Usunięto zadanie 🗑️", "success")
        return redirect(url_for("modification_edit", modification_id=modification_id))
