# Sterowanie na Discordzie

Status: kod przygotowany i przetestowany lokalnie. Komendy nie są jeszcze zarejestrowane ani wdrożone. Webhook alertów pozostaje bez zmian. Komendy nie zmieniają opóźnień GitHub Actions ani świeżości RSS.

## Komendy

- `/ustawienia`: podgląd modeli, miasta, promienia, cen i stanu.
- `/modele lista:11 13 15`: wybór modeli 11–15.
- `/lokalizacja miasto:Bielsko-Biała promien:30`: nazwa miasta zgodna z OLX. Nietypowe lub niejednoznaczne nazwy wymagają sprawdzenia adresu wyników OLX.
- `/cena minimum:200 maksimum:1500`: filtry cenowe OLX. Pominięcie maksimum usuwa limit górny.
- `/pauza`, `/start`: zatrzymanie i wznowienie alertów od kolejnego przebiegu.

Pierwsze skanowanie po zmianie wyszukiwania zapamiętuje istniejące wyniki bez alertów. Zapis KV może propagować się około minuty. Równoczesne komendy zmieniające ustawienia nie są obsługiwane transakcyjnie; wysyłaj je pojedynczo i sprawdzaj `/ustawienia`.

## Uruchomienie

Potrzebna jest aplikacja w Discord Developer Portal i bezpłatny Cloudflare Worker. Brak płatnych usług w kodzie; należy wybrać Free i pilnować limitów operatora.

1. W Cloudflare utwórz Worker z kodem `discord-control.mjs`. Dodaj namespace Workers KV jako binding `SETTINGS`.
2. Ustaw sekrety Worker: `DISCORD_PUBLIC_KEY` (publiczny klucz aplikacji Discord), `OWNER_ID` (Twoje ID użytkownika Discord), `SETTINGS_KEY` (losowy silny sekret wspólny dla monitora i endpointu).
3. W Discord Developer Portal wpisz Interactions Endpoint URL: adres Workera z końcówką `/interactions`. Discord sprawdzi podpisany PING. Kod odrzuca niepodpisane i zmodyfikowane żądania.
4. Zarejestruj komendy skryptem `discord-register.mjs` z ustawionymi zmiennymi `DISCORD_APP_ID`, `DISCORD_GUILD_ID`, `DISCORD_BOT_TOKEN`. Wymaga Node.js 22 lub nowszego. Tokenu nie zapisuj w repozytorium. Skrypt zastępuje listę komend tej aplikacji na wskazanym serwerze, dlatego użyj aplikacji przeznaczonej dla tego projektu.
5. Dodaj aplikację na swój serwer z zakresem `applications.commands`. Nie potrzebuje uprawnienia Administrator. Domyślnie komendy widzą administratorzy; dla właściciela bez tej roli przyznaj dostęp tylko do tych komend w integracjach Discorda. Endpoint zawsze niezależnie sprawdza `OWNER_ID`.
6. W GitHub Secrets dodaj `SETTINGS_URL` (adres Workera z `/settings`) i `SETTINGS_KEY`. Przekaż te dwie zmienne w kroku skanowania workflow. Bez SETTINGS_URL monitor korzysta z dotychczasowego config.json; z podanym URL przy błędzie zdalnych ustawień przerywa przebieg, aby /pauza nie została zignorowana.

Sprawdź `/ustawienia`, następnie `/pauza`, uruchom monitor i potwierdź log „Monitoring wstrzymany”. Potem wykonaj `/start` i sprawdź pobranie ofert. Dopiero ten test potwierdza pełne połączenie.

Testy serwera komend: `node --test discord-control.test.mjs`.
