import json
import re
from datetime import date

from car_manager.extensions import db
from car_manager.models import Car, OdometerEntry

from .conftest import login


def _owned_car_id(app):
    with app.app_context():
        return Car.query.filter_by(model="940").one().id


def _chart_points(response):
    match = re.search(rb"data-points='([^']*)'", response.data)
    assert match, "Brak danych wykresu przebiegu w odpowiedzi"
    return json.loads(match.group(1))


def test_mileage_chart_keeps_all_points_sorted_by_date_and_id(app, client):
    car_id = _owned_car_id(app)
    with app.app_context():
        entries = [
            OdometerEntry(
                car_id=car_id,
                date=date(2026, 11, 23),
                km=81490,
                note="Wpis serwisowy",
            ),
            OdometerEntry(
                car_id=car_id,
                date=date(2020, 3, 11),
                km=32000,
                note="Zdjęcie licznika",
            ),
            OdometerEntry(
                car_id=car_id,
                date=date(2020, 3, 11),
                km=32500,
                note=None,
            ),
            # Rzeczywisty zapis pozostaje bez automatycznego prostowania danych.
            OdometerEntry(
                car_id=car_id,
                date=date(2023, 7, 15),
                km=90000,
                note="Odczyt przed cofnięciem licznika",
            ),
            OdometerEntry(
                car_id=car_id,
                date=date(2025, 11, 22),
                km=68320,
                note="Starszy odczyt dodany później - niższa wartość",
            ),
        ]
        db.session.add_all(entries)
        db.session.commit()
        expected_ids = [
            entries[1].id, entries[2].id, entries[3].id, entries[4].id,
            entries[0].id,
        ]

    login(client)
    response = client.get(f"/cars/{car_id}?tab=dash")
    assert response.status_code == 200

    points = _chart_points(response)
    assert [point["id"] for point in points] == expected_ids
    assert [point["date"] for point in points] == [
        "2020-03-11", "2020-03-11", "2023-07-15", "2025-11-22",
        "2026-11-23",
    ]
    assert [point["km"] for point in points] == [32000, 32500, 90000, 68320, 81490]
    assert points[3]["label"] == "Starszy odczyt dodany później - niższa wartość"
    assert points[1]["label"] == "Odczyt licznika"
    assert b"mileage-chart.js" in response.data
    assert b"mileage-chart.css" in response.data
    assert b'id="odoChart"' not in response.data


def test_mileage_chart_empty_state(app, client):
    car_id = _owned_car_id(app)
    login(client)
    response = client.get(f"/cars/{car_id}?tab=dash")
    assert response.status_code == 200
    assert "Brak danych przebiegu".encode() in response.data
    assert b"data-mileage-chart" not in response.data
