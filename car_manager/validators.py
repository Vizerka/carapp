from __future__ import annotations

from datetime import date
from sqlalchemy import func

from .extensions import db
from .models import OdometerEntry, InsurancePolicy

def validate_odometer(car_id: int, when: date, km: int, entry_id: int | None = None):
    if not when:
        return False, "Podaj datę."
    if km is None:
        return False, "Podaj przebieg."

    filters_prev = [OdometerEntry.car_id == car_id, OdometerEntry.date <= when]
    filters_next = [OdometerEntry.car_id == car_id, OdometerEntry.date >= when]
    if entry_id is not None:
        filters_prev.append(OdometerEntry.id != entry_id)
        filters_next.append(OdometerEntry.id != entry_id)

    max_prev = db.session.query(func.max(OdometerEntry.km)).filter(*filters_prev).scalar()
    min_next = db.session.query(func.min(OdometerEntry.km)).filter(*filters_next).scalar()

    if max_prev is not None and km < max_prev:
        return False, f"Przebieg {km} km jest mniejszy niż wcześniejszy wpis {max_prev} km."
    if min_next is not None and km > min_next:
        return False, f"Przebieg {km} km jest większy niż późniejszy wpis {min_next} km."
    return True, None

def validate_insurance_interval(car_id: int, valid_from: date, valid_to: date, policy_id: int | None = None):
    if not valid_from or not valid_to:
        return False, "Podaj oba terminy (od/do)."
    if valid_from > valid_to:
        return False, "Data 'od' nie może być po dacie 'do'."

    q = InsurancePolicy.query.filter(InsurancePolicy.car_id == car_id)
    if policy_id is not None:
        q = q.filter(InsurancePolicy.id != policy_id)

    for p in q.all():
        if not (valid_to < p.valid_from or valid_from > p.valid_to):
            return False, f"Okres {valid_from} → {valid_to} nakłada się z polisą {p.valid_from} → {p.valid_to}."
    return True, None

def validate_inspection_dates(date_do: date, valid_to: date):
    if not date_do or not valid_to:
        return False, "Podaj datę badania i ważności."
    if date_do > valid_to:
        return False, "Data badania nie może być po dacie ważności."
    return True, None
