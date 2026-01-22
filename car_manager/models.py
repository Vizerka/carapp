from __future__ import annotations

from datetime import datetime
from sqlalchemy import desc
from .extensions import db

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer)
    vin = db.Column(db.String(32), unique=True)
    reg_number = db.Column(db.String(16), unique=True)
    first_registration = db.Column(db.Date)

    @property
    def last_odometer(self):
        return self.odometer_entries.order_by(
            desc(OdometerEntry.date), desc(OdometerEntry.id)
        ).first()

    @property
    def last_insurance(self):
        return self.insurance_policies.order_by(
            desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)
        ).first()

    @property
    def last_inspection(self):
        return self.tech_inspections.order_by(
            desc(TechInspection.valid_to), desc(TechInspection.id)
        ).first()


class OdometerEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    km = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(255))

    car = db.relationship(
        "Car",
        backref=db.backref("odometer_entries", lazy="dynamic", cascade="all, delete-orphan")
    )


class InsurancePolicy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    insurer = db.Column(db.String(128))
    policy_no = db.Column(db.String(64))

    car = db.relationship(
        "Car",
        backref=db.backref("insurance_policies", lazy="dynamic", cascade="all, delete-orphan")
    )


class TechInspection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    result = db.Column(db.String(32))
    station = db.Column(db.String(128))
    note = db.Column(db.String(255))

    car = db.relationship(
        "Car",
        backref=db.backref("tech_inspections", lazy="dynamic", cascade="all, delete-orphan")
    )


class ServiceEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)

    date = db.Column(db.Date, nullable=False)
    km = db.Column(db.Integer)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    cost = db.Column(db.Numeric(10, 2))
    vendor = db.Column(db.String(120))
    note = db.Column(db.String(255))

    car = db.relationship(
        "Car",
        backref=db.backref("service_entries", lazy="dynamic", cascade="all, delete-orphan")
    )


class FuelEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)

    date = db.Column(db.Date, nullable=False)
    km = db.Column(db.Integer, nullable=False)

    liters = db.Column(db.Numeric(10, 3), nullable=False)
    total_cost = db.Column(db.Numeric(10, 2))
    price_per_l = db.Column(db.Numeric(10, 3))
    station = db.Column(db.String(120))
    full_tank = db.Column(db.Boolean, default=True, nullable=False)
    note = db.Column(db.String(255))

    car = db.relationship(
        "Car",
        backref=db.backref("fuel_entries", lazy="dynamic", cascade="all, delete-orphan")
    )


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)

    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(64))
    note = db.Column(db.String(255))

    car = db.relationship(
        "Car",
        backref=db.backref("documents", lazy="dynamic", cascade="all, delete-orphan")
    )


class ServiceInterval(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey("car.id"), nullable=False, index=True)

    name = db.Column(db.String(120), nullable=False)
    interval_km = db.Column(db.Integer)
    interval_days = db.Column(db.Integer)

    last_done_km = db.Column(db.Integer)
    last_done_date = db.Column(db.Date)

    note = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False)

    car = db.relationship(
        "Car",
        backref=db.backref("service_intervals", lazy="dynamic", cascade="all, delete-orphan")
    )
