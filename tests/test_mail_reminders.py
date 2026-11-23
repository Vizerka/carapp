from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from car_manager import mail_reminders
from car_manager.extensions import db
from car_manager.models import Car, InsurancePolicy


def test_reminders_preview_and_dedup(app, monkeypatch):
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    with app.app_context():
        car = Car.query.filter_by(model="940").one()
        db.session.add(InsurancePolicy(car=car, valid_from=today, valid_to=today + timedelta(days=6)))
        db.session.commit()
    monkeypatch.delenv("CARAPP_MAIL_TO", raising=False)
    monkeypatch.delenv("CARAPP_MAIL_TO_BY_CAR", raising=False)
    monkeypatch.setenv("CARAPP_SMTP_USER", "garage@example.org")
    monkeypatch.setenv("CARAPP_SMTP_PASSWORD", "test")
    sent = []
    monkeypatch.setattr(mail_reminders, "deliver", lambda recipient, lines: sent.append((recipient, lines)))
    runner = app.test_cli_runner()
    preview = runner.invoke(args=["send-reminders", "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert "vizerka@proton.me: Volvo 940" in preview.output
    assert not sent
    for _ in range(2):
        result = runner.invoke(args=["send-reminders"])
        assert result.exit_code == 0, result.exception
    assert len(sent) == 1
    assert sent[0][0] == "vizerka@proton.me"
