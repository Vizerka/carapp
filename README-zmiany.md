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

# Dane aplikacji poza repozytorium

Baza SQLite i dokumenty nie są już wersjonowane przez Git. Produkcyjnie ustaw:

```ini
[Service]
Environment=CARAPP_DATA_DIR=/var/lib/carapp
```

Wtedy aplikacja korzysta z:

```text
/var/lib/carapp/cars.db
/var/lib/carapp/uploads/
```

Bez `CARAPP_DATA_DIR` zachowany jest zgodny wstecznie katalog projektu. Można też
osobno ustawić `DATABASE_URL` i `UPLOAD_FOLDER`.

Przed pierwszym pobraniem wersji usuwającej pliki runtime z repo zatrzymaj usługę,
skopiuj dane do `/var/lib/carapp`, porównaj kopię i dopiero potem oczyść katalog
roboczy Gita. Szczegółową kolejność należy wykonać z instrukcji wdrożeniowej dla
tej wersji — nie uruchamiaj aplikacji na pustej bazie.

# Pełny koszt posiadania

Zakładka **Wydatki** przechowuje koszty inne niż paliwo i serwis, m.in. OC,
przeglądy, części, opony, podatki, parking i opłaty drogowe. Dashboard sumuje
wszystkie trzy źródła i pokazuje rozbicie dla bieżącego roku, ostatnich 12
miesięcy albo całej historii. Wydatków paliwowych i serwisowych nie wpisuj drugi
raz w tej zakładce, bo są liczone bezpośrednio z tankowań i serwisu.

Eksport oraz import backupu ZIP obejmują również wydatki.

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

Oczekiwana rewizja bazy: `7d3e9a1b2c4f`.
