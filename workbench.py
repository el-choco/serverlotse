"""Dispatch only fixed workbench operations through the existing preview/audit flow."""
import docker_tools
import guardian
import backup_probe
import expert_tools
import network_extras
import docker_extras

OPS=docker_tools.OPS|guardian.OPS|expert_tools.OPS|network_extras.OPS|docker_extras.OPS|{'lab_restore_test'}


def validate(data):
    for module in (expert_tools,network_extras,docker_extras):
        if data['operation'] in module.OPS:return module.validate(data)
    if data['operation'] in docker_tools.OPS:return docker_tools.validate(data)
    if data['operation'] in guardian.OPS:return guardian.validate(data)
    if data['operation']=='lab_restore_test':return backup_probe.validate(data)
    raise ValueError('Unbekanntes Werkzeug.')


def apply(data):
    for module in (expert_tools,network_extras,docker_extras):
        if data['operation'] in module.OPS:return module.apply(data)
    if data['operation'] in docker_tools.OPS:return docker_tools.apply(data)
    if data['operation'] in guardian.OPS:return guardian.apply(data)
    if data['operation']=='lab_restore_test':return backup_probe.apply(data)
    raise ValueError('Unbekanntes Werkzeug.')


def read(data):
    if data['view'] in {'lab_inodes','lab_cron','lab_orphans','lab_analyze','lab_memory','lab_undo','lab_native_config','lab_apt_cleanup'}:return expert_tools.read(data)
    if data['view'] in {'lab_ddns','lab_domain_targets','lab_dns_check','lab_inode_watch','lab_firewall_map'}:return network_extras.read(data)
    if data['view'] in {'lab_volumes','lab_volume_files','lab_builder_load','lab_trivy_result'}:return docker_extras.read(data)
    if data['view'] in {'lab_docker','lab_environment','lab_networks','lab_ports','lab_dotenv','lab_health'}:return docker_tools.read(data)
    if data['view']=='lab_backup_options':
        import admin_core as core
        return {'backups':[{'id':r['id'],'name':r['name'],'archives':core.backup_archives(r['id'])['rows']}
                           for r in core.backup_configs()['rows'] if r.get('bundle') and r.get('container')],
                'images':[{'id':r['Id'],'tags':r.get('RepoTags') or []} for r in docker_tools.api('GET','/images/json')
                    if any(tag.startswith(('mariadb:','mysql:','docker.io/library/mariadb:','docker.io/library/mysql:')) for tag in r.get('RepoTags') or [])]}
    return guardian.read(data)


def warnings(plan):
    op=plan['operation'];result=[]
    if op=='lab_janitor':result.append('Endgültig: gestoppte Container mit ihrer beschreibbaren Schicht, bestätigte unbenutzte Images/Netzwerke/Volumes und Build-Cache. Kein Backup. Bereits an gestoppte Container gebundene Volumes werden behalten. Bei Fehlern können Teilaktionen abgeschlossen sein.')
    if op in {'lab_clone','lab_env','lab_compose'}:result.append('Container und Verbindungen können unterbrochen werden. App-Daten und feste IPs prüfen; Container-IDs können sich ändern. Änderungen an Daten lassen sich nicht automatisch zurücknehmen.')
    if op=='lab_clone':result.append('Konfigurationskopie mit neuem Namen und leerer beziehungsweise nur lesend geteilter Datenablage. Keine Kopie von Daten oder der beschreibbaren Container-Schicht; neuer Container verwendet bridge.')
    if op=='lab_env':
        if plan.get('compose'):result.append('Compose verwendet eine eigene root-geschützte Override-Datei. Diese bei späteren Portainer-/Compose-Updates mitverwenden. Der Dienst wird neu bereitgestellt; App-Bereitschaft und geänderte Container-IDs prüfen.')
        else:result.append('Eigenständiger Container: Vorgänger bleibt gestoppt erhalten; keine Garantie für App-Bereitschaft. Backup- und Auto-Heiler-Ziele anschließend neu wählen.')
    if op=='lab_template':result.append('Neue Images werden aus offiziellen Registries geladen. Apps werden am gewählten Host-Port gestartet; Installationsassistent und eigene Sicherung bleiben erforderlich. Keine alten Daten werden übernommen.')
    if op=='lab_registry':result.append('Image-Referenz und Server-IP werden an die öffentliche Registry übermittelt. Keine Zugangsdaten, kein Pull und kein Update.')
    if op=='lab_dotenv':result.append('Datei wird root-geschützt ersetzt und vorher gesichert. Compose-Variablen können App-Verhalten und Zugänge ändern. Keine Auswertung als Shellskript.')
    if op=='lab_session_end':result.append('Beendet die ausgewählte Anmeldesitzung einschließlich ihrer verwalteten Prozesse. Auch der eigene SSH-Zugang kann getrennt werden.')
    if op=='lab_baseline':result.append('Aktueller Zustand wird zur neuen FIM-Vergleichsbasis. Vorherige Warnungen werden quittiert; dadurch wird keine Datei repariert.')
    if op=='lab_settings':result.append('Nur ausdrücklich eingeschaltete Wächter laufen automatisch. Webhooks nutzen das bestehende Benachrichtigungsziel. Speedtests übertragen Netzwerk-/IP-Daten an Ookla und verbrauchen Bandbreite.')
    if op=='lab_speedtest':result.append('Ookla-Bedingungen und Datenschutz gelten. Überträgt IP-/Netzwerkdaten an Ookla und den Testserver; kann viel Bandbreite verbrauchen. Kein Test wird beim Installieren ausgelöst.')
    if op=='lab_http':result.append('Verbindet den Host mit der angegebenen Webseite. Keine Umleitungen und keine Anmeldung; Status wird aus Sicht dieses Hosts gemessen.')
    if op=='lab_rotate':result.append('Führt die vorhandene root-eigene Rotationskonfiguration einschließlich ihrer Hooks aus. Komprimierung und Wiederöffnung richten sich nach dieser Richtlinie; Dienste können neu geladen werden.')
    if op=='lab_restore_test':result.append('Bis zu 1 GiB RAM, 1 CPU und temporärer Platz neben dem Archiv. Testcontainer ohne Netzwerk, Host-Mounts oder Ports. Verwendet nur ein vorhandenes offizielles DB-Image; löscht anschließend ausschließlich den eigenen Testcontainer und dessen anonyme Volumes.')
    if op in expert_tools.OPS:result.append('Nur die bestätigte Aktion wird ausgeführt. Notfall-Netzsperre endet automatisch nach 60 Sekunden. Konfigurationsänderungen nach 30 Sekunden zurücknehmen, sofern sie nicht ausdrücklich beibehalten werden. Externe Kopier- und Verwaltungsaufgaben vorher prüfen.')
    if op=='lab_cache':result.append('Linux verwendet freien RAM sinnvoll als Cache. Leeren kann den Server vorübergehend verlangsamen und ist keine regelmäßige Wartung.')
    if op=='lab_apt_clean':result.append('Die aufgeführten Pakete werden mit ihrer Konfiguration entfernt. Kernel, Zugangs- und wichtige Systempakete sind gesperrt.')
    if op=='lab_cron_create':result.append('Der Befehl läuft künftig automatisch als '+plan['user']+' nach dem Zeitplan „'+plan['description']+'“. Ausgabe und Fehler prüft Cron nicht; bei Systemdiensten stehen sie im Journal. Befehl vorher einmal manuell testen.')
    if op=='lab_cron_remove':result.append('Nur der von ServerLotse angelegte Auftrag wird entfernt. Andere Cron-Einträge und Timer bleiben unverändert.')
    if op=='lab_volume_write':result.append('Ändert die ausgewählte kleine Datei im lokalen Docker-Volume. Vorhandene Dateien werden vorher privat gesichert. Keine Datenbankdateien bearbeiten; App-Konsistenz selbst prüfen.')
    if op=='lab_builder':result.append('Images können heruntergeladen und Dienste neu bereitgestellt werden. Nur eigene Baukastenprojekte; Daten und entfernte Dienste werden nicht gelöscht. Geänderte App-Einstellungen können Daten beeinflussen.')
    if op=='lab_trivy':result.append('Lädt den offiziellen Trivy-Scanner und seine Datenbank. Benötigt vorübergehend bis zu 1 GiB RAM und Platz für Image-Export. Scanner erhält keinen Docker-Socket und keine laufenden App-Volumes. Netzwerkzugriff zum Datenbankanbieter.')
    if op in network_extras.OPS:result.append('Nur ausdrücklich aktivierte DDNS-/Inode-Zeitpläne laufen automatisch. DDNS übermittelt öffentliche IP und Domain an ipify und den gewählten DNS-Anbieter. Proxyänderungen betreffen den nativen Caddy/Nginx, nicht Nginx Proxy Manager.')
    return result
