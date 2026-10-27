# ServerLotse 0.7.0 – freigegebene Verwaltung

Neue Werkzeuge ab 0.7: [WORKBENCH.md](WORKBENCH.md).

Diese Version ergänzt die am 25.10.2026 ausdrücklich freigegebenen Funktionen.
Beim Installieren wird **keine Automatik eingeschaltet**, kein Webhook versendet,
kein Zertifikat beantragt und keine Sicherung hochgeladen. Das Update entfernt
oder verändert den alten rclone-gdrive.service nicht.

## Installation / Update

ZIP über die bisherigen Projektdateien kopieren, die eigene .env behalten.
Bei abgeschlossenen ServerLotse-Aufgaben:

```sh
cd /mnt/intenso2tb/serverlotse
docker compose up -d --build
```

Bei erster Installation .env aus .env.example anlegen und Token/Bind-IP setzen.
Strg+F5 im Browser. Port 18099 und Reverse Proxy bleiben erhalten.

Der ausdrücklich freigegebene einmalige host-bootstrap-Container benötigt privileged
und pid: host. Er betritt mittels nsenter die Host-Namensräume und führt dort Python
für die festen ServerLotse-Installationspfade aus: /usr/local/lib/serverlotse,
/etc/systemd/system/serverlotse-{admin,view}.service und /etc/serverlotse/admin.token.
Keine .env wird als Shellskript ausgewertet. Vorhandene Pfade müssen root-geschützt
und frei von Symlinks sein. Neue Dateien werden atomar ersetzt; vollständige Updates
mehrerer Dateien sind kein gemeinsamer atomarer Vorgang. Der Helfer startet nach einer
Bereitschaftsprüfung, dann beendet sich der Start-Container. Exitcode 0 ist normal.

Bei identischem Paket wird der laufende Host-Helfer nicht neu gestartet. Geänderte
Pakete warten auf freie Aufgaben und geschlossene Terminals; sie brechen andernfalls
mit einem Hinweis ab. Logs: docker compose logs --tail 60 host-bootstrap.
Der Host-Dienst und die Systemansicht bleiben für Reboots eingerichtet, auch nach
Compose down. Der Socket-Ordner bleibt bei Dienstneustarts bestehen, damit bestehende
Container-Bind-Mounts gültig bleiben. Keine manuellen Installationsbefehle mehr nötig.
Die alten Installer bleiben nur für die bisherige manuelle Betriebsart enthalten.
Kein Node.js/npm oder pip auf dem Host erforderlich. Der Container benötigt util-linux;
der Host systemd, Python 3.9+, Bash und rootful Docker. Nicht für Swarm oder Desktop.

Der Token gewährt jetzt auch **freie Root-Befehle**. Alle bisherigen Token- und
Sitzungsinhaber erhalten diese Funktionen nach dem Update. Es gibt keine getrennten
Benutzerrollen. HTTPS beibehalten, Token wie einen Root-Zugang behandeln. Noch
kein externes Sicherheitsaudit, keine geprüfte öffentliche Community-Version.

## Interaktives Root-Terminal (0.6.1)

System → Root-Konsole → Terminal öffnen. Einmal ROOT bestätigen. Danach werden
Tastatureingaben direkt als root auf dem tatsächlichen Host ausgeführt; es gibt
keine Vorschau je Befehl. Kein SSH, kein SSH-Key und kein neuer öffentlicher Port.
Die vorhandene Anmeldung und HTTPS-Verbindung schützen den Zugang. Voraussetzung:
Linux, /bin/bash, /dev/pts und aktualisierter Host-Helfer. Kein Terminal im Docker-Container.

Unterstützt interaktive Programme wie nano, htop und dietpi-config, Tab,
Pfeiltasten, Strg+C sowie Einfügen über die normale Browserfunktion. cd und
Shell-Variablen bleiben in dieser Sitzung erhalten. Vollbild und Ziehen am unteren
Rand ändern die Terminalgröße. Programme müssen auf dem Host installiert sein.

Sitzung schließen hängt das Terminal aus und beendet die Shell. Nach exit zuerst
Sitzung schließen, dann erneut öffnen. Beim Abmelden wird die Sitzung geschlossen;
beim Tab-Schließen versucht der Browser das ebenfalls. Als Rückfallebene beendet
der Helfer Sitzungen nach 60 Sekunden ohne Browserabfrage, nach 15 Minuten ohne
Eingabe oder spätestens nach vier Stunden. Browser im Hintergrund oder schlafende
Geräte können die Verbindung unterbrechen. Maximal zwei Sitzungen gleichzeitig;
eine Sitzung wird nicht nach einem Browser-Neuladen wieder aufgenommen.

Hintergrundprozesse, nohup und eigenständig gestartete Dienste können das Schließen
überleben. Eine Terminal-Sitzung sperrt andere Verwaltungsaktionen nicht; deshalb
keine widersprüchlichen Arbeiten parallel ausführen. Vor Updates des Host-Helfers
alle Terminals schließen. Neustart des Helfers beendet dessen Shells.

ServerLotse speichert nur Öffnen/Schließen im Aktionsprotokoll, keine Befehle und
keine Terminalausgabe. Der Ausgabepuffer ist auf 512 KiB je Sitzung begrenzt;
bei Überlauf wird die Darstellung zurückgesetzt. Die Shell startet mit HISTFILE=/dev/null,
aber eigene Shell-Profile und Systemwerkzeuge können unabhängig davon protokollieren.
Ausgabe wird unverändert an das berechtigte Browserfenster übertragen und nicht
maskiert. Terminal-Steuersequenzen erhalten keinen Zugriff auf die Browser-Zwischenablage.

Die Konsole kann Schutzgrenzen aller strukturierten Module umgehen. Der
ServerLotse-Token ist damit ein Root-Zugang. Die bisherige einzelne shell_run-API
bleibt für Kompatibilität verfügbar; die Oberfläche verwendet das neue Terminal.
Terminaldarstellung: lokal mitgeliefertes xterm.js 6.0.0 und addon-fit 0.11.0.
Kurze authentifizierte HTTP-Abfragen statt zusätzlicher WebSocket-/SSH-Ports.
CSP erlaubt nur die mit einem zufälligen Seitennonce markierten xterm-Stylelemente.

Prüfstand: Sitzungsregeln und HTTP-Schutz lokal getestet, xterm-Darstellung im Browser
geprüft. Hier steht kein laufender Linux-Docker-Host zur Verfügung; der echte PTY-/Bash-
Start und interaktive DietPi-Programme sind noch auf einem Linux-Testhost zu verifizieren.

## Prozessaktionen

Die Prozessübersicht bietet für normale Benutzerprozesse Beenden, Pausieren,
Fortsetzen und Erzwingen, jeweils mit Vorschau. Root-, System- und Zugangsprozesse
bleiben in dieser Maske geschützt. Linux/Python müssen pidfd unterstützen; vor
dem Signal werden PID, Startzeit und UID erneut geprüft, um wiederverwendete PIDs
nicht versehentlich zu treffen. Erzwingen kann ungespeicherte Arbeit verlieren.
Ein angenommenes Signal beweist keinen abgeschlossenen Prozesszustand.

## Docker aufräumen

Manuelle Bereinigung entfernt nur dangling Images und unbenutzten Build-Cache,
die älter als sieben Tage sind. Keine gestoppten Container, Netzwerke oder Volumes.
Docker bietet hierfür keine vollständige exakte Dry-Run-Platzberechnung; der
Hinweis in der Vorschau benennt die Auswahlregeln.

Ein Volume wird einzeln aus der Liste nicht referenzierter Volumes ausgewählt.
Vor Ausführung wird seine Nutzung erneut geprüft. Die Bestätigung lautet
**LOESCHEN**. Docker wird ohne Force-Option zur Volume-Löschung aufgerufen und
weist inzwischen angehängte Volumes ab. Unreferenziert bedeutet nicht leer:
Alte Datenbanken oder Nextcloud-Dateien können genau dort liegen. Keine Wiederherstellung
über ServerLotse nach endgültiger Volume-Löschung.

Es gibt keinen pauschalen nächtlichen system-prune mit --volumes. Die aktivierbare
Nachtpflege betrifft ausschließlich alte Images und Cache, einmal pro lokalem
Kalendertag während der gewählten Stunde. Verpasste Stunden werden nicht nachgeholt.
Die Tagesmarkierung bleibt beim Neustart erhalten. Eine gescheiterte Pflege ist
im Aktionsprotokoll sichtbar.

## Firewall

Sicherheit → Firewall-Regeln. UFW muss bereits aktiv sein. Einfachen TCP-/UDP-Port
freigeben oder seine einfache allow-Regel entfernen. Vorschau nutzt ufw --dry-run.
Kein automatisches Aktivieren von UFW, kein Flush/Reset, keine Änderung direkter
iptables-/nftables-Regeln. SSH-Ports aus sshd -T sowie 22, 23, 443 und 18099 werden
gegen Entfernen der Freigabe geschützt. Die freie Root-Konsole hat diese Begrenzung nicht.

Andere UFW-Regeln, NAT und Docker-Publishing können den Port weiter erreichbar
machen. Eine entfernte allow-Regel beweist keine Sperre. Ein externer Test von
einem anderen Anschluss bleibt erforderlich; Erreichbarkeit vom Server selbst
ist kein unabhängiger Internet-Messpunkt.

## Automatik und Webhooks

Automatik → Automatik und Meldungen. Hauptschalter zunächst aus. Einzelne
CPU-/RAM-Warnungen, SSH-Radar, Auto-Heiler-Ziele und Nachtpflege auswählen.
Konfigurationsvorschau zeigt keine Zugangstokens. Leere Geheimnisfelder behalten
vorhandene Werte; das explizite Löschfeld entfernt Benachrichtigungsdaten.

Discord, Telegram oder ein generischer HTTPS-Webhook sind möglich. Telegram
benötigt Bot-Token und numerische Chat-ID, Discord eine offizielle Webhook-URL.
HTTPS wird geprüft, Weiterleitungen werden nicht verfolgt. Discord-Erwähnungen
sind deaktiviert. Generische Ziele erhalten JSON mit message und source.

Testnachricht ist eine eigene bestätigte Aktion und funktioniert auch bei
abgeschalteter Automatik. Der Versand übermittelt den Hostnamen. Automatische
Warnungen enthalten Messwerte bzw. SSH-Fehlermeldungszahlen; keine vollständigen
Logs, Quell-IP-Listen oder lokalen Dateien. Speicherung in der root-geschützten
SQLite-Datenbank, ohne zusätzliche Verschlüsselung. Geheimnisse nicht im Browser
vorbefüllt und nicht im Protokoll gespeichert. Versandfehler nennen keine geheime URL.

CPU/RAM müssen den Grenzwert für die gewählte Dauer überschreiten. Eine persistente
Sendepause schützt vor Wiederholungen, auch nach Neustart. Fehlgeschlagene Sendungen
pausieren ebenfalls. Unbekannte/veraltete Sensorwerte lösen keine Auslastungswarnung aus.

Das SSH-Radar liest passende sshd-/dropbear-Journalmeldungen der letzten Minute.
Es zählt Failed-password-/Bad-password-Meldungen, keine bewiesenen Einbrüche.
Es muss entsprechende Journalmeldungen geben; keine vollständige Angriffserkennung.
Ein Fenster mit mehr als 1.000 Meldungen wird begrenzt ausgewertet.

### Auto-Heiler

Nur explizit gewählte Container oder Dienste. Etwa jede Minute prüfen, erst nach
zwei Fehlerprüfungen neu starten, mindestens fünf Minuten Abstand, maximal drei
Versuche pro Stunde und Ziel. Container benötigen entweder einen fehlerhaften
Exit oder einen vorhandenen Docker-Healthcheck mit unhealthy. Pausierte Container
werden nicht gestartet. Dienste müssen failed sein; inactive allein genügt nicht.

Ein ServerLotse-Stop setzt eine dauerhafte Heiler-Sperre. Docker-Stop-Ereignisse
und typische Stop-Exitcodes werden berücksichtigt. Wenn die Absicht nicht geprüft
werden kann, wird konservativ nicht gestartet. Die Erkennung fremder Stopps ist
keine vollständige Garantie. Auto-Heiler-Status zeigt Sperren und Versuchszeiten;
Zurücksetzen ist eine eigene bestätigte Aktion. Geschützte Zugangsdienste und
eigene Container werden weiterhin durch die strukturierten Module abgewiesen.

## Nacht-Updates

System → Update-Zeitplan. Unterstützt APT/systemd auf Debian, DietPi, Ubuntu.
Benötigt das Hostpaket unattended-upgrades; die Oberfläche bietet dessen gezielte
Installation mit APT-Simulation an. Weitere feste Werkzeugpakete können über die
entsprechenden angebotenen Masken installiert werden; keine frei eingegebenen Paketnamen.

ServerLotse schreibt eine eigene Sicherheitsquellen-Richtlinie unter
/etc/apt/apt.conf.d/99serverlotse-security und einen Timer-Drop-in für
apt-daily-upgrade.timer. Vorherige eigene Richtlinie wird gesichert. Die Uhrzeit
ist Host-Zeit. Automatische Reboots sind ausgeschaltet. Paket-Skripte können
Dienste trotzdem neu starten. Später geladene fremde APT-Konfigurationen können
die Richtlinie überschreiben. Das Abschalten setzt Unattended-Upgrade auf 0.

Der APT-Timer arbeitet unabhängig vom ServerLotse-Auftragsmutex. APT besitzt eigene
Paketmanager-Sperren; Sicherungen und Wartungsfenster sinnvoll getrennt planen.
Unterbrochene Installationen können manuelle Paketmanager-Reparatur benötigen.

## Komprimierte Datei-, Datenbank- und Remote-Backups

Backups → Datenbank- und Remote-Backup. Zwei getrennte vorhandene Ordner wählen.
Das Ziel und seine Eltern müssen root gehören und dürfen für Gruppe/andere nicht
beschreibbar sein. Name, optionaler Zeitplan, Datenbankcontainer und Remote wählen.
Eine bestätigte Aktion speichert einen neuen Plan und führt die erste Sicherung aus.
Pläne lassen sich danach über die normale Sicherungsseite pausieren und erneut starten.

Optionaler MySQL-/MariaDB-Export liest das Passwort aus vorhandenen Variablen
MYSQL_ROOT_PASSWORD/MARIADB_ROOT_PASSWORD oder MYSQL_PASSWORD/MARIADB_PASSWORD
im gewählten Container. Bei Benutzer root werden die Root-Variablen verwendet.
_FILE-Secrets und PostgreSQL werden noch nicht unterstützt. Dump-Werkzeug muss
im Container vorhanden sein. Passwort nicht in argv oder ServerLotse-Logs.

single-transaction liefert einen logischen Snapshot transaktionaler Tabellen,
keinen atomaren Gesamtzustand aus Appdateien und Datenbank. Nicht transaktionale
Tabellen brauchen ein separates Konsistenzverfahren. Für einen konsistenten
Anwendungsbackup vorher Wartungsmodus/Anhalten oder anwendungseigene Exporte nutzen.

SQL-Temporärdaten liegen im gewählten Sicherungsziel, nicht pauschal auf der SSD.
Zusätzlich werden vorübergehend TAR und komprimiertes Archiv benötigt. Platzmangel
bricht ab. Datenbankexport hat 15 Minuten, Upload zwei Stunden Zeitlimit. Ein
abgebrochener docker-exec kann im Container noch laufen; dort vor Wiederholung prüfen.

Das .tar.gz enthält SHA-256-Manifest und gegebenenfalls
__serverlotse_database__/DATENBANK.sql. Nach lokaler Inhaltsprüfung wird nur das
eigene Zwischen-TAR entfernt. Ein Uploadfehler behält das fertige lokale Archiv und
markiert den Auftrag als Fehler. Zeitpläne versuchen nicht in einer engen Schleife
neu. Es gibt keine automatische Archivlöschung. Archive sind nicht verschlüsselt.

Rclone copyto --immutable lädt genau die fertige Datei hoch, ohne Remote-Dateien
zu löschen oder abweichende vorhandene Dateien zu überschreiben. Der normale
rclone-Transfercheck ist kein unabhängiger vollständiger Remote-Restore-Test.
Das Remote-Ziel kann zusätzliche Speicherkosten verursachen.

Lokale .tar und .tar.gz lassen sich über die Sicherungsseite gegen das Manifest
prüfen und in einen neuen privaten Unterordner wiederherstellen. SQL wird dabei
als Datei abgelegt; kein automatischer Import über eine laufende Datenbank.
Leere Ordner, ACLs, Eigentümer, Links und weitere Dateisysteme werden weiterhin
nicht gesichert. Maximal 250.000 Dateien/32 MB Manifest pro Plan.

### SFTP / S3

Remote-Profile liegen separat unter /etc/serverlotse/remotes.conf, root:root 600.
Neue Namen beginnen mit serverlotse_. Vorhandene Profile werden nicht überschrieben.
Beim Speichern wird diese Datei für neue ServerLotse-Uploads ausgewählt; bereits
bestehende Sicherungspläne behalten ihre gespeicherte Konfigurationsdatei.

SFTP nutzt vorhandenen privaten SSH-Schlüssel und known_hosts. Beide Dateien
müssen root gehören und geschützt liegen, der private Schlüssel etwa Modus 600.
Verschlüsselte Schlüssel mit interaktiver Passphrase werden nicht unterstützt.
Fingerabdrücke mit dem Remote-Betreiber prüfen; unbekannte Schlüssel werden nicht
blind übernommen. S3 nutzt Access-Key, Secret-Key, Region und optionalen HTTPS-
Endpunkt (z. B. kompatibler Anbieter). Nur root-lesbare Konfiguration, keine zusätzliche
Verschlüsselung der Zugangsdaten.

Vorhandene andere rclone.conf kann optional gewählt werden, muss aber root-geschützt
sein, einschließlich ihrer Elternordner. Alte Dateien in allgemein beschreibbaren
Ordnern werden nicht automatisch umberechtigt oder importiert. Bestehende Syncs und
der alte Google-Drive-Mount bleiben unverändert.

## Proxy und TLS

Netzwerk → Proxy einrichten. Native Caddy- oder Nginx-Installation auswählen.
Caddyfile muss root gehören und gegen fremde Schreibzugriffe geschützt sein.
Bestehende Domain wird nicht überschrieben. Caddy-Kandidat wird geprüft, bestehende
Datei gesichert, Rechte/Gruppe erhalten und der Dienst neu geladen. Bei Reloadfehler
wird die vorherige Datei wiederhergestellt. Zertifikate beantragt Caddy asynchron;
der erfolgreiche Reload beweist noch keine erfolgreiche Zertifikatsausstellung.

Nginx benötigt das sites-available/sites-enabled-Schema und APT-Certbot mit
certbot.timer. Neue eigene Domain-Datei mit ACME-Webroot, nginx -t, Reload,
Certbot-Zertifikat, TLS-Konfiguration, erneuter Test/Reload und Renewal-Hook.
Bei Fehlern werden nur die neu erzeugten eigenen Nginx-Dateien zurückgenommen;
eventuell ausgestellte Zertifikate bleiben bestehen. Fremde Dateien/Hooks werden
nicht überschrieben. Portkonflikte mit Docker-Proxys vorher klären.

ACME-Nutzungsbedingungen und öffentliche Domainprotokollierung müssen explizit
bestätigt werden. Keine Zertifikate wurden während der Entwicklung angefordert.
Nginx Proxy Manager wird nicht über seine API oder Konfigurationsdateien verändert.
Wenn er dein aktiver Proxy ist, Domains weiter dort anlegen; der native Assistent
ist dann nicht der passende Weg auf demselben Port.

## Prüfung, Deaktivieren und Downgrade

Geprüft werden lokal unter anderem Preview/Einmalbestätigung, Löschwort, Argument-
Allowlist, Geheimnisfilter, Heiler-Grenzen, Proxy-Dateirücknahme, gzip/SQL-Restore,
Dateirechte-Erhalt und Uploadfehler mit lokaler Sicherung. Externe Aufrufe werden
in Tests ersetzt. Es wurde nichts am DietPi ausgeführt oder gesendet.

Echte Linux-Integration von APT/UFW/Proxys, Zertifikaten, Docker-Dumps, Remote-
Uploads und Host-Sensoren konnte ohne Linux-Docker-Engine hier unter Windows nicht
vollständig getestet werden. Entwicklungsversion; zuerst entbehrliche Testdaten,
Testdomain und Testvolume verwenden. Kein formales Sicherheitsaudit.

Automatik-Hauptschalter aus stoppt neue Alert-/Heil-/Pflegeaktionen. Bereits
laufende Aufgaben laufen weiter. Unattended-Upgrades zusätzlich über den eigenen
Update-Zeitplan deaktivieren; dieser Timer arbeitet eigenständig.
Vor Downgrade auf 0.5.x alle neuen komprimierten Sicherungspläne pausieren und die
Automatik abschalten. Alte Helfer verstehen deren Datenbank-/Remote-Erweiterungen nicht.

Quellen: [Debian-Sicherheitsrichtlinie](https://sources.debian.org/src/unattended-upgrades/2.12/data/50unattended-upgrades.Debian/),
[Rclone copyto](https://rclone.org/commands/rclone_copyto/),
[SFTP-Hostschlüssel](https://rclone.org/sftp/),
[Caddy-Konfiguration](https://caddyserver.com/docs/command-line).
