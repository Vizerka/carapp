from __future__ import annotations

import os
import shutil
from datetime import date, timedelta
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import (
    Car, OdometerEntry, InsurancePolicy, TechInspection,
    ServiceEntry, FuelEntry, Document, ServiceInterval, Expense, Modification,
    TireEvent, TireSet
)
from .helpers import parse_date, compute_interval_status
from .access import accessible_cars_query, get_car_or_404
from .expense_categories import EXPENSE_CATEGORIES
from .document_links import document_link_label, document_target_options
from .routes_modifications import STATUSES as MODIFICATION_STATUSES
from .routes_tires import SEASONS as TIRE_SEASONS
from .statistics import fuel_statistics, tire_set_mileage
from .timeline import build_timeline

def init_routes(app):
    @app.get("/")
    def dashboard():
        cars = accessible_cars_query().order_by(Car.make, Car.model).all()

        upcoming_days = 60
        today = date.today()
        oc_upcoming, ti_upcoming = [], []
        oc_expired, ti_expired = [], []

        for c in cars:
            if c.last_insurance and c.last_insurance.valid_to:
                d = c.last_insurance.valid_to
                if d < today:
                    oc_expired.append((c, d))
                elif d <= today + timedelta(days=upcoming_days):
                    oc_upcoming.append((c, d))

            if c.last_inspection and c.last_inspection.valid_to:
                d = c.last_inspection.valid_to
                if d < today:
                    ti_expired.append((c, d))
                elif d <= today + timedelta(days=upcoming_days):
                    ti_upcoming.append((c, d))

        oc_upcoming.sort(key=lambda t: t[1])
        ti_upcoming.sort(key=lambda t: t[1])
        oc_expired.sort(key=lambda t: t[1])
        ti_expired.sort(key=lambda t: t[1])

        return render_template(
            "index.html",
            cars_count=len(cars),
            oc_upcoming=oc_upcoming,
            ti_upcoming=ti_upcoming,
            oc_expired=oc_expired,
            ti_expired=ti_expired,
            upcoming_days=upcoming_days
        )

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/cars")
    def list_cars():
        cars = accessible_cars_query().order_by(Car.make, Car.model).all()
        return render_template("cars.html", cars=cars)

    @app.route("/cars/new", methods=["GET", "POST"])
    def car_new():
        if request.method == "POST":
            car = Car(
                make=(request.form.get("make") or "").strip(),
                model=(request.form.get("model") or "").strip(),
                year=int(request.form.get("year") or 0) or None,
                vin=(request.form.get("vin") or "").strip().upper() or None,
                reg_number=(request.form.get("reg_number") or "").strip().upper() or None,
                first_registration=parse_date(request.form.get("first_registration"))
            )
            if not current_user.is_admin:
                car.owners.append(current_user)
            db.session.add(car)
            try:
                db.session.commit()
                flash("Dodano auto ✅", "success")
                return redirect(url_for("list_cars"))
            except IntegrityError:
                db.session.rollback()
                flash("VIN albo numer rejestracyjny już istnieje w bazie.", "danger")

        return render_template("car_form.html", car=None)

    @app.route("/cars/<int:car_id>/edit", methods=["GET", "POST"])
    def car_edit(car_id):
        car = get_car_or_404(car_id)
        if request.method == "POST":
            car.make = (request.form.get("make") or "").strip()
            car.model = (request.form.get("model") or "").strip()
            car.year = int(request.form.get("year") or 0) or None
            car.vin = (request.form.get("vin") or "").strip().upper() or None
            car.reg_number = (request.form.get("reg_number") or "").strip().upper() or None
            car.first_registration = parse_date(request.form.get("first_registration"))

            try:
                db.session.commit()
                flash("Zapisano zmiany auta ✅", "success")
                return redirect(url_for("car_detail", car_id=car.id))
            except IntegrityError:
                db.session.rollback()
                flash("VIN albo numer rejestracyjny już istnieje w bazie.", "danger")

        return render_template("car_form.html", car=car)

    @app.get("/cars/<int:car_id>")
    def car_detail(car_id):
        car = get_car_or_404(car_id)

        # --- TAB + paginacja (oddzielna dla każdej listy) ---
        tab = request.args.get("tab", "dash")

        fuel_page = request.args.get("fuel_page", 1, type=int)
        svc_page  = request.args.get("svc_page", 1, type=int)
        docs_page = request.args.get("docs_page", 1, type=int)
        odo_page = request.args.get("odo_page", 1, type=int)
        expense_page = request.args.get("expense_page", 1, type=int)
        mods_page = request.args.get("mods_page", 1, type=int)
        timeline_page = request.args.get("timeline_page", 1, type=int)
        
        PER_PAGE_ODO = 30
        PER_PAGE_FUEL = 20
        PER_PAGE_SVC  = 20
        PER_PAGE_DOCS = 15
        PER_PAGE_EXPENSES = 20
        PER_PAGE_MODS = 15

        odo_p = (
            car.odometer_entries
            .order_by(desc(OdometerEntry.date), desc(OdometerEntry.id))
            .paginate(page=odo_page, per_page=PER_PAGE_ODO, error_out=False)
        )

        # wykres zostaw jak masz:
        odo_asc = car.odometer_entries.order_by(OdometerEntry.date.asc(), OdometerEntry.id.asc()).all()
        odo_labels = [e.date.isoformat() for e in odo_asc]
        odo_values = [e.km for e in odo_asc]

        # --- OC / TI bez paginacji (zwykle mało) ---
        oc = car.insurance_policies.order_by(desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)).all()
        ti = car.tech_inspections.order_by(desc(TechInspection.valid_to), desc(TechInspection.id)).all()

        # --- Paginacja: serwis ---
        services_p = (
            car.service_entries
            .order_by(desc(ServiceEntry.date), desc(ServiceEntry.id))
            .paginate(page=svc_page, per_page=PER_PAGE_SVC, error_out=False)
        )

        # --- Paginacja: dokumenty ---
        docs_p = (
            car.documents
            .order_by(desc(Document.uploaded_at), desc(Document.id))
            .paginate(page=docs_page, per_page=PER_PAGE_DOCS, error_out=False)
        )

        expenses_p = (
            car.expenses
            .order_by(desc(Expense.date), desc(Expense.id))
            .paginate(page=expense_page, per_page=PER_PAGE_EXPENSES, error_out=False)
        )

        modifications_p = (
            car.modifications
            .order_by(desc(Modification.id))
            .paginate(page=mods_page, per_page=PER_PAGE_MODS, error_out=False)
        )

        tire_sets = car.tire_sets.order_by(TireSet.active.desc(), TireSet.name.asc()).all()
        tire_events = {
            tire_set.id: tire_set.events.order_by(
                desc(TireEvent.date), desc(TireEvent.id)
            ).all()
            for tire_set in tire_sets
        }

        # --- Paginacja: tankowania ---
        fills_p = (
            car.fuel_entries
            .order_by(desc(FuelEntry.date), desc(FuelEntry.id))
            .paginate(page=fuel_page, per_page=PER_PAGE_FUEL, error_out=False)
        )

        # --- Do wykresu spalania potrzebujemy ASC (pełny->pełny) ---
        fills_asc = car.fuel_entries.order_by(FuelEntry.date.asc(), FuelEntry.id.asc()).all()
        fuel_stats = fuel_statistics(fills_asc)

        # --- Pełny koszt posiadania + okres raportu ---
        today = date.today()
        cost_period = request.args.get("cost_period", "all")
        if cost_period not in {"all", "year", "12m"}:
            cost_period = "all"

        cost_since = None
        if cost_period == "year":
            cost_since = date(today.year, 1, 1)
        elif cost_period == "12m":
            cost_since = today - timedelta(days=365)

        fuel_query = db.session.query(func.sum(FuelEntry.total_cost)).filter(
            FuelEntry.car_id == car.id, FuelEntry.total_cost.isnot(None)
        )
        service_query = db.session.query(func.sum(ServiceEntry.cost)).filter(
            ServiceEntry.car_id == car.id, ServiceEntry.cost.isnot(None)
        )
        expense_query = db.session.query(func.sum(Expense.amount)).filter(
            Expense.car_id == car.id
        )
        modification_query = db.session.query(func.sum(Modification.actual_cost)).filter(
            Modification.car_id == car.id, Modification.actual_cost.isnot(None)
        )

        if cost_since is not None:
            fuel_query = fuel_query.filter(FuelEntry.date >= cost_since)
            service_query = service_query.filter(ServiceEntry.date >= cost_since)
            expense_query = expense_query.filter(Expense.date >= cost_since)
            modification_query = modification_query.filter(
                func.coalesce(Modification.completed_date, Modification.started_date) >= cost_since
            )

        fuel_total = fuel_query.scalar()
        service_total = service_query.scalar()
        expense_total = expense_query.scalar()
        modification_total = modification_query.scalar()

        fuel_total = Decimal(fuel_total) if fuel_total is not None else None
        service_total = Decimal(service_total) if service_total is not None else None
        expense_total = Decimal(expense_total) if expense_total is not None else None
        modification_total = Decimal(modification_total) if modification_total is not None else None

        total_cost = None
        if any(value is not None for value in (fuel_total, service_total, expense_total, modification_total)):
            total_cost = sum(
                (value or Decimal("0") for value in (
                    fuel_total, service_total, expense_total, modification_total
                )),
                Decimal("0"),
            )

        expense_breakdown_query = db.session.query(
            Expense.category, func.sum(Expense.amount)
        ).filter(Expense.car_id == car.id)
        if cost_since is not None:
            expense_breakdown_query = expense_breakdown_query.filter(Expense.date >= cost_since)
        expense_breakdown = [
            {
                "key": category,
                "label": EXPENSE_CATEGORIES.get(category, category),
                "amount": Decimal(amount),
            }
            for category, amount in expense_breakdown_query.group_by(Expense.category).all()
        ]
        cost_breakdown = [
            {"key": "fuel", "label": "Paliwo", "amount": fuel_total or Decimal("0")},
            {"key": "service", "label": "Serwis", "amount": service_total or Decimal("0")},
            {
                "key": "modification",
                "label": "Modyfikacje",
                "amount": modification_total or Decimal("0"),
            },
            *expense_breakdown,
        ]
        cost_breakdown = [row for row in cost_breakdown if row["amount"] > 0]
        cost_breakdown.sort(key=lambda row: row["amount"], reverse=True)

        distance = None
        cost_per_km = None
        if cost_since is None:
            cost_odo_entries = car.odometer_entries.order_by(
                OdometerEntry.date.asc(), OdometerEntry.id.asc()
            ).all()
        else:
            baseline = car.odometer_entries.filter(
                OdometerEntry.date < cost_since
            ).order_by(
                OdometerEntry.date.desc(), OdometerEntry.id.desc()
            ).first()
            cost_odo_entries = car.odometer_entries.filter(
                OdometerEntry.date >= cost_since
            ).order_by(
                OdometerEntry.date.asc(), OdometerEntry.id.asc()
            ).all()
            if baseline is not None:
                cost_odo_entries.insert(0, baseline)

        cost_odo_values = [entry.km for entry in cost_odo_entries]
        if len(cost_odo_values) >= 2:
            dist = cost_odo_values[-1] - cost_odo_values[0]
            if dist > 0:
                distance = dist
                if total_cost is not None:
                    cost_per_km = (total_cost / Decimal(dist))

        # Pełne tankowanie z przerwą zamyka poprzedni odcinek bez wyniku.
        cons_labels = fuel_stats["labels"]
        cons_values = fuel_stats["values"]

        # --- Interwały (bez zmian) ---
        intervals = (
            car.service_intervals
            .filter(ServiceInterval.active == True)
            .order_by(ServiceInterval.name.asc())
            .all()
        )

        current_km = car.last_odometer.km if car.last_odometer else None

        interval_reminders = []
        for iv in intervals:
            calc = compute_interval_status(iv, current_km, today)
            interval_reminders.append((iv, calc))

        order = {"due": 0, "soon": 1, "ok": 2, "unknown": 3}
        interval_reminders.sort(key=lambda t: order.get(t[1]["status"], 9))

        timeline_kind = (request.args.get("timeline_kind") or "").strip() or None
        timeline_p = build_timeline(
            car,
            page=timeline_page,
            kind=timeline_kind,
        )
        current_km_for_tires = current_km
        tire_mileages = {
            tire_set.id: tire_set_mileage(tire_set, current_km_for_tires)
            for tire_set in tire_sets
        }
        document_links = {
            document.id: [document_link_label(link) for link in document.links]
            for document in docs_p.items
        }
        target_documents = {}
        for document in car.documents.all():
            for link in document.links:
                target_documents.setdefault((link.target_type, link.target_id), []).append(document)

        return render_template(
            "car_detail.html",
            car=car,
            tab=tab,

            odo_labels=odo_labels,
            odo_values=odo_values,

            oc=oc,
            ti=ti,

            # UWAGA: teraz to są paginacje
            services_p=services_p,
            docs_p=docs_p,
            fills_p=fills_p,
            expenses_p=expenses_p,
            modifications_p=modifications_p,
            tire_sets=tire_sets,
            tire_mileages=tire_mileages,
            tire_events=tire_events,
            timeline_p=timeline_p,
            timeline_kind=timeline_kind,

            fuel_total=fuel_total,
            service_total=service_total,
            expense_total=expense_total,
            modification_total=modification_total,
            additional_total=(expense_total or Decimal("0")) + (
                modification_total or Decimal("0")
            ),
            total_cost=total_cost,
            distance=distance,
            cost_per_km=cost_per_km,
            cost_period=cost_period,
            cost_breakdown=cost_breakdown,
            expense_categories=EXPENSE_CATEGORIES,

            cons_labels=cons_labels,
            cons_values=cons_values,
            cons_rolling=fuel_stats["rolling_5"],
            fuel_stats=fuel_stats,
            fuel_price_labels=fuel_stats["price_labels"],
            fuel_price_values=fuel_stats["price_values"],

            intervals=intervals,
            interval_reminders=interval_reminders,
            current_km=current_km,
            odo_p=odo_p,
            document_target_options=document_target_options(car),
            document_links=document_links,
            target_documents=target_documents,
            modification_statuses=MODIFICATION_STATUSES,
            tire_seasons=TIRE_SEASONS,
        )

    @app.post("/cars/<int:car_id>/delete")
    def car_delete(car_id):
        car = get_car_or_404(car_id)
        upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], str(car.id))

        try:
            db.session.delete(car)
            db.session.commit()

            try:
                if os.path.isdir(upload_dir):
                    shutil.rmtree(upload_dir, ignore_errors=True)
            except Exception:
                pass

            flash("Usunięto auto, historię i pliki 🗑️", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Nie udało się usunąć auta: {e}", "danger")

        return redirect(url_for("list_cars"))
