# Texteckenintegration

## Ziel

Die LED-Textecke soll automatisch auf Veranstaltungen im ZAM-Haupthaus
hinweisen. Sie ist ein eigener Ausgabekanal und funktioniert unabhaengig von
der Playlist des Bildschirms.

Fuer die erste Umsetzung wird bewusst nur die einfache Betriebsart geplant:

- Vor einer Veranstaltung wird der naechste passende Termin angezeigt.
- Von `DTSTART` bis `DTEND` wird die laufende Veranstaltung mit `JETZT`
  angezeigt.
- Erst nach `DTEND` wird auf den folgenden Termin gewechselt.
- Manuell eingegebene Nachrichten werden in dieser ersten Version weder
  erkannt noch abwechselnd mit dem Veranstaltungshinweis dargestellt.

Im normalen Ablauf entstehen damit zwei relevante Textwechsel pro
Veranstaltung: einer zu Beginn und einer nach ihrem Ende. Eine erstmalige
Synchronisierung nach Aktivierung oder Neustart sowie Korrekturen nach einer
Terminaenderung koennen weitere Requests erforderlich machen.

## Vorgesehene Konfiguration

Die Textecke wird auf oberster Ebene der YAML-Datei konfiguriert:

```yaml
textecke:
  enabled: true
  content: https://www.zam.haus/?mec-ical-feed=1
  message_url: http://texteck.usr.zam.haus/api/v1/message
  categories:
    - Haupthaus
  fix_mec_timezone: true

items:
  - type: calendar
    content: https://www.zam.haus/?mec-ical-feed=1
    duration: 12
    enabled: true
    categories:
      - Veranstaltung
    days_ahead: 30
    fix_mec_timezone: true
```

Der Textecken-Block ist absichtlich nicht mit einem Eintrag unter `items`
gekoppelt:

- Die Textecke kann ohne Kalender-Slide auf dem Bildschirm betrieben werden.
- Es darf keinen, einen oder mehrere Kalender in der Playlist geben.
- Aenderungen an der Bildschirm-Playlist beeinflussen die Textecke nicht.
- Bildschirm und Textecke duerfen dieselbe ICS-Adresse verwenden, werden aber
  fachlich als unabhaengige Verbraucher behandelt.

Fehlt `textecke` oder ist `enabled: false`, sendet zam-tv keine Nachrichten an
das Laufband.

`categories` hat dieselbe Bedeutung wie beim bestehenden Kalenderfilter: Ein
Termin passt, wenn mindestens eine der angegebenen Kategorien vorhanden ist.
Fuer den aktuellen Anwendungsfall reicht deshalb die einzelne Kategorie
`Haupthaus`. Falls spaeter zwingend mehrere Kategorien gleichzeitig vorhanden
sein muessen, braucht diese Semantik eine ausdrueckliche Erweiterung.

Der Suchzeitraum der Textecke ist keine konfigurierbare Produkteinstellung.
Er wird im Code fest auf sieben Tage gesetzt. Das haelt die YAML-Datei klein
und reicht fuer den Zweck, zeitnah stattfindende Veranstaltungen anzukuendigen.

## Auswahl des angezeigten Termins

Zu einem Zeitpunkt `now` gilt folgende Prioritaet:

1. Ein laufender Termin mit `DTSTART <= now < DTEND` wird ausgewaehlt.
2. Gibt es keinen laufenden Termin, wird der chronologisch naechste Termin mit
   `DTSTART > now` innerhalb der naechsten sieben Tage ausgewaehlt.

Ein laufender Termin hat damit Vorrang vor allen zukuenftigen Terminen. Erst
nach seinem Ende rueckt der folgende Termin nach. Der Kalenderdienst liefert
die Events als nach Startzeit sortierte Liste. Laufen mehrere Veranstaltungen
gleichzeitig, verwendet der Textecken-Worker ohne weitere Sonderbehandlung den
ersten laufenden Eintrag dieser Liste. Weitere parallel laufende Termine werden
nicht zusaetzlich dargestellt.

## Nachrichtenformat

Fuer zukuenftige und laufende Termine gelten diese Formate:

```text
JETZT · Offene Werkstatt
SA 15:00 · Repair Cafe
```

Die Wochentage werden in der Zeitzone `Europe/Berlin` als `MO`, `DI`, `MI`,
`DO`, `FR`, `SA` und `SO` ausgegeben. Weil nur sieben Tage im Voraus gesucht
wird, ist keine zusaetzliche Datumsangabe erforderlich. Relative Angaben wie
`HEUTE` oder `MORGEN` werden nicht verwendet, da sie um Mitternacht falsch
wuerden und einen weiteren zeitgesteuerten POST erforderten.

Die Nachricht muss vor dem Senden UTF-8-sicher auf maximal 200 Bytes begrenzt
werden. Die Textecken-API begrenzt Bytes, nicht Zeichen; Umlaute benoetigen
mehr als ein Byte. Ein zu langer Titel wird an der letzten vollstaendigen
Wortgrenze innerhalb des verbleibenden Byte-Limits gekuerzt und niemals mitten
in einem Wort abgeschnitten.

Ist weder eine laufende Veranstaltung noch innerhalb der naechsten sieben Tage
ein passender Termin vorhanden, wird ein fester neutraler Standardtext
verwendet:

```text
Entdecke das ZAM in dir
```

Dieser seltene Fall benoetigt keine eigene YAML-Einstellung. Der Text wird als
fest codierte Konstante in der Texteckenintegration abgelegt.

## Nutzung des bestehenden Kalenderdienstes

`build_calendar_events()` aus `calendar_service` kann als gemeinsame Grundlage
verwendet werden. Die Funktion ist nicht an `type: calendar` oder die
`items`-Liste gebunden. Die Texteckenintegration bereitet ihren Block deshalb
wie ein Kalender-Quellobjekt auf und ergaenzt dabei intern den festen
Suchzeitraum von sieben Tagen.

Bereits vorhanden sind:

- ICS-Abruf mit HTTP-Fehlerbehandlung
- Kategorienfilter
- Begrenzung des Suchzeitraums; fuer die Textecke werden intern sieben Tage
  verwendet
- Expansion wiederkehrender Termine
- Sortierung nach Startzeit
- MEC-Zeitzonen-Workaround fuer `DTSTART`, `DTEND`, `RDATE` und `EXDATE`
- Beschraenkung einer wiederkehrenden Serie auf den jeweils naechsten Termin

Der Dienst ist momentan allerdings noch teilweise auf Bildschirm-Slides
zugeschnitten. Er erzeugt unter anderem QR-Code, Anzeigedauer,
`start_label` und eine verschachtelte `slide`-Struktur. Ausserdem wird `DTEND`
zwar korrigiert, aber nicht im Event-Ergebnis bereitgestellt.

Die bestehende Beschraenkung einer wiederkehrenden Serie auf ihr jeweils
fruehestes relevantes Vorkommen bleibt erhalten. Wird der Kalenderdienst nach
dem Ende eines Vorkommens erneut aufgerufen, ist dieses nicht mehr relevant und
der Dienst liefert das folgende Vorkommen der Serie. Es ist deshalb nicht
noetig, alle Vorkommen einer Serie an die Verbraucher weiterzugeben.

In der vorhandenen ZAM-ICS-Testdatei besitzen alle 254 Events ein syntaktisch
gueltiges `DTEND`. Ein aelterer Termin der Kategorie `Treffen` hat eine Dauer
von null, weil `DTEND == DTSTART` ist. Fuer die Textecke gilt deshalb als
einfache Sicherheitsregel: Fehlt `DTEND`, ist es ungueltig oder liegt es nicht
nach `DTSTART`, wird das Event mit einer Warnung uebersprungen. Es wird keine
Ersatzdauer angenommen.

## Geplante Trennung der Verantwortlichkeiten

`calendar_service` soll kuenftig nur normalisierte fachliche Kalenderdaten
liefern, zum Beispiel:

```python
{
    "uid": "event-123",
    "title": "Offene Werkstatt",
    "description": "...",
    "categories": ["Veranstaltung", "Haupthaus"],
    "image_url": "https://example.com/image.jpg",
    "event_url": "https://example.com/event",
    "start": start_datetime,
    "end": end_datetime,
}
```

`start` und `end` sollen zeitzonenbehaftete `datetime`-Objekte sein. Dadurch
kann die Textecke ohne erneutes Parsen entscheiden, ob ein Termin gerade
laeuft.

Der `CalendarSnapshotBuilder` erzeugt daraus die bildschirmspezifischen Daten:

- `type: calendar_event`
- `duration`
- die dargestellte Einzelkategorie
- `summary`
- `start_iso`
- `start_label`
- `qr_code_data_uri`
- die weiteren Slide-Daten und die optionale Caption

QR-Code-Erzeugung und die deutsche Datumsformatierung koennen zunaechst als
kleine Hilfsfunktionen beim Snapshot-Aufbau liegen. Ein zusaetzliches Modul ist
erst noetig, falls dieser Teil dadurch unuebersichtlich wird.

Die Textecke verwendet dagegen direkt die normalisierten Events und erzeugt
nur den Laufbandtext. So bleiben ICS-Verarbeitung, Bildschirmdarstellung und
Texteckensteuerung getrennt.

## Textecken-Worker

Die Integration wird durch einen kleinen `TexteckeWorker` mit genau einem
Hintergrund-Thread gesteuert. Dieser Thread uebernimmt:

- Laden und Normalisieren der Textecken-Konfiguration,
- regelmaessigen ICS-Abruf,
- Auswahl des laufenden oder naechsten Termins,
- Berechnung des naechsten relevanten Aufwachzeitpunkts,
- Erzeugung und Versand des Laufbandtexts,
- Fehlerprotokollierung und Wiederholungsversuche.

Der Worker sendet nicht in einem festen Intervall. Regelmaessig ist nur der
ICS-Abruf. Ein POST erfolgt ausschliesslich, wenn sich der gewuenschte Text
aendert oder der Prozess nach einem Neustart den Geraetezustand einmal
synchronisiert.

Der Thread wartet jeweils bis zum fruehesten dieser Zeitpunkte:

- naechster regulaerer ICS-Abruf,
- `DTSTART` des ausgewaehlten Termins,
- `DTEND` des laufenden Termins,
- Stop-Signal der Anwendung.

Der Worker merkt sich nur im Arbeitsspeicher den zuletzt erfolgreich
gesendeten Text. Dieser kleine Zustand verhindert identische POSTs nach jedem
unveraenderten ICS-Abruf. Er wird nicht persistent gespeichert.

## Aktualisierung und Zeitsteuerung

Der ICS-Inhalt soll weiterhin regelmaessig aktualisiert werden, damit neue,
geaenderte und abgesagte Termine erkannt werden. Der bestehende
15-Minuten-Rhythmus ist dafuer ein sinnvoller Ausgangspunkt.

Der eigentliche Wechsel zu `JETZT` beziehungsweise zum folgenden Termin sollte
nicht erst beim naechsten 15-Minuten-Abruf stattfinden. Nach einem erfolgreichen
Abruf sind `DTSTART` und `DTEND` bekannt; ein kleiner Textecken-Hintergrunddienst
kann den jeweils naechsten Umschaltzeitpunkt daraus bestimmen.

Bei `DTSTART` ist kein zusaetzlicher ICS-Abruf notwendig. Der bereits bekannte
Termin wird lediglich als laufend formatiert und per POST gesendet.

Bei `DTEND` wird die ICS-Quelle dagegen unmittelbar erneut abgerufen, bevor der
Folgetext bestimmt wird. Dadurch kann der bestehende Kalenderdienst auch das
naechste Vorkommen derselben Terminserie liefern. Der zusaetzliche Abruf pro
Veranstaltungsende ist selten und vermeidet eine komplexere Aenderung der
Wiederholungslogik. Die Anzahl der POSTs erhoeht sich dadurch nicht.

Ein POST ist erforderlich, wenn:

- die Integration erstmals einen gueltigen Zieltermin ermittelt,
- eine Veranstaltung beginnt,
- eine Veranstaltung endet,
- sich der gewaehlte Termin oder sein dargestellter Text durch einen neuen
  Kalenderstand aendert,
- der Prozess nach einem Neustart den gewuenschten Zustand wiederherstellen
  muss.

Unveraenderte Kalenderaktualisierungen sollen keinen erneuten POST ausloesen.

Ein beispielhafter Ablauf ist:

```text
09:00  Start, ICS-Abruf und POST des naechsten Termins
09:15  regulaerer ICS-Abruf, Text unveraendert, kein POST
09:30  regulaerer ICS-Abruf, Text unveraendert, kein POST
15:00  DTSTART, kein ICS-Abruf, POST "JETZT · Workshop"
17:00  DTEND, sofortiger ICS-Abruf, POST des folgenden Termins
```

## Verhalten beim Anwendungsstart

Die Texteckenintegration startet wie der Kalender-Cache im Hintergrund und
darf den Start von Flask und der Bildschirmanzeige nicht blockieren.

1. Fehlt der `textecke`-Block oder ist `enabled: false`, erfolgen weder
   ICS-Abruf noch API-Request.
2. Bei aktiver Integration wird unmittelbar ein erster ICS-Abruf gestartet.
3. Nach einem erfolgreichen Abruf wird der zu diesem Zeitpunkt gewuenschte
   Text ermittelt:
   - laufender Termin: `JETZT`-Nachricht,
   - naechster Termin innerhalb von sieben Tagen: Terminankuendigung,
   - kein passender Termin: fest codierter Standardtext.
4. Dieser Text wird beim Start einmal per POST gesendet. In der einfachen
   ersten Version gibt es weder GET-Abgleich noch persistenten
   Texteckenzustand; nach einem Prozessneustart wird der Zustand des Geraets
   deshalb einmal bewusst synchronisiert.
5. Danach merkt sich der laufende Prozess den zuletzt erfolgreich gesendeten
   Zieltext. Solange er unveraendert bleibt, wird kein weiterer POST gesendet.

Schlaegt der erste ICS-Abruf fehl, wird kein Standardtext gesendet, denn ein
Abruffehler ist nicht dasselbe wie ein erfolgreich geladener Kalender ohne
Termine. Die bestehende Nachricht am Laufband bleibt in diesem Fall
unangetastet. Der Fehler wird protokolliert und der Abruf beim naechsten
regulaeren Aktualisierungszeitpunkt erneut versucht.

## API und Fehlerverhalten

Die aktuelle Schnittstelle ist in der
[Textecken-Dokumentation](https://wiki.betreiberverein.de/books/projekte-abgeschlossen/page/41-textecke-3Lf)
beschrieben:

```http
POST http://texteck.usr.zam.haus/api/v1/message
Content-Type: application/json

{"text": "JETZT · Offene Werkstatt"}
```

Fuer die erste Betriebsart ist kein GET erforderlich.

Netzwerkfehler, Timeouts, ungueltige Antworten und API-Fehler werden knapp und
ohne sensible Inhalte protokolliert. Ein nicht erreichbares Laufband darf weder
die Kalenderaktualisierung noch die Bildschirmanzeige beeintraechtigen.
Fuer ICS-GET und Textecken-POST gilt ein fester HTTP-Timeout von zehn Sekunden.
Nach einem HTTP-Verbindungs-, Timeout- oder API-Fehler plant der Worker den
naechsten Versuch in fuenf Minuten. Schlaegt auch dieser fehl, gilt erneut
dasselbe feste Intervall. Es gibt kein exponentielles Backoff und keine
zusaetzliche Retry-Bibliothek.

Der Worker wartet auch im Fehlerfall ueber sein vorhandenes Stop-Event. Dadurch
kann die Anwendung ohne Verzoegerung beendet werden. Bereits erfolgreich
geladene Events und ihre bekannten Start- und Endzeitpunkte bleiben erhalten.
Liegt ein solcher Zeitpunkt vor dem geplanten Wiederholungsversuch, verarbeitet
der Worker ihn zuerst. Ein fehlgeschlagener POST wird nicht als erfolgreich
gesendeter Text vermerkt, sodass der naechste Versuch denselben Solltext erneut
senden kann.

## Spaetere Erweiterung: gemeinsamer ICS-Cache

In der ersten Umsetzung duerfen Bildschirmkalender und Textecke dieselbe
ICS-Adresse unabhaengig voneinander abrufen. Der doppelte Download ist bei
einem 15-Minuten-Intervall akzeptabel und haelt die erste Implementierung
einfach.

Spaeter kann ein allgemeiner ICS-Abrufdienst mit gemeinsamem Cache eingefuehrt
werden. Dieser Cache sollte den rohen ICS-Inhalt pro URL speichern, nicht die
bereits gefilterten Events. Bildschirm und Textecke koennen unterschiedliche
Kategorien, Zeitfenster und Darstellungsanforderungen haben und verarbeiten
denselben geladenen Inhalt deshalb weiterhin getrennt.

Eine moegliche Schnittstelle waere:

```python
ics_text = ics_service.load(url, force_refresh=False)
```

Dabei gilt:

- Ein normaler Aufruf verwendet einen ausreichend aktuellen Cache-Eintrag.
- Gleichzeitige Abrufe derselben URL sollen nach Moeglichkeit nur einen
  Netzwerkrequest ausloesen.
- Bei einem voruebergehenden Netzwerkfehler darf ein vorhandener letzter
  erfolgreicher Stand weiterverwendet werden.
- `force_refresh=True` erzwingt einen neuen Download und aktualisiert bei
  Erfolg den gemeinsamen Cache.
- Der Textecken-Worker kann `force_refresh=True` bei `DTEND` verwenden, bevor
  er den Folgetermin bestimmt.

Der Cache fuer den rohen ICS-Text vermeidet ausserdem, ein bereits geparstes
Kalenderobjekt zwischen Verbrauchern zu teilen. Das ist wichtig, weil der
MEC-Zeitzonen-Workaround das geparste Objekt veraendert.

## Spaetere Erweiterung: manuelle Nachrichten

Als moegliche zweite Betriebsart wurde ein Wechsel zwischen Veranstaltung und
manueller Nachricht diskutiert:

1. Aktuelle Nachricht per GET lesen und merken.
2. Veranstaltungshinweis per POST anzeigen.
3. Nach einer konfigurierten Zeit erneut lesen und eine zwischenzeitlich
   eingegebene manuelle Nachricht erkennen.
4. Veranstaltungshinweis und letzte manuelle Nachricht abwechselnd anzeigen.

Diese Variante ist nicht Teil der ersten Umsetzung. Vorher muessten unter
anderem Wechselintervall, Neustartverhalten und die Auswirkung haeufiger POSTs
auf die ESP32-Firmware praktisch geprueft werden.

## Vorgesehene Tests

- Validierung eines gueltigen und deaktivierten `textecke`-Blocks
- Betrieb ohne Kalender-Eintrag unter `items`
- Unabhaengigkeit von mehreren Kalender-Eintraegen unter `items`
- Auswahl des naechsten zukuenftigen Termins
- Vorrang eines laufenden Termins bis `DTEND`
- Wechsel bei exakt `DTSTART` und `DTEND`
- Standardtext, wenn innerhalb von sieben Tagen kein Termin vorhanden ist
- wiederkehrende Termine und Zeitzonenwechsel
- erneuter ICS-Abruf bei `DTEND` liefert das folgende Vorkommen einer Serie
- Event mit fehlendem, ungueltigem oder nicht positivem `DTEND` wird mit
  Warnung uebersprungen
- kein POST bei unveraendertem Zieltext
- neuer POST bei Titel-, Start-, End- oder Terminaenderung
- UTF-8-sichere Begrenzung auf 200 Bytes
- Logging und Isolation bei Timeout, Verbindungsfehler und HTTP-Fehler

## Noch offene Detailentscheidungen

Derzeit sind keine fuer die erste Umsetzung blockierenden Produktentscheidungen
mehr offen.
