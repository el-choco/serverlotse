# Änderungen

## 0.7.5 – Quelltext bereinigt

- Kommentare und Docstrings aus Python, JavaScript, CSS, Shell-Skripten, Compose-,
  Docker- und Konfigurationsdateien entfernt; Drittanbieterdateien unter static/vendor unverändert.
- Keine Funktionsänderung gegenüber 0.7.4; bestehende .env behalten.

## 0.7.4 – Öffentliche und interne Dateien getrennt

- .gitignore: interne Notizen (IDEAS.md, VALIDATION-*.md) sowie ZIP- und Prüfsummendateien
  werden nicht ins Repository übernommen.
- .dockerignore: Dokumentation und Screenshots bleiben aus dem Docker-Build-Kontext.
- README verlinkt nur noch öffentliche Dokumente.
- Keine Funktionsänderung gegenüber 0.7.3; bestehende .env behalten.

## 0.7.3 – GitHub-README

- Neue README für GitHub: alle Funktionen nach Kategorien mit Icons, Schnellstart,
  .env-Übersicht, Sicherheitsmodell, Architekturdiagramm und Projektstruktur.
- Sechs Demo-Screenshots unter docs/screenshots.
- Keine Funktionsänderung gegenüber 0.7.2; bestehende .env behalten.

## 0.7.2 – Navigation, Root-Lesen und ruhige Live-Ansichten

- Breadcrumbs Übersicht / Kategorie / Werkzeug; eigene Kategorieübersichten.
- Speicher untersuchen wieder in Dateiverwaltung; Footer überall entfernt.
- Einheitlicher Ordnerdialog mit Breadcrumbs, Pfadeingabe, Filter und expliziter Auswahl.
- Container-Radar aktualisiert Messwerte in vorhandenen Elementen, ohne Formulare,
  Buttons oder Seiteninhalt neu aufzubauen; Abruf alle fünf Sekunden, pausierbar.
- Temperaturkacheln, lesbare Netzwerkzeilen, dynamische Datenrateneinheiten und
  aufklappbare virtuelle Schnittstellen; Proxy-Link/Button sauber getrennt.
- Main-Container explizit UID 0 und DAC_READ_SEARCH für geschützte lokale Ordner;
  Host-/System-Mounts bleiben schreibgeschützt, Dateirechte werden nicht verändert.
- Temporärer dateibasierter SQLite-Index statt Scan-Abbruch bei 250.000 Einträgen;
  kleine RAM-Caches, begrenzte Ergebnislisten, eigene Scan-Cache-Ablage.
- Einheitliches Erscheinungsbild: ruhigere Seitenleiste mit Aktivmarkierung, fixierte
  Kopfzeile, Karten mit leichten Schatten, Hover-/Fokuszustände, einheitliche Buttons,
  Auswahlfelder, Tabellenköpfe und aufklappbare Bereiche; nur CSS, keine Logikänderung.
- Eigenes Linien-Icon-Set für alle Menüpunkte, Kategorien und Kategoriekacheln; Menü als Baumstruktur
  mit animierten Aufklapp-Chips statt Textpfeilen, auch im Ordnerdialog.
- Laufende Aktionen (z. B. „Verwaltungsaktion läuft …“) überall mit Spinner und Hervorhebung.
- Cronjobs (vorher Zeitpläne im Überblick): neue Aufträge als Cron-Eintrag oder als systemd-Dienst
  mit Timer anlegen, optional sofort starten, selbst angelegte Aufträge wieder entfernen.
- Paket-Wartung erklärt Ergebnis und geschützte Pakete verständlich statt als JSON;
  Log-Wartung-Tabelle wieder gut lesbar.
- Versionssprung nur von 0.7.1 auf 0.7.2; bestehende .env behalten.
- 199 lokale Tests: 195 bestanden, vier Plattform-Skips; großer synthetischer Testbestand mit 250.005 Einträgen und Live-Radar im Browser geprüft. Details in VALIDATION-0.7.2.md.

## 0.7.1 – Oberfläche und Server-Werkstatt

- Einheitliche Formular-/Buttonabstände und gestalteter Root-Bestätigungsdialog.
- Dunkle Log-/Docker-Ausgaben, umbrechende Pfade und passende Dateigrößeneinheiten.
- Doppelte Sicherungskategorie zusammengeführt; Docker bleibt eigenständige Kategorie.
- Cron-/Timerübersicht, Zombie-/Waisenradar, Cache-Vergleich, APT-Wartung und Befehlsanalyse.
- Rechtecheckboxen, Inode-Dashboard und opt-in Inode-Wächter.
- Konfigurationseditor für Nginx/SSH mit unabhängigem 30-Sekunden-Rücknahmetimer.
- Temporäre Notfall-Netzsperre mit expliziten IP-Ausnahmen und Freigabe nach 60 Sekunden.
- Eigener Compose-Baukasten, begrenzter Volume-Dateieditor und isolierter Trivy-Scanner.
- Opt-in DDNS für Cloudflare/Namecheap/GoDaddy und Domain-/Firewallübersicht.
- DE/EN/ES ergänzt, neue Funktionen zunächst inaktiv; Umfang und Grenzen in WORKSHOP.md.
- Kein manueller Installer erforderlich; bestehende .env behalten.
- 192 lokale Tests: 188 bestanden, vier Plattform-Skips. Neue Linux-Integration noch nicht auf einem echten Host geprüft.

## 0.7.0 – Docker-Werkzeuge und Diagnosewächter

- Docker nur noch in eigener Kategorie, einschließlich Dashboard.
- Container-Radar mit Verlauf/Health, Kloner und Nginx-/WordPress-/Nextcloud-Vorlagen.
- Maskierter Env-/Config-Inspektor, root-geschützte Compose-Overrides und .env-Editor.
- Filterbare Netzwerk-Node-Map und passive plattformspezifische Registryprüfung.
- Erweiterter manueller Janitor mit konkreten Zielen und LOESCHEN; keine neue nächtliche Volume-Löschung.
- Login-/Terminal-Sitzungen, FIM-Vergleichsbasis, Zertifikatsablauf, bestätigte OOM-Ereignisse.
- Unabhängige CPU-Spitzen-Stichproben, vorsichtige SMART-Endurance-Auswertung.
- Echte SQL-Testimporte in isolierten begrenzten Wegwerf-Containern.
- Vorhandene Logrotate-Richtlinien und manuelle/geplante HTTP-/Speedtests.
- Neue Automatiken aus, vorhandene Einstellungen erhalten; bisherige Funktionen wiederverwendet.
- DE/EN/ES erweitert. 161 Tests: 157 bestanden, vier übersprungen; 17 zusätzliche Compose-Parserprüfungen.
- Neue Linux-/Docker-Integration noch nicht vollständig getestet.

## 0.6.1 – interaktives Host-Terminal (Docker-Start korrigiert)

- Unix-Zeilenumbrüche für Shellskripte und systemd-Dateien; Release-Test verhindert CRLF-Rückfälle.
- Ausdrücklich freigegebener einmaliger Compose-Start-Helfer richtet native Dienste automatisch ein.
- Unveränderte Helfer bleiben aktiv; Socket-Verzeichnis bleibt bei Neustarts erhalten.
- Linux-PTY und interaktive Bash direkt auf dem Host, ohne SSH oder SSH-Key.
- Lokal mitgeliefertes xterm.js 6.0.0 / addon-fit 0.11.0, Größenanpassung und Vollbild.
- Einmalige ROOT-Bestätigung, an Anmeldung gebundene Sitzungen, Idle-/Verbindungszeitlimits.
- Begrenzter Ausgabepuffer; nur Öffnen/Schließen protokolliert, keine Befehle oder Ausgabe.
- CSP-Nonce für xterm-eigene Styles; keine allgemeine Freigabe für Inline-Styles.
- 131 Tests: 127 bestanden, vier plattformbedingt übersprungen. Linux-PTY/Bash noch nicht integriert getestet.

## 0.6.0 – ausdrücklich freigegebene Verwaltung und Automatik

- Freie nicht interaktive Root-Befehlskonsole, bestätigte UFW-Regeln und einzelne Volume-Löschung mit LOESCHEN.
- Alte dangling Images/Cache bereinigen; opt-in nächtliche Pflege ohne Volume-/Containerlöschung.
- Opt-in Benachrichtigungen per Discord/Telegram/HTTPS, Grenzwerte und persistente Sendepausen.
- Ausgewählte Dienste-/Container-Heiler mit Fehlerchecks, manueller Sperre und Wiederanlaufgrenzen.
- Nächtliche APT-Sicherheitsupdates ohne automatische Reboots; feste Werkzeugpakete über APT installierbar.
- .tar.gz-Dateisicherungen mit optionalem MySQL-/MariaDB-Export und SFTP-/S3-Upload; lokale Sicherung bleibt bei Uploadfehler erhalten.
- Getrennte root-geschützte Remote-Profile, vorhandene rclone-Dienste bleiben unverändert.
- Native Proxy-/TLS-Einrichtung mit ACME-Zustimmung, Validierung und Rücknahmepfad; kein Eingriff in Nginx Proxy Manager.
- Rechte/Gruppe vorhandener Konfigurationen erhalten; Backup-UUID-Vergleich übersteht geänderte Gerätenamen.
- Keine echte Root-/Netzwerkaktion bei Entwicklungstests; Linux-Integration noch unvollständig getestet.
- 114 lokale Tests: 110 bestanden, 4 plattformbedingt übersprungen.

## 0.5.1 – Live-Monitoring und lesende Sicherheitsdiagnose

- CPU pro Kern, RAM/Swap, Temperaturen und Netzwerk mit einer Stunde Messverlauf im Host-Helfer.
- Sortierbare Prozessliste, Live-Logende mit Filter und Pause; begrenzte Aktualisierung nur auf sichtbaren Seiten.
- SSH-Standardkonfiguration, UFW/iptables/nftables und fail2ban-Jails lesend prüfen.
- Nicht referenzierte Docker-Volumes und dangling Images anzeigen; keine Löschaktion.
- Feste Diagnosebefehle statt freier Shell; Caddy-/Nginx-Vorlagengenerator ohne Installation.
- Dienst-Startzeiten und Container-Logs direkt in der Verwaltungsübersicht.
- Kein zusätzlicher Container, keine Python- oder Node.js-Abhängigkeiten.
- 81 lokale Tests: 77 bestanden, 4 plattformbedingt übersprungen.
- Veränderte Root-Aktionen und externe Übertragungen bleiben aus; Funktionsmatrix in IDEAS.md.

## 0.5.0 – Diagnose und Host-Verwaltung

- Systemzustand, geführte Diagnose, Dienste und Autostart, APT-Updates.
- Laufwerke, SMART, benannte Mounts mit optionalem fstab-Eintrag und normales Unmount.
- Containersteuerung und Ressourcen; Netzwerk-, DNS- und TCP-Diagnose.
- Normale Benutzer/Gruppen sowie gezielte Rechteänderungen mit ACL-Anzeige.
- Geplante TAR-Dateisicherungen, SHA-256-Prüfung, separate Wiederherstellung.
- Lokaler root-Helfer über authentifizierten Unix-Socket, ohne TCP-Port oder Shell.
- Einmalvorschauen, Zustandsprüfung, serialisierte Änderungen, dauerhafter SQLite-Verlauf.
- Neue Kategorien, Hilfen und DE/EN/ES-Oberfläche mit sicherer Demo.
- 65 lokale Tests: 61 bestanden, 4 plattformbedingt übersprungen.
- Echte Linux-Hostintegration unter Windows ungeprüft; Details in ADMINISTRATION.md.

## 0.4.0 – Kategorien und Host-Steuerung

- Native Ordner-Dropdowns an allen nachgerüsteten Stellen, gleiche 48-Pixel-Höhe wie Ansichtsfelder.
- Sidebar-Hinweis entfernt; Sidebar und Dashboard nach Dateiverwaltung/System gruppiert.
- Neustart/Shutdown mit expliziter Bestätigung, kurzlebiger Einmalfreigabe und Sperre bei laufenden ServerLotse-Aufgaben.
- Authentifizierter interner Host-Vermittler mit festen logind-Aufrufen; keine öffentliche Portfreigabe.
- Einmaliger Installer für die persistente schreibgeschützte Systemansicht; Reboot erst nach Boot-Einrichtung.
- 42 Tests: 39 bestanden, 3 plattformbedingt übersprungen. Host-Aktionen nur mit Test-Doubles, kein echter Reboot/Shutdown ausgeführt.

## 0.3.0 – Sprachen und Anmeldung

- Gemeinsamer Übersetzungskatalog für Deutsch, Englisch und Spanisch; Sprachauswahl im Browser gespeichert.
- Übersetzte Oberfläche, Ordnerauswahl, Ergebnisbeschriftungen und bekannte Diagnosemeldungen. Pfade und originale Logzeilen bleiben unverändert.
- Einmalige Token-Anmeldung mit optionaler 30-Tage-Sitzung statt wiederholter Token-Eingabe.
- Signierte HttpOnly-/SameSite-Strict-Cookies, standardmäßig Secure für HTTPS. Kein Token in Seitencode oder localStorage.
- Abmelden, Ablauf und Tokenrotation, Loginbegrenzung und Originprüfung für POST.
- 33 Tests: 30 bestanden, 3 wegen Windows-/Linux-Plattformgrenzen übersprungen. Browser-Anmeldung, Wiederanmeldung, Abmeldung sowie Sprachwechsel und gespeicherte Sprache geprüft.

## 0.2.1 – Ordnerauswahl

- Aufklappbare Auswahl echter Serverordner in allen Pfadfeldern, getrennt nach Host- und Systemansicht.
- Pfadleiste, Ordnerfilter, Auswahlbestätigung, Abbrechen und Escape.
- Auswahl unabhängig von Prüfjobs, responsive Positionierung des Auswahlfensters.
- Pfad-Schnellwahlbuttons und die drei markierten Einführungstexte entfernt.
- Drei zusätzliche Tests für Ordnerauflistung und Pfadgrenzen; Navigation und Vergleich im Browser geprüft.

## 0.2.0 – Werkzeugkiste

- Elf zusätzliche Werkzeugseiten: Dateibrowser, große Dateien, Dateitypen, Suche, Duplikate, Systemdiagnose, Dateisystemzuordnung, Docker, Logs, Rettungskopien und Prüfleitfäden.
- Aufgabenfortschritt, Abbruch und Verlauf mit Wiederanzeige nach Browseraktualisierung.
- JSON- und CSV-Export; Tabellen mit horizontalem Scrollen und Dateibrowser-Navigation.
- Optionaler Docker-Vermittler mit zwei fest definierten Leseendpunkten.
- Optionaler Kopierplan mit ausdrücklicher Bestätigung, Ablaufzeit und geprüfter Kopie in einen getrennten Zielordner.
- Zieloperationen beim Kopieren unter Linux über Verzeichnisdeskriptoren; kein Überschreiben, kein Löschen.
- Lokale Logauswertung für Platzmangel, Berechtigungen, Redis, systemd, DNS, Proxy-Timeouts und Rclone-Sperren.
- Socket-Timeouts, begrenzte Eingaben und maskierte typische Geheimnisse in Logbefunden.
- 19 Tests, davon 4 auf dem Windows-Netzlaufwerk übersprungen; isolierter Linux-Testcontainer vorbereitet.

Noch keine Freigabe als fertig geprüftes Community-Release. Docker-Integration und Linux-Schreiboperationen benötigen Prüfung auf Linux.

## 0.1.0

Speicherübersicht, verdeckte Systemdaten und einseitiger SHA-256-Dateivergleich.
