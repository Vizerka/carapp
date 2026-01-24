from flask import abort
from flask_login import current_user
from .models import Car

def can_access_car(car: Car) -> bool:
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, "is_admin", False):
        return True
    return current_user in (car.owners or [])

def require_car_access(car: Car):
    if not can_access_car(car):
        abort(403)
