from car_manager.models import Car

from .conftest import csrf_token, login


def _car_ids(app):
    with app.app_context():
        owned = Car.query.filter_by(model="940").one().id
        other = Car.query.filter_by(model="Jetta").one().id
        return owned, other


def test_user_sees_only_assigned_cars(app, client):
    owned_id, other_id = _car_ids(app)
    login(client)

    listing = client.get("/cars")
    assert listing.status_code == 200
    assert b"Volvo" in listing.data
    assert b"Jetta" not in listing.data
    assert client.get(f"/cars/{owned_id}").status_code == 200
    assert client.get(f"/cars/{other_id}").status_code == 403


def test_admin_can_access_every_car(app, client):
    _, other_id = _car_ids(app)
    login(client, "admin", "admin-password")
    assert client.get(f"/cars/{other_id}").status_code == 200


def test_post_without_csrf_is_rejected(app, client):
    owned_id, _ = _car_ids(app)
    login(client)

    response = client.post(f"/cars/{owned_id}/delete")
    assert response.status_code == 400


def test_new_car_is_assigned_to_non_admin(app, client):
    login(client)
    token = csrf_token(client.get("/cars/new"))
    response = client.post(
        "/cars/new",
        data={"csrf_token": token, "make": "Skoda", "model": "Fabia"},
    )
    assert response.status_code == 302

    with app.app_context():
        car = Car.query.filter_by(make="Skoda", model="Fabia").one()
        assert [owner.username for owner in car.owners] == ["owner"]
