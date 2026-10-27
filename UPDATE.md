# Update auf ServerLotse 0.7.5

ZIP in den bisherigen Projektordner entpacken, eigene .env behalten. Auch die neue
compose.yaml übernehmen: Sie enthält den benötigten Root-Lesezugriff und das eigene
Scan-Cache-Volume. Nur Programmdateien zu kopieren behebt die Zugriffsfehler nicht.
Vorher laufende ServerLotse-Aufgaben und Terminals beenden.

```sh
cd /mnt/intenso2tb/serverlotse
docker compose up -d --build
```

Danach Strg+F5. Kein manueller Installer und keine neue Portfreigabe. Bootstrap
aktualisiert den Host-Helfer automatisch; Exitcode 0 ist normal.

Neu in 0.7.3–0.7.5: GitHub-README mit Screenshots, aufgeräumte Ignore-Dateien und Quelltext ohne Kommentare, keine Funktionsänderung. Aus 0.7.2:
Icons im Menü, Cronjobs anlegen (Cron oder systemd-Timer), verständliche Paket-Wartung,
hervorgehobene Laufanzeigen, Breadcrumbs mit Kategorieübersichten, Ordnerdialog mit Filter/Pfadeingabe,
Container-Radar ohne Seiten-Neuaufbau, schönere Sensor-/Netzwerkkarten und passende
Einheiten. Footer entfernt und Proxy-Aktionsabstand korrigiert. DE/EN/ES ergänzt.

Die alte 250.000-Einträge-Grenze sollte den RAM schützen. Sie wird durch einen
privaten temporären Metadatenindex im Docker-Volume scan-cache ersetzt. Das betrifft
Dateianalysen, Vergleiche und Duplikate; Ergebnislisten bleiben bewusst begrenzt.
Normaler Abschluss/Fehler entfernt den jeweiligen Index. Harte Prozessabbrüche
können Cache-Reste hinterlassen; Quelldateien werden nicht kopiert oder verändert.
Große Bestände benötigen Zeit und freien Platz für den Index.

Der Programmcontainer läuft als root mit DAC_READ_SEARCH. Host und Systemansicht
bleiben readonly; kein chmod/chown an deinen Daten. Die Berechtigung übergeht lokale
Datei-/Ordner-Leserechte. Sperren durch Netzdateisysteme, FUSE oder Kernelregeln sind
keine gewöhnlichen Linux-Dateirechte und können weiterhin Lesezugriffe verhindern.
[Docker-Dokumentation](https://docs.docker.com/engine/containers/run/).

Vorhandene Automatiken und Einstellungen bleiben erhalten. Das optionale
Rettungsmodul benötigt weiterhin einen eigenen eingerichteten Rettungsordner.
