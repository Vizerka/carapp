import re

import pytest

from car_manager import create_app
from car_manager.extensions import db
from car_manager.models import Car, User


@pytest.fixture()
def app(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.delenv("MQTT_HOST", raising=False)
    monkeypatch.delenv("MQTT_USERNAME", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)

    app = create_app()
    app.config.update(TESTING=True, SERVER_NAME="localhost")

    with app.app_context():
        db.create_all()

        owner = User(username="owner", is_active=True, is_admin=False)
        owner.set_password("owner-password")
        stranger = User(username="stranger", is_active=True, is_admin=False)
        stranger.set_password("stranger-password")
        admin = User(username="admin", is_active=True, is_admin=True)
        admin.set_password("admin-password")

        owned_car = Car(make="Volvo", model="940")
        other_car = Car(make="VW", model="Jetta")
        owner.cars.append(owned_car)
        stranger.cars.append(other_car)

        db.session.add_all([owner, stranger, admin, owned_car, other_car])
        db.session.commit()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_token(response) -> str:
    match = re.search(
        rb'name="csrf_token"\s+value="([^"]+)"',
        response.data,
    )
    assert match, "Brak tokenu CSRF w odpowiedzi"
    return match.group(1).decode()


def login(client, username="owner", password="owner-password") -> str:
    token = csrf_token(client.get("/login"))
    response = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
    )
    assert response.status_code == 302
    return token
