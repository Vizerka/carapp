from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from datetime import datetime, date
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cars.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

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
    

# Inicjalizacja bazy (Flask 3.x – bez before_first_request)
with app.app_context():
    db.create_all()

# --- POMOCNICZE ---

def parse_date(s: str | None):
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

@app.get('/')
def home():
    return render_template('index.html')    
@app.get('/about')
def about():
    return render_template('about.html')


@app.get('/cars')
def list_cars():
    cars = Car.query.order_by(Car.make, Car.model).all()
    return render_template('cars.html', cars=cars)

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

@app.get('/cars/<int:car_id>')
def car_detail(car_id):
    car = Car.query.get_or_404(car_id)
    # posortuj historię malejąco po dacie
    odo = car.odometer_entries.order_by(desc(OdometerEntry.date), desc(OdometerEntry.id)).all()
    oc  = car.insurance_policies.order_by(desc(InsurancePolicy.valid_to), desc(InsurancePolicy.id)).all()
    ti  = car.tech_inspections.order_by(desc(TechInspection.valid_to), desc(TechInspection.id)).all()
    return render_template('car_detail.html', car=car, odo=odo, oc=oc, ti=ti)

# --- DODAWANIE WPISÓW HISTORII ---

@app.post('/cars/<int:car_id>/odometer/new')
def odometer_new(car_id):
    car = Car.query.get_or_404(car_id)
    entry = OdometerEntry(
        car_id=car.id,
        date=parse_date(request.form.get('date')),
        km=int(request.form.get('km') or 0),
        note=(request.form.get('note') or '').strip() or None
    )
    db.session.add(entry)
    db.session.commit()
    flash('Dodano wpis przebiegu ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))

@app.post('/cars/<int:car_id>/insurance/new')
def insurance_new(car_id):
    car = Car.query.get_or_404(car_id)
    policy = InsurancePolicy(
        car_id=car.id,
        valid_from=parse_date(request.form.get('valid_from')),
        valid_to=parse_date(request.form.get('valid_to')),
        insurer=(request.form.get('insurer') or '').strip() or None,
        policy_no=(request.form.get('policy_no') or '').strip() or None
    )
    db.session.add(policy)
    db.session.commit()
    flash('Dodano polisę OC ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))

@app.post('/cars/<int:car_id>/inspection/new')
def inspection_new(car_id):
    car = Car.query.get_or_404(car_id)
    ins = TechInspection(
        car_id=car.id,
        date=parse_date(request.form.get('date')),
        valid_to=parse_date(request.form.get('valid_to')),
        result=(request.form.get('result') or '').strip() or None,
        station=(request.form.get('station') or '').strip() or None,
        note=(request.form.get('note') or '').strip() or None
    )
    db.session.add(ins)
    db.session.commit()
    flash('Dodano przegląd ✅', 'success')
    return redirect(url_for('car_detail', car_id=car.id))

if __name__ == "__main__":
    app.run(debug=True)  # auto-reload + debugger
# Ustaw debug=True tylko w środowisku deweloperskim!