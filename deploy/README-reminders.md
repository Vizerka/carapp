# Powiadomienia mailowe Car Managera

Jedna wiadomość na odbiorcę zawiera nowe przypomnienia o OC i przeglądach:
do 30 dni, do 7 dni, dzień przed, w dniu terminu oraz raz po terminie.
Jeśli timer wcześniej nie działał, program wysyła tylko bieżący etap.
Domyślny odbiorca wszystkich aut: `vizerka@proton.me`.

Utwórz lub edytuj `sudoedit /opt/carapp/.env` (nie zastępuj wcześniejszych ustawień):

```ini
CARAPP_SMTP_HOST=mail.vizera.dev
CARAPP_SMTP_PORT=587
CARAPP_SMTP_USER=carapp@vizera.dev
CARAPP_SMTP_FROM=carapp@vizera.dev
CARAPP_SMTP_PASSWORD='WPISZ_HASLO_SMTP'
CARAPP_MAIL_TO=vizerka@proton.me
# Opcjonalnie: odbiorcy zastępujący domyślnych dla auta o ID 42
# CARAPP_MAIL_TO_BY_CAR='{"42":"vizerka@proton.me,drugi@example.org"}'
```

Zastąp przykładowy login i adres nadawcy prawdziwą skrzynką. Port 587 wymaga
STARTTLS; dla TLS od razu użyj 465. Hasła nie zapisuj w repozytorium.
Jeśli usługa WWW używa niestandardowego `DATABASE_URL` lub `CARAPP_DATA_DIR`,
upewnij się, że usługa przypomnień dostaje te same wartości. Katalog danych
musi być zapisywalny dla użytkownika `carapp`, żeby zachować historię wysyłek.
Dla nowego pliku używanego wyłącznie przez systemd ustaw `sudo chmod 600 /opt/carapp/.env`.
Jeśli inne procesy czytają istniejący plik bezpośrednio, zachowaj im dostęp.

```bash
sudo install -m 644 /opt/carapp/deploy/carapp-reminders.service /etc/systemd/system/
sudo install -m 644 /opt/carapp/deploy/carapp-reminders.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-run --wait --pipe --collect --property=User=carapp \
  --property=WorkingDirectory=/opt/carapp --property=EnvironmentFile=/opt/carapp/.env \
  /opt/carapp/.venv/bin/python -m flask --app app send-reminders --dry-run
sudo systemctl enable --now carapp-reminders.timer
systemctl list-timers carapp-reminders.timer
```

Ręczne uruchomienie, które może wysłać prawdziwy mail:
`sudo systemctl start carapp-reminders.service`.
Logi: `sudo journalctl -u carapp-reminders.service -n 30 --no-pager`.
Funkcja nie wymaga migracji bazy ani nowych bibliotek Pythona.
