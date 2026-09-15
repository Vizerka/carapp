"""Obliczenia spalania dla kolejnych tankowań do pełna."""

from decimal import Decimal


def consumption_series(fills):
    """Zwraca daty i wyniki; None oznacza brak wiarygodnego odcinka."""
    labels = []
    values = []
    previous_full = None
    liters_since_full = Decimal("0")

    for fill in fills:
        if previous_full is None:
            if fill.full_tank:
                previous_full = fill
            continue

        liters_since_full += Decimal(fill.liters or 0)
        if not fill.full_tank:
            continue

        distance = int(fill.km) - int(previous_full.km)
        labels.append(fill.date.isoformat())
        if fill.unrecorded_refuels_since_last_full or distance <= 0:
            values.append(None)
        else:
            values.append(float(liters_since_full * Decimal("100") / Decimal(distance)))

        # Obecny pełny bak jest punktem bazowym dla następnego odcinka.
        previous_full = fill
        liters_since_full = Decimal("0")

    return labels, values
