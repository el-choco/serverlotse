# Basisverwaltung in ServerLotse 0.6

Aktuelle Installation: UPDATE.md. Compose richtet den Host-Helfer automatisch über host-bootstrap ein. Neue Root-Konsole, Automatik, Remote-Backups und
Proxy-Einrichtung: OPERATIONS.md. Diese Datei beschreibt die ursprünglichen
strukturierten Werkzeuge. Ihre Schutzgrenzen gelten nicht für freie Root-Befehle.

## Dateien und Datenträger

Host-/Systemansicht der Dateidiagnose bleiben im Webcontainer schreibgeschützt.
Die Systemansicht zeigt mit nichtrekursivem Bind-Mount verdeckte Dateien unter
Einhängepunkten. Andere Dateisysteme und Links werden bei Inventur übersprungen,
Lesefehler und Grenzen angezeigt. SHA-256-Vergleich prüft Quelldateien im Ziel,
nicht zusätzliche Zieldateien. Daraus allein keine Löschfreigabe ableiten.

Der lokale root-Helfer verwaltet Mounts mit einer vorhandenen eindeutigen UUID
unter /mnt/name; der Name ist ein Ordnername, kein neues Dateisystemlabel. Kein
Formatieren, RAID, LVM, LUKS oder Reparieren. Optional geprüfter fstab-Eintrag mit
vorheriger Dateisicherung. Bereits vorhandene fstab-Einträge werden nicht überschrieben.

Unmount ist normal, niemals Force/Lazy. Direkte Daten-Mounts unter /mnt, keine
System-/Docker-Datenplatte. Laufende Container, Unter-Mounts und aktive Sicherungspläne
werden berücksichtigt. Andere offene Nutzer können den Unmount blockieren. Ein
Autostart-Eintrag bleibt beim Aushängen erhalten und wirkt beim nächsten Boot wieder.

## Benutzer und Rechte

Normale Konten UID 1000–65533 erstellen/bearbeiten, Shell, Passwort, Passwortsperre
und zusätzliche Gruppen. Root und Systemkonten bleiben in diesen Masken geschützt.
Gruppen werden ergänzt, nicht entfernt. Keine Vergabe administrativer Gruppen.
Passwortsperren widerrufen keine vorhandenen SSH-Schlüssel. Kein Benutzerlöschen.

Dateirechte/Owner/Gruppe für genau einen Datenpfad unter /mnt, /home oder /srv,
nicht rekursiv, keine Sonderbits. ACLs werden angezeigt, nicht bearbeitet. Die
Root-Konsole kann diese Begrenzungen umgehen; entsprechend vorsichtig verwenden.

## Dienste, Docker und Stromversorgung

Strukturierte Dienst- und Containeraktionen brauchen eine Einmalvorschau. Zentrale
Zugangs-/Netzwerkdienste und ServerLotse-Container sind gegen Unterbrechungen
geschützt. Dienste zeigen Status, Autostart, Startzeit, Eigenschaften und Journal.
Docker zeigt Ressourcen und Logs. Root-Befehle besitzen diese Zielbeschränkung nicht.

Reboot/Shutdown über den internen Power-Vermittler und logind, 15 Sekunden Vorlauf,
keine Force-Option. Bestätigung REBOOT/SHUTDOWN, 60 Sekunden gültig. Reboot erst nach
Boot-Einrichtung der Systemansicht. Eine angenommene Anfrage bestätigt noch keinen
erfolgreichen Neustart. Externe Übertragungen vorher beenden.

## Sicherungen und Rettung

Dateisicherungspläne und Verlauf in /var/lib/serverlotse/admin.sqlite3. Root-geschützte
Ziele; Dateisystemzuordnung verhindert bei fehlendem Mount das Ausweichen auf die
SSD. UUID-Abgleich toleriert geänderte Gerätenamen nach einem Boot. Ein Helfer-Worker
führt verwaltete Änderungen seriell aus; externe Programme, der APT-Timer und aus
der freien Konsole gestartete Hintergrundprozesse sind nicht vollständig erfasst.

TAR-Dateisicherung mit Inhaltsmanifest, maximal 250.000 Dateien/32 MB Manifest.
Keine Links, weiteren Dateisysteme, leeren Ordner, Owner/ACLs oder anwendungskonsistente
Live-Datenbanken. Neue komprimierte/SQL-/Remote-Optionen in OPERATIONS.md. Wiederherstellung
immer in neuen privaten Unterordner, ohne Originale zu überschreiben. Kein automatisches
Löschen alter Archive. Speicher beobachten.

Die optionale Rettungskopie nutzt compose.recovery.yaml und einen eigenen leeren
RECOVERY_PATH; KOPIEREN bestätigt den Plan. Niemals bestehende App-/Datenbankordner
als Rettungsziel freigeben. Mehr Details zur alten Diagnose in DIAGNOSTICS.md.

## Anmeldung und Protokoll

Token aus .env, einmalige Anmeldung, optional signierte 30-Tage-Sitzung. Token nicht
im Browser-localStorage und nicht automatisch an unbekannte Besucher ausgegeben.
Er gewährt jetzt Root-Funktionen; alle Sitzungsinhaber sind Administratoren. HTTPS,
HttpOnly/SameSite-Cookie, Origin-Prüfung und begrenzte Requestgrößen bleiben aktiv.
Keine Mehrbenutzer-Rollenverwaltung, kein externes Sicherheitsaudit.

Aufgabenansicht des Webcontainers: letzte 20 Aufgaben, bei Neustart leer. Das
Host-Aktionsprotokoll bleibt dauerhaft bestehen, listet zuletzt 200 Einträge und
Details. Geheimnisse werden nicht darin gespeichert; originale Befehlsausgaben
werden nur bestmöglich maskiert. Unterbrochene Host-Aufträge sind gekennzeichnet.

Echte Linux-/Docker-/Proxy-/Remote-Integration konnte unter Windows nicht vollständig
geprüft werden. Testcontainer führt Logiktests mit ersetzten Hostbefehlen aus,
keine echten Systemänderungen. Entwicklungsversion zuerst mit Testdaten prüfen.
