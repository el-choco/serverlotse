import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import secrets
import shutil
import stat
import tempfile
from urllib.parse import quote
import admin_core as core
import advanced
import docker_tools as docker

OPS={'lab_builder','lab_volume_write','lab_trivy'}
TRIVY='aquasec/trivy:0.76.1'


def volume(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}',name):raise ValueError('Ungültiger Volume-Name.')
    row=docker.api('GET','/volumes/'+quote(name,safe=''));path=core.local_path(row['Mountpoint'])
    if row.get('Driver')!='local' or row.get('Options'):raise ValueError('Nur lokale Standard-Volumes ohne Treiberoptionen bearbeiten.')
    for container in docker.inventory():
        if docker.protected(container):
            info=docker.inspect(container['Id'],False)
            if any(m.get('Name')==name for m in info.get('Mounts',[])):raise ValueError('ServerLotse-eigene Volumes sind geschützt.')
    return path


def relative(value):
    if not isinstance(value,str) or len(value)>1000 or any(ord(c)<32 for c in value) or '\\' in value:raise ValueError('Ungültiger relativer Volume-Pfad.')
    if value.startswith('/') or '..' in PurePosixPath(value).parts:raise ValueError('Pfad muss im ausgewählten Volume bleiben.')
    return [p for p in value.split('/') if p and p!='.']


@contextlib.contextmanager
def directory_fd(root,parts):
    fd=core.secure_open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in parts:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        yield fd
    finally:os.close(fd)


def existing_file(fd,name):
    try:
        stream=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    except FileNotFoundError:return None,None
    try:
        info=os.fstat(stream)
        if not stat.S_ISREG(info.st_mode) or info.st_size>32768:raise ValueError('Nur reguläre Dateien bis 32 KiB bearbeiten.')
        data=os.read(stream,32769)
        if len(data)>32768:raise ValueError('Datei ist inzwischen zu groß.')
        return {'identity':[info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid],
                'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)},data
    finally:os.close(stream)


def writable_name(name):
    if re.search(r'(^\.?(?:env|my\.cnf)$|\.(?:sql|db|sqlite\d*|mdb|ibd|sock|pid)$|^(?:ibdata|ib_logfile|PG_VERSION|postmaster|dump\.rdb|appendonly))',name,re.I):
        raise ValueError('Datenbank-, Zugangsdaten- und Laufzeitdateien über das zuständige Werkzeug bearbeiten.')
    if not re.fullmatch(r'[\w .@()+,-]{1,160}',name,re.UNICODE):raise ValueError('Einfachen Dateinamen ohne Sonderzeichen verwenden.')


def volume_read(data):
    root=volume(data.get('volume'));parts=relative(data.get('path',''))
    if data.get('file'):
        if not parts:raise ValueError('Datei auswählen.')
        writable_name(parts[-1])
        with directory_fd(root,parts[:-1]) as fd:info,raw=existing_file(fd,parts[-1])
        if raw is None:raise ValueError('Datei nicht vorhanden.')
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError:raise ValueError('Nur UTF-8-Textdateien im Editor öffnen.') from None
        if '\x00' in text:raise ValueError('Binärdateien werden nicht im Editor geöffnet.')
        return {'path':'/'.join(parts),'config_text':text,'file_state':info}
    rows=[]
    with directory_fd(root,parts) as fd:
        for name in sorted(os.listdir(fd))[:500]:
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            rows.append({'name':name,'directory':stat.S_ISDIR(info.st_mode),'regular':stat.S_ISREG(info.st_mode),'bytes':info.st_size,'link':stat.S_ISLNK(info.st_mode)})
    return {'path':'/'.join(parts),'rows':rows,'note':'Maximal 500 Einträge. Symlinks werden nicht verfolgt. Bearbeiten und Upload sind auf 32 KiB pro Datei begrenzt.'}


def builder(data):
    project=docker.name(data.get('name'));base=core.local_path(data.get('directory'));core.private_destination(base)
    destination=base/('serverlotse-'+project);old=None
    if destination.exists():
        core.private_destination(core.local_path(str(destination)))
        path=core.local_path(str(destination/'compose.yaml'))
        if path.stat().st_size>64000:raise ValueError('Compose-Datei zu groß.')
        old=json.loads(path.read_text())
        if old.get('x-serverlotse-builder')!=True:raise ValueError('Nur mit diesem Baukasten erzeugte Projekte bearbeiten. Vorhandene freie Compose-Dateien bleiben erhalten.')
    rows=data.get('services')
    if not isinstance(rows,list) or not 1<=len(rows)<=8:raise ValueError('Ein bis acht Dienste angeben.')
    services={};used=set();oldservices=old.get('services',{}) if old else {}
    inventory=docker.inventory()
    for row in rows:
        name=docker.name(row.get('name'));image=row.get('image','')
        if name in services:raise ValueError('Dienstname doppelt vergeben.')
        if not isinstance(image,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9./:_@-]{0,239}',image):raise ValueError('Ungültiges Image.')
        spec={'image':image,'restart':'unless-stopped'}
        if row.get('port'):
            host=int(row['port']);target=int(row.get('target',80));bind=row.get('bind','127.0.0.1')
            if host in used or not 1<=target<=65535:raise ValueError('Doppelter Host-Port oder ungültiger Container-Port.')
            used.add(host)
            previous=next((r['Id'] for r in inventory if r.get('Labels',{}).get('com.docker.compose.project')=='sl-'+project and r.get('Labels',{}).get('com.docker.compose.service')==name),None)
            result=docker.port_check(host,bind,previous)
            if not result['available']:raise ValueError('Host-Port bereits belegt: '+str(host))
            spec['ports']=[f'{bind}:{host}:{target}']
        if row.get('volume_target'):
            target=row['volume_target'];parts=relative(target.lstrip('/'))
            if not target.startswith('/') or not parts or any(c in target for c in ':$') or target in {'/','/proc','/sys','/dev','/run','/var/run'} or target.endswith('.sock'):raise ValueError('Eindeutigen Datenordner im Container auswählen.')
            spec['volumes']=['./data-'+name+':'+target]
        updates=docker.updates(row.get('env_updates',{}));env=dict(oldservices.get(name,{}).get('environment',{}))
        for key,value in updates.items():
            if value is None:env.pop(key,None)
            else:env[key]=value.replace('$','$$')
        if env:spec['environment']=env
        services[name]=spec
    compose={'name':'sl-'+project,'x-serverlotse-builder':True,'services':services}
    return {'operation':'lab_builder','name':project,'directory':str(base),'destination':str(destination),'services':rows,
            'compose_document':compose,'existing_hash':docker.fingerprint(old) if old else None,
            'note':'Nur das verwaltete Projekt wird geändert. Entfernte Dienste bleiben als Waisen erhalten, Datenordner werden nicht gelöscht. Apps nach dem Start selbst einrichten.'}


def validate(data):
    op=data['operation']
    if op=='lab_builder':return builder(data)
    if op=='lab_volume_write':
        root=volume(data.get('volume'));parts=relative(data.get('path',''))
        if not parts:raise ValueError('Zieldatei angeben.')
        writable_name(parts[-1]);encoded=data.get('encoded_data')
        if not isinstance(encoded,str) or len(encoded)>44000:raise ValueError('Upload auf 32 KiB begrenzt.')
        try:payload=base64.b64decode(encoded,validate=True)
        except ValueError:raise ValueError('Ungültiger Upload.') from None
        if len(payload)>32768:raise ValueError('Upload auf 32 KiB begrenzt.')
        with directory_fd(root,parts[:-1]) as fd:
            parent=os.fstat(fd);current,_=existing_file(fd,parts[-1]);parent_state=[parent.st_dev,parent.st_ino]
        if 'file_state' in data and data['file_state']!=current:raise ValueError('Datei seit dem Öffnen verändert. Neu laden.')
        return {'operation':op,'volume':data['volume'],'path':'/'.join(parts),'encoded_data':encoded,'bytes':len(payload),
                'sha256':hashlib.sha256(payload).hexdigest(),'file_state':current,'parent_state':parent_state,'root_state':core.identity(root)}
    if op=='lab_trivy':
        if data.get('consent') is not True:raise ValueError('Download des Scanners und der Schwachstellen-Datenbank zuerst bestätigen.')
        info=docker.inspect(docker.ident(data.get('container')),False);image=docker.api('GET','/images/'+info['Image']+'/json')
        size=image.get('Size',0)
        if not isinstance(size,int) or not 0<size<=4*1024**3:raise ValueError('Scanner verarbeitet lokale Images bis 4 GiB.')
        if shutil.disk_usage(core.STATE).free<size*2+1024**3:raise ValueError('Zu wenig freier Platz für Image-Export und Scanner-Datenbank.')
        return {'operation':op,'container':data['container'],'image':info['Image'],'bytes':size,'consent':True,'scanner':TRIVY}
    raise ValueError('Unbekanntes Docker-Zusatzwerkzeug.')


def scan(p):
    core.STATE.mkdir(mode=0o700,parents=True,exist_ok=True);root=Path(tempfile.mkdtemp(prefix='trivy-',dir=core.STATE));container=None
    try:
        os.chmod(root,0o700);out=root/'out';out.mkdir(mode=0o700)
        archive=root/'image.tar';core.command(['docker','image','save','--output',str(archive),p['image']],timeout=600)
        if archive.stat().st_size>8*1024**3:raise ValueError('Image-Export ist zu groß.')
        core.command(['docker','pull',TRIVY],timeout=600)
        container=core.command(['docker','create','--label','serverlotse.trivy=1','--network','bridge','--read-only',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','1g','--cpus','1','--pids-limit','64',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--mount','type=bind,source='+str(archive)+',target=/scan/image.tar,readonly',
            '--mount','type=bind,source='+str(out)+',target=/out',TRIVY,'image','--input','/scan/image.tar',
            '--cache-dir','/out/cache','--scanners','vuln','--offline-scan','--quiet','--skip-version-check','--format','json','--output','/out/report.json']).strip()
        docker.ident(container);core.command(['docker','start','--attach',container],timeout=1200)
        state=docker.api('GET','/containers/'+container+'/json').get('State',{})
        if state.get('Running') or state.get('ExitCode')!=0:raise ValueError('Trivy wurde nicht erfolgreich beendet. Kein gültiges Scan-Ergebnis.')
        report=out/'report.json'
        if report.is_symlink() or not report.is_file() or report.stat().st_size>10*1024**2:raise ValueError('Scanner-Bericht fehlt oder ist zu groß.')
        parsed=json.loads(report.read_text());counts={k:0 for k in ['CRITICAL','HIGH','MEDIUM','LOW','UNKNOWN']};findings=[]
        for result in parsed.get('Results',[]):
            for item in result.get('Vulnerabilities') or []:
                severity=item.get('Severity','UNKNOWN');severity=severity if severity in counts else 'UNKNOWN';counts[severity]+=1
                if len(findings)<100:findings.append({k:str(item.get(k,''))[:300] for k in ['VulnerabilityID','PkgName','InstalledVersion','FixedVersion','Severity']})
        answer={'image':p['image'],'scanner':TRIVY,'counts':counts,'findings':findings,'note':'Datenbankbasierter Befund, kein Beweis für Ausnutzbarkeit oder Sicherheit. Maximal 100 Detailzeilen.'}
        advanced.state('trivy-'+p['image'],answer);return answer
    finally:
        if container:
            try:docker.api('DELETE','/containers/'+docker.ident(container)+'?force=true&v=true')
            except Exception:advanced.log_event('lab_trivy_cleanup',{'container':container,'note':'Testcontainer konnte nicht entfernt werden.'},'error')
        shutil.rmtree(root)


def apply(p):
    if p['operation']=='lab_trivy':return scan(p)
    if p['operation']=='lab_builder':
        dest=Path(p['destination']);dest.mkdir(mode=0o700,exist_ok=True);core.private_destination(dest)
        path=dest/'compose.yaml'
        if path.exists():advanced.atomic_write(core.STATE/('compose-'+secrets.token_hex(8)+'.bak'),path.read_bytes(),0o600)
        content=json.dumps(p['compose_document'],indent=2).encode()
        advanced.atomic_write(path,content,0o600)
        for name in p['compose_document']['services']:
            (dest/('data-'+name)).mkdir(mode=0o755,exist_ok=True)
        args=['docker','compose','--project-directory',str(dest),'-f',str(path)]
        try:core.command([*args,'config','--quiet']);core.command([*args,'up','-d'],timeout=900)
        except Exception:raise ValueError('Compose-Bereitstellung fehlgeschlagen. Projektdatei und vorherige Sicherung bleiben erhalten. Konfiguration und Dienstzustand prüfen.') from None
        return {'directory':str(dest),'note':p['note']}
    root=volume(p['volume']);parts=relative(p['path']);payload=base64.b64decode(p['encoded_data']);backup=None
    with directory_fd(root,parts[:-1]) as fd:
        parent=os.fstat(fd)
        if [parent.st_dev,parent.st_ino]!=p['parent_state']:raise ValueError('Zielordner wurde ersetzt.')
        current,original=existing_file(fd,parts[-1])
        if current!=p['file_state']:raise ValueError('Zieldatei wurde verändert.')
        if original is not None:
            backup=core.STATE/('volume-'+secrets.token_hex(8)+'.bak');advanced.atomic_write(backup,original,0o600)
        name='.serverlotse-'+secrets.token_hex(8);stream=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            state=current['identity'] if current else [0,0,0o640,parent.st_uid,parent.st_gid]
            with os.fdopen(stream,'wb') as file:
                os.fchown(file.fileno(),state[3],state[4]);os.fchmod(file.fileno(),stat.S_IMODE(state[2]));file.write(payload);file.flush();os.fsync(file.fileno())
            if current is None:os.link(name,parts[-1],src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
            else:
                check,_=existing_file(fd,parts[-1])
                if check!=current:raise ValueError('Zieldatei wurde während der Änderung ersetzt.')
                os.replace(name,parts[-1],src_dir_fd=fd,dst_dir_fd=fd)
        finally:
            try:os.unlink(name,dir_fd=fd)
            except FileNotFoundError:pass
    return {'bytes':len(payload),'backup':str(backup) if backup else None,'note':'Datei gespeichert. Dienst lädt Konfiguration gegebenenfalls erst nach eigenem Neuladen.'}


def read(data):
    if data['view']=='lab_volumes':return {'rows':[{'name':r['Name'],'driver':r['Driver']} for r in docker.api('GET','/volumes').get('Volumes') or []][:200]}
    if data['view']=='lab_volume_files':return volume_read(data)
    if data['view']=='lab_builder_load':
        root=core.local_path(data.get('directory'));core.private_destination(root);path=core.local_path(str(root/'compose.yaml'))
        if path.stat().st_size>64000:raise ValueError('Projekt zu groß.')
        content=json.loads(path.read_text())
        if content.get('x-serverlotse-builder')!=True:raise ValueError('Kein ServerLotse-Baukastenprojekt.')
        rows=[]
        for name,spec in content['services'].items():
            row={'name':name,'image':spec['image'],'port':'','target':80,'bind':'127.0.0.1','volume_target':'','environment':{key:'••••••' for key in spec.get('environment',{})}}
            if spec.get('ports'):row['bind'],row['port'],row['target']=spec['ports'][0].split(':')
            if spec.get('volumes'):row['volume_target']=spec['volumes'][0].split(':')[1]
            rows.append(row)
        return {'directory':str(root.parent),'name':root.name.removeprefix('serverlotse-'),'services':rows}
    if data['view']=='lab_trivy_result':
        info=docker.inspect(data.get('container'),False);return advanced.state('trivy-'+info['Image']) or {'note':'Dieses lokale Image wurde noch nicht gescannt.'}
    raise ValueError('Unbekannte Docker-Zusatzansicht.')
