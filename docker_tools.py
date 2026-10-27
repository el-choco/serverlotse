from collections import deque
import copy
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import threading
import time
from urllib.parse import quote
import admin_core as core
import advanced

LOCK=threading.Lock()
HISTORY={}
LATEST=[]
LAST_ERROR=''
OPS={'lab_janitor','lab_clone','lab_env','lab_template','lab_dotenv','lab_compose','lab_registry'}
SAFE_ENV={'TZ','LANG','LC_ALL','PUID','PGID','NODE_ENV','PORT','APP_ENV'}
ID=re.compile(r'[a-f0-9]{64}')


class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout);self.sock.connect('/var/run/docker.sock')


def api(method,path,body=None,timeout=45):
    connection=Connection('localhost',timeout=timeout)
    try:
        connection.request(method,path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'})
        response=connection.getresponse();raw=response.read(4_000_001)
        if len(raw)>4_000_000:raise ValueError('Docker-Ausgabe zu groß; Auswahl verkleinern.')
        if response.status not in {200,201,204}:raise ValueError('Docker-Aktion fehlgeschlagen (HTTP '+str(response.status)+'). Zustand im Docker-Protokoll prüfen.')
        return json.loads(raw) if raw else {}
    except (OSError,http.client.HTTPException):raise ValueError('Docker-Socket auf dem Host nicht erreichbar.') from None
    finally:connection.close()


def ident(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('Vollständige Container-ID erforderlich.')
    return value


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def protected(info):
    names=info.get('Names') or [info.get('Name','')]
    labels=info.get('Labels') or info.get('Config',{}).get('Labels') or {}
    return any('serverlotse' in name.lower() for name in names) or labels.get('com.docker.compose.service') in {'serverlotse','docker-reader','host-control','host-bootstrap'}


def inspect(value,guard=True):
    row=api('GET','/containers/'+ident(value)+'/json')
    if guard and protected(row):raise ValueError('ServerLotse-eigene Container sind geschützt.')
    return row


def inventory():
    rows=api('GET','/containers/json?all=true')
    if len(rows)>200:raise ValueError('Mehr als 200 Container; diese Übersicht begrenzen.')
    return rows


def name(value):
    value=str(value)
    if not re.fullmatch(r'[a-z][a-z0-9_.-]{1,62}',value) or 'serverlotse' in value:
        raise ValueError('Namen mit 2–63 Kleinbuchstaben, Zahlen, Punkt, _ oder - wählen; ServerLotse ist reserviert.')
    return value


def environment(info):
    result=[]
    for item in info.get('Config',{}).get('Env') or []:
        key,_,value=item.partition('=')
        harmless=(key in {'PORT','PUID','PGID'} and bool(re.fullmatch(r'\d{1,7}',value)) or
                  key in {'NODE_ENV','APP_ENV'} and value in {'production','development','test'} or
                  key in {'LANG','LC_ALL'} and bool(re.fullmatch(r'(?:C(?:\.UTF-8)?|[a-z]{2}_[A-Z]{2}(?:\.[A-Za-z0-9-]+)?)',value)) or
                  key=='TZ' and bool(re.fullmatch(r'(?:UTC|[A-Za-z_+-]+/[A-Za-z0-9_+/-]+)',value)))
        result.append({'key':key,'value':value if harmless else '••••••','masked':not harmless})
    labels=info.get('Config',{}).get('Labels') or {}
    return {'rows':result,'compose':bool(labels.get('com.docker.compose.project')),
            'files':labels.get('com.docker.compose.project.config_files',''),
            'directory':labels.get('com.docker.compose.project.working_dir',''),
            'note':'Nur harmlose Standardwerte werden angezeigt. Alle anderen Werte bleiben maskiert. Leere Eingabefelder verändern nichts.'}


def updates(value):
    if not isinstance(value,dict) or not 1<=len(value)<=30:raise ValueError('1–30 Variablen auswählen.')
    result={}
    for key,val in value.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}',key):raise ValueError('Ungültiger Variablenname.')
        if val is not None and (not isinstance(val,str) or len(val)>4096 or any(ord(c)<32 or ord(c)==127 for c in val)):
            raise ValueError('Variablenwerte müssen einzeilig sein und dürfen höchstens 4096 Zeichen enthalten.')
        result[key]=val
    return result


def port_check(value,bind='127.0.0.1',ignore=None):
    port=int(value)
    if not 1024<=port<=65535:raise ValueError('Host-Port zwischen 1024 und 65535 wählen.')
    address=ipaddress.ip_address(bind)
    if address.version!=4:raise ValueError('Hier eine IPv4-Bind-Adresse wählen.')
    conflicts=[]
    for row in inventory():
        if row['Id']==ignore:continue
        for item in row.get('Ports') or []:
            if item.get('PublicPort')==port and (bind=='0.0.0.0' or item.get('IP') in {bind,'0.0.0.0','::'}):
                conflicts.extend(row.get('Names',[]))
    if ignore is None:
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:sock.bind((bind,port))
        except OSError:conflicts.append('Host-Dienst oder nicht verfügbare Bind-IP')
    return {'port':port,'bind':str(address),'available':not conflicts,'conflicts':sorted(set(conflicts)),
            'note':'Prüfung jetzt; Docker prüft beim Start erneut. Auch gestoppte Container können denselben Port später beanspruchen.'}


def networks():
    nets=api('GET','/networks');containers=inventory()
    return {'networks':[{'id':r['Id'],'name':r['Name'],'driver':r['Driver'],'internal':r.get('Internal',False)} for r in nets[:100]],
            'containers':[{'id':r['Id'],'name':(r.get('Names') or [r['Id'][:12]])[0].lstrip('/'),
                           'networks':list((r.get('NetworkSettings') or {}).get('Networks',{}))} for r in containers],
            'note':'Netzwerkmitgliedschaft, keine gemessenen Datenflüsse. Firewallregeln und Apps bestimmen die tatsächliche Kommunikation.'}


def janitor_plan():
    all_containers=inventory()
    stopped=[r for r in all_containers if r.get('State') in {'exited','dead','created'} and not protected(r)]
    protected_projects={(r.get('Labels') or {}).get('com.docker.compose.project') for r in all_containers if protected(r)}-{None,''}
    remove={r['Id'] for r in stopped}
    used={r.get('ImageID') for r in all_containers if r['Id'] not in remove}
    images=api('GET','/images/json?all=true')
    by_id={row['Id']:row for row in images}
    protected_images=used|{row['Id'] for row in images if any('serverlotse' in tag.lower() for tag in row.get('RepoTags') or [])}
    for value in list(protected_images):
        seen=set()
        while value in by_id and value not in seen:
            seen.add(value);parent=by_id[value].get('ParentId')
            if not parent:break
            protected_images.add(parent);value=parent
    def depth(value):
        seen=set()
        while value in by_id and value not in seen:
            seen.add(value);value=by_id[value].get('ParentId')
            if not value:break
        return len(seen)
    volumes=(api('GET','/volumes?filters='+quote(json.dumps({'dangling':['true']}),safe='')).get('Volumes') or [])
    nets=api('GET','/networks')
    result={'containers':[{'id':r['Id'],'name':(r.get('Names') or [''])[0],'state':r['State']} for r in sorted(stopped,key=lambda r:r['Id'])],
            'images':[{'id':r['Id'],'tags':sorted(r.get('RepoTags') or [])} for r in sorted(images,key=lambda r:(-depth(r['Id']),r['Id'])) if r['Id'] not in protected_images],
            'volumes':sorted(r['Name'] for r in volumes),
            'networks':sorted(r['Id'] for r in nets if r['Name'] not in {'bridge','host','none'} and 'serverlotse' not in r['Name'].lower() and not r.get('Containers') and (r.get('Labels') or {}).get('com.docker.compose.project') not in protected_projects)}
    result['networks']=[nid for nid in result['networks'] if not api('GET','/networks/'+nid).get('Containers')]
    if sum(len(v) for v in result.values())>500:raise ValueError('Zu viele Löschziele; zuerst einzelne Ressourcen bereinigen.')
    return result


def clone_spec(info,new_name,port=None,readonly=False,env_updates=None):
    host=info.get('HostConfig') or {}
    if host.get('Privileged') or host.get('PidMode') or host.get('IpcMode')=='host' or host.get('NetworkMode')=='host' or str(host.get('NetworkMode','')).startswith('container:') or host.get('Devices') or host.get('DeviceRequests') or host.get('VolumesFrom'):
        raise ValueError('Privilegierte Container und geteilte Host-Namensräume werden hier nicht dupliziert oder ersetzt.')
    config=info['Config']
    result={key:copy.deepcopy(config[key]) for key in ['Image','Env','Cmd','Entrypoint','WorkingDir','User','ExposedPorts','Healthcheck','StopSignal','StopTimeout','Labels','Volumes'] if key in config}
    result['Image']=info['Image']
    result['Hostname']=new_name
    if env_updates is None:
        result['Labels']={k:v for k,v in (result.get('Labels') or {}).items() if not k.startswith('com.docker.compose.')}
        result['Labels']['serverlotse.clone']='true'
        result['HostConfig']={'RestartPolicy':{'Name':'unless-stopped'},'NetworkMode':'bridge'}
        if readonly:
            for mount in info.get('Mounts',[]):
                if mount['Type']!='bind':continue
                source=Path(mount['Source'])
                if source in map(Path,['/','/var/run','/var/run/docker.sock']) or any(source==base or base in source.parents for base in map(Path,['/run','/proc','/sys','/dev'])):
                    raise ValueError('Host-Steuerungspfade und Sockets werden nicht an Klone weitergegeben.')
                try:
                    if stat.S_ISSOCK(source.stat().st_mode):raise ValueError('Ein nur lesend gemounteter Socket erlaubt trotzdem Schreibbefehle und wird nicht geteilt.')
                except FileNotFoundError:pass
            result['HostConfig']['Mounts']=[{'Type':r['Type'],'Source':r.get('Name') if r['Type']=='volume' else r['Source'],
                'Target':r['Destination'],'ReadOnly':True} for r in info.get('Mounts',[]) if r['Type'] in {'bind','volume'}]
        if port:
            destination=list(config.get('ExposedPorts') or {})
            if len(destination)!=1 or not destination[0].endswith('/tcp'):raise ValueError('Klon-Port verlangt genau einen veröffentlichten TCP-Port im Image.')
            result['HostConfig']['PortBindings']={destination[0]:[{'HostIp':port['bind'],'HostPort':str(port['port'])}]}
    else:
        if (config.get('Labels') or {}).get('com.docker.compose.project'):
            raise ValueError('Compose-Container über die .env-Datei ändern und anschließend Compose neu bereitstellen.')
        allowed=['Binds','Mounts','Tmpfs','PortBindings','RestartPolicy','NetworkMode','Memory','MemorySwap','NanoCpus','CpuQuota','CpuPeriod','CpusetCpus','PidsLimit','ShmSize','ReadonlyRootfs','Dns','DnsSearch','ExtraHosts','GroupAdd','Ulimits','CapAdd','CapDrop','SecurityOpt','LogConfig','Init']
        result['HostConfig']={k:copy.deepcopy(host[k]) for k in allowed if k in host}
        for mount in host.get('Mounts') or []:
            if mount.get('VolumeOptions') or mount.get('BindOptions',{}).get('NonRecursive'):
                raise ValueError('Erweiterte Mount-Optionen über die ursprüngliche Container-Konfiguration bearbeiten.')
        result['HostConfig'].pop('Binds',None)
        result['HostConfig']['Mounts']=[{'Type':r['Type'],'Source':r.get('Name') if r['Type']=='volume' else r['Source'],
            'Target':r['Destination'],'ReadOnly':not r.get('RW',False),
            **({'BindOptions':{'Propagation':r['Propagation']}} if r['Type']=='bind' and r.get('Propagation') else {})}
            for r in info.get('Mounts',[]) if r['Type'] in {'bind','volume'}]
        env=dict(item.split('=',1) for item in config.get('Env') or [] if '=' in item)
        for key,value in env_updates.items():
            if value is None:env.pop(key,None)
            else:env[key]=value
        result['Env']=[key+'='+value for key,value in env.items()]
        endpoints={}
        for network,settings in (info.get('NetworkSettings') or {}).get('Networks',{}).items():
            if settings.get('IPAMConfig'):raise ValueError('Container mit fest vergebenen Netzwerkadressen über seine ursprüngliche Konfiguration ändern.')
            endpoints[network]={'Aliases':settings.get('Aliases') or []}
        if endpoints:result['NetworkingConfig']={'EndpointsConfig':endpoints}
    return result


def dotenv(path):
    path=core.local_path(str(path));core.private_destination(path.parent)
    if path.name!='.env':raise ValueError('Eine Datei mit dem Namen .env wählen.')
    if path.stat().st_uid!=0 or path.stat().st_mode&0o022 or path.stat().st_size>256000:raise ValueError('.env braucht root-eigene, nicht öffentlich beschreibbare Rechte und höchstens 256 KB.')
    text=path.read_text(encoding='utf-8');values={}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        match=re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)=(.*)',line)
        if not match or match[1] in values:raise ValueError('Nur eindeutige einzeilige KEY=VALUE-Dateien können hier bearbeitet werden.')
        values[match[1]]=match[2]
    return path,text,values


def dotenv_line(key,value):
    return key+'='+json.dumps(value.replace('$','$$'),ensure_ascii=False)


def template_plan(data):
    kind=str(data.get('template'));project=name(data.get('name'))
    if kind not in {'nginx','wordpress','nextcloud'}:raise ValueError('Unbekannte App-Vorlage.')
    base=core.local_path(str(data.get('directory')));core.private_destination(base)
    destination=base/('serverlotse-'+project)
    if destination.exists():raise ValueError('Projektordner existiert bereits. Einen neuen Namen wählen.')
    port=port_check(data.get('port'),str(data.get('bind','127.0.0.1')))
    if not port['available']:raise ValueError('Host-Port ist bereits belegt oder Bind-IP nicht verfügbar.')
    image={'nginx':'nginx:stable-alpine','wordpress':'wordpress:apache','nextcloud':'nextcloud:stable-apache'}[kind]
    web={'image':image,'restart':'unless-stopped','ports':[f"{port['bind']}:{port['port']}:80"]}
    services={'web':web}
    if kind=='nginx':web['volumes']=['./html:/usr/share/nginx/html:ro']
    else:
        web['volumes']=['./data:/var/www/html']
        db={'image':'mariadb:lts','restart':'unless-stopped','environment':{'MARIADB_ROOT_PASSWORD':'${DB_ROOT_PASSWORD}',
            'MARIADB_DATABASE':'app','MARIADB_USER':'app','MARIADB_PASSWORD':'${DB_PASSWORD}'},'volumes':['./database:/var/lib/mysql']}
        services['database']=db;web['depends_on']=['database']
        web['environment']=({'WORDPRESS_DB_HOST':'database','WORDPRESS_DB_NAME':'app','WORDPRESS_DB_USER':'app','WORDPRESS_DB_PASSWORD':'${DB_PASSWORD}'}
            if kind=='wordpress' else {'MYSQL_HOST':'database','MYSQL_DATABASE':'app','MYSQL_USER':'app','MYSQL_PASSWORD':'${DB_PASSWORD}'})
    return {'operation':'lab_template','template':kind,'name':project,'directory':str(base),'destination':str(destination),
            'port':port['port'],'bind':port['bind'],'compose':{'name':'sl-'+project,'services':services}}


def validate(data):
    op=data['operation']
    if op=='lab_janitor':return {'operation':op,'targets':janitor_plan()}
    if op in {'lab_clone','lab_env','lab_compose','lab_registry'}:
        value=ident(data.get('container'));info=inspect(value)
        p={'operation':op,'container':value,'source_hash':fingerprint({'Config':info['Config'],'HostConfig':info['HostConfig'],'Mounts':info.get('Mounts'),
            'Image':info['Image'],'Networks':(info.get('NetworkSettings') or {}).get('Networks',{})})}
        if op=='lab_clone':
            new=name(data.get('name'))
            if any('/'+new in row.get('Names',[]) for row in inventory()):raise ValueError('Containername ist bereits vergeben.')
            port=port_check(data['port'],str(data.get('bind','127.0.0.1'))) if data.get('port') else None
            if port and not port['available']:raise ValueError('Host-Port ist bereits belegt.')
            readonly=data.get('readonly') is True;clone_spec(info,new,port,readonly)
            p.update(name=new,port=port['port'] if port else None,bind=port['bind'] if port else '127.0.0.1',readonly=readonly,
                shared_mounts=[{'source':r.get('Name') if r['Type']=='volume' else r['Source'],'target':r['Destination'],'read_only':True}
                    for r in info.get('Mounts',[]) if readonly and r['Type'] in {'bind','volume'}])
        if op=='lab_env':
            if info.get('State',{}).get('Paused') or info.get('State',{}).get('Restarting'):raise ValueError('Pausierte oder neu startende Container zuerst stabilisieren.')
            changed=updates(data.get('env_updates'))
            if (info['Config'].get('Labels') or {}).get('com.docker.compose.project'):
                if any(value is None for value in changed.values()):raise ValueError('Compose-Variablen hier mit einem Wert überschreiben; für Entfernen die ursprüngliche Compose-Datei bearbeiten.')
                composed=validate({'operation':'lab_compose','container':value})
                override=core.local_path(str(Path(composed['directory'])/'serverlotse-environment.override.json'),existing=False)
                if override.exists():
                    if override.stat().st_uid!=0 or override.stat().st_mode&0o022:raise ValueError('Override-Datei ist nicht root-geschützt.')
                    old=json.loads(override.read_text(encoding='utf-8'))
                    if old.get('x-serverlotse-environment') is not True:raise ValueError('Vorhandene fremde Override-Datei wird nicht überschrieben.')
                p.update({key:val for key,val in composed.items() if key not in {'operation','source_hash','container'}})
                p.update(compose=True,override=str(override),override_hash=advanced.file_hash(override))
            else:
                clone_spec(info,info['Name'].lstrip('/'),env_updates=changed);p['compose']=False
            p.update(env_updates=changed,was_running=bool(info.get('State',{}).get('Running')))
        if op=='lab_compose':
            labels=info['Config'].get('Labels') or {};directory=core.local_path(labels.get('com.docker.compose.project.working_dir',''))
            core.private_destination(directory)
            files=[str(core.local_path(x)) for x in labels.get('com.docker.compose.project.config_files','').split(',') if x]
            if not files or len(files)>5:raise ValueError('Compose-Dateien nicht eindeutig gefunden.')
            for filename in files:
                path=Path(filename);core.private_destination(path.parent)
                if path.stat().st_uid!=0 or path.stat().st_mode&0o022:raise ValueError('Compose-Dateien müssen root-geschützt sein.')
            service=labels.get('com.docker.compose.service','');project=labels.get('com.docker.compose.project','')
            if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',service) or not re.fullmatch(r'[a-z0-9_-]{1,80}',project):raise ValueError('Ungültige Compose-Metadaten.')
            p.update(directory=str(directory),files=files,service=service,project=project,
                file_hashes=[advanced.file_hash(Path(x)) for x in files],env_hash=advanced.file_hash(directory/'.env'))
        return p
    if op=='lab_dotenv':
        path,text,_=dotenv(data.get('path'));return {'operation':op,'path':str(path),'file_hash':fingerprint(text),'env_updates':updates(data.get('env_updates'))}
    if op=='lab_template':return template_plan(data)
    raise ValueError('Unbekannte Docker-Erweiterung.')


def apply(plan):
    op=plan['operation']
    if op=='lab_janitor':
        targets=plan['targets']
        for row in targets['containers']:api('DELETE','/containers/'+row['id'])
        for volume in targets['volumes']:api('DELETE','/volumes/'+quote(volume,safe=''))
        for network in targets['networks']:api('DELETE','/networks/'+network)
        for row in targets['images']:
            tags=[x for x in row['tags'] if x!='<none>:<none>'] or [row['id']]
            for tag in tags:api('DELETE','/images/'+quote(tag,safe=''))
        core.command(['docker','builder','prune','--all','--force'],timeout=600)
        return {'note':'Nur bestätigte Ressourcen entfernt; Build-Cache bereinigt. Teilaktionen sind bei Fehlern nicht rückgängig zu machen.',
                'counts':{key:len(value) for key,value in targets.items()}}
    if op=='lab_registry':
        import registry_check
        info=inspect(plan['container']);result=registry_check.check(info)
        advanced.state('registry:'+plan['container'],{**result,'time':time.time()});return result
    if op=='lab_template':
        dest=Path(plan['destination']);dest.mkdir(mode=0o700)
        advanced.atomic_write(dest/'compose.yaml',(json.dumps(plan['compose'],indent=2)+'\n').encode(),0o600)
        advanced.atomic_write(dest/'.env',('DB_ROOT_PASSWORD='+secrets.token_urlsafe(32)+'\nDB_PASSWORD='+secrets.token_urlsafe(32)+'\n').encode(),0o600)
        if plan['template']=='nginx':
            (dest/'html').mkdir(mode=0o755);advanced.atomic_write(dest/'html/index.html',b'<!doctype html><title>ServerLotse</title><h1>Nginx ist bereit.</h1>\n',0o644)
        prefix=['docker','compose','--project-directory',str(dest),'--env-file',str(dest/'.env'),'-f',str(dest/'compose.yaml')]
        core.command([*prefix,'config','--quiet']);core.command([*prefix,'up','-d'],timeout=900)
        return {'directory':str(dest),'note':'Vorlage gestartet. Einrichtungsassistent der App abschließen. Zugangsdaten liegen root-geschützt in .env. Projekte werden nicht automatisch gelöscht.'}
    if op=='lab_dotenv':
        path,text,_=dotenv(plan['path']);backup=core.STATE/('dotenv-'+secrets.token_hex(8)+'.bak')
        advanced.atomic_write(backup,text.encode(),0o600);lines=[];remaining=dict(plan['env_updates'])
        for old in text.splitlines():
            key=old.partition('=')[0]
            if key in remaining:
                val=remaining.pop(key)
                if val is not None:lines.append(dotenv_line(key,val))
            else:lines.append(old)
        lines.extend(dotenv_line(k,v) for k,v in remaining.items() if v is not None)
        advanced.atomic_write(path,('\n'.join(lines)+'\n').encode(),0o600)
        return {'backup':str(backup),'note':'.env gespeichert. Laufende Container übernehmen Änderungen erst nach einer erneuten Bereitstellung.'}
    if op=='lab_compose':
        args=['docker','compose','--project-directory',plan['directory'],'--project-name',plan['project']]
        for file in plan['files']:args+=['-f',file]
        try:core.command([*args,'config','--quiet']);core.command([*args,'up','-d','--no-deps',plan['service']],timeout=900)
        except Exception:raise ValueError('Compose-Bereitstellung fehlgeschlagen. Dienstzustand prüfen; rohe Konfigurationsfehler werden wegen möglicher Zugangsdaten nicht gespeichert.') from None
        return {'note':'Compose-Dienst neu bereitgestellt. An Container-IDs gebundene Backup-/Heiler-Ziele prüfen.'}
    info=inspect(plan['container'])
    if op=='lab_clone':
        port={'port':plan['port'],'bind':plan['bind']} if plan['port'] else None
        spec=clone_spec(info,plan['name'],port,plan['readonly'])
        result=api('POST','/containers/create?name='+quote(plan['name']),spec);created=ident(result['Id'])
        api('POST','/containers/'+created+'/start')
        return {'container':created,'note':'Klon gestartet. Volumes sind leer beziehungsweise ausdrücklich nur lesend geteilt. Anwendungsbereitschaft separat prüfen.'}
    if op=='lab_env':
        if plan.get('compose'):
            path=Path(plan['override']);old=path.read_bytes() if path.exists() else None
            document=json.loads(old) if old else {'x-serverlotse-environment':True,'services':{}}
            service=document.setdefault('services',{}).setdefault(plan['service'],{})
            service.setdefault('environment',{}).update({key:value.replace('$','$$') for key,value in plan['env_updates'].items()})
            advanced.atomic_write(path,(json.dumps(document,indent=2)+'\n').encode(),0o600)
            args=['docker','compose','--project-directory',plan['directory'],'--project-name',plan['project']]
            for filename in [*plan['files'],*([str(path)] if str(path) not in plan['files'] else [])]:args+=['-f',filename]
            try:
                core.command([*args,'config','--quiet']);core.command([*args,'up','-d','--no-deps',plan['service']],timeout=900)
            except Exception:
                if old is None:path.unlink()
                else:advanced.atomic_write(path,old,0o600)
                raise ValueError('Compose-Änderung fehlgeschlagen; Override-Datei zurückgenommen. Laufenden Dienst prüfen; bereits ausgeführte Datenänderungen sind nicht automatisch rückgängig.') from None
            return {'override':str(path),'note':'Compose-Umgebung über eigene root-geschützte Override-Datei geändert. Originaldateien bleiben erhalten. Künftige Bereitstellungen müssen diese Override-Datei mitverwenden; Portainer kann sie sonst übergehen. App-Bereitschaft und Backup-/Heiler-IDs prüfen.'}
        original=info['Name'].lstrip('/');backup=original+'-before-'+secrets.token_hex(4)
        spec=clone_spec(info,original,env_updates=plan['env_updates']);created=None;renamed=False
        if plan['was_running']:api('POST','/containers/'+plan['container']+'/stop?t=30')
        try:
            api('POST','/containers/'+plan['container']+'/rename?name='+quote(backup));renamed=True
            created=ident(api('POST','/containers/create?name='+quote(original),spec)['Id'])
            if plan['was_running']:
                api('POST','/containers/'+created+'/start');time.sleep(2)
                if not inspect(created,False).get('State',{}).get('Running'):raise ValueError('Neuer Container ist nicht gestartet.')
            advanced.state('suppressed:'+plan['container'],True)
            return {'container':created,'previous':backup,'note':'Container ersetzt; vorheriger Container bleibt gestoppt zur Rücknahme erhalten. App-/Healthcheck und Backup-/Heiler-IDs prüfen. Änderungen an geteilten Daten sind nicht rückgängig gemacht.'}
        except Exception:
            if created:
                try:
                    if inspect(created,False).get('State',{}).get('Running'):api('POST','/containers/'+created+'/stop?t=10')
                except Exception:pass
                try:api('DELETE','/containers/'+created)
                except Exception:pass
            if renamed:
                try:api('POST','/containers/'+plan['container']+'/rename?name='+quote(original))
                except Exception:pass
            if plan['was_running']:
                try:api('POST','/containers/'+plan['container']+'/start')
                except Exception:pass
            raise ValueError('Ersetzen fehlgeschlagen; Rücknahme versucht. Containerzustand prüfen. Daten-Volumes wurden nicht gelöscht.') from None
    raise ValueError('Unbekannte Docker-Erweiterung.')


def sample():
    global LATEST,LAST_ERROR
    raw=core.command(['docker','stats','--no-stream','--no-trunc','--format','{{json .}}'],timeout=25)
    rows=[];now=time.time()
    invalid=0
    for line in raw.splitlines()[:100]:
        item=json.loads(line);value=item.get('ID') or item.get('Container','')
        if not ID.fullmatch(value):continue
        try:cpu=float(item['CPUPerc'].rstrip('%'));memory=float(item['MemPerc'].rstrip('%'))
        except (ValueError,KeyError):invalid+=1;continue
        if not math.isfinite(cpu) or not math.isfinite(memory):invalid+=1;continue
        row={'id':value,'name':item.get('Name',value[:12]),'cpu':max(0,cpu),
             'memory_percent':max(0,min(100,memory)),'memory':item.get('MemUsage',''),'time':now}
        rows.append(row)
    with LOCK:
        LATEST=rows;LAST_ERROR='Einzelne Docker-Messwerte sind nicht verfügbar.' if invalid else ''
        for row in rows:HISTORY.setdefault(row['id'],deque(maxlen=240)).append(row)
        for value in list(HISTORY):
            if not HISTORY[value] or now-HISTORY[value][-1]['time']>3600:del HISTORY[value]


def monitor():
    global LAST_ERROR
    while True:
        try:sample()
        except Exception as exc:
            with LOCK:LAST_ERROR='Docker-Messung fehlgeschlagen: '+type(exc).__name__
        time.sleep(15)


def read(data):
    view=data['view']
    if view=='lab_docker':
        rows=inventory()
        selected=data.get('history_container') or (rows[0]['Id'] if rows else '')
        with LOCK:stats=copy.deepcopy(LATEST);history={selected:list(HISTORY.get(selected,[]))};error=LAST_ERROR
        return {'rows':[{'id':r['Id'],'name':(r.get('Names') or [r['Id'][:12]])[0].lstrip('/'),'state':r.get('State'),
                         'status':r.get('Status'),'image':r.get('Image'),'protected':protected(r),
                         'update':advanced.state('registry:'+r['Id'])} for r in rows],
                'stats':stats,'history':history,'error':error,'note':'CPU: 100 % entspricht einem Kern. Bis zu 240 Messpunkte im RAM, ungefähr alle 15–30 Sekunden; nach Helferneustart leer.'}
    if view=='lab_environment':return environment(inspect(data.get('container')))
    if view=='lab_health':
        info=inspect(data.get('container'),False);state=info['State'];health=state.get('Health') or {}
        return {'started':state.get('StartedAt'),'restarts':info.get('RestartCount'),'oom':state.get('OOMKilled'),
                'health':health.get('Status','Kein HEALTHCHECK'),'failing':health.get('FailingStreak',0),
                'checks':[{key:r.get(key) for key in ['Start','End','ExitCode']} for r in health.get('Log',[])][-5:]}
    if view=='lab_networks':return networks()
    if view=='lab_ports':return port_check(data.get('port'),str(data.get('bind','127.0.0.1')))
    if view=='lab_dotenv':
        path,text,values=dotenv(data.get('path'))
        return {'path':str(path),'rows':[{'key':key,'value':'••••••','masked':True} for key in values]}
    raise ValueError('Unbekannte Docker-Ansicht.')
