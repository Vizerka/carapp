from flask import abort
from flask_login import current_user
from .extensions import db
from .models import Car, car_owners


def accessible_cars_query():
    """Zapytanie ograniczone do aut widocznych dla bieżącego użytkownika."""
    query = Car.query
    if getattr(current_user, "is_admin", False):
        return query
    return query.join(car_owners).filter(car_owners.c.user_id == current_user.id)

def can_access_car(car: Car) -> bool:
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, "is_admin", False):
        return True
    return current_user in (car.owners or [])

def require_car_access(car: Car):
    if not can_access_car(car):
        abort(403)


def get_car_or_404(car_id: int) -> Car:
    car = db.get_or_404(Car, car_id)
    require_car_access(car)
    return car


def get_owned_entry_or_404(model, entry_id: int):
    """Pobiera rekord należący do auta i sprawdza dostęp do tego auta."""
    entry = db.get_or_404(model, entry_id)
    require_car_access(entry.car)
    return entry
