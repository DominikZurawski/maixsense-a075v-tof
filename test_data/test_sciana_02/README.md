# Zestaw testowy MaixSense-A075V

Ten katalog zawiera jedną ramkę pomiarową oraz wszystkie dodatkowe zasoby udostępnione przez HTTP kamery w chwili przechwycenia.

- `*_depth.npy` — 16-bitowa mapa głębi ToF, `uint16`, 320×240; `Z_mm = raw / 4` (w pełnym pakiecie danych).
- `*_ir.npy` — kanał IR; `*_rgb.png` — odebrany obraz RGB.
- `*_rgb.yuv` — oryginalny bufor RGB, obecny tylko dla trybu YUV i pełnego pakietu.
- `*.raw` — kompletny pakiet protokołu; `*_metadata.json` — konfiguracja ramki.

Repozytorium może zawierać tylko metadane i podglądy PNG; duże pliki pomiarowe
udostępnia się osobno lub przez Git LFS.
- `CameraParms.json` — kalibracja RGB–ToF pobrana z kamery.
- `getinfo.bin`, `get_lut.bin` — binarne zasoby firmware; ich format nie jest opisany tekstowo przez producenta.
- `plane_test.json` — wynik dopasowania płaszczyzny dla tej samej ramki, jeżeli przechwycenie było testem ściany.
- `camera_resources_manifest.json` — rozmiary, sumy SHA-256 i ewentualne błędy pobrania.
