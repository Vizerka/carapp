# Ciągłość tankowań

Podczas dodawania lub edycji **pełnego** tankowania można zaznaczyć
„Od poprzedniego pełnego tankowania były niezapisane tankowania”.
Spalanie od poprzedniego pełnego baku do tego wpisu nie będzie liczone;
na wykresie pojawi się przerwa. Zaznaczony wpis staje się punktem
startowym dla kolejnego pomiaru. Tankowania częściowe nadal są sumowane
w odcinkach o kompletnej historii.

Pole `unrecorded_refuels_since_last_full` jest częścią schematu zarządzanego
przez migracje. Zaznacz przerwę ręcznie przy tankowaniu kończącym okres
z brakującymi wpisami.

# Wdrożenie migracji

Od tej wersji aplikacja używa Flask-Migrate/Alembic i nie modyfikuje bazy
samodzielnie podczas startu. Przed aktualizacją wykonaj kopię `cars.db`, a po
zainstalowaniu zależności uruchom migracje **przed restartem usługi**:

```bash
cp cars.db "cars.db.backup-$(date +%Y%m%d-%H%M%S)"
source .venv/bin/activate
pip install -r requirements.txt
flask --app app db upgrade
sudo systemctl restart carapp.service
```

Kontrola poprawności:

```bash
flask --app app db current
sudo systemctl status carapp.service --no-pager
```

Oczekiwana rewizja bazy: `c41f64a0d7c2`.
