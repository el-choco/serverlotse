# ServerLotse 0.7 – zusätzliche Werkzeuge

## Update

Dateien aus der ZIP über die vorhandenen Projektdateien kopieren, eigene .env behalten.
ServerLotse-Aufgaben abschließen und Terminals schließen, dann nur:

```sh
cd /mnt/intenso2tb/serverlotse
docker compose up -d --build
```

Anschließend Strg+F5. Der bereits ausdrücklich freigegebene host-bootstrap aktualisiert
auch die neuen Helfermodule. Exitcode 0 ist normal. Keine neue Portfreigabe, kein
manueller Installer. Bei Problemen: docker compose logs --tail 60 host-bootstrap.
Neue Automatiken starten nicht durch das Update. Bestehende Automatik und Backuppläne
bleiben erhalten. Docker steht auch im Dashboard nur noch in seiner eigenen Kategorie.

## Docker-Radar, Health und Registry

Messung ungefähr alle 15–30 Sekunden, maximal 100 laufende Container pro Messung.
Pro Container bis zu 240 Punkte im RAM; nach Helferneustart leer. Die Kurve lässt
sich auswählen und mit der Maus ablesen. CPU 100 % entspricht einem Kern, RAM-Prozent
bezieht sich auf das Docker-Limit. Bestätigte Startzeiten, HEALTHCHECK-Fehlerfolge,
letzte Check-Zeiten/Exitcodes, Neustartzähler und OOM-Flag werden angezeigt.

Der vorhandene ausgewählte Auto-Heiler wird wiederverwendet: zwei Fehlerprüfungen,
begrenzte Wiederanläufe und Schutz absichtlich gestoppter Container. Im Radar führt
„Auto-Heiler konfigurieren“ zu dessen bestehenden Einstellungen. Kein globaler
Neustart aller unhealthy Container durch die Installation.

„Registry vergleichen“ übermittelt Image-Referenz und IP des Servers an die Registry,
aber keine gespeicherten Docker-Zugangsdaten. Es wird das passende OS-/Architektur-
Manifest gewählt und dessen Config-Digest mit dem lokalen Image verglichen. Keine
verwechslungsträchtige Gegenüberstellung von Multiarch-Index und Plattform-Image.
Digest-Antworten werden geprüft, fremde Auth-Dienste/Weiterleitungen abgelehnt.
Private Registries und Sonderfälle können daher „nicht prüfbar“ liefern. Kein Pull,
keine automatische Image-Aktualisierung. Ein angezeigtes Ergebnis trägt seinen Zeitpunkt.
Werkzeugbefehle verwenden ausdrücklich den lokalen Host-Docker-Socket, keinen fremden Kontext.

## Klonen und Vorlagen

Ein Klon übernimmt das vorhandene lokale Image und die App-Konfiguration, aber weder
Daten noch Änderungen der beschreibbaren Container-Schicht. Standard: bridge und
leere neue Volumes. Optional vorhandene Daten nur lesend teilen; Host-Steuerungspfade
und Sockets werden dafür abgewiesen. Auch ein nur lesender Socket kann nämlich
Schreibbefehle an einen Dienst senden. Privilegierte/Host-Namensraum-Container und
erweiterte Gerätekonfigurationen werden nicht blind kopiert.

Optional kann genau ein im Image veröffentlichter TCP-Port neu zugeordnet werden.
Prüfung gegen Docker-Zuordnungen und einen kurzen lokalen bind-Versuch. Andere Dienste
können den Port anschließend trotzdem belegen; Docker meldet dies beim tatsächlichen
Start. Bind-IP 127.0.0.1 beschränkt den Zugriff auf den Host; andere Bind-IPs sind eine
bewusste Entscheidung über die Erreichbarkeit.

Vorlagen: nginx:stable-alpine, wordpress:apache, nextcloud:stable-apache und mariadb:lts.
Das sind veränderliche stabile Kanäle, keine automatische Migration bestehender Apps.
Im ausgewählten Basisordner wird ein neuer Ordner serverlotse-NAME mit compose.yaml,
.env und Datenunterordnern angelegt. Die Compose-Datei verwendet gültige JSON/YAML-
Syntax ohne zusätzliche YAML-Bibliothek. DB-Passwörter werden zufällig erzeugt und
nur in der root-geschützten .env gespeichert. Daten bleiben auch bei fehlgeschlagenem
Pull/Start für eine Prüfung erhalten. Web-Einrichtungsassistenten selbst abschließen;
HTTPS/Proxy, Backups und App-Pflege sind weiterhin erforderlich.

## Konfigurationsinspektor

Nur wenige syntaktisch harmlose Standardwerte (z. B. TZ, numerischer PORT) werden
angezeigt. Alle unbekannten Variablen werden vollständig maskiert, nicht nur Namen
mit PASSWORD. Vorschau und Aktionsprotokoll enthalten ebenfalls keine eingegebenen
Variablenwerte. Diese Werte müssen vom berechtigten Browser über HTTPS an den Host
übertragen und in der jeweiligen Containerkonfiguration gespeichert werden.

Eigenständiger Container: stoppen, bisherigen Container umbenennen, Ersatz aus dem
lokalen Image mit neuen Variablen erstellen, ursprüngliche Daten-Mounts einschließlich
anonymer Volumes erhalten, Ersatz starten. Der alte Container bleibt gestoppt erhalten.
Scheitert das Erstellen/Starten, wird eine Rücknahme versucht. App-Bereitschaft und
geteilte Daten sind nicht automatisch zurückgerollt. Keine Garantie der bisherigen
IP, keine Kopie der beschreibbaren Schicht; erweiterte/feste Netzwerk-IP-Konfigurationen
werden abgewiesen. Anschließend Container-IDs in Backup-/Heiler-Zielen prüfen.

Compose-Container: die schnelle Änderung erzeugt/ergänzt eine eigene root-geschützte
serverlotse-environment.override.json im Projektverzeichnis und stellt nur den gewählten
Dienst mit --no-deps neu bereit. Originaldateien bleiben unverändert. Die Override-Datei
muss bei späteren Portainer-/Compose-Updates mitverwendet werden; Portainer kann sie
sonst übergehen. Hier nur Werte überschreiben; zum Entfernen einer Compose-Variable
die ursprüngliche Konfiguration verwenden. Keine Bearbeitung beliebiger YAML-Quelldateien.

.env-Editor: root-geschützter Projektordner und Datei namens .env; höchstens 256 KB,
eindeutige einzeilige KEY=VALUE-Einträge. Kommentare und unveränderte Zeilen bleiben
erhalten. Neue Werte werden als Literale zitiert, nie als Shell-Code ausgewertet.
Vorherige Datei wird unter /var/lib/serverlotse mit Modus 600 gesichert. Speichern
allein startet keinen Dienst. Compose übernimmt nur in seiner Konfiguration verwendete
Variablen. Keine automatische Synchronisierung verschiedener Konfigurationsquellen.

## Erweiterter Janitor

Kein unkontrolliertes generisches Prune: erst konkrete Löschziele erfassen und
anzeigen, dann LOESCHEN. Unmittelbar vor Beginn wird neu validiert; geänderte
Ziele machen die Vorschau ungültig. Löscht bestätigte gestoppte fremde Container,
bestätigte unbenutzte Images/Netzwerke und aktuell unreferenzierte Volumes sowie
unbenutzten Build-Cache. Kein force bei Container-/Volume-/Image-Löschung.
ServerLotse-eigene Container/Images/Netzwerke bleiben geschützt. Volumes, die noch
an gestoppte Container gebunden sind, werden behalten, auch wenn diese Container
anschließend entfernt werden. Für diese Volumes gegebenenfalls erneut prüfen.

Nicht referenziert bedeutet weder leer noch entbehrlich. Beschreibbare Container-
Schichten und Volumes können die einzigen Kopien wichtiger Daten enthalten. Die
Aktion ist nicht rückgängig zu machen und keine gemeinsame Transaktion; bei Fehlern
können vorherige Teilaktionen abgeschlossen sein. Die vorhandene nächtliche Pflege
bleibt auf alte Images/Cache begrenzt und verwendet diesen vollständigen Janitor nie.

## Sitzungen und Netzwerkplan

loginctl-Sitzungen für SSH, dropbear und lokale Logins, ergänzt um ServerLotse-Terminals.
Nach Bestätigung gezielte Beendigung; Leader/Zeitpunkt bzw. Terminal-Identität werden
neu geprüft. Kann auch den eigenen Zugang trennen. Kein Key- oder Kontenentzug;
eigenständig gestartete Hintergrunddienste können weiterlaufen. Zugriff auf fremde
Terminalausgabe bleibt gesperrt; ein berechtigter Root-Administrator kann die Sitzung
über diese gesonderte bestätigte Verwaltungsaktion beenden.

Die filterbare Node-Map zeigt Netzwerkmitgliedschaften. Das beweist keine tatsächlichen
Datenflüsse oder Erreichbarkeit: Firewall, Treiber, Ports und Apps bestimmen diese.
Karte bis 30 Netze/40 Container, Tabelle bis zur begrenzten Gesamtübersicht (200 Container).

## Datei-, Zertifikats-, HTTP- und OOM-Wächter

Automatik → Datei- und Dienstwächter. Eigener Hauptschalter und einzelne Optionen;
Benachrichtigungsziel und Sendepause stammen aus Automatik und Meldungen. Lokale Befunde
funktionieren ohne Ziel; Versand wird dann als Fehler protokolliert. Neue Optionen aus.

FIM: zuerst Pfade unter /etc wählen/speichern und eine bestätigte Vergleichsbasis
anlegen. Erfasst SHA-256, Modus, UID/GID; neue/entfernte/geänderte Einträge. Symlink-
Ziele werden als Link-Metadaten gehasht, nicht inhaltlich verfolgt. Zielinhalte müssen
über ihren tatsächlichen /etc-Pfad separat in der Auswahl liegen. Maximal 2000 Dateien,
32 MiB je Datei, 256 MiB insgesamt und zehn Ausgangspfade. Eine unvollständige Basis
wird nicht übernommen. Vergleich ungefähr minütlich, langsame Prüfungen können länger
dauern. Updates/Administrationsarbeiten verändern Dateien ebenfalls: eine Abweichung
ist kein Nachweis eines Angriffs. Neue Basis ersetzt die alte ausdrücklich, ohne Reparatur.
Webhooks melden die Zahl der Änderungen, keine Dateiinhalte. Keine Echtzeit-/Inotify-Garantie.

Zertifikate: native LE-/Nginx-/Caddy-Pfade und aus Docker-Mounts erkennbare Ablagen
(z. B. Nginx Proxy Manager mit /etc/letsencrypt), ergänzbare Zertifikatsordner. Öffnet
nur Zertifikatsdateien für openssl x509; private Schlüssel werden nicht angezeigt.
Höchstens 300 Kandidaten/5000 gesichtete Dateien, Tiefe zehn. Keine Prüfung der gesamten
TLS-Vertrauenskette oder automatischer Renew-Versuch. Wächter ungefähr stündlich,
Warnung ab 14 angezeigten Resttagen, mit Sendepause. Dashboard zählt anhand des zuletzt
gesehenen Ablaufdatums weiter; nach einer Erneuerung neu prüfen oder Wächter aktivieren.

HTTP: GET mit erwartetem Status, zehn Sekunden Timeout, keine Umleitung, Anmeldung,
Query-Token oder deaktivierte TLS-Prüfung. Sicht vom Host, nicht von einem fremden
Internetzugang. Bis zehn konfigurierte Ziele, ungefähr minütlich bei aktiviertem Wächter.

OOM: begrenztes Kerneljournal (anfangs etwa fünf Minuten) plus Docker OOMKilled und
FinishedAt. Exitcode 137 allein gilt nicht als Beweis. Beim Öffnen der Diagnosehistorie
wird geprüft, bei aktivem OOM-Wächter wiederkehrend; bis 200 gespeicherte Ereignisse.
Keine vollständige rückwirkende Kernelarchivierung oder sichere PID-Zuordnung nach
Prozessende. Die Containerzuordnung stammt nur aus dem expliziten Docker-OOM-Flag.

## CPU-Verlauf, SMART und Logs

Ein eigener Sammler liest ungefähr alle fünf Sekunden Prozesszeiten, unabhängig von
langsamen Docker-/HTTP-Abfragen. Ab wählbarer Gesamt-CPU-Schwelle Top 5 mit PID/Name/
CPU, höchstens alle 30 Sekunden, 200 Ereignisse dauerhaft. Keine vollständige Profilierung;
sehr kurze Spitzen oder Messungen während starker Überlast können fehlen. CPU pro Prozess
kann bei mehreren Kernen über 100 % liegen. Keine Speicherung voller Befehlszeilen.

SSD-Anzeige liest SMART beim Öffnen/aktiven Aktualisieren. NVMe Percentage Used bzw.
eindeutig bekannte SATA-Lebensdauerattribute, unbekannte Werte bleiben unbekannt.
Rest-Endurance ist eine Herstellerschätzung, keine Restlaufzeit oder Ausfallgarantie.
USB-Bridges können SMART verhindern. Dashboard zeigt zuletzt gelesene Werte.

Log-Wartung zeigt die 30 größten regulären Dateien unter /var/log (bis 10.000 Einträge).
Manuelle Rotation mit Vorschau oder optionaler Wächter für bis zehn explizite root-
geschützte Dateien unter /etc/logrotate.d. Richtlinie wird vorgeprüft und gehasht;
Änderungen verlangen neue Bestätigung. Ab Schwelle mindestens 100 MiB, höchstens
stündlich je Richtlinie. Nutzt logrotate inklusive vorhandener Hooks, Komprimierungs-
und Wiederöffnungsregeln. Kein blindes truncate offener Dateien und keine selbst
erratene App-Konfiguration. Native Logrotate-Zeitpläne können unabhängig weiterlaufen.

## Echter Backup-Testrestore

Zusätzlich zur bestehenden vollständigen SHA-256-Manifestprüfung: Archiv aus einem
SQL-Bundleplan wählen und ein passendes bereits vorhandenes offizielles lokales
MySQL-/MariaDB-Image auswählen. Kein automatischer Pull. Der neue Testcontainer
verwendet genau diese Image-ID, keine Ports, Netzwerk none, keine Host-Mounts,
readonly Root-Dateisystem, begrenzte tmpfs-Ablagen, 1 GiB RAM, eine CPU und 128 Tasks.
SQL bis 512 MiB; große Datenbanken oder inkompatible Versionen können am Limit scheitern.

Das SQL wird verifiziert, neben dem Archiv temporär abgelegt, tatsächlich importiert
und die Tabellenzahl abgefragt. Keine Inhalte, Passwörter oder Client-IP werden
protokolliert. Anschließend nur der exakt neu erzeugte und markierte Testcontainer
inklusive eigener anonymer Volumes entfernt; keine bestehende Datenbank benutzt.
Bei Bereinigungsfehler nennt der Auftrag die übrig gebliebene konkrete ID. Nach hartem
Hostabbruch können temporäre Artefakte bleiben; keine pauschale Root-Bereinigung.
SQL-Import beweist keine App-Funktion, keine plattform-/versionsübergreifende Garantie
und keinen gemeinsamen atomaren Snapshot von Dateiablage und Datenbank.

## Speedtests

Debian speedtest-cli über den vorhandenen APT-Werkzeugdialog installierbar. Alternativ
bereits vorhandene offizielle Ookla-CLI. Vor jedem manuellen Start bzw. aktivierten
Zeitplan ausdrückliche Zustimmung zu Datenübertragung und ggf. Ookla-Bedingungen.
Verbindet den Server mit Testanbieter/Testserver, überträgt IP-/Netzwerkdaten und kann
viel Bandbreite verbrauchen. Anbieter können die Community-CLI blockieren; dann Fehler,
kein erfundener Messwert. Zeitplan mindestens sechs Stunden. Speichert nur Zeitpunkt,
Ping, Up-/Download und Servername, keine rohe Client-IP oder öffentliche Ergebnis-URL.

## Prüfumfang

161 lokale Tests: 157 bestanden, vier plattformbedingt übersprungen. Zusätzlich wurden
alle drei App-Vorlagen sowie 14 Variablen-/Override-Roundtrips mit dem echten Compose-
Konfigurationsparser geprüft, ohne Containerstart oder Image-Download.

Lokale Tests nutzen Testdateien und simulierte Docker-, Host- und Netzwerkaufrufe.
Browserprüfung mit deutlich markierten Demodaten. Der echte Linux-Docker-Lebenszyklus,
Registryzugriff, Speedtest, Logrotate-Hooks und SQL-Image-Start wurden hier unter Windows
nicht integriert ausgeführt. Zuerst eigene Testcontainer/Projekte verwenden. Vorhandene
Serverdaten und der alte rclone-Dienst wurden während der Entwicklung nicht verändert.
