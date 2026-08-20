# MaixSense-A075V — stanowisko badawcze RGB-D

Narzędzie diagnostyczne i przechwytujące dla sieciowej kamery ToF/RGB Sipeed
MaixSense-A075V. Odbiera ramki przez USB RNDIS, wyświetla kanały głębi, IR,
RGB i Status RAW, zapisuje dane pomiarowe oraz tworzy chmurę punktów 3D.
Projekt służy do badań i dokumentowania zachowania kamery — nie jest
oficjalnym oprogramowaniem Sipeed.

## Wymagania i instalacja

- Linux z Pythonem 3.10 lub nowszym oraz środowiskiem graficznym dla OpenCV;
- kamera podłączona przez USB (interfejs RNDIS);
- zależności z `requirements.txt`.

Zalecana instalacja w wirtualnym środowisku:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Szybka kontrola instalacji bez podłączonej kamery:

```bash
python3 maixsense_probe.py --help
```

## Podłączenie kamery

Kamera jest urządzeniem sieciowym USB RNDIS o adresie `192.168.233.1`. Po podłączeniu poczekaj 10–15 sekund, potem sprawdź połączenie:

```bash
ip -brief address
ping -c 3 192.168.233.1
```

Zwykle NetworkManager sam ustawi adres `192.168.233.*` na interfejsie USB. Nazwa interfejsu może zmieniać się po odłączeniu kamery. Tylko gdy nie ma takiego adresu, ustaw go na **aktualnie widocznym** interfejsie:

```bash
sudo ip address add 192.168.233.2/24 dev AKTUALNY_INTERFEJS
sudo ip route replace 192.168.233.0/24 dev AKTUALNY_INTERFEJS
```

## Uruchomienie

```bash
python3 maixsense_probe.py
```

Program automatycznie wybiera adres RNDIS. Domyślnie odbiera 16-bitową głębię, potrzebną do pomiarów i 3D. Szybki 8-bitowy podgląd włączysz przez `--depth-bits 8`.

## Widoki i sterowanie

Główne okno zawiera pięć miniatur:

- **Depth** — głębia. W 16-bitowym strumieniu wartość surowa / 4 oznacza odległość w mm.
- **IR** — intensywność światła podczerwonego odbieranego przez sensor.
- **RGB** — obraz kamery kolorowej.
- **Status RAW** — surowy kanał diagnostyczny; opis w [dokumentacji Status](docs/status-channel.md).
- **Point Cloud** — miniatura chmury punktów 3D.

Kliknięcie miniatury ją powiększa; kolejne kliknięcie wraca do pięciu widoków. Klawisze `1`–`5` wybierają Depth, IR, RGB, Status i chmurę punktów; `0` wraca do wszystkich miniatur.

W chmurze punktów: lewy przycisk obraca, prawy przesuwa, kółko przybliża, `r` resetuje, `s` zapisuje chmurę PLY do `pointclouds/`. `c` przełącza **skalibrowane RGB Map**: każdy punkt ToF jest przeliczany do kamery RGB i dostaje jej kolor. Małe trzy okręgi w prawym górnym rogu to **Arcball** — kontrolka orientacji wzorowana na oryginalnym programie Sipeed.

`g` włącza/wyłącza lokalny filtr Gaussa głębi. Filtr wygładza szum wyłącznie w aktualnym widoku 2D i chmurze punktów; surowe dane, telemetria i pliki zapisywane przez `s` pozostają niezmienione. Jest to nasza implementacja wygładzania, a nie identyczne wywołanie algorytmu WebAssembly producenta. `a` włącza automatyczny zakres kolorów głębi, `q`/`Esc` kończy program.

Klawisz `p` uruchamia test płaskiej powierzchni: wylicza `Z`, odległość po promieniu `R`, kąt płaszczyzny i błąd RMS. Wzory oraz instrukcja testu są w [dokumentacji geometrii ToF](docs/geometria-tof.md).

## Zapisy i logi

Każde uruchomienie tworzy `logs/a075v_*.jsonl`: jedna linia JSON opisuje jedną klatkę. Dokładny opis każdego pola jest w [dokumentacji logów](docs/logs.md).

Klawisz `s` w widokach 2D zapisuje do `captures/` pakiet `.raw`, macierze `.npy`, obrazy i plik `*_metadata.json`. Aby zapisywać każdy odebrany pakiet RAW:

```bash
python3 maixsense_probe.py --record-raw-dir recordings/seria_01
```

## Kompletny zestaw do testu ściany

Do przekazania wyników testu uruchom pojedyncze przechwycenie w nowym katalogu:

```bash
python3 maixsense_probe.py --once --rgb-format yuv --rgb-resolution 800 --test-bundle-dir test_data/sciana_01
```

Polecenie prosi kamerę o 16-bitową mapę ToF, 8-bitowy IR oraz RGB `800×600`,
a następnie zapisuje w `test_data/sciana_01/`:

- pełny pakiet `.raw`, mapy `depth.npy`, `ir.npy`, `status.npy`, PNG RGB i
  metadane ramki;
- pobrane z kamery `CameraParms.json`, `getinfo.bin` i `get_lut.bin`;
- `plane_test.json` z `Zc`, `R`, `tilt`, RMS i porównaniem brzegu z centrum;
- `camera_resources_manifest.json` z rozmiarami i sumami SHA-256 oraz `README.md`.

Po przechwyceniu komunikat programu podaje rzeczywiście odebrany rozmiar RGB.
Na sprawdzonej kamerze tryb JPEG zwracał tylko 640×480, nawet po żądaniu
800×600 i 1600×1200. Tryb `--rgb-format yuv --rgb-resolution 800` zwrócił
natomiast pełne 800×600; program dekoduje go jako planar YUV420 i zachowuje
też niezmieniony bufor `*_rgb.yuv`. Nie zmieniaj ręcznie zawartości katalogu
przed spakowaniem:

W tym trybie program automatycznie dobiera zakres kolorów wyłącznie dla
`*_depth_preview.png` i zapisuje go w metadanych. Nie zmienia to macierzy
`*_depth.npy`. W terminalu drukowany jest także pełny wynik `Plane test`
(`Zc`, `R`, `edge-centre`, `tilt`, `RMS`), a liczby trafiają do
`plane_test.json`.

```bash
zip -r sciana_01.zip test_data/sciana_01
```

## Struktura projektu

- `maixsense_probe.py` — punkt wejścia programu.
- `a075v/protocol.py` — konfiguracja kamery i dekoder pakietu binarnego.
- `a075v/transport.py` — połączenie HTTP przez USB RNDIS.
- `a075v/analysis.py` — analiza i widoki 2D.
- `a075v/pointcloud.py` — geometria 3D i eksport PLY.
- `a075v/persistence.py` — przechwycenia i logi.
- `a075v/cli.py` — argumenty oraz obsługa okna.
- `docs/` — polska dokumentacja użytkowa i techniczna.
- `camera_original/` — niezmieniany backup całego programu z kamery.
- `vendor/sipeed_a075v/` — kopie plików producenta użytych przez program.
