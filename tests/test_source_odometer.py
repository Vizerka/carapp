from car_manager.models import Car, FuelEntry, OdometerEntry, ServiceEntry

from .conftest import csrf_token, login


def _owned_car_id(app):
    with app.app_context():
        return Car.query.filter_by(model="940").one().id


def test_fuel_edit_and_delete_keep_odometer_in_sync(app, client):
    car_id = _owned_car_id(app)
    login(client)
    token = csrf_token(client.get(f"/cars/{car_id}"))

    response = client.post(
        f"/cars/{car_id}/fuel/new",
        data={
            "csrf_token": token,
            "date": "2026-09-01",
            "km": "200000",
            "liters": "50.5",
            "full_tank": "1",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        fill = FuelEntry.query.one()
        fill_id = fill.id
        odo = OdometerEntry.query.filter_by(source_type="fuel", source_id=fill.id).one()
        assert (odo.date.isoformat(), odo.km) == ("2026-09-01", 200000)

    response = client.post(
        f"/fuel/{fill_id}/edit",
        data={
            "csrf_token": token,
            "date": "2026-09-02",
            "km": "200123",
            "liters": "51",
            "full_tank": "1",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        odo = OdometerEntry.query.filter_by(source_type="fuel", source_id=fill_id).one()
        assert (odo.date.isoformat(), odo.km) == ("2026-09-02", 200123)

    assert client.post(
        f"/fuel/{fill_id}/delete", data={"csrf_token": token}
    ).status_code == 302
    with app.app_context():
        assert FuelEntry.query.count() == 0
        assert OdometerEntry.query.filter_by(source_type="fuel", source_id=fill_id).count() == 0


def test_service_edit_without_km_removes_only_its_odometer(app, client):
    car_id = _owned_car_id(app)
    login(client)
    token = csrf_token(client.get(f"/cars/{car_id}"))

    response = client.post(
        f"/cars/{car_id}/service/new",
        data={
            "csrf_token": token,
            "date": "2026-09-03",
            "km": "200500",
            "title": "Olej",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        service = ServiceEntry.query.one()
        service_id = service.id
        assert OdometerEntry.query.filter_by(
            source_type="service", source_id=service_id
        ).count() == 1

    response = client.post(
        f"/service/{service_id}/edit",
        data={
            "csrf_token": token,
            "date": "2026-09-03",
            "km": "",
            "title": "Olej i filtr",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        assert OdometerEntry.query.filter_by(
            source_type="service", source_id=service_id
        ).count() == 0
