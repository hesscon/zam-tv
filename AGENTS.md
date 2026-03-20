# AGENTS.md

## Projektziel
Wir bauen eine moeglichst einfache Signage-Software fuer einen direkt angeschlossenen Raspberry Pi 4 mit genau einem Monitor.

Die Software soll:
- Inhalte fullscreen anzeigen
- Hoch- und Querformat unterstuetzen
- Bilder, Videos, externe Webseiten und ausgewaehlte Events aus einer ICS-Datei darstellen
- Inhalte nacheinander in definierter Reihenfolge abspielen
- eine einfache Admin-Oberflaeche zum Konfigurieren und spaeter auch zum Hochladen bieten
- als Docker-Image gebaut werden koennen

## Prioritaeten
Bei Architektur- und Technologieentscheidungen gelten diese Prioritaeten in dieser Reihenfolge:
1. Einfachheit vor Vollstaendigkeit
2. Ein einzelner Prozess vor mehreren Diensten
3. Datei-basierte Konfiguration vor Datenbank
4. Wartbarkeit vor Cleverness
5. Solide Basis zuerst, Erweiterungen spaeter

## Produktannahmen
Solange nichts anderes entschieden wurde, gelten diese Annahmen:
- Es gibt genau einen Bildschirm.
- Es gibt genau eine lokale Installation pro Geraet.
- Die Admin-Seite darf anfangs ohne Login erreichbar sein.
- Inhalte werden in einer festen Playlist/Reihenfolge abgespielt.
- Die Anzeige laeuft im Kiosk-Modus.
- Internet kann fuer externe Webseiten und Kalenderdaten verfuegbar sein, die Grundsoftware soll aber moeglichst robust bei temporaeren Ausfaellen bleiben.

## Empfohlene Startarchitektur
Wenn keine gegenteilige Anforderung besteht, bevorzuge diese einfache Architektur:
- Backend: Python
- Web-Framework: Flask
- Templates: serverseitig gerenderte HTML-Seiten
- Datenhaltung: YAML-Datei
- Uploads: lokales Dateisystem
- Anzeige: Browser-basierte Signage-Oberflaeche im Vollbild
- Containerisierung: Docker

Warum diese Wahl:
- Python + Flask ist fuer ein erstes, kleines Projekt besonders gut verstaendlich.
- YAML ist fuer eine kleine, feste Playlist leichter als eine Datenbank.
- Ein Textfeld zur Bearbeitung der Konfiguration ist fuer V1 ausreichend.
- Serverseitiges Rendering reduziert Frontend-Komplexitaet.

## Technische Leitplanken
- Keine Microservices.
- Standardmaessig kein SPA-Frontend, solange kein klarer Bedarf entsteht.
- Keine Datenbank in der ersten Version.
- Keine Authentifizierung im ersten Schritt.
- Abhaengigkeiten klein halten.
- Bevorzuge bewaehrte Bibliotheken statt Eigenbau.

## Kernfunktionen fuer die erste Version
- Eine zentrale YAML-Konfigurationsdatei fuer Inhalte und Reihenfolge
- Inhalte vom Typ `image`, `video`, `web`, `calendar`
- Admin-Seite mit Textfeld zum direkten Bearbeiten der YAML-Konfiguration
- Spaeter erweiterbar um Datei-Uploads fuer Medien
- Signage-Ansicht fuer den Bildschirm
- Einfache Verarbeitung einer ICS-Quelle fuer ausgewaehlte Events

## Nicht-Ziele fuer die erste Version
- Mehrbenutzerbetrieb
- Rechte- und Rollensystem
- Verteilte Geraeteverwaltung
- Aufwendige Animationen
- Drag-and-drop-Builder
- Komplexe Datenmodelle

## Erwartete Ordnerstruktur
Wenn Dateien neu angelegt werden, ist diese Struktur der Standard:

```text
app/
  templates/
  static/
  services/
config/
data/
  uploads/
tests/
```

## Coding-Regeln
- Bevorzuge einfache, lesbare Funktionen.
- Fuehre Logik nicht in Templates aus, wenn sie im Backend liegen kann.
- Halte Dateizugriff, Validierung und Darstellung getrennt.
- Schreibe kleine, klar benannte Module.
- Dokumentiere nur dort, wo die Absicht nicht sofort offensichtlich ist.
- Fuege nur dann neue Tools oder Frameworks hinzu, wenn sie klaren Nutzen bringen.

## Entscheidungsregeln fuer Codex
Bei Vorschlaegen oder Implementierungen in diesem Repository:
- Schlage standardmaessig die einfachste funktionierende Loesung vor.
- Bevorzuge YAML- und Dateisystem-Loesungen vor Datenbank- oder UI-Komfortfunktionen.
- Begruende komplexere Alternativen nur, wenn sie einen klaren Mehrwert haben.
- Weisen auf Raspberry-Pi-spezifische Auswirkungen hin, wenn Performance, Video, Browser-Kiosk oder Docker betroffen sind.
- Frage vor groesseren Architekturwechseln nach.
- Halte den Einstieg fuer einen Anfaenger nachvollziehbar und erklaere wichtige Entscheidungen knapp und praktisch.

## Zusammenarbeit
Conrad ist neu in Codex und im Projektsetup. Deshalb gilt:
- Erklaere wichtige Schritte kurz mit.
- Weise gelegentlich auf hilfreiche Codex-Moeglichkeiten hin, wenn sie im aktuellen Schritt wirklich nuetzlich sind.
- Arbeite iterativ und mit moeglichst kleinen, pruefbaren Schritten.

## Offene Entscheidungen
Diese Punkte sind noch nicht final und duerfen spaeter gemeinsam entschieden werden:
- Exakte Python-Bibliotheken fuer ICS-Verarbeitung
- Wie die Bildschirmansicht auf dem Raspberry Pi genau gestartet wird
- Wann aus dem YAML-Editor ein komfortableres Admin-UI werden soll
