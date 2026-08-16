# TODO

## Admin

- [x] YAML-Schalter `caption_generation_enabled` für Kalender-Einträge ergänzen.
  - Die Einstellung wird direkt im jeweiligen Eintrag vom Typ `calendar` gepflegt.
  - Fehlt die Einstellung, gilt aus Ressourcenschutzgründen `false`.
  - Wenn die Funktion für einen Kalender ausgeschaltet ist, darf für dessen Events keine Caption-Generierung gestartet werden.
  - Die Beispielkonfiguration auf der Admin-Seite zeigt die Einstellung mit einem kurzen erklaerenden Kommentar.
  - So soll der Betrieb auch auf schwächeren Geräten wie einem Raspberry Pi 3 möglich sein.
- [x] Status der Kalender-Aktualisierung auf der Admin-Seite anzeigen.
  - Ein Feld `Letzte Anwendungsmeldungen` auf der Admin-Seite anzeigen. Es enthaelt
    die letzten Logzeilen in zeitlicher Reihenfolge; die neuesten stehen unten.
  - Einen kleinen threadsicheren Logging-Handler mit begrenztem In-Memory-Puffer
    verwenden, zum Beispiel fuer die letzten 100 Meldungen. Keine Datenbank, keine
    zusaetzliche Statusdatei und keine eigene Status-API einfuehren.
  - Beim normalen Laden beziehungsweise manuellen Neuladen von `/admin` die letzten
    Meldungen aus dem Puffer serverseitig rendern. Automatische Aktualisierung kann
    spaeter ergaenzt werden, falls sie im Betrieb wirklich gebraucht wird.
  - Nur Meldungen der zam-tv-Anwendung anzeigen. Logs gelten nur fuer den laufenden
    Prozess und muessen einen Neustart nicht ueberleben.
  - Die Kalender-Logs so ergaenzen beziehungsweise vereinheitlichen, dass sie den
    Ablauf ohne weitere Statuslogik verstaendlich beschreiben:
    - Start der Kalender-Aktualisierung.
    - Erfolgreicher ICS-Abruf mit Kalenderquelle und Anzahl verwendeter Events.
    - Start und Ergebnis der Caption-Generierung mit angefragten,
      wiederverwendeten und fehlgeschlagenen Captions.
    - Erfolgreicher Abschluss mit Event-Anzahl und Dauer.
    - Fehler mit kurzer Ursache; der Hinweis, dass der alte Snapshot weiter benutzt
      wird, soll direkt in der Meldung stehen.
  - Kalenderquellen in der Anzeige ohne URL-Query-Parameter ausgeben und lange oder
    sensible Modell-Ausgaben nicht ungefiltert ins Admin-Log schreiben.
  - Die Log-Ausgabe im Template als reinen Text rendern, damit Log-Inhalte kein HTML
    einschleusen koennen.
  - Tests ergaenzen fuer Begrenzung und Reihenfolge des Puffers, Ausgabe und
    HTML-Escaping auf `/admin` sowie die wichtigsten Erfolgs- und Fehlermeldungen
    von ICS-Abruf und Caption-Generierung.
  - Abnahmekriterium: Nach einem manuellen Neuladen von `/admin` ist aus den letzten
    Meldungen erkennbar, ob der ICS-Abruf erfolgreich war, wie viele Events verwendet
    werden und ob die Caption-Generierung erfolgreich war oder einen Fehler hatte.

## Kalender

- [ ] Wiederkehrende Kalender-Events innerhalb von `days_ahead` nicht als einzelne Slides anzeigen.
  - Noch zu entscheiden: Alle betroffenen Tage gemeinsam in der Datumszeile aufführen.
  - Alternative: Nur den unmittelbar nächsten Termin des Events anzeigen.

## Dauerbetrieb

- [ ] Watchdog für Chromium einrichten.
  - Eine leere oder hängende Anzeige erkennen und Chromium automatisch neu starten.
  - Dadurch soll bei diesem Fehler kein Neustart des gesamten Raspberry Pi mehr nötig sein.
