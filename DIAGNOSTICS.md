# Diagnose-Referenz aus Version 0.4

Historische Detailbeschreibung der Diagnose- und Rettungswerkzeuge. Für aktuelle Installation, Rechte und Funktionen gelten README.md und ADMINISTRATION.md.

# ServerLotse

Dein Server. Verständlich. Mehrsprachige Werkzeugzentrale für Linux-Homeserver, Entwicklungsversion 0.4.0.

## Neu in 0.4 – Kategorien, einheitliche Felder und Host-Steuerung

Alle Ordnerfelder verwenden native Dropdowns wie die Ansichts-Auswahl, einheitlich 48 Pixel hoch. Auswahl eines Unterordners übernimmt seinen Pfad und lädt dessen Unterordner; mit `↑` geht es zum Elternordner. Die Sidebar und die Dashboard-Werkzeuge sind in aufklappbare Kategorien **Dateiverwaltung** und **System** gegliedert. Der markierte Hinweistext im Sidebar-Fuß wurde entfernt.

Das Dashboard bietet **Neustart (Reboot)** und **Herunterfahren (Shutdown)**. Der erste Klick öffnet nur eine Bestätigung. Dort `REBOOT` oder `SHUTDOWN` eingeben und bestätigen. Eine einmalige, aktionsgebundene Freigabe gilt 60 Sekunden. Laufende ServerLotse-Aufgaben blockieren die Aktion. Nach angeforderter Host-Aktion werden neue Aufgaben vorübergehend gesperrt. Externe Übertragungen, Rclone und andere Anwendungen kennt diese Sperre nicht: vorab selbst deren Abschluss sicherstellen.

### Einmalige Einrichtung vor dem ersten Reboot

Die schreibgeschützte Systemansicht unter `/run` verschwindet nach einem Neustart. Das folgende Skript installiert den bestehenden Mount-Helfer samt systemd-Unit und aktiviert ihn vor Docker:

```sh
cd /mnt/intenso2tb/serverlotse
sudo sh install-host-view.sh
docker compose up -d --build
```

Der Reboot-Button bleibt gesperrt, solange die erwartete Unit nicht installiert und aktiviert ist. Der Installer legt `/usr/local/lib/serverlotse/prepare-host.sh` und `/etc/systemd/system/serverlotse-view.service` an. Für systemd-freie oder rootlose Systeme ist diese Host-Steuerung nicht vorgesehen.

### Wie Neustart und Shutdown ausgeführt werden

Ein zusätzlicher Container `host-control` hat keinen veröffentlichten Port und ein eigenes internes Netz mit der Hauptanwendung. Er erhält den Host-Systembus unter `/run/dbus/system_bus_socket`. Seine HTTP-API authentifiziert den gemeinsamen serverseitigen Token und erlaubt nur Status, Bestätigungsvorbereitung und die beiden festen Aktionen. Über `systemd-logind` wird `ScheduleShutdown` mit 15 Sekunden Vorlauf angefordert; kein erzwungenes Abschalten, kein direkter Reboot-Systemaufruf, kein beliebiges Shellkommando. Inhibitoren, Berechtigungs- und D-Bus-Fehler werden nicht durch Force-Optionen umgangen. Eine angenommene Anforderung bestätigt noch nicht den erfolgreichen Abschluss. Nach Shutdown ist externes Einschalten nötig.

**Rechte des Vermittlers:** Ein schreibgeschützt eingebundener D-Bus-Socket begrenzt nicht die D-Bus-Methoden. Die Begrenzung liegt in unserem Vermittler; bei dessen Kompromittierung ist weitreichender Hostzugriff möglich. Es gibt noch kein externes Sicherheitsaudit. Standard ist `HOST_CONTROL_ENABLED=1`; mit `0` sperrt der Vermittler die Aktionen, der Socket bleibt dennoch eingebunden. Nur hinter dem bestehenden HTTPS-Zugang verwenden.

Geprüft sind Bestätigung, Ablauf, Wiederverwendungsschutz und feste D-Bus-Argumente mit Test-Doubles. **Ein echter Reboot/Shutdown auf Linux wurde in dieser Windows-Entwicklungsumgebung nicht durchgeführt.** Die Demo führt grundsätzlich keine Host-Aktionen aus.

## Neu in 0.3 – Deutsch, Spanisch, Englisch und gespeicherte Anmeldung

Sprachauswahl oben rechts: DE, ES, EN. Die Auswahl bleibt in diesem Browser gespeichert. Menüs, Werkzeuge, Ordnerauswahl, Ergebnisbeschriftungen und bekannte Diagnosemeldungen werden übersetzt. Dateinamen, Pfade und originale Protokollzeilen bleiben unverändert. Unbekannte Betriebssystem-/Drittdienstmeldungen bleiben im Original. Zahlen und Datumsangaben folgen der gewählten Sprache.

Den Token liest der Server weiterhin beim Start über Docker Compose aus der eigenen `.env`. Ein Browser meldet sich einmal mit diesem Schlüssel an. Mit **Angemeldet bleiben (30 Tage)** erhält er eine signierte Sitzung und wird bei späteren Besuchen automatisch angemeldet. Der Token wird nie automatisch an Besucher ausgeliefert und nicht in localStorage gespeichert. Im Browser liegen nur die Sprachpräferenz und eine separate HttpOnly-/SameSite-Strict-Sitzung. Ein Browser ohne gültige Sitzung braucht weiterhin eine Anmeldung; eine `.env`-Datei kann keinen unbekannten Besucher authentifizieren.

Sitzungen bleiben bei unverändertem Token nach Containerneustarts gültig, maximal bis zu ihrem Ablauf. **Abmelden** löscht das Browser-Cookie und sperrt die aktuelle Sitzung im laufenden Prozess. Diese Sperrliste liegt im RAM; bei einem Serverneustart geht sie verloren. Bei Verdacht auf einen gestohlenen Sitzungsschlüssel den Token in der `.env` ändern und den Container neu erstellen: Dadurch werden alle bisherigen Sitzungen ungültig. Ohne die Erinnerungsoption wird ein Browser-Sitzungscookie mit serverseitig maximal 12 Stunden Laufzeit verwendet; Browser können Sitzungen je nach Wiederherstellungseinstellungen fortsetzen.

Standardmäßig haben Sitzungscookies **Secure** und werden nur über HTTPS gesendet. Der bestehende HTTPS-Proxy funktioniert unverändert. Ausschließlich für private lokale HTTP-Entwicklung kann `SESSION_COOKIE_SECURE=0` gesetzt werden; nicht für öffentlichen Zugriff. Loginversuche werden auf 10 pro Minute und direkter Peer-IP begrenzt; hinter einem Proxy teilen sich Nutzer dessen Grenze. Fremde Browser-Origins werden bei POST-Anfragen abgewiesen.

## Neu in 0.2.1 – Serverordner auswählen

Aufklappbare Ordnerauswahl für Speicheranalyse, Vergleich (Quelle und Ziel), Dateibrowser, große Dateien, Dateitypen, Suche, Duplikate und Rettungskopien. Die Ordnerliste wird direkt in der gewählten Host-/Systemansicht geladen, unabhängig von laufenden Prüfaufgaben. Mit Pfadleiste, Filter, Auswahlbestätigung, Escape und Abbrechen. Die bisherigen Pfad-Schnellwahlbuttons entfallen. Drei markierte Einführungstexte wurden entfernt. Keine zusätzlichen Analysefunktionen in diesem Update.

## Neu in 0.2 – die große Werkzeugkiste

Dateibrowser mit Rechten und Eigentümern, große Dateien, Speicher nach Dateitypen, Dateinamensuche, SHA-256-Duplikatsuche, Host-Systemwerte, Dateisystemzuordnung, lokale Protokollauswertung, Prüfleitfäden, Aufgabenverlauf, Fortschritt, Abbrechen sowie JSON- und CSV-Export. Dazu optional Docker-Status/Logs und bestätigte Rettungskopien mit SHA-256-Prüfung. Die Basis bleibt ein einzelner Container ohne Drittanbieter-Pythonpakete.

Nach einer Browseraktualisierung erneut anmelden: Laufende Jobs sind im Verlauf verfügbar. Nur die letzten 20 Jobs im Container-RAM, kein dauerhaftes Auditarchiv. Abbrechen wird zwischen Leseoperationen geprüft; blockierte Dateisystemzugriffe können weiterhin dauern.

### Update von einer älteren Version

Neue Projektdateien über die bisherigen kopieren, **die eigene `.env` behalten**. Port 18099 und Bind-IP bleiben im bereitgestellten Compose-Schema erhalten. Eine eigene abweichende Portänderung übernehmen. Das Docker-Lesemodul ist inzwischen in der Hauptdatei enthalten; keine zusätzliche Compose-Datei dafür nötig.

```sh
cd /mnt/intenso2tb/serverlotse
sudo sh prepare-host.sh
docker compose build --pull
docker compose up -d
docker compose ps
```

Der HTTPS-Proxy kann unverändert auf den bisherigen LAN-Port zeigen. Weboberfläche nach dem Update vollständig neu laden. Öffentlich ausschließlich hinter dem eingerichteten HTTPS-Proxy betreiben, den direkten HTTP-Port nicht ins Internet weiterleiten.

### Docker lesen

```sh
docker compose up -d --build
```

Der in der Hauptdatei enthaltene kleine `docker-reader`-Container erhält den Docker-Socket und ist ausschließlich über ein internes Docker-Netz erreichbar, ohne veröffentlichten Port. Er erlaubt nur bereinigte Containerlisten und die letzten 150 Logzeilen anhand einer validierten Container-ID. Keine beliebigen API-Pfade, Containeraktionen, Shell oder Exec. Die Hauptanwendung bekommt den Socket nicht. `compose.docker.yaml` bleibt lediglich zur Kompatibilität älterer Aufrufe erhalten.

Der Socket bleibt grundsätzlich mächtig: `:ro` macht die Docker-API **nicht** zu einer schreibgeschützten API. Die Begrenzung implementiert unser Vermittler; bei einer Kompromittierung dieses Containers ist Docker-Zugriff möglich. Noch kein externes Sicherheitsaudit. Logmaskierung erkennt häufige Token-/Passwortmuster, aber nicht alle möglichen Geheimnisse.

### Optional: Dateien retten

Einen **eigenen leeren Rettungsordner** erstellen, niemals `/`, ein Datenbankverzeichnis oder bestehende Appdaten verwenden:

```sh
mkdir -p /mnt/intenso2tb/serverlotse-rettung
```

In der eigenen `.env` ergänzen:

```dotenv
RECOVERY_PATH=/mnt/intenso2tb/serverlotse-rettung
```

Dann optional aktivieren:

```sh
docker compose -f compose.yaml -f compose.recovery.yaml up -d --build
```

Für beide optionalen Module alle drei Compose-Dateien angeben; dieselbe Dateikombination bei folgenden Updates verwenden.

Die Oberfläche bietet zuerst einen Kopierplan, höchstens 10.000 Dateien. Nach Eingabe von `KOPIEREN` wird in einen neuen eindeutigen Unterordner kopiert und währenddessen sowie anschließend im Ziel SHA-256 geprüft. Vorhandene Dateien werden nicht überschrieben. Die Plan-ID ist einmalig und 30 Minuten gültig. Abbruch/Fehler kann `.part`-Dateien oder fertige Kopien hinterlassen. Quelle bleibt unverändert. Kein Verschieben, kein Löschen, keine Übernahme von Rechten/Eigentümern/Zeitstempeln, keine Sicherung leerer Ordner und keine konsistente Datenbanksicherung.

Sichere Zieloperationen verwenden unter Linux Verzeichnisdeskriptoren und `O_NOFOLLOW`. Der Linux-Kopiertest ist enthalten; auf diesem Windows-Entwicklungsrechner konnte er nicht ausgeführt werden. Rettungsmodul bis zur erfolgreichen Linux-Prüfung als experimentell behandeln.


## Docker auf DietPi / Debian

Projektordner auf den Server kopieren, beispielsweise nach `/mnt/intenso2tb/serverlotse`. Docker Engine mit Compose-Plugin muss installiert sein. Linux amd64/arm64 sind die vorgesehenen Plattformen; bislang keine Prüfung auf echter DietPi-Hardware.

```sh
cd /mnt/intenso2tb/serverlotse
cp .env.example .env
```

Einen zufälligen Zugangsschlüssel erzeugen und in `.env` als `SERVERLOTSE_TOKEN` eintragen:

```sh
openssl rand -hex 32
```

Für Zugriff im Heimnetz in `.env` `SERVERLOTSE_BIND` auf die LAN-IP des Servers setzen, z. B. `192.168.178.20`. Standard ist ausschließlich `127.0.0.1`. `DATA_PATHS` enthält absolute Hostpfade, durch Doppelpunkt getrennt. Niemals die Systemansicht als externe Datenplatte eintragen.

### Systemansicht vorbereiten

Ein normaler Bind-Mount von `/` (ohne `--rbind`) macht die Systemplatte ohne darüber eingehängte Datenträger sichtbar. Das ist Voraussetzung für die Suche nach verdeckten Daten. Der Webcontainer selbst erhält keine Mount-Berechtigung.

```sh
sudo sh prepare-host.sh
docker compose build --pull
docker compose up -d
```

Im Browser `http://SERVER-IP:18099` öffnen und den Schlüssel eingeben. Für LAN-Zugriff nur in einem vertrauenswürdigen Netz verwenden; außerhalb davon HTTPS über einen bestehenden Reverse Proxy oder VPN benutzen. Der Schlüssel wird sonst unverschlüsselt übertragen. Zugriff erlaubt das Lesen großer Teile des Hosts: Schlüssel wie ein Administrator-Passwort behandeln. Die API gibt keine beliebigen Dateiinhalte aus, aber Dateinamen und Prüfergebnisse können vertraulich sein.

Nach einem Hostneustart muss die Systemansicht **vor** dem Containerstart wieder eingerichtet werden. Für automatischen Betrieb:

```sh
sudo install -D -m 0755 prepare-host.sh /usr/local/lib/serverlotse/prepare-host.sh
sudo install -m 0644 serverlotse-view.service /etc/systemd/system/serverlotse-view.service
sudo systemctl daemon-reload
sudo systemctl enable --now serverlotse-view.service
```

Prüfen, dass der Dienst erfolgreich ist: `systemctl status serverlotse-view.service`. Dann den Container neu erstellen, falls er vor der Systemansicht gestartet wurde. Vor Stoppen oder Entfernen der Hostansicht den ServerLotse-Container stoppen.

### Ports / Portainer

Compose baut aus diesem Quellordner. In Portainer muss der gesamte Projektordner als Build-Kontext verfügbar sein; eine allein hineinkopierte YAML reicht nicht. Einfachster Start ist `docker compose up -d` über SSH. Danach erscheint der Container in Portainer. Es gibt noch kein öffentlich veröffentlichtes Image.

### Updates

Basis: offizielles `python:3.15.1-alpine3.24`, am 24.10.2026 anhand der offiziellen Python- und Docker-Quellen geprüft. Die Version ist bewusst festgelegt, damit ein Neuaufbau keine unangekündigte Hauptversion einführt. Für gepatchte Basis-Layer erneut `docker compose build --pull` und `docker compose up -d` ausführen. Neue Python-Patchversionen bewusst im Dockerfile übernehmen. Es werden beim Containerstart keine Pakete installiert.

## Lokale Demo unter Windows

```powershell
$env:SERVERLOTSE_DEMO='1'
$env:BIND='127.0.0.1'
python server.py
```

Browser: `http://127.0.0.1:8099`. Beispieldaten, keine Live-Analyse des Linux-Servers; eingefügter Protokolltext wird lokal ausgewertet. Kopieren bleibt in der Demo deaktiviert. Ohne Demomodus startet der Dienst nur mit einem mindestens 24 Zeichen langen Schlüssel.

## Prüfungen

```sh
python -m unittest discover -s tests -v
```

Tests prüfen Pfadausbruch, symbolische Links, versteckte Dateien, Hardlinks und echte Inhaltsunterschiede bei gleicher Dateigröße.

Zusätzlich werden die neuen Werkzeuge, Abbruch, Logmaskierung, Docker-Logframes und die Kopiervorschau geprüft. Den vollständigen Test einschließlich Linux-Kopieren ohne Host-Einbindungen ausführen:

```sh
docker build --pull -f Dockerfile.test -t serverlotse-tests .
docker run --rm serverlotse-tests
```

## Grenzen der ersten Version

- Entwicklungsversion, kein fertiges Community-Release. Noch keine SMART-Daten, Live-CPU-Anzeige, frei ausführbaren Hostbefehle, Containeraktionen oder automatischen Reparaturen. Nur die beiden ausdrücklich bestätigten Host-Energieaktionen sind implementiert.
- Nur eine Prüfung gleichzeitig, höchstens 250.000 Einträge pro Inventur und 1.000 angezeigte Vergleichsabweichungen. Jobzustand im Arbeitsspeicher; ein Containerneustart verwirft Ergebnisse. Browser kann geschlossen werden; Verlauf nach erneuter Anmeldung abrufen.
- `st_blocks` misst belegten Dateispeicher, Verzeichnismetadaten werden nicht mitgerechnet. Nicht identisch mit `df`; Snapshots, gelöschte offene Dateien, Metadaten, Kompression und CoW können Unterschiede verursachen.
- Andere Dateisysteme werden übersprungen; Bind-Mounts desselben Dateisystems können dennoch mitgezählt werden. Für die Rootanalyse die Systemansicht verwenden.
- Keine symbolischen Links verfolgen. Unlesbare Dateien, Link-Sprünge und übersprungene Einträge verhindern eine Aussage über eine vollständige Kopie.
- Vergleich ist keine konsistente Sicherung laufender Anwendungen. Für Datenbanken werden anwendungsgerechte Backups benötigt. Veränderte Dateien können das Ergebnis beeinflussen; keine Freigabe zum Löschen daraus ableiten.
- Hostzugriff ist schreibgeschützt, Container läuft aber für das Lesen von Rootdateien als UID 0 mit entfernten Linux-Capabilities. Kein `privileged`, kein Host-PID-Netzwerk, kein Docker-Socket in der Hauptanwendung. Read-only-Unterbindungen hängen von Docker und Linux-Kernel ab; auf moderner Docker Engine mit Kernel >= 5.12 betreiben. Noch kein formales Sicherheitsaudit.

## Nächste Ausbaustufen

1. Linux-Integrationstests für Einhängepunkte, Berechtigungen, Vermittler und Wiederherstellungskopien.
2. Dauerhaftes Auditprotokoll, feinere Benutzerrechte und erweiterte Diagnosen.
3. Erst danach ausdrücklich bestätigte Bereinigungen und Reparaturaktionen.

Lizenz: MIT, siehe LICENSE.
