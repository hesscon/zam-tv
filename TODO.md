# TODO

## Admin

- [x] YAML-Schalter `caption_generation_enabled` für Kalender-Einträge ergänzen.
  - Die Einstellung wird direkt im jeweiligen Eintrag vom Typ `calendar` gepflegt.
  - Fehlt die Einstellung, gilt aus Ressourcenschutzgründen `false`.
  - Wenn die Funktion für einen Kalender ausgeschaltet ist, darf für dessen Events keine Caption-Generierung gestartet werden.
  - Die Beispielkonfiguration auf der Admin-Seite zeigt die Einstellung mit einem kurzen erklaerenden Kommentar.
  - So soll der Betrieb auch auf schwächeren Geräten wie einem Raspberry Pi 3 möglich sein.
- [ ] Status der Kalender-Aktualisierung auf der Admin-Seite anzeigen.
  - Zeitpunkt der letzten erfolgreichen Aktualisierung anzeigen.
  - Anzahl der gefundenen Events anzeigen.
  - Die letzte Fehlermeldung anzeigen, falls eine Aktualisierung fehlgeschlagen ist.

## Kalender

- [ ] Wiederkehrende Kalender-Events innerhalb von `days_ahead` nicht als einzelne Slides anzeigen.
  - Noch zu entscheiden: Alle betroffenen Tage gemeinsam in der Datumszeile aufführen.
  - Alternative: Nur den unmittelbar nächsten Termin des Events anzeigen.

## Dauerbetrieb

- [ ] Watchdog für Chromium einrichten.
  - Eine leere oder hängende Anzeige erkennen und Chromium automatisch neu starten.
  - Dadurch soll bei diesem Fehler kein Neustart des gesamten Raspberry Pi mehr nötig sein.
