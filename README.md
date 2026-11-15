## Źródło ofert: publiczny kanał RSS

Monitor korzysta z publicznego generatora OLX RSS pod adresem https://tedeelock.com/ zamiast bezpośrednio pobierać strony OLX z GitHub Actions. Generator otrzymuje wyłącznie publiczny link wyszukiwania. Webhook Discorda pozostaje w GitHub Secrets i nie jest przekazywany generatorowi.

To niezależny, zewnętrzny serwis. Nie ma potwierdzonej gwarancji dostępności, kompletności ani świeżości danych. Sprawdzanie co 5 minut nie gwarantuje, że samo źródło odświeża dane w tym rytmie. Pierwszy przebieg ustala historię bez alertów; późniejsze wysyłają nowo wykryte ID. Wyniki mogą obejmować promowane oferty. Dane są ograniczone do ofert udostępnionych przez kanał.

## Szybkość i ograniczenia źródła

GitHub Actions uruchamia monitoring co 5 minut — to najkrótszy obsługiwany interwał harmonogramu, a start może się opóźnić. W trybie ciągłym na stale działającym komputerze/VPS bot sprawdza co 90 sekund (`python bot.py --loop`). Oba tryby korzystają z publicznego kanału RSS, więc jego opóźnienie może być większe niż interwał sprawdzania. Sprawdzenia wyszukiwań odbywają się równolegle, aby skrócić pojedynczy przebieg.

Nieaktywne oferty spoza publicznych wyników nie są dostępne w tym RSS. MoneyAlert opisuje, że korzysta z danych spoza wyników wyszukiwania, ale nie publikuje sposobu ich pozyskiwania; nie da się tego odtworzyć z publicznego kanału. Bot nie próbuje odczytywać niepublicznych danych ani omijać zabezpieczeń OLX.

## Stan wdrożenia

W historii jest wcześniejszy przebieg z HTTP 403, ale nowszy skan 15 listopada o 06:35 UTC zakończył się poprawnie; lokalny odczyt publicznego RSS również zwrócił HTTP 200. Kod nie obchodzi odmowy dostępu OLX. Osobny test webhooka Discorda nadal trzeba uruchomić ręcznie, żeby potwierdzić dostarczenie wiadomości.

W Actions wybierz `iPhone Sniper OLX` → `Run workflow` i zaznacz `test_discord`, aby wysłać pojedynczą wiadomość testową bez pobierania ofert. Webhook pozostaje w sekrecie `DISCORD_WEBHOOK_URL`. Test działa niezależnie od blokady OLX i nie zmienia historii ofert. Test jest ręczny, żeby zwykłe zmiany kodu nie wysyłały wiadomości na serwer.

Sterowanie filtrami komendami Discorda opisuje [DISCORD_SETUP.md](DISCORD_SETUP.md). Historia GitHub Actions potwierdza także udaną rejestrację komend 15 listopada o 07:10 UTC.

Poprawiona wersja zapamiętuje pierwsze poprawne skanowanie osobno dla każdego wyszukiwania, zachowuje kolejność historii, ponawia nieudane alerty i oznacza częściowe błędy jako nieudany przebieg. Stan poprawnie obsłużonych ofert zapisuje się także po częściowym błędzie.

# iPhone Sniper — alerty o nowych iPhone'ach z OLX

Bot sprawdza zapisane wyszukiwania OLX i wysyła nowe pasujące ogłoszenia na Discorda, Telegram albo oba kanały. Zapamiętuje ID ofert, żeby nie wysyłać tych samych ogłoszeń przy każdym sprawdzeniu.

## Co jest ustawione

- iPhone 11–15, również warianty Pro / Pro Max / mini, jeśli źródło zwróci je w wynikach.
- iPhone 16 i nowsze nie są uwzględniane.
- Alert pokazuje rozpoznany model, cenę, miejscowość oraz przybliżoną odległość w linii prostej od Wilkowic. Odległość wykorzystuje współrzędne GeoNames; część miejscowości może nie mieć dopasowania.
- Domyślne wyszukiwania obejmują okolice Bielska-Białej w promieniu 30 km, bez limitu ceny. Możesz zmienić miasto, promień i ceny w komendach Discord albo w `config.json`.
- Odrzucane są typowe ogłoszenia z akcesoriami, np. etui, szkła, kable i ładowarki.
- Pierwsze uruchomienie zapisuje aktualnie widoczne ogłoszenia bez wysyłania ich jako nowych. Powiadomienia ruszają dla kolejnych publikacji.

## Najprostsze uruchomienie w chmurze: GitHub Actions

1. W Discordzie otwórz ustawienia serwera → Integracje → Webhooki → Nowy webhook. Wybierz kanał alertów i skopiuj adres.
2. W repozytorium przejdź do Settings → Secrets and variables → Actions → New repository secret. Dodaj `DISCORD_WEBHOOK_URL` i wklej adres webhooka. Nie dodawaj go do plików ani wiadomości.
3. Otwórz zakładkę Actions i włącz workflow, jeśli GitHub o to poprosi. Uruchom `iPhone Sniper OLX` ręcznie, by sprawdzić konfigurację.
4. Pierwszy poprawny przebieg zapisze obecne oferty bez alertów; następne powinny wysyłać nowe pasujące ogłoszenia.

GitHub Actions uruchamia skan co 5 minut, z przesunięciem na 2., 7., 12. minutę itd., żeby unikać szczytu obciążenia na początku każdej godziny. GitHub może opóźnić uruchomienie, więc nie da się zagwarantować sztywnego limitu 5 minut. Przy prywatnym repozytorium sprawdź limit minut GitHub Actions na swoim koncie. Szczegóły opisuje [dokumentacja harmonogramów GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule).

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

Wymagany Python 3.10 lub nowszy. Po skopiowaniu `.env.example` do `.env` wpisz potrzebne ustawienia lokalne. Nie commituj pliku `.env`.

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

To alternatywa dla bieżącego trybu GitHub Actions. Domyślnie tryb ciągły sprawdza RSS co 60 sekund; tę wartość ustawia `poll_interval_seconds`. Dockerfile uruchamia ten tryb automatycznie. `docker-compose.yml` zachowuje pamięć ogłoszeń i uruchamia bota ponownie po restarcie maszyny. Skopiuj `.env.example` do `.env`, wpisz webhook Discorda w `DISCORD_WEBHOOK_URL`, a opcjonalnie ustaw `SETTINGS_URL` i `SETTINGS_KEY`. Uruchom `docker compose up -d --build`; logi podejrzysz przez `docker compose logs -f`. Nie wysyłaj ani nie commituj pliku `.env`. Po uruchomieniu i potwierdzeniu alertu wyłącz harmonogram GitHub Actions, aby nie działały dwa niezależne skanery i nie wysyłały duplikatów. Baza miejscowości pochodzi z [GeoNames](https://www.geonames.org/) i jest udostępniana na licencji CC BY 4.0.

W bieżącym trybie GitHub Actions odstęp wynosi 5 minut; w trybie ciągłym około 0–60 sekund plus pobranie danych i wysłanie alertu. Żaden z nich nie przyspieszy publikacji po stronie OLX ani odświeżenia zewnętrznego RSS. Monitor nie widzi ofert, których publiczne wyniki i RSS jeszcze nie udostępniają.

## Ważne ograniczenia

- To monitor publicznych stron wyników OLX, a nie oficjalna integracja OLX. Oficjalne API OLX opisuje integracje do zarządzania / publikowania własnych ogłoszeń, nie publiczne wyszukiwanie całego rynku.
- OLX może zmieniać układ strony, ograniczać częstotliwość zapytań albo zwrócić błąd 403/429. Bot nie obchodzi zabezpieczeń; zapisuje błąd i próbuje przy następnym przebiegu.
- Nie gwarantuje alertu w sekundę po publikacji. Przy GitHub Actions typowy interwał to 5 minut plus ewentualne opóźnienie harmonogramu.
- Bot tylko wysyła linki. Nie loguje się na OLX, nie pisze do sprzedawców i niczego nie kupuje.
