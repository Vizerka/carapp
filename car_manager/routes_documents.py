from __future__ import annotations

import os
from datetime import datetime

from flask import request, redirect, url_for, flash, send_from_directory, abort, render_template
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Car, Document
from .helpers import allowed_file, ensure_car_upload_dir


def init_routes(app):
    # -------------------
    # DOCUMENTS
    # -------------------

    @app.post("/cars/<int:car_id>/documents/upload")
    def document_upload(car_id):
        car = Car.query.get_or_404(car_id)
        file = request.files.get("file")

        if not file or file.filename == "":
            flash("Nie wybrano pliku.", "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        if not allowed_file(file.filename):
            flash("Nieobsługiwany typ pliku. Dozwolone: pdf, jpg, jpeg, png, webp.", "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        upload_dir = ensure_car_upload_dir(car.id)
        original = file.filename
        safe = secure_filename(original)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        stored = f"{stamp}_{safe}"

        file.save(os.path.join(upload_dir, stored))

        doc = Document(
            car_id=car.id,
            stored_name=stored,
            original_name=original,
            category=(request.form.get("category") or "").strip() or None,
            note=(request.form.get("note") or "").strip() or None,
        )
        db.session.add(doc)
        db.session.commit()

        flash("Dodano dokument 📎", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.get("/documents/<int:doc_id>/download")
    def document_download(doc_id):
        doc = Document.query.get_or_404(doc_id)
        upload_dir = ensure_car_upload_dir(doc.car_id)
        path = os.path.join(upload_dir, doc.stored_name)
        if not os.path.isfile(path):
            abort(404)
        return send_from_directory(
            upload_dir,
            doc.stored_name,
            as_attachment=True,
            download_name=doc.original_name,
        )

    @app.get("/documents/<int:doc_id>/view")
    def document_view(doc_id):
        doc = Document.query.get_or_404(doc_id)
        upload_dir = ensure_car_upload_dir(doc.car_id)
        path = os.path.join(upload_dir, doc.stored_name)
        if not os.path.isfile(path):
            abort(404)
        return send_from_directory(upload_dir, doc.stored_name, as_attachment=False)

    @app.post("/documents/<int:doc_id>/delete")
    def document_delete(doc_id):
        doc = Document.query.get_or_404(doc_id)
        car_id = doc.car_id
        upload_dir = ensure_car_upload_dir(car_id)
        path = os.path.join(upload_dir, doc.stored_name)

        db.session.delete(doc)
        db.session.commit()

        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

        flash("Usunięto dokument 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))

    @app.route("/documents/<int:doc_id>/edit", methods=["GET", "POST"])
    def document_edit(doc_id):
        doc = Document.query.get_or_404(doc_id)

        if request.method == "POST":
            doc.category = (request.form.get("category") or "").strip() or None
            doc.note = (request.form.get("note") or "").strip() or None

            file = request.files.get("file")
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash("Nieobsługiwany typ pliku. Dozwolone: pdf, jpg, jpeg, png, webp.", "danger")
                    return redirect(url_for("document_edit", doc_id=doc.id))

                upload_dir = ensure_car_upload_dir(doc.car_id)

                old_path = os.path.join(upload_dir, doc.stored_name)

                original = file.filename
                safe = secure_filename(original)
                stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
                stored = f"{stamp}_{safe}"
                new_path = os.path.join(upload_dir, stored)

                try:
                    file.save(new_path)

                    doc.original_name = original
                    doc.stored_name = stored

                    db.session.commit()

                    try:
                        if os.path.isfile(old_path):
                            os.remove(old_path)
                    except OSError:
                        pass

                    flash("Zapisano zmiany dokumentu ✅", "success")
                    flash("Plik został podmieniony 📎", "info")
                    return redirect(url_for("car_detail", car_id=doc.car_id))

                except Exception as e:
                    db.session.rollback()
                    try:
                        if os.path.isfile(new_path):
                            os.remove(new_path)
                    except OSError:
                        pass

                    flash(f"Nie udało się podmienić pliku: {e}", "danger")
                    return redirect(url_for("document_edit", doc_id=doc.id))

            db.session.commit()
            flash("Zapisano zmiany dokumentu ✅", "success")
            return redirect(url_for("car_detail", car_id=doc.car_id))

        return render_template("document_form.html", doc=doc)
