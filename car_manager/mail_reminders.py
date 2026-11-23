"""Scheduled email reminders; deliberately independent of web requests."""
import fcntl
import json
import os
import smtplib
import ssl
from collections import defaultdict
from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask import current_app
from flask.cli import with_appcontext

from .models import Car


def stage(days):
    if days < 0:
        return "overdue"
    return next((limit for limit in (0, 1, 7, 30) if days <= limit), None)


def addresses(value):
    result = tuple(dict.fromkeys(Address(addr_spec=x.strip()).addr_spec
                                 for x in value.split(",") if x.strip()))
    if not result:
        raise ValueError("Missing recipients")
    return result


def reminders(cars, today, default, overrides):
    batches = defaultdict(dict)
    for car in cars:
        for kind, label, record in (
            ("oc", "OC", car.last_insurance),
            ("inspection", "Przegląd", car.last_inspection),
        ):
            if not record or not record.valid_to:
                continue
            due = record.valid_to
            days = (due - today).days
            milestone = stage(days)
            if milestone is None:
                continue
            status = "po terminie" if days < 0 else ("dziś" if days == 0 else f"za {days} dni")
            key = f"{car.id}:{kind}:{record.id}:{due}:{milestone}"
            line = f"{car.make} {car.model} ({car.reg_number or 'ID ' + str(car.id)}): {label} – {due:%d.%m.%Y} ({status})"
            for recipient in overrides.get(str(car.id), default):
                batches[recipient][key] = line
    return batches


def deliver(recipient, lines):
    username = os.environ["CARAPP_SMTP_USER"]
    password = os.environ["CARAPP_SMTP_PASSWORD"]
    sender = Address(addr_spec=os.environ.get("CARAPP_SMTP_FROM", username))
    message = EmailMessage()
    message["From"] = str(sender)
    message["To"] = recipient
    message["Subject"] = "Car Manager: terminy OC i przeglądów"
    message.set_content("Przypomnienia:\n\n" + "\n".join(lines) + "\n")
    host = os.environ.get("CARAPP_SMTP_HOST", "mail.vizera.dev")
    port = int(os.environ.get("CARAPP_SMTP_PORT", "587"))
    context = ssl.create_default_context()
    if port == 465:
        connection = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
    else:
        connection = smtplib.SMTP(host, port, timeout=20)
    with connection as smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(username, password)
        smtp.send_message(message)


def save_state(path, state):
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(state, stream)
    temp.replace(path)


@click.command("send-reminders")
@click.option("--dry-run", is_flag=True, help="Pokaż przypomnienia bez SMTP i zapisu stanu.")
@with_appcontext
def send_reminders(dry_run):
    try:
        default = addresses(os.environ.get("CARAPP_MAIL_TO", "vizerka@proton.me"))
        raw = json.loads(os.environ.get("CARAPP_MAIL_TO_BY_CAR", "{}"))
        overrides = {key: addresses(value) for key, value in raw.items()}
    except (ValueError, AttributeError, TypeError):
        raise click.ClickException("Niepoprawna konfiguracja odbiorców.") from None
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    batches = reminders(Car.query.order_by(Car.id).all(), today, default, overrides)
    if dry_run:
        for recipient, entries in batches.items():
            for line in entries.values():
                click.echo(f"{recipient}: {line}")
        if not batches:
            click.echo("Brak przypomnień.")
        return

    if not all(os.environ.get(key) for key in ("CARAPP_SMTP_USER", "CARAPP_SMTP_PASSWORD")):
        raise click.ClickException("Ustaw CARAPP_SMTP_USER i CARAPP_SMTP_PASSWORD.")
    path = Path(os.environ.get(
        "CARAPP_MAIL_STATE", str(Path(current_app.config["CARAPP_DATA_DIR"]) / ".mail-reminders.json")
    ))
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        # Zachowaj tylko bieżące przypomnienia już wysłane.
        state = {to: sorted(set(state.get(to, [])) & entries.keys()) for to, entries in batches.items()}
        failed = False
        for recipient, entries in batches.items():
            pending = {key: line for key, line in entries.items() if key not in state[recipient]}
            if not pending:
                continue
            try:
                deliver(recipient, list(pending.values()))
            except (OSError, smtplib.SMTPException, ValueError) as exc:
                click.echo(f"Wysyłka nieudana ({type(exc).__name__}).", err=True)
                failed = True
                continue
            state[recipient].extend(pending)
            save_state(path, state)
            click.echo(f"Wysłano przypomnienia: {len(pending)}.")
        save_state(path, state)
        if failed:
            raise click.ClickException("Nie wszystkie przypomnienia zostały wysłane.")
