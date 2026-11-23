from datetime import date, timedelta

from car_manager.extensions import db
from car_manager.models import (
    Car,
    InsurancePolicy,
    OdometerEntry,
    ServiceInterval,
    TechInspection,
)

from .conftest import login


def _owned_car_id(app):
    with app.app_context():
        return Car.query.filter_by(model="940").one().id


def test_dashboard_prioritizes_deadlines_and_moves_costs_to_bottom(app, client):
    car_id = _owned_car_id(app)
    today = date.today()
    with app.app_context():
        db.session.add_all([
            OdometerEntry(car_id=car_id, date=today, km=20_000),
            InsurancePolicy(
                car_id=car_id,
                valid_from=today - timedelta(days=367),
                valid_to=today - timedelta(days=2),
            ),
            TechInspection(
                car_id=car_id,
                date=today - timedelta(days=355),
                valid_to=today + timedelta(days=10),
            ),
            ServiceInterval(
                car_id=car_id,
                name="Wymiana oleju",
                interval_km=500,
                interval_days=30,
                last_done_km=19_000,
                last_done_date=today - timedelta(days=40),
                active=True,
            ),
        ])
        db.session.commit()

    login(client)
    response = client.get(f"/cars/{car_id}?tab=dash")
    assert response.status_code == 200

    html = response.data.decode()
    assert "Najbliższe terminy" in html
    assert "2 dni po terminie" in html
    assert "za 10 dni" in html
    assert "przekroczono o 500 km" in html
    assert "10 dni po terminie" in html
    assert "Szybkie akcje" not in html
    assert 'data-dashboard-main' in html
    assert 'data-dashboard-sidebar' in html
    assert f'action="/cars/{car_id}/odometer/new"' in html
    assert 'data-bs-target="#modalFuel"' in html
    assert html.index('data-dashboard-costs') > html.index('data-dashboard-sidebar')


def test_interval_tab_uses_independent_time_and_mileage_messages(app, client):
    car_id = _owned_car_id(app)
    today = date.today()
    with app.app_context():
        db.session.add_all([
            OdometerEntry(car_id=car_id, date=today, km=101_000),
            ServiceInterval(
                car_id=car_id,
                name="Rozrząd",
                interval_km=5_000,
                interval_days=365,
                last_done_km=100_000,
                last_done_date=today - timedelta(days=300),
                active=True,
            ),
        ])
        db.session.commit()

    login(client)
    response = client.get(f"/cars/{car_id}?tab=iv")
    assert response.status_code == 200
    assert "zostało 4000 km".encode() in response.data
    assert "za 65 dni".encode() in response.data
    assert "Każdy termin pokazuje osobno".encode() in response.data
