# Kanał Status — MaixSense-A075V

## Najkrótsze wyjaśnienie

**Status RAW nie jest obrazem odległości ani gotową informacją „dobry/zły piksel”.** Jest to pomocnicza mapa danych używana przez algorytm kalibracji producenta. Oryginalny program przekazuje ją razem z głębią do kalibratora `TOF_cali`; dopiero po tym kroku powstają zrozumiałe klasy jakości punktu.

Nasz Python zapisuje i pokazuje wejście do tego kroku kalibracji. Jest to użyteczne do badań, ale bez uruchomienia `TOF_cali` nie można uczciwie odczytać znaczenia pojedynczej liczby.

## Co odbiera program

Każda klatka A075V zawiera mapę Status o rozdzielczości 320×240. W domyślnej
konfiguracji `status_mode=2` jest to jeden bajt na piksel. Pythonowy program
zapisuje jej niezmienione wartości do `*_status.npy` i do pola `status` w
telemetrii JSONL.

Widok `STATUS RAW` pokazuje te bajty kolorem fałszywym Viridis: liczba `0`
jest jednym końcem palety, `255` drugim, a wartości pośrednie dostają kolory
pośrednie. Kolor służy wyłącznie do łatwego zauważenia obszarów o podobnych
kodach — **nie oznacza odległości i nie jest jeszcze klasyfikacją jakości**.

## Co robi oryginalny program (kalibracja)

Producent nie opublikował w dokumentacji kompletnej tabeli znaczeń każdego
surowego kodu Status. Dlatego program nie opisuje obecnie np. „kod 17” jako
konkretnej usterki pomiaru. To byłoby zgadywanie.

Oryginalny `viewdeep.html` wywołuje funkcję `TOF_cali` z pliku
`calibration.wasm`. Dopiero wynik tej funkcji traktuje jako klasy stanu:
`0` normal, `1` UE, `2` OE, `3` bad i `5` invalid. UE/OE są nazwami użytymi
przez Sipeed; kod źródłowy nie rozwija ich pełnych nazw. Te klasy nie mogą być
bezpiecznie przypisane bezpośrednio do surowych bajtów odbieranych przez nasz
program.

## Jak używać w badaniach

1. Zapisz jednocześnie RAW, Depth, IR i Status (`s` lub `--record-raw-dir`).
2. Porównuj powtarzalne obszary i zmiany kodów Status z błędami/nagłymi
   zmianami głębi oraz IR.
3. Traktuj kanał jako materiał diagnostyczny do własnej walidacji, dopóki nie
   zintegrujemy lub nie odtworzymy kalibratora `TOF_cali`.

Następnym poprawnym etapem jest niezależna implementacja tej części kalibracji
albo udokumentowane wywołanie jej z WASM; dopiero wtedy widok może uczciwie
pokazywać dyskretne klasy jakości.
