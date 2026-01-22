from __future__ import annotations

import os
import shutil
from datetime import date, timedelta
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import (
    Car, OdometerEntry, InsurancePolicy, TechInspection,
    ServiceEntry, FuelEntry, Document, ServiceInterval
)
from .helpers import parse_date, parse_decimal, compute_interval_status

def init_routes(app):
    @app.get("/")
    def dashboard():
        cars = Car.query.order_by(Car.make, Car.model).all()

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
        cars = Car.query.order_by(Car.make, Car.model).all()
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
        car = Car.query.get_or_404(car_id)
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
        car = Car.query.get_or_404(car_id)

        odo_desc = car.odometer_entries.order_by(desc(OdometerEntry.date), desc(OdometerEntry.id)).all()
        odo_asc = car.odometer_entries.order_by(OdometerEntry.date.asc(), OdometerEntry.id.asc()).all()
        odo_labels = [e.date.isoformat() for e in odo_asc]
        odo_values = [e.km for e in odo_asc]

        oc = car.insurance_policies.order_by(desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)).all()
        ti = car.tech_inspections.order_by(desc(TechInspection.valid_to), desc(TechInspection.id)).all()
        services = car.service_entries.order_by(desc(ServiceEntry.date), desc(ServiceEntry.id)).all()
        docs = car.documents.order_by(desc(Document.uploaded_at), desc(Document.id)).all()

        fills_desc = car.fuel_entries.order_by(desc(FuelEntry.date), desc(FuelEntry.id)).all()
        fills_asc = car.fuel_entries.order_by(FuelEntry.date.asc(), FuelEntry.id.asc()).all()

        fuel_total = db.session.query(func.sum(FuelEntry.total_cost)).filter(
            FuelEntry.car_id == car.id, FuelEntry.total_cost.isnot(None)
        ).scalar()

        service_total = db.session.query(func.sum(ServiceEntry.cost)).filter(
            ServiceEntry.car_id == car.id, ServiceEntry.cost.isnot(None)
        ).scalar()

        if fuel_total is not None:
            fuel_total = Decimal(fuel_total)
        if service_total is not None:
            service_total = Decimal(service_total)

        total_cost = None
        if fuel_total is not None or service_total is not None:
            total_cost = (fuel_total or Decimal("0")) + (service_total or Decimal("0"))

        distance = None
        cost_per_km = None
        if len(odo_values) >= 2:
            dist = odo_values[-1] - odo_values[0]
            if dist > 0:
                distance = dist
                if total_cost is not None:
                    cost_per_km = (total_cost / Decimal(dist))

        cons_labels: list[str] = []
        cons_values: list[float] = []

        last_full = None
        liters_acc = Decimal("0")

        for f in fills_asc:
            if last_full is None:
                if f.full_tank:
                    last_full = f
                    liters_acc = Decimal("0")
                continue

            liters_acc += Decimal(f.liters or 0)

            if f.full_tank:
                km1 = int(last_full.km)
                km2 = int(f.km)
                dist = km2 - km1

                if dist > 0:
                    l_per_100 = (liters_acc / Decimal(dist)) * Decimal("100")
                    cons_labels.append(f.date.isoformat())
                    cons_values.append(float(l_per_100))

                last_full = f
                liters_acc = Decimal("0")

        intervals = (
            car.service_intervals
            .filter(ServiceInterval.active == True)
            .order_by(ServiceInterval.name.asc())
            .all()
        )

        today = date.today()
        current_km = car.last_odometer.km if car.last_odometer else None

        interval_reminders = []
        for iv in intervals:
            calc = compute_interval_status(iv, current_km, today)
            interval_reminders.append((iv, calc))

        order = {"due": 0, "soon": 1, "ok": 2, "unknown": 3}
        interval_reminders.sort(key=lambda t: order.get(t[1]["status"], 9))

        return render_template(
            "car_detail.html",
            car=car,
            odo=odo_desc,
            odo_labels=odo_labels,
            odo_values=odo_values,
            oc=oc,
            ti=ti,
            services=services,
            docs=docs,
            fills=fills_desc,
            fuel_total=fuel_total,
            service_total=service_total,
            total_cost=total_cost,
            distance=distance,
            cost_per_km=cost_per_km,
            cons_labels=cons_labels,
            cons_values=cons_values,
            intervals=intervals,
            interval_reminders=interval_reminders,
            current_km=current_km
        )

    @app.post("/cars/<int:car_id>/delete")
    def car_delete(car_id):
        car = Car.query.get_or_404(car_id)
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
