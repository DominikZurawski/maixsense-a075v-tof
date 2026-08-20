# Kanał Status — MaixSense-A075V

## Najważniejsze

Widok **Status RAW** nie pokazuje odległości ani prostego komunikatu, czy
pomiar danego piksela jest dobry lub błędny. Jest to dodatkowa mapa liczb
przekazywana przez kamerę. Producent wykorzystuje ją we własnym etapie
przetwarzania, ale nie opisał publicznie znaczenia każdej liczby.

Dlatego ten program zapisuje i wyświetla wartości Status bez ich
interpretowania. Nie należy na przykład zakładać, że wartość `17` oznacza
konkretny rodzaj błędu.

## Co odbiera i zapisuje program

Każda klatka A075V zawiera mapę Status o rozdzielczości 320×240 — po jednej
liczbie dla każdego piksela obrazu głębi. W zwykłym trybie jest to liczba od
0 do 255. Program zapisuje ją bez zmian w pliku `*_status.npy` oraz dodaje
jej podsumowanie do pola `status` w pliku z logiem.

Widok `STATUS RAW` zamienia liczby na umowne kolory, aby łatwiej zauważyć
obszary o podobnych wartościach. Kolory nie oznaczają odległości ani jakości
pomiaru: są tylko sposobem wyświetlania liczb.

## Dlaczego program nie pokazuje „dobrych” i „złych” pikseli

Oryginalny program producenta przekazuje Status razem z mapą głębi do funkcji
`TOF_cali` z pliku `calibration.wasm`. Jej wynik dzieli piksele na kilka
kategorii, między innymi `normal`, `bad` i `invalid`.

Nie znamy jednak publicznej tabeli, która mówiłaby, jak pojedyncza surowa
wartość Status ma się do tych kategorii. Nazwy `UE` i `OE`, widoczne w
oryginalnym programie, także nie są rozwinięte w dokumentacji Sipeed.
Przypisanie kategorii na podstawie samej liczby byłoby więc zgadywaniem.

## Jak z niego korzystać

1. Zapisz jednocześnie dane Status, głębi, IR i pełny pakiet z kamery
   (klawisz `s` albo opcja `--record-raw-dir`).
2. Obserwuj, czy zmiana wartości Status występuje w tych samych miejscach co
   brak głębi, skoki odległości lub słaby obraz IR.
3. Traktuj ją jako wskazówkę pomocniczą, a nie ocenę poprawności pomiaru.

Aby wiarygodnie pokazać kategorie jakości, trzeba byłoby odtworzyć działanie
funkcji producenta albo skorzystać z jej opisanej wersji. Dopiero wtedy można
by przypisać pikselom znaczenie takie jak „prawidłowy” lub „nieważny”.
