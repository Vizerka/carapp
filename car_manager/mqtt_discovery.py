from __future__ import annotations

import json
import os
from datetime import date, datetime

from flask import current_app
from paho.mqtt import publish

from .extensions import db
from .models import Car, FuelEntry, MqttPublishedCar
from .statistics import fuel_statistics, monthly_total_cost, next_service_summary


SENSORS = {
    "odometer": {"name": "Przebieg", "field": "odometer_km", "unit": "km", "icon": "mdi:counter"},
    "insurance_valid_to": {"name": "OC do", "field": "insurance_valid_to", "device_class": "date", "icon": "mdi:shield-car"},
    "inspection_valid_to": {"name": "Przegląd do", "field": "inspection_valid_to", "device_class": "date", "icon": "mdi:car-wrench"},
    "insurance_days": {"name": "OC pozostało", "field": "insurance_days", "unit": "d", "icon": "mdi:calendar-clock"},
    "inspection_days": {"name": "Przegląd pozostało", "field": "inspection_days", "unit": "d", "icon": "mdi:calendar-clock"},
    "next_service_km": {"name": "Następny serwis km", "field": "next_service_km", "unit": "km", "icon": "mdi:wrench-clock"},
    "next_service_days": {"name": "Następny serwis dni", "field": "next_service_days", "unit": "d", "icon": "mdi:wrench-clock"},
    "last_consumption": {"name": "Ostatnie spalanie", "field": "last_consumption", "unit": "L/100 km", "icon": "mdi:fuel"},
    "average_consumption": {"name": "Średnie spalanie", "field": "average_consumption", "unit": "L/100 km", "icon": "mdi:chart-line"},
    "monthly_cost": {"name": "Koszt w miesiącu", "field": "monthly_cost", "unit": "PLN", "icon": "mdi:cash"},
}

BINARY_SENSORS = {
    "insurance_expiring": {"name": "OC wygasa", "field": "insurance_expiring", "icon": "mdi:shield-alert"},
    "inspection_expiring": {"name": "Przegląd wygasa", "field": "inspection_expiring", "icon": "mdi:car-clock"},
    "service_due": {"name": "Serwis wymagany", "field": "service_due", "icon": "mdi:car-wrench"},
}


def _settings():
    host = (os.environ.get("MQTT_HOST") or "").strip()
    username = (os.environ.get("MQTT_USERNAME") or "").strip()
    password = os.environ.get("MQTT_PASSWORD") or ""
    if not host or not username or not password:
        return None
    return {
        "hostname": host,
        "port": int(os.environ.get("MQTT_PORT", "1883")),
        "auth": {"username": username, "password": password},
    }


def _iso(value):
    return value.isoformat() if value else None


def _car_state(car: Car) -> dict:
    odometer = car.last_odometer
    insurance = car.last_insurance
    inspection = car.last_inspection
    today = date.today()
    insurance_days = (insurance.valid_to - today).days if insurance and insurance.valid_to else None
    inspection_days = (inspection.valid_to - today).days if inspection and inspection.valid_to else None
    fills = car.fuel_entries.order_by(FuelEntry.date, FuelEntry.id).all()
    fuel = fuel_statistics(fills, today)
    _, service = next_service_summary(car, today)
    service_km = service["km_left"] if service else None
    service_days = service["days_left"] if service else None
    return {
        "car_id": car.id,
        "make": car.make,
        "model": car.model,
        "registration_number": car.reg_number,
        "year": car.year,
        "odometer_km": odometer.km if odometer else None,
        "odometer_date": _iso(odometer.date) if odometer else None,
        "insurance_valid_to": _iso(insurance.valid_to) if insurance else None,
        "inspection_valid_to": _iso(inspection.valid_to) if inspection else None,
        "insurance_days": insurance_days,
        "inspection_days": inspection_days,
        "next_service_km": service_km,
        "next_service_days": service_days,
        "last_consumption": round(fuel["last"], 2) if fuel["last"] is not None else None,
        "average_consumption": round(fuel["average_all"], 2) if fuel["average_all"] is not None else None,
        "monthly_cost": float(monthly_total_cost(car, today)),
        "insurance_expiring": "ON" if insurance_days is not None and insurance_days <= 30 else "OFF",
        "inspection_expiring": "ON" if inspection_days is not None and inspection_days <= 30 else "OFF",
        "service_due": "ON" if (
            (service_km is not None and service_km <= 0)
            or (service_days is not None and service_days <= 0)
        ) else "OFF",
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }


def _device(car: Car) -> dict:
    registration = car.reg_number or f"ID {car.id}"
    display_name = f"{car.make} {car.model} {registration}"
    return {
        "identifiers": [f"carapp_car_{car.id}"],
        "name": display_name,
        "manufacturer": car.make,
        "model": car.model,
    }


def _discovery_config(car: Car, state_topic: str, key: str, definition: dict, binary=False) -> dict:
    config = {
        "name": definition["name"],
        "unique_id": f"carapp_car_{car.id}_{key}",
        "state_topic": state_topic,
        "value_template": "{{ value_json.%s }}" % definition["field"],
        "icon": definition["icon"],
        "availability_topic": "carapp/status",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": _device(car),
        "origin": {
            "name": "CarApp",
            "sw_version": "1",
            "support_url": "http://carapp.vizera.dev",
        },
    }
    if definition.get("unit"):
        config["unit_of_measurement"] = definition["unit"]
    if definition.get("device_class"):
        config["device_class"] = definition["device_class"]
    if key == "odometer":
        config["json_attributes_topic"] = state_topic
    if binary:
        config["payload_on"] = "ON"
        config["payload_off"] = "OFF"
    return config


def publish_all_cars() -> bool:
    """Publikuje stan wszystkich aut i usuwa osierocone encje discovery."""
    settings = _settings()
    if not settings:
        current_app.logger.info("MQTT wyłączone: brak MQTT_HOST/USERNAME/PASSWORD")
        return False

    cars = Car.query.order_by(Car.id).all()
    current_ids = {car.id for car in cars}
    published_ids = {row.car_id for row in MqttPublishedCar.query.all()}
    removed_ids = published_ids - current_ids

    messages = [{"topic": "carapp/status", "payload": "online", "qos": 1, "retain": True}]

    for car in cars:
        state_topic = f"carapp/cars/{car.id}/state"
        for key, definition in SENSORS.items():
            messages.append({
                "topic": f"homeassistant/sensor/carapp_car_{car.id}_{key}/config",
                "payload": json.dumps(
                    _discovery_config(car, state_topic, key, definition), ensure_ascii=False
                ),
                "qos": 1,
                "retain": True,
            })
        for key, definition in BINARY_SENSORS.items():
            messages.append({
                "topic": f"homeassistant/binary_sensor/carapp_car_{car.id}_{key}/config",
                "payload": json.dumps(
                    _discovery_config(car, state_topic, key, definition, binary=True),
                    ensure_ascii=False,
                ),
                "qos": 1,
                "retain": True,
            })
        messages.append({
            "topic": state_topic,
            "payload": json.dumps(_car_state(car), ensure_ascii=False),
            "qos": 1,
            "retain": True,
        })

    for car_id in removed_ids:
        for key in SENSORS:
            messages.append({
                "topic": f"homeassistant/sensor/carapp_car_{car_id}_{key}/config",
                "payload": "",
                "qos": 1,
                "retain": True,
            })
        for key in BINARY_SENSORS:
            messages.append({
                "topic": f"homeassistant/binary_sensor/carapp_car_{car_id}_{key}/config",
                "payload": "",
                "qos": 1,
                "retain": True,
            })
        messages.append({
            "topic": f"carapp/cars/{car_id}/state",
            "payload": "",
            "qos": 1,
            "retain": True,
        })

    publish.multiple(messages, **settings)

    if removed_ids:
        MqttPublishedCar.query.filter(MqttPublishedCar.car_id.in_(removed_ids)).delete(
            synchronize_session=False
        )
    for car_id in current_ids:
        row = db.session.get(MqttPublishedCar, car_id)
        if row:
            row.published_at = datetime.utcnow()
        else:
            db.session.add(MqttPublishedCar(car_id=car_id))
    db.session.commit()
    return True


def publish_safely() -> None:
    try:
        publish_all_cars()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Nie udało się opublikować danych CarApp przez MQTT")
