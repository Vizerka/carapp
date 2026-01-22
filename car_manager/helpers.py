from __future__ import annotations

import os
from datetime import datetime, date, timedelta
from decimal import Decimal
from flask import current_app
from sqlalchemy import desc, func
from sqlalchemy.inspection import inspect as sa_inspect

from .extensions import db
from .models import OdometerEntry, ServiceInterval

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}

def parse_date(s: str | None):
    try:
        s = (s or "").strip()
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        return None

def parse_decimal(s: str | None) -> Decimal | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_car_upload_dir(car_id: int) -> str:
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], str(car_id))
    os.makedirs(path, exist_ok=True)
    return path

def days_left_filter(d):
    if not d:
        return None
    return (d - date.today()).days

def _model_to_dict(obj):
    out = {}
    mapper = sa_inspect(obj.__class__)
    for col in mapper.columns:
        val = getattr(obj, col.key)
        if isinstance(val, (date, datetime)):
            out[col.key] = val.isoformat()
        elif isinstance(val, Decimal):
            out[col.key] = float(val)
        else:
            out[col.key] = val
    return out

def _parse_any_date(s):
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s)
        return date.fromisoformat(s)
    except ValueError:
        return None

def _dict_to_model_kwargs(model_cls, data: dict):
    mapper = sa_inspect(model_cls)
    kwargs = {}
    for col in mapper.columns:
        key = col.key
        if key not in data:
            continue
        if key == "id":
            continue
        val = data[key]
        if hasattr(col.type, "python_type") and col.type.python_type in (date, datetime):
            kwargs[key] = _parse_any_date(val)
        else:
            kwargs[key] = val
    return kwargs

def _safe_unique_filename(existing_names: set[str], filename: str) -> str:
    if filename not in existing_names:
        existing_names.add(filename)
        return filename
    base, dot, ext = filename.rpartition(".")
    if not dot:
        base, ext = filename, ""
    i = 2
    while True:
        cand = f"{base}_{i}.{ext}" if ext else f"{base}_{i}"
        if cand not in existing_names:
            existing_names.add(cand)
            return cand
        i += 1

def compute_interval_status(iv: ServiceInterval, current_km: int | None, today: date):
    next_km = None
    km_left = None
    next_date = None
    days_left = None

    if iv.interval_km and iv.last_done_km is not None:
        next_km = iv.last_done_km + iv.interval_km
        if current_km is not None:
            km_left = next_km - current_km

    if iv.interval_days and iv.last_done_date:
        next_date = iv.last_done_date + timedelta(days=int(iv.interval_days))
        days_left = (next_date - today).days

    status = "unknown"
    due = False
    soon = False

    if km_left is not None:
        if km_left <= 0:
            due = True
        elif km_left <= 500:
            soon = True

    if days_left is not None:
        if days_left <= 0:
            due = True
        elif days_left <= 14:
            soon = True

    if due:
        status = "due"
    elif soon:
        status = "soon"
    else:
        if (km_left is not None) or (days_left is not None):
            status = "ok"

    return {
        "next_km": next_km,
        "km_left": km_left,
        "next_date": next_date,
        "days_left": days_left,
        "status": status,
    }

def upsert_odometer_for_date(car_id: int, when: date, km: int, note: str | None = None):
    existing = (OdometerEntry.query
                .filter(OdometerEntry.car_id == car_id, OdometerEntry.date == when)
                .order_by(desc(OdometerEntry.id))
                .first())

    if existing:
        if km > existing.km:
            existing.km = km
        if note:
            existing.note = f"{existing.note}; {note}" if existing.note else note
        return existing

    entry = OdometerEntry(car_id=car_id, date=when, km=km, note=note)
    db.session.add(entry)
    return entry
