import io
from datetime import date
from decimal import Decimal

from car_manager.extensions import db
from car_manager.models import (
    Car, Document, DocumentLink, FuelEntry, Modification, ModificationTask,
    ServiceEntry, ServiceItem, TireEvent, TireSet,
)
from car_manager.mqtt_discovery import BINARY_SENSORS, SENSORS, _car_state
from car_manager.statistics import fuel_statistics

from .conftest import csrf_token, login


def _owned_car(app):
    with app.app_context():
        return Car.query.filter_by(model="940").one().id


def test_all_car_tabs_render(app, client):
    car_id = _owned_car(app)
    login(client)
    for tab in (
        "dash", "history", "odo", "oc", "ti", "fuel", "iv", "svc",
        "tires", "mods", "expenses", "docs",
    ):
        response = client.get(f"/cars/{car_id}?tab={tab}")
        assert response.status_code == 200, tab


def test_service_items_recalculate_service_cost(app, client):
    car_id = _owned_car(app)
    with app.app_context():
        service = ServiceEntry(car_id=car_id, date=date(2026, 9, 1), title="Rozrząd")
        db.session.add(service)
        db.session.commit()
        service_id = service.id

    login(client)
    token = csrf_token(client.get(f"/service/{service_id}/edit"))
    response = client.post(
        f"/service/{service_id}/items/new",
        data={
            "csrf_token": token,
            "item_type": "part",
            "name": "Rolka prowadząca",
            "manufacturer": "INA",
            "part_number": "532 0000 10",
            "quantity": "2",
            "unit_price": "50,00",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        item = ServiceItem.query.filter_by(service_id=service_id).one()
        assert item.total_cost == Decimal("100.00")
        assert db.session.get(ServiceEntry, service_id).cost == Decimal("100.00")
        item_id = item.id

    token = csrf_token(client.get(f"/service/{service_id}/edit"))
    client.post(f"/service-items/{item_id}/delete", data={"csrf_token": token})
    with app.app_context():
        assert db.session.get(ServiceEntry, service_id).cost is None


def test_tires_modifications_timeline_and_document_link(app, client):
    car_id = _owned_car(app)
    with app.app_context():
        service = ServiceEntry(car_id=car_id, date=date(2026, 9, 2), title="Olej")
        db.session.add(service)
        db.session.commit()
        service_id = service.id

    login(client)
    token = csrf_token(client.get(f"/cars/{car_id}"))
    response = client.post(
        f"/cars/{car_id}/tires/new",
        data={"csrf_token": token, "name": "Lato", "season": "summer", "width": "205", "aspect_ratio": "55", "diameter": "16"},
    )
    assert response.status_code == 302
    with app.app_context():
        tire_set_id = TireSet.query.filter_by(car_id=car_id).one().id

    token = csrf_token(client.get(f"/tires/{tire_set_id}/events/new"))
    client.post(
        f"/tires/{tire_set_id}/events/new",
        data={"csrf_token": token, "date": "2026-04-15", "action": "installed", "km": "221430", "tread_fl": "6,2"},
    )

    token = csrf_token(client.get(f"/cars/{car_id}"))
    response = client.post(
        f"/cars/{car_id}/modifications/new",
        data={"csrf_token": token, "title": "Elektryczne szyby", "status": "in_progress", "started_date": "2026-09-01", "actual_cost": "380"},
    )
    assert response.status_code == 302
    with app.app_context():
        modification_id = Modification.query.filter_by(car_id=car_id).one().id

    token = csrf_token(client.get(f"/modifications/{modification_id}/edit"))
    client.post(
        f"/modifications/{modification_id}/tasks/new",
        data={"csrf_token": token, "title": "Kupić wiązkę"},
    )

    token = csrf_token(client.get(f"/cars/{car_id}?tab=docs"))
    response = client.post(
        f"/cars/{car_id}/documents/upload",
        data={
            "csrf_token": token,
            "file": (io.BytesIO(b"%PDF-1.4 test"), "faktura.pdf"),
            "category": "Faktura",
            "target": f"service:{service_id}",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302

    history = client.get(f"/cars/{car_id}?tab=history")
    assert "Założono: Lato".encode() in history.data
    assert "Elektryczne szyby".encode() in history.data
    docs = client.get(f"/cars/{car_id}?tab=docs")
    assert "Serwis 2026-09-02: Olej".encode() in docs.data

    with app.app_context():
        assert TireEvent.query.count() == 1
        assert ModificationTask.query.count() == 1
        assert Document.query.one().links[0].target_id == service_id


def test_fuel_statistics_and_mqtt_state(app):
    car_id = _owned_car(app)
    with app.app_context():
        fills = [
            FuelEntry(car_id=car_id, date=date(2026, 1, 1), km=1000, liters=Decimal("40"), total_cost=Decimal("240"), station="A", full_tank=True),
            FuelEntry(car_id=car_id, date=date(2026, 2, 1), km=1500, liters=Decimal("35"), total_cost=Decimal("210"), station="A", full_tank=True),
            FuelEntry(car_id=car_id, date=date(2026, 3, 1), km=2000, liters=Decimal("40"), total_cost=Decimal("260"), station="B", full_tank=True),
        ]
        db.session.add_all(fills)
        db.session.commit()
        stats = fuel_statistics(fills, date(2026, 9, 16))
        assert round(stats["last"], 2) == 8.00
        assert round(stats["average_price"], 3) == 6.174
        state = _car_state(db.session.get(Car, car_id))
        for definition in SENSORS.values():
            assert definition["field"] in state
        for definition in BINARY_SENSORS.values():
            assert definition["field"] in state


def test_backup_round_trip_for_new_models(app, client):
    car_id = _owned_car(app)
    with app.app_context():
        car = db.session.get(Car, car_id)
        car.reg_number = "TEST123"
        service = ServiceEntry(car_id=car_id, date=date(2026, 1, 1), title="Hamulce")
        db.session.add(service)
        db.session.flush()
        db.session.add(ServiceItem(service_id=service.id, item_type="part", name="Klocki", quantity=1, unit_price=Decimal("100")))
        tire_set = TireSet(car_id=car_id, name="Zima", season="winter")
        db.session.add(tire_set)
        db.session.flush()
        db.session.add(TireEvent(tire_set_id=tire_set.id, date=date(2026, 1, 2), action="installed", km=1000))
        modification = Modification(car_id=car_id, title="Hamulce 288", status="planned")
        db.session.add(modification)
        db.session.flush()
        db.session.add(ModificationTask(modification_id=modification.id, title="Jarzma", position=0))
        document = Document(car_id=car_id, stored_name="roundtrip.pdf", original_name="roundtrip.pdf")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentLink(document_id=document.id, target_type="service", target_id=service.id))
        db.session.commit()
        service_id = service.id

        upload_dir = app.config["UPLOAD_FOLDER"] + f"/{car_id}"
        import os
        os.makedirs(upload_dir, exist_ok=True)
        with open(upload_dir + "/roundtrip.pdf", "wb") as handle:
            handle.write(b"%PDF-1.4 test")

    login(client, "admin", "admin-password")
    exported = client.get("/backup/export.zip")
    assert exported.status_code == 200

    with app.app_context():
        DocumentLink.query.delete()
        ModificationTask.query.delete()
        TireEvent.query.delete()
        ServiceItem.query.delete()
        Document.query.delete()
        Modification.query.delete()
        TireSet.query.delete()
        db.session.commit()

    token = csrf_token(client.get("/backup"))
    imported = client.post(
        "/backup/import",
        data={"csrf_token": token, "file": (io.BytesIO(exported.data), "backup.zip")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 302
    with app.app_context():
        assert ServiceItem.query.one().name == "Klocki"
        assert TireEvent.query.one().action == "installed"
        assert ModificationTask.query.one().title == "Jarzma"
        link = DocumentLink.query.one()
        assert link.target_type == "service"
        assert link.target_id == service_id


def test_new_modules_enforce_car_access(app, client):
    with app.app_context():
        other_id = Car.query.filter_by(model="Jetta").one().id
        owned_id = Car.query.filter_by(model="940").one().id
    login(client)
    token = csrf_token(client.get(f"/cars/{owned_id}"))

    tire = client.post(
        f"/cars/{other_id}/tires/new",
        data={"csrf_token": token, "name": "Cudze", "season": "winter"},
    )
    modification = client.post(
        f"/cars/{other_id}/modifications/new",
        data={"csrf_token": token, "title": "Cudzy projekt", "status": "planned"},
    )
    assert tire.status_code == 403
    assert modification.status_code == 403
