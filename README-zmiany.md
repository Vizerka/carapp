# Ciągłość tankowań

Podczas dodawania lub edycji **pełnego** tankowania można zaznaczyć
„Od poprzedniego pełnego tankowania były niezapisane tankowania”.
Spalanie od poprzedniego pełnego baku do tego wpisu nie będzie liczone;
na wykresie pojawi się przerwa. Zaznaczony wpis staje się punktem
startowym dla kolejnego pomiaru. Tankowania częściowe nadal są sumowane
w odcinkach o kompletnej historii.

Przy pierwszym uruchomieniu aplikacja dodaje do istniejącej tabeli
`fuel_entry` pole `unrecorded_refuels_since_last_full` z wartością
`0` dla wcześniejszych wpisów. Wykonaj kopię swojej bazy `cars.db`
przed pierwszym uruchomieniem nowej wersji. Zaznacz przerwę ręcznie
przy tankowaniu kończącym okres z brakującymi wpisami.
