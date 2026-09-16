from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, timedelta
from decimal import Decimal

from .fuel_consumption import consumption_series
from .helpers import compute_interval_status
from .models import TireEvent


def _average(values):
    values = [Decimal(str(value)) for value in values if value is not None]
    if not values:
        return None
    return float(sum(values, Decimal("0")) / len(values))


def fuel_statistics(fills, today: date | None = None):
    today = today or date.today()
    fills = list(fills)
    labels, values = consumption_series(fills)
    valid_values = [value for value in values if value is not None]

    cutoff_12m = today - timedelta(days=365)
    values_12m = [
        value
        for label, value in zip(labels, values)
        if value is not None and date.fromisoformat(label) >= cutoff_12m
    ]

    rolling = []
    window = deque(maxlen=5)
    for value in values:
        if value is None:
            window.clear()
            rolling.append(None)
            continue
        window.append(value)
        rolling.append(_average(window))

    price_labels = []
    price_values = []
    station_totals = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    priced_liters = Decimal("0")
    priced_cost = Decimal("0")
    highest_fill = None

    year_liters = Decimal("0")
    year_cost = Decimal("0")
    for fill in fills:
        liters = Decimal(fill.liters or 0)
        total_cost = Decimal(fill.total_cost) if fill.total_cost is not None else None
        price = Decimal(fill.price_per_l) if fill.price_per_l is not None else None
        if price is None and total_cost is not None and liters > 0:
            price = total_cost / liters

        if price is not None:
            price_labels.append(fill.date.isoformat())
            price_values.append(float(price))
        if total_cost is not None and liters > 0:
            priced_liters += liters
            priced_cost += total_cost
            if fill.station:
                station_totals[fill.station][0] += liters
                station_totals[fill.station][1] += total_cost
            if highest_fill is None or total_cost > Decimal(highest_fill.total_cost or 0):
                highest_fill = fill
        if fill.date.year == today.year:
            year_liters += liters
            if total_cost is not None:
                year_cost += total_cost

    station_averages = [
        (station, cost / liters)
        for station, (liters, cost) in station_totals.items()
        if liters > 0
    ]
    cheapest_station = min(station_averages, key=lambda item: item[1]) if station_averages else None

    return {
        "labels": labels,
        "values": values,
        "rolling_5": rolling,
        "last": valid_values[-1] if valid_values else None,
        "average_5": _average(valid_values[-5:]),
        "average_10": _average(valid_values[-10:]),
        "average_12m": _average(values_12m),
        "average_all": _average(valid_values),
        "minimum": min(valid_values) if valid_values else None,
        "maximum": max(valid_values) if valid_values else None,
        "average_price": float(priced_cost / priced_liters) if priced_liters > 0 else None,
        "cheapest_station": cheapest_station,
        "highest_fill": highest_fill,
        "year_liters": float(year_liters),
        "year_cost": float(year_cost),
        "price_labels": price_labels,
        "price_values": price_values,
    }


def monthly_total_cost(car, today: date | None = None):
    today = today or date.today()
    start = date(today.year, today.month, 1)
    fuel = sum(
        (Decimal(entry.total_cost) for entry in car.fuel_entries.all()
         if entry.total_cost is not None and entry.date >= start),
        Decimal("0"),
    )
    service = sum(
        (Decimal(entry.cost) for entry in car.service_entries.all()
         if entry.cost is not None and entry.date >= start),
        Decimal("0"),
    )
    expenses = sum(
        (Decimal(entry.amount) for entry in car.expenses.all()
         if entry.date >= start),
        Decimal("0"),
    )
    modifications = sum(
        (Decimal(entry.actual_cost) for entry in car.modifications.all()
         if entry.actual_cost is not None
         and (entry.completed_date or entry.started_date)
         and (entry.completed_date or entry.started_date) >= start),
        Decimal("0"),
    )
    return fuel + service + expenses + modifications


def next_service_summary(car, today: date | None = None):
    today = today or date.today()
    current_km = car.last_odometer.km if car.last_odometer else None
    candidates = []
    for interval in car.service_intervals.filter_by(active=True).all():
        state = compute_interval_status(interval, current_km, today)
        candidates.append((interval, state))
    if not candidates:
        return None, None

    def rank(item):
        _, state = item
        values = []
        if state["km_left"] is not None:
            values.append(state["km_left"] / 500)
        if state["days_left"] is not None:
            values.append(state["days_left"] / 14)
        return min(values) if values else float("inf")

    return min(candidates, key=rank)


def tire_set_mileage(tire_set, current_km: int | None = None):
    total = 0
    installed_at = None
    for event in tire_set.events.order_by(TireEvent.date, TireEvent.id).all():
        if event.action == "installed" and event.km is not None:
            installed_at = event.km
        elif event.action == "removed" and event.km is not None and installed_at is not None:
            if event.km >= installed_at:
                total += event.km - installed_at
            installed_at = None
    if installed_at is not None and current_km is not None and current_km >= installed_at:
        total += current_km - installed_at
    return total
