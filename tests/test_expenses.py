import io
import json
import zipfile
from datetime import date
from decimal import Decimal

from car_manager.extensions import db
from car_manager.models import Car, Expense, FuelEntry, OdometerEntry, ServiceEntry

from .conftest import csrf_token, login


def _cars(app):
    with app.app_context():
        owned = Car.query.filter_by(model="940").one()
        other = Car.query.filter_by(model="Jetta").one()
        return owned.id, other.id


def test_expense_crud_and_total_cost(app, client):
    owned_id, _ = _cars(app)
    login(client)
    token = csrf_token(client.get(f"/cars/{owned_id}?tab=expenses"))

    response = client.post(
        f"/cars/{owned_id}/expenses/new",
        data={
            "csrf_token": token,
            "date": "2026-09-10",
            "category": "insurance",
            "amount": "812,50",
            "title": "OC 2026/2027",
            "vendor": "Przykładowe TU",
            "km": "245000",
        },
    )
    assert response.status_code == 302
    assert "tab=expenses" in response.headers["Location"]

    with app.app_context():
        expense = Expense.query.filter_by(car_id=owned_id).one()
        assert expense.amount == Decimal("812.50")
        expense_id = expense.id

        db.session.add_all([
            FuelEntry(
                car_id=owned_id,
                date=date(2026, 9, 1),
                km=244000,
                liters=Decimal("40.000"),
                total_cost=Decimal("250.00"),
            ),
            ServiceEntry(
                car_id=owned_id,
                date=date(2026, 9, 2),
                title="Olej",
                cost=Decimal("300.00"),
            ),
            OdometerEntry(car_id=owned_id, date=date(2026, 1, 1), km=240000),
            OdometerEntry(car_id=owned_id, date=date(2026, 9, 10), km=245000),
        ])
        db.session.commit()

    dashboard = client.get(f"/cars/{owned_id}?cost_period=all")
    assert dashboard.status_code == 200
    assert "1,362.50".encode() in dashboard.data or b"1362.50" in dashboard.data
    assert "Ubezpieczenie".encode() in dashboard.data

    edit_token = csrf_token(client.get(f"/expenses/{expense_id}/edit"))
    edited = client.post(
        f"/expenses/{expense_id}/edit",
        data={
            "csrf_token": edit_token,
            "date": "2026-09-11",
            "category": "tax",
            "amount": "900",
            "title": "Opłata",
        },
    )
    assert edited.status_code == 302

    delete_token = csrf_token(client.get(f"/cars/{owned_id}?tab=expenses"))
    deleted = client.post(
        f"/expenses/{expense_id}/delete",
        data={"csrf_token": delete_token},
    )
    assert deleted.status_code == 302
    with app.app_context():
        assert db.session.get(Expense, expense_id) is None


def test_expense_routes_enforce_car_access(app, client):
    owned_id, other_id = _cars(app)
    login(client)
    token = csrf_token(client.get(f"/cars/{owned_id}"))

    response = client.post(
        f"/cars/{other_id}/expenses/new",
        data={
            "csrf_token": token,
            "date": "2026-09-10",
            "category": "other",
            "amount": "10",
            "title": "Nie moje",
        },
    )
    assert response.status_code == 403


def test_expense_rejects_unknown_category(app, client):
    owned_id, _ = _cars(app)
    login(client)
    token = csrf_token(client.get(f"/cars/{owned_id}"))

    response = client.post(
        f"/cars/{owned_id}/expenses/new",
        data={
            "csrf_token": token,
            "date": "2026-09-10",
            "category": "made-up",
            "amount": "10",
            "title": "Błędna kategoria",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Wybierz prawidłową kategorię".encode() in response.data
    with app.app_context():
        assert Expense.query.filter_by(car_id=owned_id).count() == 0


def test_backup_export_contains_expenses(app, client):
    owned_id, _ = _cars(app)
    with app.app_context():
        db.session.add(Expense(
            car_id=owned_id,
            date=date(2026, 9, 10),
            category="tires",
            amount=Decimal("1200.00"),
            title="Komplet opon",
        ))
        db.session.commit()

    login(client, "admin", "admin-password")
    response = client.get("/backup/export.zip")
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        payload = json.loads(archive.read("backup.json"))

    assert len(payload["expenses"]) == 1
    assert payload["expenses"][0]["title"] == "Komplet opon"
