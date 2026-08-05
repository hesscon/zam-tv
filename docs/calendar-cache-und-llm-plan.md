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

- Der Kalender-Snapshot wird beim Start und danach alle 15 Minuten in einem
  Hintergrund-Thread neu aufgebaut.
- `/screen` liest nur den jeweils fertig aufgebauten Snapshot.
- Bei einem Fehler bleibt der alte Cache erhalten.
- Der eigenstaendige Caption-Worker mit JSON-/JSONL-Ein-/Ausgabe, Titelklassifikation,
  optionaler Caption-Erzeugung und `--classify-only` ist implementiert und
  getestet.
- `calendar_service` liefert `UID` und `DESCRIPTION` als Event-Kandidaten.
- Der `CalendarSnapshotBuilder` uebernimmt vorhandene Captions und uebergibt
  nur neue oder in Titel beziehungsweise Beschreibung geaenderte Events
  gesammelt an den externen Caption-Worker.
- Jedes fertige Worker-Ergebnis wird sofort atomar in Speicher- und Datei-Cache
  uebernommen. Ein spaeterer Worker-Abbruch verwirft bereits fertige Captions
  daher nicht.
- Der fertige Snapshot enthaelt die Caption bereits; ihre Darstellung auf dem
  Kalender-Slide folgt separat.

## Geplanter Ablauf

1. Ein Hintergrund-Thread startet alle 15 Minuten die Aktualisierung.
2. ICS-Daten und Slides werden vollstaendig neben dem aktiven Cache aufgebaut.
3. Der alte Cache bleibt waehrenddessen lesbar.
4. Nach jedem fertigen Caption-Ergebnis wird der aktuelle Zwischenstand atomar
   aktiviert; nach Abschluss folgt der finale Snapshot.
5. Bei Fehlern bleibt der letzte gueltige Snapshot erhalten.

`/screen` liest damit nur fertige Daten und wartet weder auf den ICS-Abruf noch auf das LLM.

## LLM-Beschriftungen

- Bevorzugtes Testmodell nach den bisherigen Vergleichen: Gemma E4B Q5_K_M.
- Ausfuehrung einmal pro Aktualisierung in einem kurzlebigen Unterprozess.
- Alle zu bearbeitenden Events werden gesammelt als JSON ueber `stdin` uebergeben.
- Ergebnisse kommen einzeln als JSONL ueber `stdout` zurueck; Logs gehen nach
  `stderr`.
- Ist kein Event neu oder inhaltlich geaendert, wird kein Worker-Prozess
  gestartet.
- Wiederkehrende Termine mit gleicher Quelle, UID und gleichem Inhalts-Hash
  werden innerhalb eines Refreshs nur einmal verarbeitet.
- Der erste Modellaufruf erhaelt nur den Titel und bewertet Aktivitaet und
  Begriffe ueber kurze Enum-Werte.
- `explicit` und `common` zaehlen null Punkte, `context_specific` einen Punkt
  und `generic`, `missing` sowie `unfamiliar` zwei Punkte.
- Ab zwei Punkten erhaelt ein zweiter Modellaufruf Titel und Beschreibung und
  erzeugt per eigenem JSON-Schema die `caption`.
- Der Generator darf eine leere Caption liefern, wenn die Beschreibung keine
  hilfreiche inhaltliche Ergaenzung bietet. Das ist eine erfolgreiche
  Enthaltung und kein LLM-Fehler.
- Das Modell wird pro Durchlauf einmal geladen und verarbeitet danach alle neuen oder geaenderten Events.
- Der Worker-Timeout misst die Zeit bis zum jeweils naechsten Ergebnis. Jedes
  empfangene Ergebnis startet diese Frist neu.
- Nur der Caption-Unterprozess wird mit dem ueber
  `EVENT_CAPTION_NICE_LEVEL` konfigurierten Nice-Level gestartet
  (Standard: `10`). Flask selbst bleibt bei Nice `0`.
- Der Klassifikationsaufruf bewertet ausschliesslich anhand des Titels, wie
  konkret die Aktivitaet und wie allgemein verstaendlich die entscheidenden
  Begriffe sind. Die Beschreibung beeinflusst diese Stufe nicht.
- Eine Caption soll die Aktivitaet erklaeren oder ungelaeufige Begriffe,
  Wortspiele und Abkuerzungen verstaendlich machen.
- Die beiden Aufrufe haben getrennte kurze System-Prompts, Beispiele und
  JSON-Schemas. Es gibt weiterhin keine Ueberarbeitungs- oder
  Validierungsrunde.

## Persistenter Cache

Der letzte gueltige Kalender-Snapshot wird in
`data/cache/calendar_cache.json` gespeichert. Die Beschriftung und ihre
Pruefdaten liegen direkt im jeweiligen Slide. Es gibt keine separate
Caption-Map.

Ein Kalender-Slide enthaelt zusaetzlich mindestens:

- `uid`
- `caption_input_hash` aus normalisiertem Titel und `DESCRIPTION`
- `caption`

Beim Neuaufbau gilt:

- Passender alter Slide mit gleicher UID und gleichem Hash: Beschriftung uebernehmen
- Inhalt geaendert oder Event neu: Beschriftung neu erzeugen
- LLM-Fehler: Fehler loggen und Event ohne Beschriftung speichern

So kann der Kalender weiterhin komplett neu aufgebaut werden, ohne unveraenderte Texte erneut zu generieren. Beschriftungen ausgefilterter oder abgelaufener Slides werden bewusst nicht dauerhaft aufbewahrt.

## Verhalten nach einem Neustart

1. Flask laedt sofort den letzten gueltigen Snapshot aus
   `data/cache/calendar_cache.json`.
2. Die Anzeige verwendet diese Daten, waehrend im Hintergrund eine Aktualisierung startet.
3. Nach erfolgreichem Neuaufbau werden Speicher-Cache und Datei atomar ersetzt.
4. Gibt es beim allerersten Start noch keine Cache-Datei, laeuft die normale Playlist vorerst ohne Kalender-Slides weiter.

Der Browser muss die aktualisierte Playlist danach neu abrufen oder die Seite neu laden.

## Umsetzungsschritte

1. Hintergrundaktualisierung und atomaren Cache-Tausch einfuehren. (umgesetzt)
2. `UID` und `DESCRIPTION` aus der ICS-Datei uebernehmen. (umgesetzt)
3. Persistenten Kalender-Snapshot implementieren. (umgesetzt)
4. Vorhandenen LLM-Worker an den Kalender-Refresh anbinden. (umgesetzt)
5. Ressourcenverbrauch und Laufzeit auf dem Raspberry Pi 4 messen.
