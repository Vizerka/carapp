from datetime import date, timedelta

from car_manager.extensions import db
from car_manager.models import Car, InsurancePolicy
from tests.conftest import login


def test_home_uses_visible_cars_and_real_deadlines(app, client):
    with app.app_context():
        car = Car.query.filter_by(make="Volvo", model="940").one()
        today = date.today()
        db.session.add(InsurancePolicy(car=car, valid_from=today, valid_to=today + timedelta(days=3)))
        db.session.commit()

    login(client)
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Volvo 940" in html
    assert "VW Jetta" not in html
    assert 'data-garage-status="upcoming"' in html
    assert "Termin za 3 dni" in html
    assert "css/theme.css" in html
