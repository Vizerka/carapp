# car_manager/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()

login_manager = LoginManager()
# endpoint funkcji logowania (nie blueprint!)
login_manager.login_view = "login"
login_manager.login_message = "Zaloguj się, żeby wejść."
login_manager.login_message_category = "warning"
