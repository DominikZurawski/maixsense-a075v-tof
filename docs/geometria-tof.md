# Jak kamera ToF mierzy odległość

## Dwie różne odległości

Fizyczny sensor ToF mierzy opóźnienie odbitego światła podczerwonego dla
każdego piksela. Pierwotny pomiar dotyczy promienia wychodzącego z kamery.
Format udostępniany przez firmware i używany przez program producenta jest
jednak **mapą głębi osiowej `Z`** w układzie kamery. Potwierdzają to zarówno
oryginalny skrypt `calVolumes.py`, jak i test płaskiej ściany opisany niżej.

Wartość surowa 16-bitowego piksela jest tak przeliczana:

```text
Z_mm = raw_depth / 4
X_mm = (u - cx) · Z_mm / fx
Y_mm = (v - cy) · Z_mm / fy
R_mm = √(X_mm² + Y_mm² + Z_mm²)
```

`u`, `v` to współrzędne piksela. Parametry ToF użyte przez program to
`fx=226,5142`, `fy=227,8584`, `cx=163,7246`, `cy=123,3738`; pochodzą z
oryginalnego `calVolumes.py` producenta.

`Z_mm` jest głębią wzdłuż osi optycznej kamery. `R_mm` jest odległością od
środka kamery po promieniu danego piksela. W środku obrazu są niemal równe;
przy brzegach różnica rośnie.

## Jednoznaczna odpowiedź: co jest zapisane w pliku 16-bitowym?

Zapisywana jest macierz `uint16` 320×240. Pojedyncza wartość `raw_depth` nie
jest jeszcze współrzędną 3D i nie zawiera osobno wartości `R`.

- **W pliku:** `raw_depth`; zgodnie z programem producenta `Z_mm = raw_depth / 4`.
  Jest to głębia osiowa **Z**.
- **Nie w pliku:** `X_mm`, `Y_mm` i `R_mm`. Program oblicza je później z
  `Z_mm`, pozycji piksela (`u`, `v`) i parametrów kamery (`fx`, `fy`, `cx`,
  `cy`).
- Nie ma udostępnionego ustawienia przełączającego zapis między wariantem
  „Z” i „R”. Przełącznik 8/16 bitów zmienia rozdzielczość zapisu kanału głębi,
  a nie znaczenie geometryczne odległości.

Słowo „surowa” oznacza tu nieprzefiltrowaną wartość 16-bitową odebraną z
firmware. Nie należy go rozumieć jako „surowy czas lotu po promieniu”; taki
wewnętrzny etap sensora nie jest udostępniony przez publiczny protokół kamery.

## Nachylenie powierzchni

Kamera nie mierzy bezpośrednio kąta, pod jakim znajduje się powierzchnia. Dla
przykładu: ściana ustawiona dokładnie frontem do kamery ma nachylenie 0°,
a obrócona ściana — większe nachylenie. Nachylenie może osłabić odbicie IR i
zwiększyć szum lub liczbę nieważnych pikseli.

Kąt ten program wyznacza dopiero z wielu zmierzonych punktów 3D: dopasowuje
do nich płaszczyznę, a potem porównuje jej ustawienie z kierunkiem, w którym
patrzy kamera. Kamera nie ma osobnego czujnika mierzącego to nachylenie.

## Test płaskiej powierzchni

1. Ustaw jedną płaską ścianę lub płytę przed kamerą, możliwie prostopadle do
   jej osi.
2. Uruchom program w domyślnym trybie 16-bitowym.
3. Wciśnij `p`.
4. Program obliczy płaszczyznę metodą najmniejszych kwadratów i pokaże:
   - `Zc` — głębię osiową środkowego piksela;
   - `R` — odległość środkowego piksela po promieniu;
   - `tilt` — kąt nachylenia dopasowanej płaszczyzny względem kamery;
   - `RMS` — typowy błąd punktów względem płaszczyzny.
   - `edge-centre` — różnicę mediany głębi na bocznych brzegach i w centrum.

Małe `tilt` i `RMS` oznaczają dobrą, prostopadłą i płaską scenę testową.
Duże `RMS` może oznaczać szum, nierówną powierzchnię, wiele obiektów w kadrze
albo problemy z odbiciem IR.

Filtr Gaussa (`g`) pomaga obserwować stabilność widoku, lecz test porównawczy
warto wykonywać zarówno z filtrem wyłączonym, jak i włączonym.

## Co ten test mówi o pytaniu „po promieniu czy po osi?”

Każdy piksel kamery patrzy w trochę innym kierunku. **Odległość po promieniu**
to długość prostej od kamery do punktu, właśnie w kierunku danego piksela.
**Głębia po osi** to natomiast odległość punktu mierzona tylko w kierunku,
w którym patrzy środek kamery — jak odległość ściany od obiektywu po prostej
prostopadłej do jej matrycy.

Fizyka ToF zaczyna od drogi światła po promieniu piksela. Czujnik nie mierzy
jednak osobno nachylenia obiektu i nie poprawia odległości zależnie od tego,
czy ściana jest obrócona. Nachylona powierzchnia może jedynie słabiej odbijać
światło, przez co rośnie szum lub liczba błędnych punktów.

Następnie oprogramowanie kamery może przeliczyć odległość po promieniu na
głębię osiową Z, korzystając z kąta, pod którym dany piksel patrzy względem
środka obrazu. Jest to zwykłe przeliczenie geometrii kamery, niezależne od
nachylenia fotografowanej powierzchni.

Płaska ściana prostopadła do kamery daje prosty eksperyment. Dla mapy po
promieniu wartości na brzegach powinny być wyraźnie większe niż w centrum:
przy ścianie w odległości 1000 mm lewy/prawy brzeg A075V mógłby mieć około
1230 mm. Dla mapy osiowej Z `edge-centre` powinno być bliskie 0%. Małe RMS i
małe `edge-centre`, są mocną praktyczną wskazówką, że
16-bitowa mapa udostępniana przez kamerę jest już mapą osiowej głębi Z.
