from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func
from datetime import datetime, date, timedelta
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cars.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Opcjonalnie: pokaż zapytania SQL w konsoli
# app.config["SQLALCHEMY_ECHO"] = True

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

class OdometerEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    km = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(255))
    car = db.relationship('Car', backref=db.backref('odometer_entries', lazy='dynamic', cascade='all, delete-orphan'))

class InsurancePolicy(db.Model):  # OC
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False, index=True)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    insurer = db.Column(db.String(128))
    policy_no = db.Column(db.String(64))
    car = db.relationship('Car', backref=db.backref('insurance_policies', lazy='dynamic', cascade='all, delete-orphan'))

class TechInspection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)            # data badania
    valid_to = db.Column(db.Date, nullable=False)        # ważność do
    result = db.Column(db.String(32))                    # np. 'pozytywny'
    station = db.Column(db.String(128))
    note = db.Column(db.String(255))
    car = db.relationship('Car', backref=db.backref('tech_inspections', lazy='dynamic', cascade='all, delete-orphan'))

# Właściwości ułatwiające dostęp do „ostatnich” wpisów
def _car_last_odometer(self):
    return self.odometer_entries.order_by(desc(OdometerEntry.date), desc(OdometerEntry.id)).first()
def _car_last_insurance(self):
    return self.insurance_policies.order_by(desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)).first()
def _car_last_inspection(self):
    return self.tech_inspections.order_by(desc(TechInspection.valid_to), desc(TechInspection.id)).first()
Car.last_odometer = property(_car_last_odometer)
Car.last_insurance = property(_car_last_insurance)
Car.last_inspection = property(_car_last_inspection)

# Inicjalizacja bazy przy starcie (Flask 3.x)
with app.app_context():
    db.create_all()

# -------------------
# POMOCNICZE
# -------------------

def parse_date(s):
    try:
        s = (s or '').strip()
        return datetime.strptime(s, '%Y-%m-%d').date() if s else None
    except ValueError:
        return None

@app.template_filter('days_left')
def days_left(d):
    if not d:
        return None
    return (d - date.today()).days

# --- Walidacje ---

def validate_odometer(car_id: int, when: date, km: int, entry_id: int | None = None):
    """Przebieg nie może maleć: km >= max(km) dla wpisów <= when oraz km <= min(km) dla wpisów >= when."""
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
        # nakładanie (overlap) jeśli NIE zachodzi: new_to < p.from lub new_from > p.to
        if not (valid_to < p.valid_from or valid_from > p.valid_to):
            return False, f"Okres {valid_from} → {valid_to} nakłada się z istniejącą polisą {p.valid_from} → {p.valid_to}."
    return True, None

def validate_inspection_dates(date_do: date, valid_to: date):
    if not date_do or not valid_to:
        return False, "Podaj datę badania i ważności."
    if date_do > valid_to:
        return False, "Data badania nie może być po dacie ważności."
    return True, None

# -------------------
# ROUTES
# -------------------

# Dashboard (punkt 2)
@app.get('/')
def dashboard():
    cars = Car.query.order_by(Car.make, Car.model).all()

    # Najbliższe terminy z ostatnich wpisów
    upcoming_days = 60  # zakres widoczności
    today = date.today()
    oc_upcoming = []
    ti_upcoming = []
    oc_expired = []
    ti_expired = []

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

    # sortuj najbliższe
    oc_upcoming.sort(key=lambda t: t[1])
    ti_upcoming.sort(key=lambda t: t[1])
    oc_expired.sort(key=lambda t: t[1])   # najstarsze wygasłe na górze
    ti_expired.sort(key=lambda t: t[1])

    return render_template(
        'index.html',
        cars_count=len(cars),
        oc_upcoming=oc_upcoming,
        ti_upcoming=ti_upcoming,
        oc_expired=oc_expired,
        ti_expired=ti_expired,
        upcoming_days=upcoming_days
    )

# Lista aut
@app.get('/cars')
def list_cars():
    cars = Car.query.order_by(Car.make, Car.model).all()
    return render_template('cars.html', cars=cars)
@app.get('/about')
def about():
    return render_template('about.html')

# Dodanie auta
@app.route('/cars/new', methods=['GET','POST'])
def car_new():
    if request.method == 'POST':
        car = Car(
            make=(request.form.get('make') or '').strip(),
            model=(request.form.get('model') or '').strip(),
            year=int(request.form.get('year') or 0) or None,
            vin=(request.form.get('vin') or '').strip() or None,
            reg_number=(request.form.get('reg_number') or '').strip() or None,
            first_registration=parse_date(request.form.get('first_registration'))
        )
        db.session.add(car)
        db.session.commit()
        flash('Dodano auto ✅', 'success')
        return redirect(url_for('list_cars'))
    return render_template('car_form.html')

# Szczegóły auta
@app.get('/cars/<int:car_id>')
def car_detail(car_id):
    car = Car.query.get_or_404(car_id)
    odo_desc = car.odometer_entries.order_by(desc(OdometerEntry.date), desc(OdometerEntry.id)).all()
    odo_asc  = car.odometer_entries.order_by(OdometerEntry.date.asc(), OdometerEntry.id.asc()).all()

    # 👇 przygotuj gotowe listy do Chart.js
    odo_labels = [e.date.isoformat() for e in odo_asc]  # np. '2025-10-07'
    odo_values = [e.km for e in odo_asc]

    oc  = car.insurance_policies.order_by(desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)).all()
    ti  = car.tech_inspections.order_by(desc(TechInspection.valid_to), desc(TechInspection.id)).all()

    return render_template(
        'car_detail.html',
        car=car,
        odo=odo_desc,
        odo_labels=odo_labels,
        odo_values=odo_values,
        oc=oc,
        ti=ti
    )



# --- HISTORIA: DODAWANIE / EDYCJA / USUWANIE (punkt 1 + 3 walidacje) ---

# ODOMETER
@app.post('/cars/<int:car_id>/odometer/new')
def odometer_new(car_id):
    car = Car.query.get_or_404(car_id)
    when = parse_date(request.form.get('date'))
    km = int(request.form.get('km') or 0)
    ok, msg = validate_odometer(car.id, when, km, None)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('car_detail', car_id=car.id))

    entry = OdometerEntry(car_id=car.id, date=when, km=km,
                          note=(request.form.get('note') or '').strip() or None)
    db.session.add(entry)
    db.session.commit()
    flash('Dodano wpis przebiegu ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))

@app.route('/odometer/<int:entry_id>/edit', methods=['GET','POST'])
def odometer_edit(entry_id):
    entry = OdometerEntry.query.get_or_404(entry_id)
    car = entry.car
    if request.method == 'POST':
        when = parse_date(request.form.get('date'))
        km = int(request.form.get('km') or 0)
        ok, msg = validate_odometer(car.id, when, km, entry.id)
        if not ok:
            flash(msg, 'danger')
            return redirect(url_for('odometer_edit', entry_id=entry.id))
        entry.date = when
        entry.km = km
        entry.note = (request.form.get('note') or '').strip() or None
        db.session.commit()
        flash('Zaktualizowano wpis przebiegu ✅', 'success')
        return redirect(url_for('car_detail', car_id=car.id))
    return render_template('odometer_form.html', car=car, entry=entry)

@app.post('/odometer/<int:entry_id>/delete')
def odometer_delete(entry_id):
    entry = OdometerEntry.query.get_or_404(entry_id)
    car_id = entry.car_id
    db.session.delete(entry)
    db.session.commit()
    flash('Usunięto wpis przebiegu 🗑️', 'success')
    return redirect(url_for('car_detail', car_id=car_id))

# INSURANCE
@app.post('/cars/<int:car_id>/insurance/new')
def insurance_new(car_id):
    car = Car.query.get_or_404(car_id)
    valid_from = parse_date(request.form.get('valid_from'))
    valid_to = parse_date(request.form.get('valid_to'))
    ok, msg = validate_insurance_interval(car.id, valid_from, valid_to, None)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('car_detail', car_id=car.id))

    policy = InsurancePolicy(
        car_id=car.id,
        valid_from=valid_from,
        valid_to=valid_to,
        insurer=(request.form.get('insurer') or '').strip() or None,
        policy_no=(request.form.get('policy_no') or '').strip() or None
    )
    db.session.add(policy)
    db.session.commit()
    flash('Dodano polisę OC ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))

@app.route('/insurance/<int:policy_id>/edit', methods=['GET','POST'])
def insurance_edit(policy_id):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    car = policy.car
    if request.method == 'POST':
        valid_from = parse_date(request.form.get('valid_from'))
        valid_to = parse_date(request.form.get('valid_to'))
        ok, msg = validate_insurance_interval(car.id, valid_from, valid_to, policy.id)
        if not ok:
            flash(msg, 'danger')
            return redirect(url_for('insurance_edit', policy_id=policy.id))
        policy.valid_from = valid_from
        policy.valid_to = valid_to
        policy.insurer = (request.form.get('insurer') or '').strip() or None
        policy.policy_no = (request.form.get('policy_no') or '').strip() or None
        db.session.commit()
        flash('Zaktualizowano polisę OC ✅', 'success')
        return redirect(url_for('car_detail', car_id=car.id))
    return render_template('insurance_form.html', car=car, policy=policy)

@app.post('/insurance/<int:policy_id>/delete')
def insurance_delete(policy_id):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    car_id = policy.car_id
    db.session.delete(policy)
    db.session.commit()
    flash('Usunięto polisę OC 🗑️', 'success')
    return redirect(url_for('car_detail', car_id=car_id))

# TECH INSPECTION
@app.post('/cars/<int:car_id>/inspection/new')
def inspection_new(car_id):
    car = Car.query.get_or_404(car_id)
    date_do = parse_date(request.form.get('date'))
    valid_to = parse_date(request.form.get('valid_to'))
    ok, msg = validate_inspection_dates(date_do, valid_to)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('car_detail', car_id=car.id))

    ins = TechInspection(
        car_id=car.id,
        date=date_do,
        valid_to=valid_to,
        result=(request.form.get('result') or '').strip() or None,
        station=(request.form.get('station') or '').strip() or None,
        note=(request.form.get('note') or '').strip() or None
    )
    db.session.add(ins)
    db.session.commit()
    flash('Dodano przegląd ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))

@app.route('/inspection/<int:ins_id>/edit', methods=['GET','POST'])
def inspection_edit(ins_id):
    ins = TechInspection.query.get_or_404(ins_id)
    car = ins.car
    if request.method == 'POST':
        date_do = parse_date(request.form.get('date'))
        valid_to = parse_date(request.form.get('valid_to'))
        ok, msg = validate_inspection_dates(date_do, valid_to)
        if not ok:
            flash(msg, 'danger')
            return redirect(url_for('inspection_edit', ins_id=ins.id))
        ins.date = date_do
        ins.valid_to = valid_to
        ins.result = (request.form.get('result') or '').strip() or None
        ins.station = (request.form.get('station') or '').strip() or None
        ins.note = (request.form.get('note') or '').strip() or None
        db.session.commit()
        flash('Zaktualizowano przegląd ✅', 'success')
        return redirect(url_for('car_detail', car_id=car.id))
    return render_template('inspection_form.html', car=car, ins=ins)

@app.post('/inspection/<int:ins_id>/delete')
def inspection_delete(ins_id):
    ins = TechInspection.query.get_or_404(ins_id)
    car_id = ins.car_id
    db.session.delete(ins)
    db.session.commit()
    flash('Usunięto przegląd 🗑️', 'success')
    return redirect(url_for('car_detail', car_id=car_id))

#usuń auto z historią
@app.post('/cars/<int:car_id>/delete')
def car_delete(car_id):
    car = Car.query.get_or_404(car_id)
    try:
        db.session.delete(car)  # skasuje też powiązane wpisy dzięki cascade
        db.session.commit()
        flash('Usunięto auto i całą powiązaną historię 🗑️', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Nie udało się usunąć: {e}', 'danger')
    return redirect(url_for('list_cars'))

if __name__ == '__main__':
    app.run(debug=True)
