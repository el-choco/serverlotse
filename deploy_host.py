"""One-shot Docker bootstrap for the explicitly approved native root helper."""
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

PYTHON_FILES = ('admin_core.py','admin_agent.py','sensors.py','toolkit.py','advanced.py',
                'automation.py','bundle_backup.py','proxy_control.py','terminal_host.py','workbench.py','docker_tools.py','registry_check.py','guardian.py','backup_probe.py','expert_tools.py','network_extras.py','docker_extras.py')
FILES = PYTHON_FILES + ('prepare-host.sh','serverlotse-admin.service','serverlotse-view.service')


def validate(payload):
    if not isinstance(payload,dict) or set(payload) != {'token','files'}:
        raise ValueError('Ungültiges Startpaket.')
    if not isinstance(payload['token'],str) or not re.fullmatch(r'[A-Za-z0-9_\-.]{24,256}',payload['token']):
        raise ValueError('Zugangsschlüssel in .env prüfen: 24–256 Buchstaben, Zahlen, _, - oder Punkt.')
    files=payload['files']
    if not isinstance(files,dict) or set(files) != set(FILES): raise ValueError('Startpaket unvollständig.')
    for name,text in files.items():
        if not isinstance(text,str) or len(text)>500000 or '\r' in text or '\x00' in text:
            raise ValueError('Ungültige Startdatei: '+name)
        if name in PYTHON_FILES: compile(text,name,'exec')


def safe_path(root,relative):
    current=root
    for part in Path(relative).parts:
        if part in ('..','/') or not part: raise ValueError('Ungültiger Installationspfad.')
        current=current/part
        if current.is_symlink(): raise ValueError('Installationspfad ist ein Symlink: '+str(current))
        if current.exists():
            info=current.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError('Installationspfad hat unsichere Rechte: '+str(current))
    return current


def write(root,relative,text,mode):
    path=safe_path(root,relative)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    fd,tmp=tempfile.mkstemp(prefix='.serverlotse-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as output:
            output.write(text);output.flush();os.fsync(output.fileno());os.fchmod(output.fileno(),mode)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def request(token,data):
    class Connection(http.client.HTTPConnection):
        def connect(self):
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.settimeout(5);self.sock.connect('/run/serverlotse-admin/agent.sock')
    client=Connection('localhost',timeout=5)
    try:
        client.request('POST','/read',json.dumps(data),{'Authorization':'Bearer '+token})
        result=client.getresponse();body=json.loads(result.read(100000))
        if result.status != 200:raise ValueError('Host-Helfer meldet einen Fehler; Dienstprotokoll prüfen.')
        return body
    finally:client.close()


def run(args):
    subprocess.run(args,check=True,timeout=90,stdin=subprocess.DEVNULL)


def install(payload,root=Path('/'),runner=run,reader=request):
    validate(payload)
    reserved=False
    token_path=safe_path(root,'etc/serverlotse/admin.token')
    socket_path=root/'run/serverlotse-admin/agent.sock'
    if socket_path.exists() and token_path.exists():
        old_token=token_path.read_text().strip()
        status=reader(old_token,{'view':'status'})
        unchanged=old_token==payload['token'] and status.get('terminal') and status.get('version')=='0.7.4'
        for name,text in payload['files'].items():
            relative=('etc/systemd/system/' if name.endswith('.service') else 'usr/local/lib/serverlotse/')+name
            path=safe_path(root,relative)
            unchanged=unchanged and path.is_file() and path.read_bytes()==text.encode('utf-8')
        if unchanged:
            runner(['systemctl','enable','--now','serverlotse-view.service'])
            print('Host-Helfer unverändert und bereit; laufende Sitzungen bleiben erhalten.',flush=True)
            return
        if status.get('busy') or status.get('terminal_sessions'):
            raise ValueError('Zuerst laufende ServerLotse-Aufgaben abschließen und Terminals schließen; dann Compose erneut starten.')
        if not reader(old_token,{'view':'power_reserve'}).get('reserved'):
            raise ValueError('Host-Helfer konnte nicht für das Update reserviert werden.')
        reserved=True
    try:
        for name in FILES:
            relative=('etc/systemd/system/' if name.endswith('.service') else 'usr/local/lib/serverlotse/')+name
            safe_path(root,relative)
        config=safe_path(root,'etc/serverlotse');config.mkdir(parents=True,exist_ok=True,mode=0o700)
        for name,text in payload['files'].items():
            relative=('etc/systemd/system/' if name.endswith('.service') else 'usr/local/lib/serverlotse/')+name
            write(root,relative,text,0o755 if name.endswith('.sh') else 0o644)
        write(root,'etc/serverlotse/admin.token',payload['token']+'\n',0o600)
        runner(['systemctl','daemon-reload'])
        runner(['systemctl','enable','--now','serverlotse-view.service'])
        runner(['systemctl','enable','serverlotse-admin.service'])
        runner(['systemctl','restart','serverlotse-admin.service'])
        deadline=time.monotonic()+20
        while True:
            try:
                status=reader(payload['token'],{'view':'status'})
                if status.get('terminal') and status.get('version')=='0.7.4':break
            except (OSError,ValueError,http.client.HTTPException):pass
            if time.monotonic()>deadline:raise ValueError('Host-Helfer startet nicht. journalctl -u serverlotse-admin.service -n 40 --no-pager prüfen.')
            time.sleep(.25)
        print('Host-Helfer 0.7.4 und Systemansicht bereit. Kein manueller Installer nötig.',flush=True)
    finally:
        if reserved:
            try:reader(payload['token'],{'view':'power_release'})
            except Exception:pass


def launch():
    payload={'token':os.getenv('SERVERLOTSE_TOKEN',''),
             'files':{name:Path('/payload',name).read_text(encoding='utf-8').replace('\r\n','\n') for name in FILES}}
    validate(payload)
    source=Path(__file__).read_text(encoding='utf-8')
    subprocess.run(['nsenter','--target','1','--mount','--uts','--ipc','--net','--pid','--root','--wd',
                    '--','/usr/bin/python3','-c',source],input=json.dumps(payload).encode(),check=True,timeout=180)


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--launch']:launch()
        else:
            if os.geteuid()!=0 or Path('/proc/1/comm').read_text().strip()!='systemd':
                raise ValueError('Benötigt einen Linux-Host mit systemd, Python 3 und rootful Docker.')
            install(json.load(sys.stdin))
    except Exception as exc:
        print('ServerLotse-Start abgebrochen: '+str(exc),file=sys.stderr)
        sys.exit(1)
