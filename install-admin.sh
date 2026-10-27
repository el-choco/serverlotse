#!/bin/sh
# Install the root helper explicitly; the web container stays unprivileged.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Bitte mit sudo ausführen.'; exit 1; }
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
command -v python3 >/dev/null || { echo 'Bitte zuerst python3 auf dem Host installieren.'; exit 1; }
# Read .env as data, never source/evaluate it as a root shell script.
python3 - "$script_dir" <<'PY'
import os, pathlib, re, sys, socket, http.client, json
root = pathlib.Path(sys.argv[1])
socket_path = pathlib.Path('/run/serverlotse-admin/agent.sock')
token_path = pathlib.Path('/etc/serverlotse/admin.token')
if socket_path.exists() and token_path.exists():
    class Connection(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(5); self.sock.connect(str(socket_path))
    connection = Connection('localhost', timeout=5)
    try:
        connection.request('POST', '/read', json.dumps({'view':'status'}), {'Authorization':'Bearer '+token_path.read_text().strip()})
        response = connection.getresponse()
        status = json.loads(response.read())
        if response.status != 200 or status.get('busy') or status.get('terminal_sessions'):
            raise SystemExit('Host-Helfer ist beschäftigt oder meldet einen Fehler. Vor Installation Aufgaben abschließen und Terminalsitzungen schließen.')
        connection.request('POST', '/read', json.dumps({'view':'power_reserve'}), {'Authorization':'Bearer '+token_path.read_text().strip()})
        reserved = connection.getresponse()
        if reserved.status != 200 or not json.loads(reserved.read()).get('reserved'):
            raise SystemExit('Wartungssperre konnte nicht gesetzt werden. Dienstzustand prüfen.')
    except OSError:
        raise SystemExit('Vorhandener Host-Helfer antwortet nicht. Dienstzustand vor Installation prüfen.')
    finally: connection.close()
values = {}
for line in (root / '.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    key, value = line.split('=', 1)
    value = value.strip()
    if value[:1] in ('"', "'"):
        if len(value) < 2 or value[-1] != value[0]: raise SystemExit('Ungültige .env-Zeile.')
        value = value[1:-1]
    else:
        value = value.split(' #', 1)[0].rstrip()
    values[key.strip()] = value
token = values.get('SERVERLOTSE_TOKEN', '')
if not re.fullmatch(r'[A-Za-z0-9_\-.]{24,256}', token):
    raise SystemExit('Token benötigt 24–256 Buchstaben, Zahlen, _, - oder Punkt. Kein Shell-Code und keine Compose-$-Interpolation.')
os.umask(0o077)
folder = pathlib.Path('/etc/serverlotse'); folder.mkdir(mode=0o700, exist_ok=True)
path = folder / 'admin.token'; path.write_text(token+'\n'); path.chmod(0o600)
PY
install -d -m 0755 /usr/local/lib/serverlotse
install -m 0644 "$script_dir/admin_core.py" "$script_dir/admin_agent.py" "$script_dir/sensors.py" "$script_dir/toolkit.py" /usr/local/lib/serverlotse/
install -m 0644 "$script_dir/workbench.py" "$script_dir/docker_tools.py" "$script_dir/registry_check.py" "$script_dir/guardian.py" "$script_dir/backup_probe.py" "$script_dir/expert_tools.py" "$script_dir/network_extras.py" "$script_dir/docker_extras.py" "$script_dir/terminal_host.py" "$script_dir/advanced.py" "$script_dir/automation.py" "$script_dir/bundle_backup.py" "$script_dir/proxy_control.py" /usr/local/lib/serverlotse/
install -m 0644 "$script_dir/serverlotse-admin.service" /etc/systemd/system/serverlotse-admin.service
systemctl daemon-reload
systemctl enable serverlotse-admin.service
systemctl restart serverlotse-admin.service
echo 'Host-Verwaltung installiert. Jetzt docker compose up -d --build ausführen.'
echo 'Optionale Diagnosewerkzeuge: smartmontools und acl. Fehlende Werkzeuge zeigt die Oberfläche an.'
