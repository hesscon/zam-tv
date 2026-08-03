# Kalender-Cache und LLM-Kurztexte

## Ziel

Kalender-Updates sollen die Anzeige nicht blockieren. Aus Titel und
ICS-Langbeschreibung soll nur bei Bedarf eine kurze Erklaer-Beschriftung
entstehen, zum Beispiel:

> Pecha-Kucha-Nacht → Kurze Vortraege zu vielfaeltigen Themen

Ist der Titel bereits aus sich heraus verstaendlich, bleibt die Beschriftung
leer. Ziel ist nicht, fuer jedes Event Text zu erzeugen, sondern nur die
kleinste fehlende Erklaerung zu liefern.

## Aktueller Stand

- Der Kalender-Cache gilt 15 Minuten.
- Nach Ablauf wird er beim naechsten `/screen`-Aufruf synchron neu aufgebaut.
- Bei einem Fehler bleibt der alte Cache erhalten.
- Der Neuaufbau kann den Browser-Request blockieren.
- `DESCRIPTION` und `UID` werden bisher nicht fuer Slides verwendet.

## Geplanter Ablauf

1. Ein Hintergrund-Thread startet alle 15 Minuten die Aktualisierung.
2. ICS-Daten und Slides werden vollstaendig neben dem aktiven Cache aufgebaut.
3. Der alte Cache bleibt waehrenddessen lesbar.
4. Nach Erfolg wird der neue Snapshot atomar aktiviert.
5. Bei Fehlern bleibt der letzte gueltige Snapshot erhalten.

`/screen` liest damit nur fertige Daten und wartet weder auf den ICS-Abruf noch auf das LLM.

## LLM-Beschriftungen

- Bevorzugtes Testmodell nach den bisherigen Vergleichen: Gemma E4B Q5_K_M.
- Ausfuehrung einmal pro Aktualisierung in einem kurzlebigen Unterprozess.
- Alle zu bearbeitenden Events werden gesammelt als JSON ueber `stdin` uebergeben.
- Ergebnisse kommen als JSON ueber `stdout` zurueck; Logs gehen nach `stderr`.
- Der erste Modellaufruf erhaelt nur den Titel und bewertet Aktivitaet und
  Begriffe ueber kurze Enum-Werte.
- Der Worker leitet daraus deterministisch ab, ob eine Caption erforderlich
  ist. Nur dann erhaelt ein zweiter Modellaufruf Titel und Beschreibung und
  erzeugt per eigenem JSON-Schema die `caption`.
- Das Modell wird pro Durchlauf einmal geladen und verarbeitet danach alle neuen oder geaenderten Events.
- Der Klassifikationsaufruf entscheidet ausschliesslich anhand des Titels, ob
  ein Mensch ohne Vorwissen unmissverstaendlich auf die konkrete Aktivitaet
  schliessen kann.
- Eine Caption soll die Aktivitaet erklaeren oder ungelaeufige Begriffe,
  Wortspiele und Abkuerzungen verstaendlich machen.
- Die beiden Aufrufe haben getrennte kurze System-Prompts, Beispiele und
  JSON-Schemas. Es gibt weiterhin keine Ueberarbeitungs- oder
  Validierungsrunde.

## Persistenter Cache

Der letzte gueltige Kalender-Snapshot wird in `data/calendar_cache.json` gespeichert. Die Beschriftung und ihre Pruefdaten liegen direkt im jeweiligen Slide. Es gibt keine separate Caption-Map.

Ein Kalender-Slide enthaelt zusaetzlich mindestens:

- `uid`
- Hash aus normalisiertem Titel und `DESCRIPTION`
- generierte Beschriftung
- Modell- und Prompt-Version

Beim Neuaufbau gilt:

- Passender alter Slide mit gleicher UID und gleichem Hash: Beschriftung uebernehmen
- Inhalt geaendert oder Event neu: Beschriftung neu erzeugen
- LLM-Fehler: Event ohne Beschriftung anzeigen

So kann der Kalender weiterhin komplett neu aufgebaut werden, ohne unveraenderte Texte erneut zu generieren. Beschriftungen ausgefilterter oder abgelaufener Slides werden bewusst nicht dauerhaft aufbewahrt.

## Verhalten nach einem Neustart

1. Flask laedt sofort den letzten gueltigen Snapshot aus `calendar_cache.json`.
2. Die Anzeige verwendet diese Daten, waehrend im Hintergrund eine Aktualisierung startet.
3. Nach erfolgreichem Neuaufbau werden Speicher-Cache und Datei atomar ersetzt.
4. Gibt es beim allerersten Start noch keine Cache-Datei, laeuft die normale Playlist vorerst ohne Kalender-Slides weiter.

Der Browser muss die aktualisierte Playlist danach neu abrufen oder die Seite neu laden.

## Umsetzungsschritte

1. Hintergrundaktualisierung und atomaren Cache-Tausch einfuehren.
2. `UID` und `DESCRIPTION` aus der ICS-Datei uebernehmen.
3. Persistenten Kalender-Snapshot inklusive Caption-Daten implementieren.
4. LLM-Worker mit JSON-Ein-/Ausgabe anbinden.
5. Ressourcenverbrauch und Laufzeit auf dem Raspberry Pi 4 messen.
