## Stan wdrożenia i test Discorda

Ostatni potwierdzony przebieg z GitHub Actions zwrócił HTTP 403 dla wszystkich trzech wyszukiwań. Te poprawki nie usuwają odmowy dostępu OLX. Nie uznawaj projektu za uruchomiony, dopóki odczyt ofert i dostarczenie powiadomienia nie zostaną potwierdzone na GitHubie.

W Actions wybierz `iPhone Sniper OLX` → `Run workflow` i zaznacz `test_discord`, aby wysłać pojedynczą wiadomość testową bez pobierania ofert. Webhook pozostaje w sekrecie `DISCORD_WEBHOOK_URL`. Test działa niezależnie od blokady OLX i nie zmienia historii ofert.

Poprawiona wersja zapamiętuje pierwsze poprawne skanowanie osobno dla każdego wyszukiwania, zachowuje kolejność historii, ponawia nieudane alerty i oznacza częściowe błędy jako nieudany przebieg. Stan poprawnie obsłużonych ofert zapisuje się także po częściowym błędzie.

# iPhone Sniper — alerty o nowych iPhone'ach z OLX

Bot sprawdza zapisane wyszukiwania OLX i wysyła nowe pasujące ogłoszenia na Discorda, Telegram albo oba kanały. Zapamiętuje ID ofert, żeby nie wysyłać tych samych ogłoszeń przy każdym sprawdzeniu.

## Co jest ustawione

- iPhone 11, 12 i 13, również warianty Pro / Pro Max / mini, jeśli OLX zwróci je w wynikach.
- iPhone 14 i nowsze nie są uwzględniane.
- Odrzucane są typowe ogłoszenia z akcesoriami, np. etui, szkła, kable i ładowarki.
- Nie ma sztywnego limitu ceny ani lokalizacji. Możesz dodać je w filtrach OLX i wkleić własny adres wyszukiwania do `config.json`.
- Pierwsze uruchomienie zapisuje aktualnie widoczne ogłoszenia bez wysyłania ich jako nowych. Powiadomienia ruszają dla kolejnych publikacji.

## Najprostsze uruchomienie w chmurze: GitHub Actions

1. Utwórz repozytorium na GitHubie. Najtańszy wariant to repozytorium publiczne: standardowe uruchomienia Actions są wtedy bezpłatne. Kod i plik z ID ogłoszeń będą publiczne, ale tokeny dodane jako GitHub Secrets nie są publikowane. Nie wpisuj sekretów do `config.json` ani kodu.

   Prywatne repozytorium też zadziała, ale przy sprawdzaniu co 5 minut każde uruchomienie jest rozliczane co najmniej za pełną minutę. Na GitHub Free może to przekroczyć miesięczny limit bezpłatnego użycia. Sprawdź aktualne limity na swoim koncie.
2. Rozpakuj ZIP i wgraj do repozytorium całą zawartość folderu `iphone_sniper_bot` (razem z folderem `.github`).
3. Na Discordzie otwórz ustawienia swojego serwera → Integracje → Webhooki → Nowy webhook. Wybierz kanał na alerty i skopiuj adres webhooka.
4. W repozytorium GitHub przejdź do Settings → Secrets and variables → Actions → New repository secret. Dodaj sekret o nazwie `DISCORD_WEBHOOK_URL` i wklej do niego skopiowany adres. Nie wpisuj go do plików i nikomu go nie wysyłaj.
5. Otwórz zakładkę Actions i włącz workflow, jeśli GitHub o to poprosi. Możesz uruchomić go ręcznie przez `iPhone Sniper OLX` → Run workflow.
6. Pierwszy przebieg zapisze obecne oferty. Kolejne przebiegi będą wysyłać tylko nowe, pasujące ogłoszenia.

Workflow jest ustawiony na sprawdzanie co 5 minut. GitHub może czasami opóźnić zaplanowane uruchomienie. Przy prywatnym repozytorium sprawdź limit minut GitHub Actions na swoim koncie.

### Opcjonalnie: Telegram zamiast Discorda albo równolegle

1. W Telegramie otwórz `@BotFather`, wyślij `/newbot` i utwórz własnego bota.
2. Skopiuj token i dodaj w GitHub Secrets jako `TELEGRAM_BOT_TOKEN`.
3. Otwórz rozmowę ze swoim botem i naciśnij Start.
4. Odczytaj swój identyfikator czatu z `https://api.telegram.org/bot<TWOJ_TOKEN>/getUpdates` po wysłaniu botowi wiadomości. Wstaw wartość `message.chat.id` jako sekret `TELEGRAM_CHAT_ID`.
5. Nie udostępniaj tokenu. Każdy, kto go zna, może sterować Twoim botem.

Możesz skonfigurować oba kanały. Wtedy każde ogłoszenie przyjdzie na Discord i Telegram.

## Zmiana modeli, cen i lokalizacji

Edytuj `config.json`. Najlepiej ustaw filtry na OLX w przeglądarce (np. zakres ceny, miasto, promień), wybierz sortowanie od najnowszych i skopiuj cały adres strony z wynikami do odpowiedniego pola `url`.

Możesz dodać dowolną liczbę obiektów do `searches`. Przykładowo osobne wyszukiwania dla iPhone 13 Pro i iPhone 13 Pro Max pozwolą ustawić różne limity cenowe.

`include_title_regex` określa dozwolone modele. `exclude_title_words` zawiera słowa, które odrzucają ogłoszenia. Nie dodawaj tam słów typu „uszkodzony”, jeśli chcesz też łapać telefony do naprawy.

## Uruchomienie lokalne do testu

Wymagany Python 3.10 lub nowszy.

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

Bot automatycznie wczytuje zmienne z pliku `.env`. W GitHub Actions sekrety są przekazywane automatycznie.

## Tryb ciągły na własnym serwerze / VPS

Ustaw zmienne środowiskowe `DISCORD_WEBHOOK_URL` lub `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID`, a następnie uruchom:

```bash
python bot.py --loop
```

Domyślnie sprawdza OLX co 90 sekund. Możesz zmienić `poll_interval_seconds` w `config.json` (minimum w kodzie to 60 sekund). Katalog `data/` musi być trwały, bo zawiera pamięć wysłanych ofert.

## Ważne ograniczenia

- To monitor publicznych stron wyników OLX, a nie oficjalna integracja OLX. Oficjalne API OLX opisuje integracje do zarządzania / publikowania własnych ogłoszeń, nie publiczne wyszukiwanie całego rynku.
- OLX może zmieniać układ strony, ograniczać częstotliwość zapytań albo zwrócić błąd 403/429. Bot nie obchodzi zabezpieczeń; zapisuje błąd i próbuje przy następnym przebiegu.
- Nie gwarantuje alertu w sekundę po publikacji. Przy GitHub Actions typowy interwał to 5 minut plus ewentualne opóźnienie harmonogramu.
- Bot tylko wysyła linki. Nie loguje się na OLX, nie pisze do sprzedawców i niczego nie kupuje.
