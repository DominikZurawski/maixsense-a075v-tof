# Logi telemetryczne

Plik `logs/a075v_*.jsonl` ma jedną linię JSON dla każdej odebranej klatki. Można go wczytać do Pythona, `jq` albo programu do analizy danych.

## Pola wspólne

- `received_at_utc` — czas odebrania klatki przez laptop, w UTC.
- `frame_id` — kolejny numer klatki nadany przez kamerę.
- `camera_timestamp_ms` — czas kamery w milisekundach.
- `fps_rolling` — szacowana częstotliwość klatek po stronie laptopa.
- `packet_bytes` — liczba bajtów w pakiecie HTTP.
- `stream_config` — aktywne ustawienia: tryb 8/16-bitowy, RGB, Status i ekspozycja.

## Kanały `depth`, `ir`, `status`

Każdy z tych kanałów zawiera:

- `shape` — rozdzielczość, zazwyczaj `[240, 320]`.
- `dtype` — typ liczby: `uint8` albo `uint16`.
- `minimum`, `maximum` — najmniejsza i największa wartość w macierzy.
- `nonzero_pixels` — liczba pikseli innych niż zero.
- `nonzero_median` — mediana wartości innych niż zero.

To są liczby kontrolne. Przykład: nagły spadek `nonzero_pixels` oznacza, że kamera nie uzyskuje danych dla części sceny; stałe `maximum` może oznaczać nasycenie zakresu. W 16-bitowym Depth wartość surowa / 4 jest odległością w mm. W 8-bitowym Depth liczby służą tylko do szybkiego podglądu.

## Kanał `rgb`

`rgb` jest `null`, jeśli RGB wyłączono. W przeciwnym razie zawiera `shape` (zwykle `[480, 640, 3]`) i `dtype` obrazu po dekodowaniu JPEG.

## Dane pełne

Log zawiera opis, a nie wszystkie piksele. Pełne dane znajdują się w plikach `.raw` i `.npy` zapisywanych przez `s` oraz w katalogu wskazanym przez `--record-raw-dir`.
