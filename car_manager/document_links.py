from __future__ import annotations

from .extensions import db
from .models import (
    DocumentLink, InsurancePolicy, Modification, ServiceEntry, TechInspection
)


TARGET_MODELS = {
    "service": ServiceEntry,
    "insurance": InsurancePolicy,
    "inspection": TechInspection,
    "modification": Modification,
}


def _car_id(target):
    return getattr(target, "car_id", None)


def resolve_target(target_type, target_id):
    model = TARGET_MODELS.get(target_type)
    if model is None:
        return None
    return db.session.get(model, target_id)


def target_label(target_type, target):
    if target_type == "service":
        return f"Serwis {target.date}: {target.title}"
    if target_type == "insurance":
        return f"OC {target.valid_from}–{target.valid_to}"
    if target_type == "inspection":
        return f"Przegląd {target.date}"
    if target_type == "modification":
        return f"Modyfikacja: {target.title}"
    return str(target.id)


def document_target_options(car):
    options = []
    groups = (
        ("service", car.service_entries.order_by(ServiceEntry.date.desc()).all()),
        ("insurance", car.insurance_policies.order_by(InsurancePolicy.valid_from.desc()).all()),
        ("inspection", car.tech_inspections.order_by(TechInspection.date.desc()).all()),
        ("modification", car.modifications.order_by(Modification.id.desc()).all()),
    )
    for target_type, targets in groups:
        for target in targets:
            options.append({
                "value": f"{target_type}:{target.id}",
                "label": target_label(target_type, target),
            })
    return options


def set_document_target(document, raw_value):
    document.links.clear()
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return True
    try:
        target_type, raw_id = raw_value.split(":", 1)
        target_id = int(raw_id)
    except (ValueError, TypeError):
        return False
    target = resolve_target(target_type, target_id)
    if target is None or _car_id(target) != document.car_id:
        return False
    document.links.append(DocumentLink(target_type=target_type, target_id=target_id))
    return True


def document_link_label(link):
    target = resolve_target(link.target_type, link.target_id)
    return target_label(link.target_type, target) if target is not None else "Usunięty wpis"


def delete_links_for_target(target_type, target_id):
    DocumentLink.query.filter_by(target_type=target_type, target_id=target_id).delete(
        synchronize_session=False
    )
