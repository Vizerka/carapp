# car_manager/cli.py
from __future__ import annotations

import click
from flask import Flask

from .extensions import db
from .models import User


def register_cli(app: Flask) -> None:

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt="Email (opcjonalnie)", default="", show_default=False)
    @click.password_option("--password", confirmation_prompt=True)
    def create_admin(username: str, email: str, password: str):
        username = username.strip()
        email = (email.strip() or None)

        if User.query.filter_by(username=username).first():
            raise click.ClickException("Taki user już istnieje.")

        if email and User.query.filter_by(email=email).first():
            raise click.ClickException("Taki email już istnieje.")

        u = User(username=username, email=email, is_admin=True, is_active=True, password_hash="x")
        u.set_password(password)

        db.session.add(u)
        db.session.commit()
        click.echo(f"✅ Utworzono admina: {username}")

    @app.cli.command("promote-admin")
    @click.option("--username", prompt=True)
    def promote_admin(username: str):
        u = User.query.filter_by(username=username.strip()).first()
        if not u:
            raise click.ClickException("Nie ma takiego użytkownika.")
        u.is_admin = True
        db.session.commit()
        click.echo(f"OK ✅ {username} jest adminem.")
