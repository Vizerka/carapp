from __future__ import annotations

import json
import os
from datetime import datetime

from flask import current_app
from paho.mqtt import publish

from .extensions import db
from .models import Car, MqttPublishedCar


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
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }


def _discovery_config(car: Car, state_topic: str) -> dict:
    registration = car.reg_number or f"ID {car.id}"
    display_name = f"{car.make} {car.model} {registration}"
    return {
        "name": "Przebieg",
        "unique_id": f"carapp_car_{car.id}_odometer",
        "state_topic": state_topic,
        "value_template": "{{ value_json.odometer_km }}",
        "json_attributes_topic": state_topic,
        "unit_of_measurement": "km",
        "icon": "mdi:car",
        "availability_topic": "carapp/status",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": {
            "identifiers": [f"carapp_car_{car.id}"],
            "name": display_name,
            "manufacturer": car.make,
            "model": car.model,
        },
        "origin": {
            "name": "CarApp",
            "sw_version": "1",
            "support_url": "http://carapp.vizera.dev",
        },
    }


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
        config_topic = f"homeassistant/sensor/carapp_car_{car.id}_odometer/config"
        messages.extend([
            {
                "topic": config_topic,
                "payload": json.dumps(_discovery_config(car, state_topic), ensure_ascii=False),
                "qos": 1,
                "retain": True,
            },
            {
                "topic": state_topic,
                "payload": json.dumps(_car_state(car), ensure_ascii=False),
                "qos": 1,
                "retain": True,
            },
        ])

    for car_id in removed_ids:
        messages.extend([
            {
                "topic": f"homeassistant/sensor/carapp_car_{car_id}_odometer/config",
                "payload": "",
                "qos": 1,
                "retain": True,
            },
            {
                "topic": f"carapp/cars/{car_id}/state",
                "payload": "",
                "qos": 1,
                "retain": True,
            },
        ])

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
