from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass
class TimelinePage:
    items: list
    total: int
    page: int
    per_page: int

    @property
    def pages(self):
        return ceil(self.total / self.per_page) if self.total else 0

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def prev_num(self):
        return self.page - 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def next_num(self):
        return self.page + 1


def _event(kind, when, title, details=None, km=None, cost=None, url=None):
    return {
        "kind": kind,
        "date": when,
        "title": title,
        "details": details,
        "km": km,
        "cost": cost,
        "url": url,
    }


def build_timeline(car, page=1, per_page=30, kind=None):
    events = []
    for entry in car.odometer_entries.filter_by(source_type=None).all():
        events.append(_event("odometer", entry.date, "Pomiar przebiegu", entry.note, entry.km))
    for entry in car.fuel_entries.all():
        events.append(_event(
            "fuel", entry.date, "Tankowanie",
            f"{entry.liters} L" + (f" · {entry.station}" if entry.station else ""),
            entry.km, entry.total_cost,
        ))
    for entry in car.service_entries.all():
        events.append(_event("service", entry.date, entry.title, entry.description or entry.note, entry.km, entry.cost))
    for entry in car.insurance_policies.all():
        events.append(_event(
            "insurance", entry.valid_from, "Polisa OC",
            f"ważna do {entry.valid_to}" + (f" · {entry.insurer}" if entry.insurer else ""),
        ))
    for entry in car.tech_inspections.all():
        events.append(_event(
            "inspection", entry.date, "Przegląd techniczny",
            f"ważny do {entry.valid_to}" + (f" · {entry.result}" if entry.result else ""),
        ))
    for entry in car.expenses.all():
        events.append(_event("expense", entry.date, entry.title, entry.note, entry.km, entry.amount))
    for tire_set in car.tire_sets.all():
        for entry in tire_set.events.all():
            labels = {"installed": "Założono", "removed": "Zdjęto", "inspection": "Pomiar"}
            events.append(_event(
                "tires", entry.date,
                f"{labels.get(entry.action, entry.action)}: {tire_set.name}",
                entry.note, entry.km,
            ))
    for entry in car.modifications.all():
        when = entry.completed_date or entry.started_date
        if when:
            events.append(_event(
                "modification", when, entry.title,
                entry.description or entry.note, cost=entry.actual_cost,
            ))

    if kind:
        events = [event for event in events if event["kind"] == kind]
    events.sort(key=lambda event: event["date"], reverse=True)
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    return TimelinePage(events[start:start + per_page], len(events), page, per_page)
