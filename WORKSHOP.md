# ServerLotse 0.7.1 – Werkstatt und Bedienung

Die neuen Funktionen erweitern die vorhandenen Werkzeuge. Installation aktiviert
keine neue Automatik und führt keine Wartung, DNS-Änderung oder Löschung aus.
Alle Änderungen nutzen Vorschau, einmalige Bestätigung und Aktionsprotokoll.
Keine neue Python-/Node-Abhängigkeit oder ständig laufender Zusatzcontainer.

## Oberfläche

Einheitlicher Abstand unter Auswahlfeldern, zwischen Buttons und in Dialogen.
Log-Wartung und Docker-Speicherausgaben haben dunkle Konsolenflächen. Lange Pfade
umbrechen, Dateigrößen verwenden passende Einheiten. Doppelte Sicherungskategorien
werden zusammengeführt. Neue Beschriftungen sind auf Deutsch, Englisch und Spanisch.

„Rettungsmodul noch nicht aktiviert“ bezeichnet weiterhin eine fehlende optionale
Schreibablage, keinen Darstellungsfehler. Wer Kopien anlegen möchte, richtet den
separaten Rettungsordner entsprechend README/compose.recovery.yaml ein. Host- und
Systemansicht bleiben lesend; diese Version aktiviert keine unbekannte Schreibablage.

## System und Rechte

* **Zeitpläne:** liest /etc/crontab, /etc/cron.d und Benutzer-Crontabs unter
  /var/spool/cron/crontabs; zeigt außerdem systemd-Timer. Einfache Intervalle, tägliche
  und einzelne Wochentagtermine werden erklärt. Kein allgemeiner Cron-Editor. Ohne
  verlässliche Abschlussdaten bleibt das letzte Ergebnis ausdrücklich unbekannt.
* **Zombie-/Waisenradar:** Zombies sind bereits beendet und erhalten keinen Kill-Button.
  PPID 1 allein ist kein Fehler. SIGTERM nur für einzeln bestätigte Prozesse mit
  nicht mehr vorhandener Docker-Zuordnung und erneut geprüfter Prozessidentität;
  benötigt Linux pidfd-Unterstützung. Kein pauschales SIGKILL.
* **RAM-Dateicache:** einmal sync und drop_caches=3 mit Vorher-/Nachher-Werten im
  Auftragsergebnis. Keine regelmäßige Automatik, kein Versprechen über frei werdenden
  RAM. Anwendungen behalten ihren Speicher; erneute Zugriffe können langsamer sein.
* **Paket-Wartung:** simuliert APT autoremove/purge. Blockiert Kernel, Zugangsdienste,
  Systempakete und Essential/Important-Pakete. Prüft die Auswahl vor Ausführung erneut;
  APT erhält zusätzliche NeverAutoRemove-Schutzmuster. Anschließend APT-Downloadcache
  leeren. Keine alten Kernel entfernen. Währenddessen keinen zweiten Paketmanager
  starten; Paket-Skripte können Dienste beeinflussen.
* **Befehle verstehen:** erklärt wörtliche rm/chmod/chown-Eingaben und ausgewählte
  absolute Ziele. Keine Ausführung, keine Sandbox, keine vollständige rekursive
  Folgenberechnung. Shellverkettungen und Ersetzungen werden abgelehnt. Das echte
  Root-Terminal bleibt eine unabhängige, ausdrücklich freigegebene Shell.
* **Rechteübersetzer:** Lesen/Schreiben/Ausführen für Eigentümer, Gruppe und Andere
  als Checkboxen im bestehenden Dateirechte-Dialog; gezielte Änderung mit Vorschau.

## Konfiguration mit Rücknahme

Nur die root-geschützten Hauptdateien /etc/nginx/nginx.conf und /etc/ssh/sshd_config,
maximal 32 KiB. Include-Dateien bleiben unverändert. Datei zuerst laden; ein geänderter
Hash verlangt erneutes Laden. Eine private Kopie liegt unter /var/lib/serverlotse.

Vor dem Schreiben wird ein unabhängiger systemd-Rücknahmetimer angelegt. Ist dies
nicht möglich, wird nicht geschrieben. Nach Schreiben erfolgen nginx -t bzw. sshd -t,
Reload und Statusprüfung mit begrenzten Laufzeiten. Bei Fehler sofortiger Rücknahmeversuch,
sonst nach 30 Sekunden automatisch. In einem zweiten Fenster den Zugang testen und
oben im Rücknahmehinweis **Beibehalten** bestätigen. Ein laufender Auftrag kann noch
keine zweite Änderung annehmen; Vorgang im Aktionsprotokoll beobachten.

Der Timer arbeitet auch nach Browser-/Helferabbruch, solange Host und systemd laufen.
Er ist kein Backup gegen Stromausfall, Plattenschäden oder fremde Eingriffe. Verändert
jemand die Datei erneut, überschreibt die Rücknahme diese Änderung nicht blind, sondern
meldet Konflikt und erhält die Sicherung. Ein geladener, aber falsch konfigurierter Dienst
kann trotz erfolgreichem Syntaxcheck unerreichbar sein. Die 30-Sekunden-Frist ist fest.

## Notfallbremse

Roter Dashboard-Button mit Vorschau. nftables muss verfügbar sein, Installer vorhanden.
Eine bis acht **explizite Verwaltungs-IP-Adressen** angeben; hinter einem Proxy auch
dessen Quell-IP beachten. Eigene temporäre inet-/bridge-Tabellen blockieren anderen
Host-/Weiterleitungsverkehr. Vorhandene Firewallregeln werden nicht gelöscht. Eine
Freigabe setzt vorhandene Sperren nicht außer Kraft. Automatische Aufhebung nach
60 Sekunden per unabhängigem systemd-Timer; keine dauerhafte Aktivierung.

Falsche IPs können den Browser/SSH kurzfristig trennen. Keine Garantie gegen DDoS auf
der Internetleitung oder gegen einen Angreifer mit Root-Rechten. Docker-Netzwerke
werden nicht entfernt oder dauerhaft umgebaut. Separater Verwaltungszugang bleibt sinnvoll.

## Speicher

Inode-Radar im Dashboard und eigene Detailseite für lokale Dateisysteme. „Unbekannt“
bei fehlendem sinnvollen Zähler. Optionaler Wächter 50–99 %, standardmäßig aus,
nutzt vorhandenes Webhook-Ziel, frühestens stündliche Warnung. Prüft Dateieinträge,
nicht die Dateigröße; keine automatische Löschung.

## Docker

**Compose-Baukasten:** bis acht Dienste, Image, ein Host-/Container-Port, Bind-IP,
Umgebungsvariablen und ein eigener Datenordner je Dienst. Nur selbst erzeugte Projekte
mit Kennzeichnung bearbeiten; freie Compose-Dateien bleiben erhalten. JSON ist gültiges
YAML. Echter Compose-Parser prüft vor up -d. Bestehende Werte bleiben bei leerer
Variablenliste erhalten; Dollarzeichen werden wörtlich behandelt. Bestehende Datei
wird privat gesichert. Entfernte Dienste/Daten werden nicht gelöscht. Kein beliebiger
YAML-Import, Drag-and-Drop, privilegierter Container, Host-Socket oder freier Host-Mount.
Bei fehlgeschlagener Bereitstellung können Teiländerungen bestehen; Datei und Sicherung
bleiben für Prüfung erhalten. Apps und Daten separat sichern.

**Volume-Dateien:** lokale Standard-Volumes ohne Treiberoptionen. Maximal 500 Einträge
je Verzeichnis; Symlinks werden nicht verfolgt. UTF-8-Editor/Upload bis **32 KiB**,
einzelne Datei mit Vorschau und erneuter Identitäts-/Inhaltsprüfung. Bestehende Datei
wird privat gesichert, Eigentümer/Rechte bleiben erhalten. ServerLotse-eigene Volumes,
bekannte Datenbank-, .env- und Laufzeitdateinamen sind gesperrt. Dies erkennt nicht
jede denkbare App-Datendatei; keine Dateien laufender Datenbanken manuell ändern.
Keine rekursiven Uploads, kein integrierter Live-Datenbankeditor.

**Trivy:** eigener Menüpunkt und Verknüpfung am Container-Radar. Verwendet
aquasec/trivy:0.76.1 aus der offiziellen Registry und lädt die Schwachstellendatenbank
erst nach Zustimmung. Lokales Image bis 4 GiB wird exportiert, Scanner untersucht
das Archiv ohne Docker-Socket und ohne App-Volumes. Readonly-Root, eigene begrenzte
temporäre Ablage, max. 1 GiB RAM, 1 CPU, 64 Prozesse. Bericht nur nach erfolgreichem
Scanner-Exit; maximal 100 Detailbefunde. Eigener Scannercontainer wird anschließend
entfernt; bei Bereinigungsfehler konkrete ID im Protokoll. Keine blinde globale Bereinigung.
Ein fehlender Befund ist kein Sicherheitsnachweis. Nicht auf allen Architekturen getestet.

## Netzwerk

**DDNS:** optionaler Zeitplan 5–1440 Minuten, aus bei Installation. ipify ermittelt die
öffentliche IP; Domain und Adresse gehen nach Zustimmung an den gewählten Anbieter.
Cloudflare: bestehender A/AAAA-Record mit Zonen-/Record-ID und DNS-Edit-Token, nur
content per PATCH. GoDaddy: PAT mit DNS-Rechten/API-Zugang, genau ein bestehender
A/AAAA-Record; Mehrfach-Records werden nicht ersetzt. Namecheap: vorhandener Dynamic-DNS-
A-Record und separates DDNS-Passwort; kein AAAA. Keine beliebigen API-URLs oder Redirects.
Zugangsdaten bleiben privat im Host-Zustand und werden in Vorschau/Audit maskiert.
Leere Felder erhalten Werte; explizites Entfernen löscht sie. Zeitplan kann unabhängig
von unvollständigen Record-Einstellungen deaktiviert werden. Kein zweiter DNS-Client
soll denselben Record konkurrierend aktualisieren.

**Domain zum Container:** vorhandenen veröffentlichten TCP-Port wählen, DNS-Auflösung
mit erwarteter Server-IP vergleichen, vorhandenen nativen Caddy/Nginx-Assistenten nutzen.
CDN-Abweichung nur ausdrücklich zulassen. ACME-Zustimmung erforderlich. Kein Eingriff
in Nginx Proxy Manager, kein automatisches Router-Portforwarding, keine 10-Sekunden-Garantie.

**Firewall und Datenwege:** gemeinsam Listener, veröffentlichte Containerziele und echte
Regelausgaben ansehen; verknüpft vorhandenen Firewallmanager. Keine erfundene Aussage
„erlaubt/blockiert“ aus einer vereinfachten Skizze. Docker kann UFW umgehen, daher keine
vollständige Paketflusssimulation.

## Quellen und Tests

192 lokale Tests: 188 bestanden, vier plattformbedingt übersprungen. Alle eigenen
Python-/JavaScript-Dateien auf Syntax geprüft. Compose-Hauptdatei mit echtem Parser
validiert; drei zusätzliche Vergleiche für Dollarzeichen, Anführungszeichen,
Backslashes und Unicode im Baukasten. Dabei kein Container gestartet.

Browserprüfung aller 14 neuen Werkstattseiten mit Demodaten sowie Deutsch/Englisch/
Spanisch. Bei allen sechs markierten Dateiformularen 18 Pixel Feld-/Buttonabstand
gemessen. Root-Dialog und Log-Konsolenbox visuell geprüft; keine JavaScript-Fehler
in der geprüften Sitzung. Die optionale Rettungsablage bleibt wie bisher separat.

Offizielle API-/Scannerreferenzen, geprüft bei der Entwicklung:

- [Trivy Installation](https://trivy.dev/docs/latest/getting-started/installation/)
- [Cloudflare Record-PATCH](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/edit/)
- [GoDaddy Authentifizierung](https://developer.godaddy.com/en/docs/api-users/troubleshoot/authentication)
- [Namecheap Dynamic DNS](https://www.namecheap.com/support/knowledgebase/article.aspx/43/11/how-do-i-set-up-a-host-for-dynamic-dns/)

Lokale Regressionstests verwenden ausschließlich temporäre Dateien und simulierte
Host-/Docker-/Anbieteraufrufe. Browserprüfung mit klar gekennzeichneten Demodaten.
Keine echte Firewall-, DNS-, Paket-, Mount-, Dienst- oder Volume-Änderung während der
Entwicklung. Die vollständige Integration dieser neuen Root-Funktionen auf dem
Linux-Host ist noch nicht ausgeführt. Erst eigene Testprojekte und unabhängigen
Zugang verwenden. Der alte rclone-Dienst wird durch dieses Update nicht entfernt.
