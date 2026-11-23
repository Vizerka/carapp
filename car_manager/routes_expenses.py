from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from .access import get_car_or_404, get_owned_entry_or_404
from .expense_categories import EXPENSE_CATEGORIES
from .extensions import db
from .helpers import parse_date, parse_decimal
from .models import Expense


def _expense_values():
    when = parse_date(request.form.get("date"))
    category = (request.form.get("category") or "").strip()
    amount = parse_decimal(request.form.get("amount"))
    title = (request.form.get("title") or "").strip()
    vendor = (request.form.get("vendor") or "").strip() or None
    note = (request.form.get("note") or "").strip() or None

    km_raw = (request.form.get("km") or "").strip()
    try:
        km = int(km_raw) if km_raw else None
    except ValueError:
        km = None

    errors = []
    if when is None:
        errors.append("Podaj prawidłową datę.")
    if category not in EXPENSE_CATEGORIES:
        errors.append("Wybierz prawidłową kategorię.")
    if amount is None or amount < 0:
        errors.append("Kwota musi być liczbą nie mniejszą niż zero.")
    if not title:
        errors.append("Podaj nazwę wydatku.")
    if km_raw and km is None:
        errors.append("Przebieg musi być liczbą całkowitą.")
    elif km is not None and km < 0:
        errors.append("Przebieg nie może być ujemny.")

    return {
        "date": when,
        "category": category,
        "amount": amount,
        "title": title,
        "vendor": vendor,
        "km": km,
        "note": note,
    }, errors


def init_routes(app):
    @app.post("/cars/<int:car_id>/expenses/new")
    def expense_new(car_id):
        car = get_car_or_404(car_id)
        values, errors = _expense_values()
        if errors:
            for message in errors:
                flash(message, "danger")
            return redirect(url_for("car_detail", car_id=car.id, tab="expenses"))

        db.session.add(Expense(car_id=car.id, **values))
        db.session.commit()
        flash("Dodano wydatek ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id, tab="expenses"))

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    def expense_edit(expense_id):
        expense = get_owned_entry_or_404(Expense, expense_id)
        if request.method == "POST":
            values, errors = _expense_values()
            if errors:
                for message in errors:
                    flash(message, "danger")
            else:
                for field, value in values.items():
                    setattr(expense, field, value)
                db.session.commit()
                flash("Zapisano wydatek ✅", "success")
                return redirect(url_for("car_detail", car_id=expense.car_id, tab="expenses"))

        return render_template(
            "expense_form.html",
            car=expense.car,
            expense=expense,
            expense_categories=EXPENSE_CATEGORIES,
        )

    @app.post("/expenses/<int:expense_id>/delete")
    def expense_delete(expense_id):
        expense = get_owned_entry_or_404(Expense, expense_id)
        car_id = expense.car_id
        db.session.delete(expense)
        db.session.commit()
        flash("Usunięto wydatek 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id, tab="expenses"))
