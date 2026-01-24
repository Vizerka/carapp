# app.py
from __future__ import annotations

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, abort, send_file
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect as sa_inspect
from datetime import datetime, date, timedelta
from decimal import Decimal
import os
import shutil
from werkzeug.utils import secure_filename
import zipfile
import io
import json
from decimal import Decimal, InvalidOperation

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cars.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Uploads (dokumenty)
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}

db = SQLAlchemy(app)


# -------------------
# MODELE
# -------------------

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False)      # Marka
    model = db.Column(db.String(80), nullable=False)     # Model
    year = db.Column(db.Integer)                         # Rocznik
    vin = db.Column(db.String(32), unique=True)          # Numer VIN
    reg_number = db.Column(db.String(16), unique=True)   # Rejestracja
    first_registration = db.Column(db.Date)              # Data pierwszej rejestracji

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


class InsurancePolicy(db.Model):  # OC
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
    date = db.Column(db.Date, nullable=False)      # data badania
    valid_to = db.Column(db.Date, nullable=False)  # ważność do
    result = db.Column(db.String(32))              # np. 'pozytywny'
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
    km = db.Column(db.Integer)  # opcjonalnie
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    cost = db.Column(db.Numeric(10, 2))  # PLN
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
    total_cost = db.Column(db.Numeric(10, 2))      # PLN (opc.)
    price_per_l = db.Column(db.Numeric(10, 3))     # PLN/L (opc.)
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
    stored_name = db.Column(db.String(255), nullable=False)     # nazwa na dysku
    original_name = db.Column(db.String(255), nullable=False)   # nazwa od usera
    category = db.Column(db.String(64))                         # "OC", "Przegląd", "Faktura"...
    note = db.Column(db.String(255))

    car = db.relationship(
        "Car",
        backref=db.backref("documents", lazy="dynamic", cascade="all, delete-orphan")
    )

class ServiceInterval(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False, index=True)

    name = db.Column(db.String(120), nullable=False)     # np. "Olej + filtr"
    interval_km = db.Column(db.Integer)                  # np. 10000
    interval_days = db.Column(db.Integer)                # np. 365

    last_done_km = db.Column(db.Integer)                 # ostatnio wykonane przy km
    last_done_date = db.Column(db.Date)                  # ostatnio wykonane dnia

    note = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True, nullable=False)

    car = db.relationship(
        'Car',
        backref=db.backref('service_intervals', lazy='dynamic', cascade='all, delete-orphan')
    )



with app.app_context():
    db.create_all()


# -------------------
# POMOCNICZE
# -------------------

def parse_date(s: str | None):
    try:
        s = (s or "").strip()
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        return None


def parse_decimal(s: str | None) -> Decimal | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def ensure_car_upload_dir(car_id: int) -> str:
    path = os.path.join(app.config["UPLOAD_FOLDER"], str(car_id))
    os.makedirs(path, exist_ok=True)
    return path


@app.template_filter("days_left")
def days_left(d):
    if not d:
        return None
    return (d - date.today()).days


from decimal import Decimal

def _model_to_dict(obj):
    """Zamień model SQLAlchemy na dict (kolumny), z ISO dla dat i JSON-safe typami."""
    out = {}
    mapper = sa_inspect(obj.__class__)

    for col in mapper.columns:
        val = getattr(obj, col.key)

        if isinstance(val, (date, datetime)):
            out[col.key] = val.isoformat()
        elif isinstance(val, Decimal):
            # JSON nie ogarnia Decimal -> robimy float
            # (dla PLN i litrów to wystarczy)
            out[col.key] = float(val)
        else:
            out[col.key] = val

    return out

def _parse_any_date(s):
    """ISO -> date lub datetime (zależnie od formatu)."""
    if not s:
        return None
    try:
        # datetime?
        if "T" in s:
            return datetime.fromisoformat(s)
        # date
        return date.fromisoformat(s)
    except ValueError:
        return None

def _dict_to_model_kwargs(model_cls, data: dict):
    """Weź dict z backupu i przygotuj kwargs do konstruktora modelu."""
    mapper = sa_inspect(model_cls)
    kwargs = {}
    for col in mapper.columns:
        key = col.key
        if key not in data:
            continue
        if key == "id":
            continue  # nie importujemy ID
        val = data[key]
        # Daty
        if hasattr(col.type, "python_type") and col.type.python_type in (date, datetime):
            parsed = _parse_any_date(val)
            kwargs[key] = parsed
        else:
            kwargs[key] = val
    return kwargs

def _safe_unique_filename(existing_names: set[str], filename: str) -> str:
    """Jak koliduje, dorzuć suffix."""
    if filename not in existing_names:
        existing_names.add(filename)
        return filename
    base, dot, ext = filename.rpartition(".")
    if not dot:
        base, ext = filename, ""
    i = 2
    while True:
        cand = f"{base}_{i}.{ext}" if ext else f"{base}_{i}"
        if cand not in existing_names:
            existing_names.add(cand)
            return cand
        i += 1

def compute_interval_status(iv: ServiceInterval, current_km: int | None, today: date):
    """
    Zwraca słownik z wyliczonym następnym terminem/km i statusem:
    - status: 'ok' | 'soon' | 'due' | 'unknown'
    """
    next_km = None
    km_left = None
    next_date = None
    days_left = None

    # KM
    if iv.interval_km and iv.last_done_km is not None:
        next_km = iv.last_done_km + iv.interval_km
        if current_km is not None:
            km_left = next_km - current_km

    # DNI
    if iv.interval_days and iv.last_done_date:
        next_date = iv.last_done_date + timedelta(days=int(iv.interval_days))
        days_left = (next_date - today).days

    # Status (priorytet: po terminie > wkrótce > ok)
    status = "unknown"
    due = False
    soon = False

    if km_left is not None:
        if km_left <= 0:
            due = True
        elif km_left <= 500:   # próg "wkrótce" (możesz zmienić)
            soon = True

    if days_left is not None:
        if days_left <= 0:
            due = True
        elif days_left <= 14:  # próg "wkrótce" (możesz zmienić)
            soon = True

    if due:
        status = "due"
    elif soon:
        status = "soon"
    else:
        # jeśli cokolwiek policzyliśmy, ale nie jest due/soon
        if (km_left is not None) or (days_left is not None):
            status = "ok"

    return {
        "next_km": next_km,
        "km_left": km_left,
        "next_date": next_date,
        "days_left": days_left,
        "status": status,
    }
# -------------------


# --- Walidacje ---

def validate_odometer(car_id: int, when: date, km: int, entry_id: int | None = None):
    """
    Przebieg nie może maleć:
    km >= max(km) dla wpisów <= when oraz km <= min(km) dla wpisów >= when.
    """
    if not when:
        return False, "Podaj datę."
    if km is None:
        return False, "Podaj przebieg."

    filters_prev = [OdometerEntry.car_id == car_id, OdometerEntry.date <= when]
    filters_next = [OdometerEntry.car_id == car_id, OdometerEntry.date >= when]
    if entry_id is not None:
        filters_prev.append(OdometerEntry.id != entry_id)
        filters_next.append(OdometerEntry.id != entry_id)

    max_prev = db.session.query(func.max(OdometerEntry.km)).filter(*filters_prev).scalar()
    min_next = db.session.query(func.min(OdometerEntry.km)).filter(*filters_next).scalar()

    if max_prev is not None and km < max_prev:
        return False, f"Przebieg {km} km jest mniejszy niż wcześniejszy wpis {max_prev} km."
    if min_next is not None and km > min_next:
        return False, f"Przebieg {km} km jest większy niż późniejszy wpis {min_next} km."
    return True, None


def validate_insurance_interval(car_id: int, valid_from: date, valid_to: date, policy_id: int | None = None):
    if not valid_from or not valid_to:
        return False, "Podaj oba terminy (od/do)."
    if valid_from > valid_to:
        return False, "Data 'od' nie może być po dacie 'do'."

    q = InsurancePolicy.query.filter(InsurancePolicy.car_id == car_id)
    if policy_id is not None:
        q = q.filter(InsurancePolicy.id != policy_id)

    for p in q.all():
        if not (valid_to < p.valid_from or valid_from > p.valid_to):
            return False, f"Okres {valid_from} → {valid_to} nakłada się z polisą {p.valid_from} → {p.valid_to}."
    return True, None


def validate_inspection_dates(date_do: date, valid_to: date):
    if not date_do or not valid_to:
        return False, "Podaj datę badania i ważności."
    if date_do > valid_to:
        return False, "Data badania nie może być po dacie ważności."
    return True, None


def upsert_odometer_for_date(car_id: int, when: date, km: int, note: str | None = None):
    """
    Jeśli dla danej daty jest już wpis przebiegu – aktualizuj do max(stary, nowy).
    Jeśli nie ma – dodaj nowy.
    """
    existing = (OdometerEntry.query
                .filter(OdometerEntry.car_id == car_id, OdometerEntry.date == when)
                .order_by(desc(OdometerEntry.id))
                .first())

    if existing:
        if km > existing.km:
            existing.km = km
        if note:
            existing.note = f"{existing.note}; {note}" if existing.note else note
        return existing

    entry = OdometerEntry(car_id=car_id, date=when, km=km, note=note)
    db.session.add(entry)
    return entry


# -------------------
# ROUTES
# -------------------

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

    # przebieg: lista do historii + lista do wykresu
    odo_desc = car.odometer_entries.order_by(desc(OdometerEntry.date), desc(OdometerEntry.id)).all()
    odo_asc = car.odometer_entries.order_by(OdometerEntry.date.asc(), OdometerEntry.id.asc()).all()
    odo_labels = [e.date.isoformat() for e in odo_asc]
    odo_values = [e.km for e in odo_asc]

    # OC / przeglądy
    oc = car.insurance_policies.order_by(desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)).all()
    ti = car.tech_inspections.order_by(desc(TechInspection.valid_to), desc(TechInspection.id)).all()

    # Serwis
    services = car.service_entries.order_by(desc(ServiceEntry.date), desc(ServiceEntry.id)).all()

    # Dokumenty
    docs = car.documents.order_by(desc(Document.uploaded_at), desc(Document.id)).all()

    # Tankowania
    fills_desc = car.fuel_entries.order_by(desc(FuelEntry.date), desc(FuelEntry.id)).all()
    fills_asc = car.fuel_entries.order_by(FuelEntry.date.asc(), FuelEntry.id.asc()).all()

    # --- Suma kosztów ---
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

    # --- dystans (z przebiegu) ---
    distance = None
    cost_per_km = None
    if len(odo_values) >= 2:
        dist = odo_values[-1] - odo_values[0]
        if dist > 0:
            distance = dist
            if total_cost is not None:
                cost_per_km = (total_cost / Decimal(dist))

    # --- wykres spalania (pełny -> pełny) ---
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

        # sumuj litry między pełnymi bakami (wliczając obecne tankowanie)
        liters_acc += Decimal(f.liters or 0)

        if f.full_tank:
            km1 = int(last_full.km)
            km2 = int(f.km)
            dist = km2 - km1

            if dist > 0:
                l_per_100 = (liters_acc / Decimal(dist)) * Decimal("100")
                cons_labels.append(f.date.isoformat())
                cons_values.append(float(l_per_100))

            # start nowego odcinka
            last_full = f
            liters_acc = Decimal("0")

    # --- Interwały + przypominajki (MUSI BYĆ POZA pętlą!) ---
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

        # kafle + wykres spalania
        fuel_total=fuel_total,
        service_total=service_total,
        total_cost=total_cost,
        distance=distance,
        cost_per_km=cost_per_km,
        cons_labels=cons_labels,
        cons_values=cons_values,

        # interwały
        intervals=intervals,
        interval_reminders=interval_reminders,
        current_km=current_km
    )


# -------------------
# ODOMETER
# -------------------

@app.post("/cars/<int:car_id>/odometer/new")
def odometer_new(car_id):
    car = Car.query.get_or_404(car_id)
    when = parse_date(request.form.get("date"))
    km = int(request.form.get("km") or 0)

    ok, msg = validate_odometer(car.id, when, km, None)
    if not ok:
        flash(msg, "danger")
        return redirect(url_for("car_detail", car_id=car.id))

    entry = OdometerEntry(
        car_id=car.id,
        date=when,
        km=km,
        note=(request.form.get("note") or "").strip() or None
    )
    db.session.add(entry)
    db.session.commit()
    flash("Dodano wpis przebiegu ✅", "success")
    return redirect(url_for("car_detail", car_id=car.id))


@app.route("/odometer/<int:entry_id>/edit", methods=["GET", "POST"])
def odometer_edit(entry_id):
    entry = OdometerEntry.query.get_or_404(entry_id)
    car = entry.car

    if request.method == "POST":
        when = parse_date(request.form.get("date"))
        km = int(request.form.get("km") or 0)

        ok, msg = validate_odometer(car.id, when, km, entry.id)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("odometer_edit", entry_id=entry.id))

        entry.date = when
        entry.km = km
        entry.note = (request.form.get("note") or "").strip() or None
        db.session.commit()

        flash("Zaktualizowano wpis przebiegu ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    return render_template("odometer_form.html", car=car, entry=entry)


@app.post("/odometer/<int:entry_id>/delete")
def odometer_delete(entry_id):
    entry = OdometerEntry.query.get_or_404(entry_id)
    car_id = entry.car_id
    db.session.delete(entry)
    db.session.commit()
    flash("Usunięto wpis przebiegu 🗑️", "success")
    return redirect(url_for("car_detail", car_id=car_id))


# -------------------
# INSURANCE (OC)
# -------------------

@app.post("/cars/<int:car_id>/insurance/new")
def insurance_new(car_id):
    car = Car.query.get_or_404(car_id)
    valid_from = parse_date(request.form.get("valid_from"))
    valid_to = parse_date(request.form.get("valid_to"))

    ok, msg = validate_insurance_interval(car.id, valid_from, valid_to, None)
    if not ok:
        flash(msg, "danger")
        return redirect(url_for("car_detail", car_id=car.id))

    policy = InsurancePolicy(
        car_id=car.id,
        valid_from=valid_from,
        valid_to=valid_to,
        insurer=(request.form.get("insurer") or "").strip() or None,
        policy_no=(request.form.get("policy_no") or "").strip() or None
    )
    db.session.add(policy)
    db.session.commit()

    flash("Dodano polisę OC ✅", "success")
    return redirect(url_for("car_detail", car_id=car.id))


@app.route("/insurance/<int:policy_id>/edit", methods=["GET", "POST"])
def insurance_edit(policy_id):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    car = policy.car

    if request.method == "POST":
        valid_from = parse_date(request.form.get("valid_from"))
        valid_to = parse_date(request.form.get("valid_to"))

        ok, msg = validate_insurance_interval(car.id, valid_from, valid_to, policy.id)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("insurance_edit", policy_id=policy.id))

        policy.valid_from = valid_from
        policy.valid_to = valid_to
        policy.insurer = (request.form.get("insurer") or "").strip() or None
        policy.policy_no = (request.form.get("policy_no") or "").strip() or None

        db.session.commit()
        flash("Zaktualizowano polisę OC ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    return render_template("insurance_form.html", car=car, policy=policy)


@app.post("/insurance/<int:policy_id>/delete")
def insurance_delete(policy_id):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    car_id = policy.car_id
    db.session.delete(policy)
    db.session.commit()
    flash("Usunięto polisę OC 🗑️", "success")
    return redirect(url_for("car_detail", car_id=car_id))


# -------------------
# TECH INSPECTION
# -------------------

@app.post("/cars/<int:car_id>/inspection/new")
def inspection_new(car_id):
    car = Car.query.get_or_404(car_id)
    date_do = parse_date(request.form.get("date"))
    valid_to = parse_date(request.form.get("valid_to"))

    ok, msg = validate_inspection_dates(date_do, valid_to)
    if not ok:
        flash(msg, "danger")
        return redirect(url_for("car_detail", car_id=car.id))

    ins = TechInspection(
        car_id=car.id,
        date=date_do,
        valid_to=valid_to,
        result=(request.form.get("result") or "").strip() or None,
        station=(request.form.get("station") or "").strip() or None,
        note=(request.form.get("note") or "").strip() or None
    )
    db.session.add(ins)
    db.session.commit()
    flash("Dodano przegląd ✅", "success")
    return redirect(url_for("car_detail", car_id=car.id))


@app.route("/inspection/<int:ins_id>/edit", methods=["GET", "POST"])
def inspection_edit(ins_id):
    ins = TechInspection.query.get_or_404(ins_id)
    car = ins.car

    if request.method == "POST":
        date_do = parse_date(request.form.get("date"))
        valid_to = parse_date(request.form.get("valid_to"))

        ok, msg = validate_inspection_dates(date_do, valid_to)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("inspection_edit", ins_id=ins.id))

        ins.date = date_do
        ins.valid_to = valid_to
        ins.result = (request.form.get("result") or "").strip() or None
        ins.station = (request.form.get("station") or "").strip() or None
        ins.note = (request.form.get("note") or "").strip() or None

        db.session.commit()
        flash("Zaktualizowano przegląd ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    return render_template("inspection_form.html", car=car, ins=ins)


@app.post("/inspection/<int:ins_id>/delete")
def inspection_delete(ins_id):
    ins = TechInspection.query.get_or_404(ins_id)
    car_id = ins.car_id
    db.session.delete(ins)
    db.session.commit()
    flash("Usunięto przegląd 🗑️", "success")
    return redirect(url_for("car_detail", car_id=car_id))


# -------------------
# SERVICE
# -------------------

@app.post("/cars/<int:car_id>/service/new")
def service_new(car_id):
    car = Car.query.get_or_404(car_id)

    when = parse_date(request.form.get("date"))
    km = int(request.form.get("km") or 0) or None

    interval_id_raw = (request.form.get('interval_id') or '').strip()
    interval_id = int(interval_id_raw) if interval_id_raw else None


    entry = ServiceEntry(
        car_id=car.id,
        date=when,
        km=km,
        title=(request.form.get("title") or "").strip(),
        description=(request.form.get("description") or "").strip() or None,
        vendor=(request.form.get("vendor") or "").strip() or None,
        note=(request.form.get("note") or "").strip() or None
    )
    cost = parse_decimal(request.form.get("cost"))
    entry.cost = cost if cost is not None else None

    # walidacja przebiegu + update przebiegu z serwisu
    if km is not None:
        ok, msg = validate_odometer(car.id, when, km, None)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("car_detail", car_id=car.id))

    db.session.add(entry)

    if km is not None:
        upsert_odometer_for_date(
            car_id=car.id,
            when=when,
            km=km,
            note=f"Serwis: {entry.title}"
        )
    
    if interval_id:
        iv = ServiceInterval.query.get(interval_id)
        if iv and iv.car_id == car.id:
            iv.last_done_date = when
            if km is not None:
                iv.last_done_km = km


    db.session.commit()
    flash("Dodano wpis serwisowy ✅", "success")
    if km is not None:
        flash("Przebieg zaktualizowany na podstawie serwisu ✅", "info")
    return redirect(url_for("car_detail", car_id=car.id))


@app.route("/service/<int:service_id>/edit", methods=["GET", "POST"])
def service_edit(service_id):
    s = ServiceEntry.query.get_or_404(service_id)
    car = s.car

    if request.method == "POST":
        s.date = parse_date(request.form.get("date"))
        s.km = int(request.form.get("km") or 0) or None
        s.title = (request.form.get("title") or "").strip()
        s.description = (request.form.get("description") or "").strip() or None
        s.vendor = (request.form.get("vendor") or "").strip() or None
        s.note = (request.form.get("note") or "").strip() or None
        s.cost = parse_decimal(request.form.get("cost"))

        db.session.commit()
        flash("Zapisano serwis ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    return render_template("service_form.html", car=car, s=s)


@app.post("/service/<int:service_id>/delete")
def service_delete(service_id):
    s = ServiceEntry.query.get_or_404(service_id)
    car_id = s.car_id
    db.session.delete(s)
    db.session.commit()
    flash("Usunięto wpis serwisowy 🗑️", "success")
    return redirect(url_for("car_detail", car_id=car_id))


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

    # ✅ FIX dla selecta: 1/0 / true/false / on/off
    full_raw = (request.form.get("full_tank") or "").strip().lower()
    full_tank = full_raw in ("1", "true", "on", "yes", "y")

    # walidacja przebiegu
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
        note=note
    )
    db.session.add(fill)

    # aktualizacja przebiegu z tankowania
    upsert_odometer_for_date(
        car_id=car.id,
        when=when,
        km=km,
        note="Tankowanie"
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

        # walidacja przebiegu (monotonic) dla daty km
        ok, msg = validate_odometer(car.id, when, km, None)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("fuel_edit", fill_id=f.id))

        # update wpisu paliwa
        f.date = when
        f.km = km
        f.liters = liters
        f.total_cost = total_cost
        f.price_per_l = price_per_l
        f.station = station
        f.full_tank = full_tank
        f.note = note

        # update przebiegu z tankowania
        upsert_odometer_for_date(
            car_id=car.id,
            when=when,
            km=km,
            note="Tankowanie (edycja)"
        )

        db.session.commit()
        flash("Zapisano tankowanie ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    # fuel_form.html masz już zrobione
    return render_template("fuel_form.html", car=car, f=f)



@app.post("/fuel/<int:fill_id>/delete")
def fuel_delete(fill_id):
    f = FuelEntry.query.get_or_404(fill_id)
    car_id = f.car_id
    db.session.delete(f)
    db.session.commit()
    flash("Usunięto tankowanie 🗑️", "success")
    return redirect(url_for("car_detail", car_id=car_id))


# -------------------
# DOCUMENTS
# -------------------

@app.post("/cars/<int:car_id>/documents/upload")
def document_upload(car_id):
    car = Car.query.get_or_404(car_id)
    file = request.files.get("file")

    if not file or file.filename == "":
        flash("Nie wybrano pliku.", "danger")
        return redirect(url_for("car_detail", car_id=car.id))

    if not allowed_file(file.filename):
        flash("Nieobsługiwany typ pliku. Dozwolone: pdf, jpg, jpeg, png, webp.", "danger")
        return redirect(url_for("car_detail", car_id=car.id))

    upload_dir = ensure_car_upload_dir(car.id)
    original = file.filename
    safe = secure_filename(original)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    stored = f"{stamp}_{safe}"

    file.save(os.path.join(upload_dir, stored))

    doc = Document(
        car_id=car.id,
        stored_name=stored,
        original_name=original,
        category=(request.form.get("category") or "").strip() or None,
        note=(request.form.get("note") or "").strip() or None
    )
    db.session.add(doc)
    db.session.commit()

    flash("Dodano dokument 📎", "success")
    return redirect(url_for("car_detail", car_id=car.id))


@app.get("/documents/<int:doc_id>/download")
def document_download(doc_id):
    doc = Document.query.get_or_404(doc_id)
    upload_dir = ensure_car_upload_dir(doc.car_id)
    path = os.path.join(upload_dir, doc.stored_name)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(
        upload_dir,
        doc.stored_name,
        as_attachment=True,
        download_name=doc.original_name
    )


@app.post("/documents/<int:doc_id>/delete")
def document_delete(doc_id):
    doc = Document.query.get_or_404(doc_id)
    car_id = doc.car_id
    upload_dir = ensure_car_upload_dir(car_id)
    path = os.path.join(upload_dir, doc.stored_name)

    db.session.delete(doc)
    db.session.commit()

    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass

    flash("Usunięto dokument 🗑️", "success")
    return redirect(url_for("car_detail", car_id=car_id))

@app.get('/documents/<int:doc_id>/view')
def document_view(doc_id):
    """
    Podgląd w przeglądarce (bez wymuszania pobierania).
    Działa dla PDF i obrazków (jpg/png/webp).
    """
    doc = Document.query.get_or_404(doc_id)
    upload_dir = ensure_car_upload_dir(doc.car_id)
    path = os.path.join(upload_dir, doc.stored_name)
    if not os.path.isfile(path):
        abort(404)

    # as_attachment=False -> przeglądarka spróbuje wyświetlić inline
    return send_from_directory(upload_dir, doc.stored_name, as_attachment=False)


@app.route('/documents/<int:doc_id>/edit', methods=['GET', 'POST'])
def document_edit(doc_id):
    doc = Document.query.get_or_404(doc_id)

    if request.method == 'POST':
        doc.category = (request.form.get('category') or '').strip() or None
        doc.note = (request.form.get('note') or '').strip() or None

        file = request.files.get('file')
        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Nieobsługiwany typ pliku. Dozwolone: pdf, jpg, jpeg, png, webp.', 'danger')
                return redirect(url_for('document_edit', doc_id=doc.id))

            upload_dir = ensure_car_upload_dir(doc.car_id)

            old_path = os.path.join(upload_dir, doc.stored_name)

            original = file.filename
            safe = secure_filename(original)
            stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
            stored = f"{stamp}_{safe}"
            new_path = os.path.join(upload_dir, stored)

            try:
                # 1) zapisz nowy plik
                file.save(new_path)

                # 2) zaktualizuj rekord
                doc.original_name = original
                doc.stored_name = stored

                db.session.commit()

                # 3) usuń stary plik (po commicie)
                try:
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

                flash('Zapisano zmiany dokumentu ✅', 'success')
                flash('Plik został podmieniony 📎', 'info')
                return redirect(url_for('car_detail', car_id=doc.car_id))

            except Exception as e:
                db.session.rollback()

                # posprzątaj nowy plik jeśli zapisany, a commit się wywalił
                try:
                    if os.path.isfile(new_path):
                        os.remove(new_path)
                except OSError:
                    pass

                flash(f'Nie udało się podmienić pliku: {e}', 'danger')
                return redirect(url_for('document_edit', doc_id=doc.id))

        # jeśli nie było nowego pliku → tylko meta
        db.session.commit()
        flash('Zapisano zmiany dokumentu ✅', 'success')
        return redirect(url_for('car_detail', car_id=doc.car_id))

    return render_template('document_form.html', doc=doc)


# -------------------
# CAR DELETE
# -------------------

@app.post('/cars/<int:car_id>/delete')
def car_delete(car_id):
    car = Car.query.get_or_404(car_id)
    upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], str(car.id))

    try:
        db.session.delete(car)  # skasuje też powiązane wpisy dzięki cascade
        db.session.commit()

        # po udanym commicie: usuń cały katalog uploadów dla auta
        try:
            if os.path.isdir(upload_dir):
                shutil.rmtree(upload_dir, ignore_errors=True)
        except Exception:
            # nie blokuj usuwania auta przez problemy z plikami
            pass

        flash('Usunięto auto, historię i pliki 🗑️', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Nie udało się usunąć auta: {e}', 'danger')

    return redirect(url_for('list_cars'))


@app.get("/backup")
def backup_page():
    return render_template("backup.html")


@app.get("/backup/export.zip")
def backup_export_zip():
    """
    Eksportuje ZIP: backup.json (dane) + uploads/<car_id>/... (pliki dokumentów).
    """
    # 1) Dane z bazy
    payload = {
        "meta": {
            "app": "car_manager",
            "exported_at": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        },
        "cars": [_model_to_dict(c) for c in Car.query.order_by(Car.id.asc()).all()],
        "odometer_entries": [_model_to_dict(x) for x in OdometerEntry.query.order_by(OdometerEntry.id.asc()).all()],
        "insurance_policies": [_model_to_dict(x) for x in InsurancePolicy.query.order_by(InsurancePolicy.id.asc()).all()],
        "tech_inspections": [_model_to_dict(x) for x in TechInspection.query.order_by(TechInspection.id.asc()).all()],
        "service_entries": [_model_to_dict(x) for x in ServiceEntry.query.order_by(ServiceEntry.id.asc()).all()],
        "fuel_entries": [_model_to_dict(x) for x in FuelEntry.query.order_by(FuelEntry.id.asc()).all()],
        "service_intervals": [_model_to_dict(x) for x in ServiceInterval.query.order_by(ServiceInterval.id.asc()).all()],
        "documents": [_model_to_dict(x) for x in Document.query.order_by(Document.id.asc()).all()],
}


    # Jeśli masz model tankowań, dorzuć (bez wywalania apki jak go nie ma)
    try:
        payload["fuel_entries"] = [_model_to_dict(x) for x in FuelEntry.query.order_by(FuelEntry.id.asc()).all()]  # type: ignore
    except Exception:
        pass

    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    # 2) ZIP do pamięci
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup.json", json_bytes)

        # 3) Dorzuć pliki z uploads/
        root = app.config.get("UPLOAD_FOLDER")
        if root and os.path.isdir(root):
            for dirpath, _, filenames in os.walk(root):
                for fn in filenames:
                    abs_path = os.path.join(dirpath, fn)
                    rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
                    z.write(abs_path, arcname=f"uploads/{rel_path}")

    mem.seek(0)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return send_file(
        mem,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"car_manager_backup_{stamp}.zip",
    )

@app.post('/cars/<int:car_id>/intervals/new')
def interval_new(car_id):
    car = Car.query.get_or_404(car_id)

    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Podaj nazwę interwału.', 'danger')
        return redirect(url_for('car_detail', car_id=car.id))

    def to_int(x):
        x = (x or '').strip()
        return int(x) if x else None

    iv = ServiceInterval(
        car_id=car.id,
        name=name,
        interval_km=to_int(request.form.get('interval_km')),
        interval_days=to_int(request.form.get('interval_days')),
        last_done_km=to_int(request.form.get('last_done_km')),
        last_done_date=parse_date(request.form.get('last_done_date')),
        note=(request.form.get('note') or '').strip() or None,
        active=True
    )
    db.session.add(iv)
    db.session.commit()
    flash('Dodano interwał serwisowy ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))


@app.route('/intervals/<int:interval_id>/edit', methods=['GET', 'POST'])
def interval_edit(interval_id):
    iv = ServiceInterval.query.get_or_404(interval_id)
    car_id = iv.car_id

    def to_int(x):
        x = (x or '').strip()
        return int(x) if x else None

    if request.method == 'POST':
        iv.name = (request.form.get('name') or '').strip() or iv.name
        iv.interval_km = to_int(request.form.get('interval_km'))
        iv.interval_days = to_int(request.form.get('interval_days'))
        iv.last_done_km = to_int(request.form.get('last_done_km'))
        iv.last_done_date = parse_date(request.form.get('last_done_date'))
        iv.note = (request.form.get('note') or '').strip() or None
        iv.active = (request.form.get('active') == '1')

        db.session.commit()
        flash('Zapisano interwał ✅', 'success')
        return redirect(url_for('car_detail', car_id=car_id))

    return render_template('service_interval_form.html', iv=iv)


@app.post('/intervals/<int:interval_id>/delete')
def interval_delete(interval_id):
    iv = ServiceInterval.query.get_or_404(interval_id)
    car_id = iv.car_id
    db.session.delete(iv)
    db.session.commit()
    flash('Usunięto interwał 🗑️', 'success')
    return redirect(url_for('car_detail', car_id=car_id))


@app.post('/intervals/<int:interval_id>/mark_done')
def interval_mark_done(interval_id):
    iv = ServiceInterval.query.get_or_404(interval_id)
    car = Car.query.get_or_404(iv.car_id)

    when = parse_date(request.form.get('date')) or date.today()
    km_raw = (request.form.get('km') or '').strip()
    km = int(km_raw) if km_raw else None

    iv.last_done_date = when
    if km is not None:
        iv.last_done_km = km

    db.session.commit()
    flash('Zaksięgowano wykonanie interwału ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))


@app.post("/backup/import")
def backup_import():
    """
    Import ZIP z backup.json + uploads/.
    Tryb: MERGE (dokleja), ale z DEDUPLIKACJĄ:
    - Auta: dopasowanie po VIN, a jak brak to po reg_number.
    - Wpisy: dodawane tylko jeśli identyczny wpis nie istnieje (po kluczach).
    - Dokumenty: kopiowane do uploads/<new_car_id>/, stored_name dostaje suffix jak koliduje.
      Deduplikacja dokumentów: po (car_id, original_name, category, uploaded_at).
    """

    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Nie wybrano pliku ZIP.", "danger")
        return redirect(url_for("backup_page"))

    if not file.filename.lower().endswith(".zip"):
        flash("To nie wygląda na ZIP.", "danger")
        return redirect(url_for("backup_page"))

    # ----------------------------
    # Helpery NORMALIZACJI + dedupe
    # ----------------------------
    from decimal import Decimal, InvalidOperation

    def _to_dec(v) -> Decimal | None:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v).replace(",", "."))
        except (InvalidOperation, ValueError):
            return None

    def _q(v, quantum: str) -> str | None:
        """
        Quantize -> string, żeby Decimal('100.00') i Decimal('100.0') dawały to samo.
        """
        d = _to_dec(v)
        if d is None:
            return None
        return str(d.quantize(Decimal(quantum)))

    def _k(x):
        if isinstance(x, (date, datetime)):
            return x.isoformat()
        return x

    def build_existing_keys(model_cls, key_func):
        keys = set()
        for obj in model_cls.query.all():
            keys.add(key_func(obj))
        return keys

    # ---------
    # KEY FUNCS (OBIEKT -> tuple)
    # ---------
    def key_odometer(o: OdometerEntry):
        return (_k(o.car_id), _k(o.date), _k(o.km))

    def key_insurance(p: InsurancePolicy):
        return (_k(p.car_id), _k(p.valid_from), _k(p.valid_to), (p.insurer or "").strip(), (p.policy_no or "").strip())

    def key_inspection(i: TechInspection):
        return (_k(i.car_id), _k(i.date), _k(i.valid_to), (i.result or "").strip(), (i.station or "").strip())

    # Serwis: cost ujednolicone do 2 miejsc
    def key_service(s: ServiceEntry):
        return (
            _k(s.car_id),
            _k(s.date),
            _k(s.km),
            (s.title or "").strip(),
            _q(s.cost, "0.01"),
            (s.vendor or "").strip(),
        )

    # Tankowanie: liters 3 miejsca, total_cost 2 miejsca, NIE bierzemy station/note (bo to psuje dedupe)
    def key_fuel(f: FuelEntry):
        return (
            _k(f.car_id),
            _k(f.date),
            _k(f.km),
            _q(f.liters, "0.001"),
            _q(f.total_cost, "0.01"),
            bool(f.full_tank),
        )

    # Interwał: w obrębie auta unikalny po nazwie
    def key_interval(iv: ServiceInterval):
        return (_k(iv.car_id), (iv.name or "").strip())

    # ---------
    # KEY FUNCS (KWARGS -> tuple)
    # ---------
    def key_odometer_kwargs(w):
        return (_k(w.get("car_id")), _k(w.get("date")), _k(w.get("km")))

    def key_insurance_kwargs(w):
        return (
            _k(w.get("car_id")),
            _k(w.get("valid_from")),
            _k(w.get("valid_to")),
            ((w.get("insurer") or "")).strip(),
            ((w.get("policy_no") or "")).strip(),
        )

    def key_inspection_kwargs(w):
        return (
            _k(w.get("car_id")),
            _k(w.get("date")),
            _k(w.get("valid_to")),
            ((w.get("result") or "")).strip(),
            ((w.get("station") or "")).strip(),
        )

    def key_service_kwargs(w):
        return (
            _k(w.get("car_id")),
            _k(w.get("date")),
            _k(w.get("km")),
            ((w.get("title") or "")).strip(),
            _q(w.get("cost"), "0.01"),
            ((w.get("vendor") or "")).strip(),
        )

    def key_fuel_kwargs(w):
        return (
            _k(w.get("car_id")),
            _k(w.get("date")),
            _k(w.get("km")),
            _q(w.get("liters"), "0.001"),
            _q(w.get("total_cost"), "0.01"),
            bool(w.get("full_tank")),
        )

    def key_interval_kwargs(w):
        return (_k(w.get("car_id")), ((w.get("name") or "")).strip())

    # ----------------------------
    # Import
    # ----------------------------
    try:
        zdata = io.BytesIO(file.read())
        with zipfile.ZipFile(zdata, "r") as z:
            if "backup.json" not in z.namelist():
                flash("W ZIP nie ma backup.json.", "danger")
                return redirect(url_for("backup_page"))

            raw = z.read("backup.json").decode("utf-8")
            payload = json.loads(raw)

            # --- mapowanie stary car_id -> nowy car_id
            car_id_map: dict[int, int] = {}

            # index istniejących aut po VIN/reg
            existing_by_vin = {}
            existing_by_reg = {}
            for c in Car.query.all():
                if c.vin:
                    existing_by_vin[str(c.vin).upper()] = c
                if c.reg_number:
                    existing_by_reg[str(c.reg_number).upper()] = c

            # 1) auta
            imported_cars = payload.get("cars", [])
            for cdata in imported_cars:
                old_id = cdata.get("id")
                vin = (cdata.get("vin") or "").strip().upper() or None
                reg = (cdata.get("reg_number") or "").strip().upper() or None

                target = None
                if vin and vin in existing_by_vin:
                    target = existing_by_vin[vin]
                elif reg and reg in existing_by_reg:
                    target = existing_by_reg[reg]

                if target is None:
                    kwargs = _dict_to_model_kwargs(Car, cdata)
                    if kwargs.get("vin"):
                        kwargs["vin"] = str(kwargs["vin"]).upper()
                    if kwargs.get("reg_number"):
                        kwargs["reg_number"] = str(kwargs["reg_number"]).upper()

                    target = Car(**kwargs)
                    db.session.add(target)
                    db.session.flush()  # żeby dostać id

                    if target.vin:
                        existing_by_vin[str(target.vin).upper()] = target
                    if target.reg_number:
                        existing_by_reg[str(target.reg_number).upper()] = target

                if isinstance(old_id, int):
                    car_id_map[old_id] = target.id

            # 2) wpisy powiązane (dedupe)
            def import_rows(model_cls, rows_key: str, key_func_obj, key_func_kwargs, car_id_field: str = "car_id"):
                rows = payload.get(rows_key, [])
                count = 0

                existing = build_existing_keys(model_cls, key_func_obj)

                for r in rows:
                    old_car_id = r.get(car_id_field)
                    if not isinstance(old_car_id, int) or old_car_id not in car_id_map:
                        continue

                    kwargs = _dict_to_model_kwargs(model_cls, r)
                    kwargs[car_id_field] = car_id_map[old_car_id]

                    k = key_func_kwargs(kwargs)
                    if k in existing:
                        continue  # DUPLIKAT -> pomijamy

                    obj = model_cls(**kwargs)
                    db.session.add(obj)
                    existing.add(k)
                    count += 1

                return count

            odo_n = import_rows(OdometerEntry, "odometer_entries", key_odometer, key_odometer_kwargs)
            oc_n  = import_rows(InsurancePolicy, "insurance_policies", key_insurance, key_insurance_kwargs)
            ti_n  = import_rows(TechInspection, "tech_inspections", key_inspection, key_inspection_kwargs)
            svc_n = import_rows(ServiceEntry, "service_entries", key_service, key_service_kwargs)
            fuel_n = import_rows(FuelEntry, "fuel_entries", key_fuel, key_fuel_kwargs)
            iv_n   = import_rows(ServiceInterval, "service_intervals", key_interval, key_interval_kwargs)

            # 3) dokumenty + pliki (dedupe)
            docs = payload.get("documents", [])
            doc_n = 0

            existing_stored: dict[int, set[str]] = {}

            # dedupe dokumentów: (car_id, original_name, category, uploaded_at)
            existing_doc_keys = set(
                (_k(d.car_id), _k(d.original_name), _k(d.category), _k(d.uploaded_at))
                for d in Document.query.all()
            )

            for d in docs:
                old_car_id = d.get("car_id")
                if not isinstance(old_car_id, int) or old_car_id not in car_id_map:
                    continue

                new_car_id = car_id_map[old_car_id]
                upload_dir = ensure_car_upload_dir(new_car_id)

                if new_car_id not in existing_stored:
                    names = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()
                    for dd in Document.query.filter_by(car_id=new_car_id).all():
                        if dd.stored_name:
                            names.add(dd.stored_name)
                    existing_stored[new_car_id] = names

                kwargs = _dict_to_model_kwargs(Document, d)
                kwargs["car_id"] = new_car_id

                stored = d.get("stored_name")
                original = d.get("original_name") or stored
                if not stored:
                    continue

                dk = (_k(new_car_id), _k(original), _k(kwargs.get("category")), _k(kwargs.get("uploaded_at")))
                if dk in existing_doc_keys:
                    continue

                zip_path = f"uploads/{old_car_id}/{stored}"
                new_stored = _safe_unique_filename(existing_stored[new_car_id], stored)

                if zip_path not in z.namelist():
                    continue

                data = z.read(zip_path)
                with open(os.path.join(upload_dir, new_stored), "wb") as f:
                    f.write(data)

                kwargs["stored_name"] = new_stored
                kwargs["original_name"] = original

                doc = Document(**kwargs)
                db.session.add(doc)

                existing_doc_keys.add(dk)
                doc_n += 1

            db.session.commit()

            flash("Import zakończony ✅", "success")
            flash(
                f"Auta: {len(car_id_map)} | Odo: {odo_n} | OC: {oc_n} | Przeglądy: {ti_n} | "
                f"Serwis: {svc_n} | Tankowania: {fuel_n} | Interwały: {iv_n} | Dokumenty: {doc_n}",
                "info"
            )
            return redirect(url_for("list_cars"))

    except zipfile.BadZipFile:
        flash("ZIP jest uszkodzony albo nieprawidłowy.", "danger")
        return redirect(url_for("backup_page"))
    except Exception as e:
        db.session.rollback()
        flash(f"Import wywalił się: {e}", "danger")
        return redirect(url_for("backup_page"))




if __name__ == "__main__":
    app.run(debug=True)
