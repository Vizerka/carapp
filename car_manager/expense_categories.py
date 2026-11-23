EXPENSE_CATEGORIES = {
    "insurance": "Ubezpieczenie",
    "inspection": "Przegląd",
    "parts": "Części",
    "tires": "Opony i koła",
    "tax": "Podatki i opłaty",
    "parking": "Parking",
    "tolls": "Drogi i autostrady",
    "car_wash": "Mycie i pielęgnacja",
    "accessories": "Akcesoria",
    "other": "Inne",
}


def expense_category_label(category: str) -> str:
    return EXPENSE_CATEGORIES.get(category, category)
