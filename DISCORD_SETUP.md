# Konfiguracja sterowania botem przez Discorda

Repozytorium zawiera obsługę komend, Worker Cloudflare i workflow rejestrujący komendy. Połączenie zacznie działać dopiero po utworzeniu aplikacji Discord, wdrożeniu Workera i dodaniu sekretów do GitHuba. Alerty z OLX nadal przychodzą osobno przez webhook DISCORD_WEBHOOK_URL.

## 1. Utwórz aplikację Discord

1. W Discord Developer Portal utwórz aplikację dla tego projektu.
2. W General Information skopiuj Application ID i Public Key.
3. W zakładce Bot utwórz bota i skopiuj jego token. Traktuj token jak hasło; nie wklejaj go do repozytorium ani czatu.
4. W ustawieniach zaawansowanych Discorda włącz Developer Mode. Skopiuj ID swojego użytkownika i ID serwera, na którym będą działać komendy.
5. Dodaj aplikację do serwera z zakresem applications.commands. Bot nie potrzebuje uprawnień Administratora.

## 2. Wdróż endpoint komend

1. W Cloudflare utwórz Worker o nazwie np. iphone-sniper-discord-control oraz namespace Workers KV.
2. W ustawieniach Workera dodaj KV binding o nazwie SETTINGS, wskazujący na utworzony namespace.
3. Wgraj zawartość pliku discord-control.mjs jako kod Workera.
4. Dodaj sekrety Workera:
   - DISCORD_PUBLIC_KEY — Public Key aplikacji Discord,
   - OWNER_ID — Twoje numeryczne ID użytkownika,
   - SETTINGS_KEY — nowy, losowy sekret. Użyj go również później jako sekretu GitHub.
5. Zapisz i wdroż Workera. Skopiuj adres https://…workers.dev.
6. W Discord Developer Portal w polu Interactions Endpoint URL wpisz adres Workera zakończony /interactions. Zapisz zmianę; Discord sprawdzi podpisane żądanie testowe.

## 3. Dodaj sekrety i zarejestruj komendy

W GitHub otwórz Settings → Secrets and variables → Actions i upewnij się, że jest sekret:

- DISCORD_BOT_TOKEN — token bota z Developer Portal.

Rejestrację komend można wykonać przez Actions → Konfiguracja komend Discord → Run workflow. Workflow sprawdzi token, pobierze ID aplikacji i zarejestruje sześć komend globalnych. Operacja zastępuje listę komend globalnych tej aplikacji; użyj dedykowanej aplikacji projektu. W logu kroku pojawi się też OWNER_ID potrzebny w ustawieniach Workera.

Do monitora dodaj osobne sekrety:

- SETTINGS_URL — adres Workera zakończony /settings,
- SETTINGS_KEY — ten sam sekret, który ustawiono w Workerze.

Ostatnia zarejestrowana próba komend zakończyła się sukcesem 15 listopada 2026. Jeśli komendy są już widoczne na serwerze, nie uruchamiaj rejestracji ponownie.

Komendy z domyślnymi uprawnieniami 0 mogą wymagać w ustawieniach serwera jawnego dopuszczenia Twojego użytkownika: Integracje → aplikacja → uprawnienia komend. Endpoint i tak odrzuca każdą interakcję, jeśli ID użytkownika nie zgadza się z OWNER_ID.

## 4. Test i obsługa

Po rejestracji sprawdź na serwerze:

- /ustawienia — pokazuje bieżące filtry,
- /modele lista:11 13 15,
- /lokalizacja miasto:Bielsko-Biała promien:30,
- /cena minimum:200 maksimum:1500,
- /pauza i /start — zatrzymują lub wznawiają alerty.

Po zmianie lokalizacji lub modeli pierwszy przebieg zapisuje aktualne wyniki jako punkt odniesienia bez alertowania o starych ofertach. Zmiany w KV mogą być widoczne z opóźnieniem do około minuty; kolejne skanowanie następuje zgodnie z harmonogramem, który może być opóźniony przez GitHub.

Osobno skonfiguruj webhook alertów OLX: dodaj DISCORD_WEBHOOK_URL jako sekret repozytorium GitHub Actions. W Actions → iPhone Sniper OLX → Run workflow zaznacz test_discord, aby wysłać pojedynczy test bez pobierania ofert.

Komendy sterują filtrami, ale nie poprawiają dostępności RSS. Wcześniejszy przebieg GitHub Actions zapisał HTTP 403 z OLX; źródło ofert i dostarczenie testowego alertu muszą zostać potwierdzone osobno. Bot nie obchodzi blokad OLX.
