from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from flask import render_template, request, redirect, url_for, flash, send_file

from .extensions import db
from .models import (
    Car, OdometerEntry, InsurancePolicy, TechInspection,
    ServiceEntry, FuelEntry, ServiceInterval, Document
)
from .helpers import (
    _model_to_dict, _dict_to_model_kwargs,
    ensure_car_upload_dir, _safe_unique_filename
)


def init_routes(app):
    @app.get("/backup")
    def backup_page():
        return render_template("backup.html")

    @app.get("/backup/export.zip")
    def backup_export_zip():
        """
        Eksportuje ZIP: backup.json (dane) + uploads/<car_id>/... (pliki dokumentów).
        """
        payload = {
            "meta": {
                "app": "car_manager",
                "exported_at": datetime.utcnow().isoformat(),
                "version": "1.0.0",
            },
            "cars": [_model_to_dict(c) for c in Car.query.order_by(Car.id.asc()).all()],
            "odometer_entries": [_model_to_dict(x) for x in OdometerEntry.query.order_by(OdometerEntry.id.asc()).all()],
            "insurance_policies": [_model_to_dict(x) for x in InsurancePolicy.query.order_by(InsurancePolicy.id.asc()).all()],
            "tech_inspections": [_model_to_dict(x) for x in TechInspection.query.order_by(TechInspection.id.asc()).all()],
            "service_entries": [_model_to_dict(x) for x in ServiceEntry.query.order_by(ServiceEntry.id.asc()).all()],
            "fuel_entries": [_model_to_dict(x) for x in FuelEntry.query.order_by(FuelEntry.id.asc()).all()],
            "service_intervals": [_model_to_dict(x) for x in ServiceInterval.query.order_by(ServiceInterval.id.asc()).all()],
            "documents": [_model_to_dict(x) for x in Document.query.order_by(Document.id.asc()).all()],
        }

        json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        mem = io.BytesIO()
        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("backup.json", json_bytes)

            root = app.config.get("UPLOAD_FOLDER")
            if root and os.path.isdir(root):
                for dirpath, _, filenames in os.walk(root):
                    for fn in filenames:
                        abs_path = os.path.join(dirpath, fn)
                        rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
                        z.write(abs_path, arcname=f"uploads/{rel_path}")

        mem.seek(0)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return send_file(
            mem,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"car_manager_backup_{stamp}.zip",
        )

    @app.post("/backup/import")
    def backup_import():
        """
        Import ZIP z backup.json + uploads/.
        Tryb: MERGE (dokleja), ale z DEDUPLIKACJĄ:
        - Auta: dopasowanie po VIN, a jak brak to po reg_number.
        - Wpisy: dodawane tylko jeśli identyczny wpis nie istnieje (po kluczach).
        - Dokumenty: kopiowane do uploads/<new_car_id>/, stored_name dostaje suffix jak koliduje.
          Deduplikacja dokumentów: po (car_id, original_name, category, uploaded_at).
        """
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Nie wybrano pliku ZIP.", "danger")
            return redirect(url_for("backup_page"))

        if not file.filename.lower().endswith(".zip"):
            flash("To nie wygląda na ZIP.", "danger")
            return redirect(url_for("backup_page"))

        # ----------------------------
        # Helpery NORMALIZACJI + dedupe
        # ----------------------------
        def _to_dec(v) -> Decimal | None:
            if v is None:
                return None
            if isinstance(v, Decimal):
                return v
            try:
                return Decimal(str(v).replace(",", "."))
            except (InvalidOperation, ValueError):
                return None

        def _q(v, quantum: str) -> str | None:
            d = _to_dec(v)
            if d is None:
                return None
            return str(d.quantize(Decimal(quantum)))

        def _k(x):
            if isinstance(x, (date, datetime)):
                return x.isoformat()
            return x

        def build_existing_keys(model_cls, key_func):
            keys = set()
            for obj in model_cls.query.all():
                keys.add(key_func(obj))
            return keys

        # ---------
        # KEY FUNCS (OBIEKT -> tuple)
        # ---------
        def key_odometer(o: OdometerEntry):
            return (_k(o.car_id), _k(o.date), _k(o.km))

        def key_insurance(p: InsurancePolicy):
            return (_k(p.car_id), _k(p.valid_from), _k(p.valid_to), (p.insurer or "").strip(), (p.policy_no or "").strip())

        def key_inspection(i: TechInspection):
            return (_k(i.car_id), _k(i.date), _k(i.valid_to), (i.result or "").strip(), (i.station or "").strip())

        def key_service(s: ServiceEntry):
            return (
                _k(s.car_id),
                _k(s.date),
                _k(s.km),
                (s.title or "").strip(),
                _q(s.cost, "0.01"),
                (s.vendor or "").strip(),
            )

        def key_fuel(f: FuelEntry):
            return (
                _k(f.car_id),
                _k(f.date),
                _k(f.km),
                _q(f.liters, "0.001"),
                _q(f.total_cost, "0.01"),
                bool(f.full_tank),
            )

        def key_interval(iv: ServiceInterval):
            return (_k(iv.car_id), (iv.name or "").strip())

        # ---------
        # KEY FUNCS (KWARGS -> tuple)
        # ---------
        def key_odometer_kwargs(w):
            return (_k(w.get("car_id")), _k(w.get("date")), _k(w.get("km")))

        def key_insurance_kwargs(w):
            return (
                _k(w.get("car_id")),
                _k(w.get("valid_from")),
                _k(w.get("valid_to")),
                ((w.get("insurer") or "")).strip(),
                ((w.get("policy_no") or "")).strip(),
            )

        def key_inspection_kwargs(w):
            return (
                _k(w.get("car_id")),
                _k(w.get("date")),
                _k(w.get("valid_to")),
                ((w.get("result") or "")).strip(),
                ((w.get("station") or "")).strip(),
            )

        def key_service_kwargs(w):
            return (
                _k(w.get("car_id")),
                _k(w.get("date")),
                _k(w.get("km")),
                ((w.get("title") or "")).strip(),
                _q(w.get("cost"), "0.01"),
                ((w.get("vendor") or "")).strip(),
            )

        def key_fuel_kwargs(w):
            return (
                _k(w.get("car_id")),
                _k(w.get("date")),
                _k(w.get("km")),
                _q(w.get("liters"), "0.001"),
                _q(w.get("total_cost"), "0.01"),
                bool(w.get("full_tank")),
            )

        def key_interval_kwargs(w):
            return (_k(w.get("car_id")), ((w.get("name") or "")).strip())

        # ----------------------------
        # Import
        # ----------------------------
        try:
            zdata = io.BytesIO(file.read())
            with zipfile.ZipFile(zdata, "r") as z:
                if "backup.json" not in z.namelist():
                    flash("W ZIP nie ma backup.json.", "danger")
                    return redirect(url_for("backup_page"))

                raw = z.read("backup.json").decode("utf-8")
                payload = json.loads(raw)

                # --- mapowanie stary car_id -> nowy car_id
                car_id_map: dict[int, int] = {}

                # index istniejących aut po VIN/reg
                existing_by_vin = {}
                existing_by_reg = {}
                for c in Car.query.all():
                    if c.vin:
                        existing_by_vin[str(c.vin).upper()] = c
                    if c.reg_number:
                        existing_by_reg[str(c.reg_number).upper()] = c

                # 1) auta
                imported_cars = payload.get("cars", [])
                for cdata in imported_cars:
                    old_id = cdata.get("id")
                    vin = (cdata.get("vin") or "").strip().upper() or None
                    reg = (cdata.get("reg_number") or "").strip().upper() or None

                    target = None
                    if vin and vin in existing_by_vin:
                        target = existing_by_vin[vin]
                    elif reg and reg in existing_by_reg:
                        target = existing_by_reg[reg]

                    if target is None:
                        kwargs = _dict_to_model_kwargs(Car, cdata)
                        if kwargs.get("vin"):
                            kwargs["vin"] = str(kwargs["vin"]).upper()
                        if kwargs.get("reg_number"):
                            kwargs["reg_number"] = str(kwargs["reg_number"]).upper()

                        target = Car(**kwargs)
                        db.session.add(target)
                        db.session.flush()

                        if target.vin:
                            existing_by_vin[str(target.vin).upper()] = target
                        if target.reg_number:
                            existing_by_reg[str(target.reg_number).upper()] = target

                    if isinstance(old_id, int):
                        car_id_map[old_id] = target.id

                # 2) wpisy powiązane (dedupe)
                def import_rows(model_cls, rows_key: str, key_func_obj, key_func_kwargs, car_id_field: str = "car_id"):
                    rows = payload.get(rows_key, [])
                    count = 0

                    existing = build_existing_keys(model_cls, key_func_obj)

                    for r in rows:
                        old_car_id = r.get(car_id_field)
                        if not isinstance(old_car_id, int) or old_car_id not in car_id_map:
                            continue

                        kwargs = _dict_to_model_kwargs(model_cls, r)
                        kwargs[car_id_field] = car_id_map[old_car_id]

                        k = key_func_kwargs(kwargs)
                        if k in existing:
                            continue

                        obj = model_cls(**kwargs)
                        db.session.add(obj)
                        existing.add(k)
                        count += 1

                    return count

                odo_n = import_rows(OdometerEntry, "odometer_entries", key_odometer, key_odometer_kwargs)
                oc_n  = import_rows(InsurancePolicy, "insurance_policies", key_insurance, key_insurance_kwargs)
                ti_n  = import_rows(TechInspection, "tech_inspections", key_inspection, key_inspection_kwargs)
                svc_n = import_rows(ServiceEntry, "service_entries", key_service, key_service_kwargs)
                fuel_n = import_rows(FuelEntry, "fuel_entries", key_fuel, key_fuel_kwargs)
                iv_n   = import_rows(ServiceInterval, "service_intervals", key_interval, key_interval_kwargs)

                # 3) dokumenty + pliki (dedupe)
                docs = payload.get("documents", [])
                doc_n = 0

                existing_stored: dict[int, set[str]] = {}

                existing_doc_keys = set(
                    (_k(d.car_id), _k(d.original_name), _k(d.category), _k(d.uploaded_at))
                    for d in Document.query.all()
                )

                for d in docs:
                    old_car_id = d.get("car_id")
                    if not isinstance(old_car_id, int) or old_car_id not in car_id_map:
                        continue

                    new_car_id = car_id_map[old_car_id]
                    upload_dir = ensure_car_upload_dir(new_car_id)

                    if new_car_id not in existing_stored:
                        names = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()
                        for dd in Document.query.filter_by(car_id=new_car_id).all():
                            if dd.stored_name:
                                names.add(dd.stored_name)
                        existing_stored[new_car_id] = names

                    kwargs = _dict_to_model_kwargs(Document, d)
                    kwargs["car_id"] = new_car_id

                    stored = d.get("stored_name")
                    original = d.get("original_name") or stored
                    if not stored:
                        continue

                    dk = (_k(new_car_id), _k(original), _k(kwargs.get("category")), _k(kwargs.get("uploaded_at")))
                    if dk in existing_doc_keys:
                        continue

                    zip_path = f"uploads/{old_car_id}/{stored}"
                    new_stored = _safe_unique_filename(existing_stored[new_car_id], stored)

                    if zip_path not in z.namelist():
                        continue

                    data = z.read(zip_path)
                    with open(os.path.join(upload_dir, new_stored), "wb") as f:
                        f.write(data)

                    kwargs["stored_name"] = new_stored
                    kwargs["original_name"] = original

                    doc = Document(**kwargs)
                    db.session.add(doc)

                    existing_doc_keys.add(dk)
                    doc_n += 1

                db.session.commit()

                flash("Import zakończony ✅", "success")
                flash(
                    f"Auta: {len(car_id_map)} | Odo: {odo_n} | OC: {oc_n} | Przeglądy: {ti_n} | "
                    f"Serwis: {svc_n} | Tankowania: {fuel_n} | Interwały: {iv_n} | Dokumenty: {doc_n}",
                    "info",
                )
                return redirect(url_for("list_cars"))

        except zipfile.BadZipFile:
            flash("ZIP jest uszkodzony albo nieprawidłowy.", "danger")
            return redirect(url_for("backup_page"))
        except Exception as e:
            db.session.rollback()
            flash(f"Import wywalił się: {e}", "danger")
            return redirect(url_for("backup_page"))
