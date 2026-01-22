from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash

from .extensions import db
from .models import Car, InsurancePolicy
from .helpers import parse_date
from .validators import validate_insurance_interval


def init_routes(app):
    # -------------------
    # INSURANCE (OC)
    # -------------------

    @app.post("/cars/<int:car_id>/insurance/new")
    def insurance_new(car_id):
        car = Car.query.get_or_404(car_id)
        valid_from = parse_date(request.form.get("valid_from"))
        valid_to = parse_date(request.form.get("valid_to"))

        ok, msg = validate_insurance_interval(car.id, valid_from, valid_to, None)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("car_detail", car_id=car.id))

        policy = InsurancePolicy(
            car_id=car.id,
            valid_from=valid_from,
            valid_to=valid_to,
            insurer=(request.form.get("insurer") or "").strip() or None,
            policy_no=(request.form.get("policy_no") or "").strip() or None,
        )
        db.session.add(policy)
        db.session.commit()

        flash("Dodano polisę OC ✅", "success")
        return redirect(url_for("car_detail", car_id=car.id))

    @app.route("/insurance/<int:policy_id>/edit", methods=["GET", "POST"])
    def insurance_edit(policy_id):
        policy = InsurancePolicy.query.get_or_404(policy_id)
        car = policy.car

        if request.method == "POST":
            valid_from = parse_date(request.form.get("valid_from"))
            valid_to = parse_date(request.form.get("valid_to"))

            ok, msg = validate_insurance_interval(car.id, valid_from, valid_to, policy.id)
            if not ok:
                flash(msg, "danger")
                return redirect(url_for("insurance_edit", policy_id=policy.id))

            policy.valid_from = valid_from
            policy.valid_to = valid_to
            policy.insurer = (request.form.get("insurer") or "").strip() or None
            policy.policy_no = (request.form.get("policy_no") or "").strip() or None

            db.session.commit()
            flash("Zaktualizowano polisę OC ✅", "success")
            return redirect(url_for("car_detail", car_id=car.id))

        return render_template("insurance_form.html", car=car, policy=policy)

    @app.post("/insurance/<int:policy_id>/delete")
    def insurance_delete(policy_id):
        policy = InsurancePolicy.query.get_or_404(policy_id)
        car_id = policy.car_id
        db.session.delete(policy)
        db.session.commit()
        flash("Usunięto polisę OC 🗑️", "success")
        return redirect(url_for("car_detail", car_id=car_id))
