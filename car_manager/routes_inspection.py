from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash

from .extensions import db
from .models import Car, TechInspection
from .helpers import parse_date
from .validators import validate_inspection_dates


def init_routes(app):
    # -------------------
    # TECH INSPECTION
    # -------------------

    @app.post("/cars/<int:car_id>/inspection/new")
    def inspection_new(car_id):
        car = Car.query.get_or_404(car_id)
        date_do = parse_date(request.form.get("date"))
        valid_to = parse_date(request.form.get("valid_to"))

        ok, msg = validate_inspection_dates(date_do, valid_to)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        ins = TechInspection(
            car_id=car.id,
            date=date_do,
            valid_to=valid_to,
            result=(request.form.get("result") or "").strip() or None,
            station=(request.form.get("station") or "").strip() or None,
            note=(request.form.get("note") or "").strip() or None,
        )
        db.session.add(ins)
        db.session.commit()
        flash("Dodano przegląd ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.route("/inspection/<int:ins_id>/edit", methods=["GET", "POST"])
    def inspection_edit(ins_id):
        ins = TechInspection.query.get_or_404(ins_id)
        car = ins.car

        if request.method == "POST":
            date_do = parse_date(request.form.get("date"))
            valid_to = parse_date(request.form.get("valid_to"))

            ok, msg = validate_inspection_dates(date_do, valid_to)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("inspection_edit", ins_id=ins.id))

            ins.date = date_do
            ins.valid_to = valid_to
            ins.result = (request.form.get("result") or "").strip() or None
            ins.station = (request.form.get("station") or "").strip() or None
            ins.note = (request.form.get("note") or "").strip() or None

            db.session.commit()
            flash("Zaktualizowano przegląd ✅", "success")
            return redirect(url_for("car_detail", car_id=car.id))

        return render_template("inspection_form.html", car=car, ins=ins)

    @app.post("/inspection/<int:ins_id>/delete")
    def inspection_delete(ins_id):
        ins = TechInspection.query.get_or_404(ins_id)
        car_id = ins.car_id
        db.session.delete(ins)
        db.session.commit()
        flash("Usunięto przegląd 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))
