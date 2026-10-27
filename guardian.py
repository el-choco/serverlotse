import copy
import datetime
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
import admin_core as core
import advanced
import sensors
import docker_tools
import toolkit

DEFAULTS={'enabled':False,'fim':False,'fim_paths':['/etc/passwd','/etc/group'],
          'certificates':False,'certificate_dirs':[],'http':False,'http_targets':[],'oom':False,'logrotate':False,'rotation_configs':[],
          'log_megabytes':500,'speedtest':False,'speedtest_hours':24,'speedtest_consent':False,'speedtest_driver':'community','peak_cpu':90}
LAST={};CPU_PREVIOUS={};COLLECT_LOCK=threading.Lock()
OPS={'lab_settings','lab_baseline','lab_session_end','lab_http','lab_speedtest','lab_rotate'}


def config():return {**copy.deepcopy(DEFAULTS),**(advanced.state('guardian_config') or {})}


def remembered(key,item,limit=200):
    rows=advanced.state(key) or [];rows.append(item);advanced.state(key,rows[-limit:])


def public_config():
    cfg=config();cfg['configuration_hash']=docker_tools.fingerprint(cfg);return cfg


def target_url(value):
    if not isinstance(value,str) or len(value)>500:raise ValueError('Ungültige HTTP-Adresse.')
    parsed=urlsplit(value)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('HTTP(S)-Adresse ohne Zugangsdaten, Abfrageparameter oder Fragment angeben.')
    if parsed.port is not None and not 1<=parsed.port<=65535:raise ValueError('Ungültiger HTTP-Port.')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def http_check(url,expected=200):
    target_url(url);started=time.monotonic();status=None;error=''
    try:
        with build_opener(NoRedirect).open(Request(url,headers={'User-Agent':'ServerLotse/0.7.0'}),timeout=10) as response:
            status=response.status;response.read(1024)
    except HTTPError as exc:status=exc.code;exc.close()
    except OSError:error='Verbindung oder TLS-Prüfung fehlgeschlagen.'
    return {'url':url,'status':status,'expected':expected,'ok':status==expected,'milliseconds':round((time.monotonic()-started)*1000),
            'error':error,'time':time.time(),'note':'GET vom Host, keine Weiterleitungen; kein unabhängiger externer Messpunkt.'}


def normalize(data):
    if not isinstance(data,dict):raise ValueError('Ungültige Wächter-Einstellungen.')
    cfg=config()
    for key in ['enabled','fim','certificates','http','oom','logrotate','speedtest','speedtest_consent']:
        if key in data:cfg[key]=data[key] is True
    for key,low,high in [('log_megabytes',100,100000),('speedtest_hours',6,168),('peak_cpu',30,100)]:
        cfg[key]=int(data.get(key,cfg[key]))
        if not low<=cfg[key]<=high:raise ValueError('Ungültiger Wächter-Grenzwert.')
    paths=data.get('fim_paths',cfg['fim_paths'])
    if not isinstance(paths,list) or not 1<=len(paths)<=10:raise ValueError('1–10 FIM-Pfade angeben.')
    cfg['fim_paths']=[]
    for value in paths:
        path=core.local_path(str(value),existing=cfg['enabled'] and cfg['fim'])
        if not (path==Path('/etc') or Path('/etc') in path.parents):raise ValueError('FIM ist auf /etc begrenzt.')
        cfg['fim_paths'].append(str(path))
    certificate_dirs=data.get('certificate_dirs',cfg['certificate_dirs'])
    if not isinstance(certificate_dirs,list) or len(certificate_dirs)>10:raise ValueError('Höchstens zehn zusätzliche Zertifikatsordner wählen.')
    cfg['certificate_dirs']=[]
    for value in certificate_dirs:
        path=core.local_path(str(value),existing=cfg['enabled'] and cfg['certificates'])
        if (path.exists() and not path.is_dir()) or len(path.parts)<3 or path.parts[1] in {'proc','sys','dev'}:raise ValueError('Einen konkreten Zertifikatsunterordner wählen.')
        cfg['certificate_dirs'].append(str(path))
    checks=data.get('http_targets',cfg['http_targets'])
    if not isinstance(checks,list) or len(checks)>10:raise ValueError('Höchstens zehn HTTP-Ziele angeben.')
    cfg['http_targets']=[]
    for row in checks:
        status=int(row.get('expected',200))
        if not 100<=status<=599:raise ValueError('Ungültiger erwarteter HTTP-Status.')
        cfg['http_targets'].append({'url':target_url(row.get('url')),'expected':status})
    selected=data.get('rotation_configs',cfg['rotation_configs'])
    if not isinstance(selected,list) or len(selected)>10:raise ValueError('Höchstens zehn Logrotate-Konfigurationen wählen.')
    old_rotations={row['path']:row['hash'] for row in config()['rotation_configs']}
    cfg['rotation_configs']=[]
    for row in selected:
        value=row['path'] if isinstance(row,dict) else row
        if not cfg['enabled'] and value in old_rotations:
            cfg['rotation_configs'].append({'path':value,'hash':old_rotations[value]});continue
        path=rotation_path(value)
        cfg['rotation_configs'].append({'path':str(path),'hash':advanced.file_hash(path)})
    driver=data.get('speedtest_driver',cfg['speedtest_driver'])
    if driver not in {'community','ookla'}:raise ValueError('Unbekannter Speedtest-Anbieter.')
    cfg['speedtest_driver']=driver
    if cfg['enabled'] and cfg['speedtest'] and (not cfg['speedtest_consent'] or not shutil.which('speedtest-cli' if driver=='community' else 'speedtest')):
        raise ValueError('Zeitgesteuerter Speedtest benötigt die vorhandene Ookla-CLI und ausdrückliche Zustimmung zu Bedingungen und Datenübertragung.')
    return cfg


def fim_snapshot(paths):
    files={};skipped=[];total=0
    for value in paths:
        path=core.local_path(value)
        candidates=[path] if path.is_file() else (Path(base)/name for base,dirs,names in os.walk(path,followlinks=False)
            for name in [*names,*(directory for directory in dirs if (Path(base)/directory).is_symlink())])
        for candidate in candidates:
            if len(files)>=2000:raise ValueError('FIM-Auswahl enthält mehr als 2000 Dateien; kleinere Ordner wählen.')
            try:
                info=candidate.lstat()
                if stat.S_ISLNK(info.st_mode):
                    files[str(candidate)]={'symlink':hashlib.sha256(os.readlink(candidate).encode()).hexdigest(),
                        'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
                    continue
                fd=core.secure_open(candidate,os.O_RDONLY|os.O_NONBLOCK)
                with os.fdopen(fd,'rb') as stream:
                    info=os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size>32*1024*1024:
                        skipped.append(str(candidate));continue
                    total+=info.st_size
                    if total>256*1024*1024:raise ValueError('FIM-Auswahl ist größer als 256 MiB; Auswahl verkleinern.')
                    digest=hashlib.sha256();read=0
                    while chunk:=stream.read(1024*1024):
                        read+=len(chunk)
                        if read>32*1024*1024:raise ValueError('FIM-Datei wächst während der Prüfung.')
                        digest.update(chunk)
                    after=os.fstat(stream.fileno())
                    if (info.st_size,info.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('FIM-Datei verändert sich während der Prüfung.')
                    files[str(candidate)]={'sha256':digest.hexdigest(),'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
            except OSError:skipped.append(str(candidate))
    return {'files':files,'skipped':skipped[:100]}


def fim_diff(before,after):
    return [{'path':key,'change':'neu' if key not in before else 'entfernt' if key not in after else 'verändert'}
            for key in sorted(set(before)|set(after)) if before.get(key)!=after.get(key)]


def certificates():
    if not shutil.which('openssl'):raise ValueError('openssl fehlt. Unter Datei- und Dienstwächter über den Werkzeugdialog installieren.')
    paths=[];scanned=0;docker_note=''
    extra_dirs=set(map(Path,config()['certificate_dirs']))
    roots=[(Path('/etc/letsencrypt/live'),Path('/etc/letsencrypt')),
           (Path('/var/lib/caddy/.local/share/caddy/certificates'),Path('/var/lib/caddy')), (Path('/etc/nginx'),Path('/etc/nginx'))]
    for value in extra_dirs:roots.append((value,value))
    try:
        for row in docker_tools.inventory():
            for mount in row.get('Mounts',[]):
                source=Path(mount.get('Source','/'));destination=mount.get('Destination','')
                if len(source.parts)<3:continue
                if destination=='/etc/letsencrypt':roots.append((source/'live',source))
                if destination=='/data':roots.append((source/'caddy/certificates',source/'caddy/certificates'))
    except ValueError:docker_note=' Docker-Ablagen konnten nicht vollständig geprüft werden.'
    unique_roots=list(dict.fromkeys(roots))
    for base,allowed in unique_roots:
        if not base.exists():continue
        for parent,dirs,files in os.walk(base,followlinks=False):
            if len(Path(parent).relative_to(base).parts)>10:dirs[:]=[];continue
            for name in files:
                scanned+=1
                if scanned>5000:raise ValueError('Zertifikatsauswahl enthält mehr als 5000 Dateien; konkrete Unterordner wählen.')
                path=Path(parent)/name
                if name=='fullchain.pem' or name.endswith('.crt') or base in extra_dirs and name.endswith('.pem'):paths.append((path,allowed))
                if len(paths)>300:raise ValueError('Mehr als 300 Zertifikatsdateien; Prüfung begrenzen.')
    rows=[];seen=set()
    for path,allowed in paths:
        try:
            resolved=path.resolve(strict=True)
            allowed=allowed.resolve(strict=True)
            if not (allowed==resolved or allowed in resolved.parents):continue
            if resolved.stat().st_size>256000:continue
            text=core.command(['openssl','x509','-in',str(resolved),'-noout','-enddate','-subject','-fingerprint','-sha256'],timeout=8)
            end=next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('notAfter='))
            expires=datetime.datetime.strptime(end,'%b %d %H:%M:%S %Y %Z').replace(tzinfo=datetime.timezone.utc).timestamp()
            fingerprint=next(line for line in text.splitlines() if 'Fingerprint=' in line)
            if fingerprint in seen:continue
            seen.add(fingerprint)
            rows.append({'path':str(path),'subject':next((line[8:] for line in text.splitlines() if line.startswith('subject=')),''),
                'expires':expires,'days':int((expires-time.time())//86400),'fingerprint':fingerprint})
        except (OSError,ValueError,StopIteration):continue
    advanced.state('certificates_latest',rows)
    return {'rows':rows,'note':'Native und anhand von Docker-Mounts erkannte Let’s-Encrypt-/Caddy-Zertifikate sowie eigene Zertifikatsordner. Keine privaten Schlüssel werden angezeigt.'+docker_note}


def wear_value(data):
    nvme=data.get('nvme_smart_health_information_log') or {}
    if isinstance(nvme.get('percentage_used'),(int,float)) and math.isfinite(nvme['percentage_used']) and 0<=nvme['percentage_used']<=255:
        used=nvme['percentage_used'];return {'remaining':max(0,100-used),'used':used,'source':'NVMe Percentage Used','estimated':True}
    for row in (data.get('ata_smart_attributes') or {}).get('table',[]):
        if re.fullmatch(r'(Media_Wearout_Indicator|Percent_Lifetime_Remain|SSD_Life_Left)',row.get('name','')) and isinstance(row.get('value'),(int,float)) and 0<=row['value']<=100:
            return {'remaining':row['value'],'source':row['name'],'estimated':True}
    return {'remaining':None,'source':'Kein eindeutig interpretierbarer Verschleißwert','estimated':True}


def disks():
    rows=[]
    for disk in [row for row in core.disks()['rows'] if row['type']=='disk'][:8]:
        try:
            data=core.smart(disk['path']);rows.append({'path':disk['path'],'model':disk.get('model'),
                'passed':data.get('smart_status',{}).get('passed'),**wear_value(data)})
        except (ValueError,OSError):rows.append({'path':disk['path'],'remaining':None,'source':'SMART nicht verfügbar'})
    advanced.state('wear_latest',rows)
    return {'rows':rows,'note':'Endurance-Schätzung des Herstellers, keine vorhergesagte Lebensdauer oder Ausfallgarantie. Unbekannte SATA-Attribute werden nicht geraten.'}


def sessions():
    ids=core.command(['loginctl','list-sessions','--no-legend','--no-pager'],timeout=10)
    rows=[]
    for line in ids.splitlines()[:100]:
        value=line.split()[0]
        if not re.fullmatch(r'[a-zA-Z0-9]{1,30}',value):continue
        raw=core.command(['loginctl','show-session',value,'--no-pager','--property=Id,Name,User,Remote,RemoteHost,TTY,Service,Leader,State,Timestamp,Type'],timeout=8)
        row=dict(item.split('=',1) for item in raw.splitlines() if '=' in item)
        if row.get('Service') in {'sshd','ssh','login','dropbear'} and row.get('Type') in {'tty','unspecified'}:rows.append(row)
    import terminal_host
    with terminal_host.LOCK:
        terminals=[{'id':value.ident,'type':'ServerLotse-Terminal','age':round(time.monotonic()-value.born)} for value in terminal_host.SESSIONS.values() if not value.closed]
    return {'rows':rows,'terminals':terminals,'note':'loginctl-Sitzungen und ServerLotse-Terminals. Die eigene Admin-Sitzung kann getrennt werden; SSH-Keys und Konten bleiben unverändert.'}


def rotation_path(value):
    value=str(value)
    if not re.fullmatch(r'/etc/logrotate\.d/[A-Za-z0-9_.-]{1,80}',value):raise ValueError('Eine vorhandene Datei direkt unter /etc/logrotate.d wählen.')
    path=core.local_path(value);core.private_destination(path.parent)
    if not path.is_file() or path.stat().st_uid!=0 or path.stat().st_mode&0o022 or path.stat().st_size>128000:
        raise ValueError('Logrotate-Konfiguration ist nicht root-geschützt oder zu groß.')
    return path


def rotation_matches(path):
    patterns=re.findall(r'(?m)(?:^|\s)(/var/log/[^\s{};]+)',path.read_text())
    files=[]
    for pattern in patterns[:50]:
        if '..' in Path(pattern).parts:continue
        for filename in glob.glob(pattern)[:500]:
            try:
                file=core.local_path(filename)
                if file.is_file() and not file.is_symlink():files.append({'path':str(file),'bytes':file.stat().st_size})
            except (ValueError,OSError):pass
    return files


def log_sizes():
    rows=[];scanned=0
    for directory,dirs,files in os.walk('/var/log',followlinks=False):
        for name in files:
            scanned+=1
            if scanned>10000:break
            path=Path(directory)/name
            try:
                info=path.lstat()
                if stat.S_ISREG(info.st_mode):rows.append({'path':str(path),'bytes':info.st_size})
            except OSError:pass
        if scanned>10000:break
    return {'rows':sorted(rows,key=lambda row:row['bytes'],reverse=True)[:30],'available':bool(shutil.which('logrotate')),
            'configs':[str(p) for p in Path('/etc/logrotate.d').glob('*') if p.is_file() and not p.is_symlink()][:100],
            'note':'Rotation führt die vorhandene root-geschützte Richtlinie inklusive ihrer Hooks aus. Komprimierung richtet sich nach dieser Richtlinie; kein blindes Leeren offener Logs.'}


def speedtest(driver='community'):
    try:
        binary=shutil.which('speedtest-cli' if driver=='community' else 'speedtest')
        if not binary:raise ValueError('Speedtest-CLI fehlt.')
        args=[binary,'--secure','--json'] if driver=='community' else [binary,'--accept-license','--accept-gdpr','--format=json']
        result=json.loads(core.command(args,timeout=180))
        if driver=='ookla' and result.get('type')!='result':raise ValueError('Kein Ookla-Ergebnis.')
        row={'time':time.time(),'driver':driver,'ping':result['ping'] if driver=='community' else result['ping']['latency'],
             'download_mbps':result['download']/1e6 if driver=='community' else result['download']['bandwidth']*8/1e6,
             'upload_mbps':result['upload']/1e6 if driver=='community' else result['upload']['bandwidth']*8/1e6,
             'server':result.get('server',{}).get('name','')}
        if any(not isinstance(row[key],(int,float)) or not math.isfinite(row[key]) or row[key]<0 for key in ['ping','download_mbps','upload_mbps']):raise ValueError('Ungültiger Messwert.')
    except Exception:raise ValueError('Speedtest fehlgeschlagen. Vorhandene Ookla-CLI und Netzwerk prüfen; Rohdaten werden nicht gespeichert.') from None
    remembered('speedtest_history',row,100);return row


def validate(data):
    op=data['operation']
    if op=='lab_settings':return {'operation':op,'settings':normalize(data.get('settings')),'configuration_hash':docker_tools.fingerprint(config())}
    if op=='lab_baseline':
        cfg=config();snapshot=fim_snapshot(cfg['fim_paths'])
        return {'operation':op,'paths':cfg['fim_paths'],'snapshot':snapshot,'file_count':len(snapshot['files']),'configuration_hash':docker_tools.fingerprint(cfg)}
    if op=='lab_session_end':
        if data.get('kind')=='terminal':
            import terminal_host
            value=str(data.get('session'))
            with terminal_host.LOCK:
                session=terminal_host.SESSIONS.get(value)
                if not session or session.closed:raise ValueError('Terminalsitzung nicht mehr vorhanden.')
                return {'operation':op,'kind':'terminal','session':value,'born':session.born}
        value=str(data.get('session'));row=next((row for row in sessions()['rows'] if row.get('Id')==value),None)
        if not row:raise ValueError('Anmeldesitzung nicht mehr gefunden.')
        return {'operation':op,'session':value,'leader':row.get('Leader'),'timestamp':row.get('Timestamp'),'user':row.get('Name'),'service':row.get('Service')}
    if op=='lab_http':
        status=int(data.get('expected',200))
        if not 100<=status<=599:raise ValueError('Ungültiger HTTP-Status.')
        return {'operation':op,'url':target_url(data.get('url')),'expected':status}
    if op=='lab_speedtest':
        driver=data.get('driver','community')
        if driver not in {'community','ookla'} or data.get('consent') is not True or not shutil.which('speedtest-cli' if driver=='community' else 'speedtest'):
            raise ValueError('Gewählte Speedtest-CLI und Zustimmung zu Bedingungen und Datenübertragung erforderlich.')
        return {'operation':op,'consent':True,'driver':driver}
    if op=='lab_rotate':
        path=rotation_path(data.get('path'));core.command(['logrotate','--debug',str(path)],timeout=30)
        return {'operation':op,'path':str(path),'file_hash':advanced.file_hash(path),'logs':[row['path'] for row in rotation_matches(path)]}
    raise ValueError('Unbekannte Wächter-Aktion.')


def apply(plan):
    op=plan['operation']
    if op=='lab_settings':
        before=config();advanced.state('guardian_config',plan['settings'])
        advanced.state('guardian_last_error',{})
        if before['fim_paths']!=plan['settings']['fim_paths']:advanced.state('fim_baseline',{})
        return {'note':'Wächter gespeichert. Neue Automatiken wirken erst mit eigenem Hauptschalter; Webhook-Ziel stammt aus Automatik und Meldungen.'}
    if op=='lab_baseline':
        if plan['snapshot']['skipped']:raise ValueError('Nicht alle FIM-Dateien lesbar. Auswahl und Rechte prüfen; unvollständige Basis wird nicht übernommen.')
        advanced.state('fim_baseline',{'time':time.time(),'paths':plan['paths'],'files':plan['snapshot']['files']})
        advanced.state('fim_changes',[]);return {'files':len(plan['snapshot']['files']),'note':'Aktueller Zustand als Vergleichsbasis übernommen. Künftige Änderungen benötigen eine eigene Bewertung.'}
    if op=='lab_session_end':
        if plan.get('kind')=='terminal':
            import terminal_host
            with terminal_host.LOCK:
                session=terminal_host.SESSIONS.get(plan['session'])
                if not session or session.born!=plan['born']:raise ValueError('Terminalsitzung hat sich verändert.')
                session.close();terminal_host.SESSIONS.pop(plan['session'],None)
            return {'note':'Die ausgewählte ServerLotse-Terminalsitzung wurde beendet. Es wurde keine Terminalausgabe gelesen.'}
        core.command(['loginctl','terminate-session',plan['session']],timeout=30)
        return {'note':'Anmeldesitzung beendet. Nicht verwaltete Hintergrundprozesse können weiterlaufen.'}
    if op=='lab_http':
        result=http_check(plan['url'],plan['expected']);remembered('http_results',result,100);return result
    if op=='lab_speedtest':return speedtest(plan['driver'])
    if op=='lab_rotate':
        core.command(['logrotate','--force',plan['path']],timeout=300)
        return {'note':'Vorhandene Rotationsrichtlinie ausgeführt. Dienst- und Logzustand prüfen.'}
    raise ValueError('Unbekannte Wächter-Aktion.')


def cpu_snapshot(now):
    rows=[];ticks=os.sysconf('SC_CLK_TCK');page=os.sysconf('SC_PAGE_SIZE');seen=set()
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        try:
            row=sensors.parse_process((directory/'stat').read_text(),int(directory.name),directory.stat().st_uid,page)
            before=CPU_PREVIOUS.get(row['pid']);CPU_PREVIOUS[row['pid']]=(row['start'],row['ticks'],now);seen.add(row['pid'])
            row['cpu']=max(0,(row['ticks']-before[1])/ticks/(now-before[2])*100) if before and before[0]==row['start'] and now>before[2] else None
            row.pop('ticks');rows.append(row)
        except (ValueError,OSError,IndexError):pass
    for pid in list(CPU_PREVIOUS):
        if pid not in seen:CPU_PREVIOUS.pop(pid,None)
    return sorted([r for r in rows if r['cpu'] is not None],key=lambda r:r['cpu'],reverse=True)[:5]


def collect_oom(now):
    since=int(LAST.get('oom_since',now-300));LAST['oom_since']=now
    raw=core.command(['journalctl','-k','--since','@'+str(since),'--no-pager','-n','300','-o','short-iso'],timeout=15)
    rows=advanced.state('oom_events') or [];keys={row['key'] for row in rows}
    for line in raw.splitlines():
        if re.search(r'Out of memory:|oom-kill:|Killed process \d+',line,re.I):
            key=docker_tools.fingerprint(line)
            if key not in keys:rows.append({'key':key,'time':now,'source':'Kernel','text':toolkit.redact(line)});keys.add(key)
    for item in docker_tools.inventory():
        info=docker_tools.inspect(item['Id'],False);state=info.get('State',{})
        if state.get('OOMKilled'):
            key=docker_tools.fingerprint([item['Id'],state.get('FinishedAt')])
            if key not in keys:rows.append({'key':key,'time':now,'source':'Docker','text':info['Name'].lstrip('/')+' · OOMKilled=true · '+state.get('FinishedAt','')});keys.add(key)
    advanced.state('oom_events',rows[-200:]);return rows


def tick(now=None):
    now=time.time() if now is None else now
    if not COLLECT_LOCK.acquire(blocking=False):return
    try:
        cfg=config()
        if not cfg['enabled']:return
        import automation
        alerts=advanced.config(True)
        def alert(key,text):automation.alert('guardian:'+key,text,alerts,now)
        if now-LAST.get('checks',0)>=60:
            LAST['checks']=now
            if cfg['fim']:
                baseline=advanced.state('fim_baseline') or {}
                if baseline.get('files') and baseline.get('paths')==cfg['fim_paths']:
                    after=fim_snapshot(cfg['fim_paths'])
                    if after['skipped']:raise ValueError('FIM-Prüfung unvollständig; Rechte oder Auswahl prüfen.')
                    changes=fim_diff(baseline['files'],after['files']);advanced.state('fim_changes',changes[:2000])
                    if changes:alert('fim',str(len(changes))+' Systemdateien weichen von der bestätigten FIM-Basis ab. Ursache prüfen; nicht automatisch als Angriff gewertet.')
            if cfg['http']:
                results=[]
                for target in cfg['http_targets']:
                    result=http_check(target['url'],target['expected']);results.append(result)
                    if not result['ok']:alert('http:'+docker_tools.fingerprint(target),target['url']+' liefert '+str(result['status'])+' statt '+str(target['expected']))
                advanced.state('http_latest',results)
            if cfg['oom']:
                before={r['key'] for r in advanced.state('oom_events') or []};events=collect_oom(now)
                fresh=[r for r in events if r['key'] not in before]
                if fresh:alert('oom',str(len(fresh))+' neue OOM-Meldungen. RAM, Swap und Container-Limits prüfen.')
            if cfg['logrotate'] and not core.MUTEX.locked() and core.POWER_UNTIL<=now:
                for row in cfg['rotation_configs']:
                    path=rotation_path(row['path'])
                    if advanced.file_hash(path)!=row['hash']:raise ValueError('Rotationsrichtlinie verändert. Wächter-Einstellungen neu bestätigen.')
                    if any(r['bytes']>=cfg['log_megabytes']*1024**2 for r in rotation_matches(path)) and now-(advanced.state('rotated:'+str(path)) or 0)>3600:
                        core.enqueue(core.validate({'operation':'lab_rotate','path':str(path)}));advanced.state('rotated:'+str(path),now);break
        if cfg['certificates'] and now-LAST.get('certificates',0)>=3600:
            LAST['certificates']=now
            for row in certificates()['rows']:
                if row['days']<=14:alert('cert:'+row['fingerprint'],'Zertifikat '+row['subject']+' läuft in '+str(row['days'])+' Tagen ab. Erneuerung prüfen.')
        if cfg['speedtest'] and now-(advanced.state('speedtest_last_run') or 0)>=cfg['speedtest_hours']*3600 and not core.MUTEX.locked() and core.POWER_UNTIL<=now:
            core.enqueue(core.validate({'operation':'lab_speedtest','consent':cfg['speedtest_consent'],'driver':cfg['speedtest_driver']}));advanced.state('speedtest_last_run',now)
    finally:COLLECT_LOCK.release()


def loop():
    while True:
        try:tick()
        except Exception as exc:
            if time.time()-LAST.get('error',0)>900:
                LAST['error']=time.time()
                try:
                    advanced.state('guardian_last_error',{'time':time.time(),'message':toolkit.redact(str(exc))[:1000]})
                    advanced.log_event('guardian','Wächter-Prüfung unvollständig: '+type(exc).__name__,'error')
                except Exception:pass
        time.sleep(5)


def record_cpu(now=None):
    now=time.time() if now is None else now
    top=cpu_snapshot(now)
    with sensors.LOCK:latest=dict(sensors.PREVIOUS.get('latest') or {})
    if now-latest.get('time',0)<30 and (latest.get('cpu') or 0)>=config()['peak_cpu'] and now-LAST.get('peak',0)>=30:
        LAST['peak']=now;remembered('cpu_peaks',{'time':now,'cpu':latest['cpu'],'processes':top})


def process_loop():
    while True:
        try:record_cpu()
        except Exception:pass
        time.sleep(5)


def read(data):
    view=data['view']
    if view=='lab_guardian':return {'settings':public_config(),'fim':advanced.state('fim_changes') or [],'baseline':bool((advanced.state('fim_baseline') or {}).get('files')),'last_error':advanced.state('guardian_last_error') or {},
        'http':advanced.state('http_latest') or advanced.state('http_results') or [],'speedtests':advanced.state('speedtest_history') or [],
        'tools':{key:bool(shutil.which(key)) for key in ['speedtest','speedtest-cli','openssl','logrotate','smartctl']}}
    if view=='lab_sessions':return sessions()
    if view=='lab_certificates':return certificates()
    if view=='lab_disks':return disks()
    if view=='lab_logs':return log_sizes()
    if view=='lab_history':
        warning=''
        if time.time()-LAST.get('oom_read',0)>60:
            LAST['oom_read']=time.time()
            try:collect_oom(time.time())
            except Exception:warning='Kernel- oder Docker-OOM-Prüfung zurzeit unvollständig.'
        return {'peaks':advanced.state('cpu_peaks') or [],'oom':advanced.state('oom_events') or [],'warning':warning,
            'note':'Bis zu 200 Ereignisse dauerhaft begrenzt. CPU-Spitzen sind Stichproben ungefähr alle fünf Sekunden; OOM-Zuordnung nur bei bestätigtem Docker-Status.'}
    if view=='lab_summary':return {'certificates':[{**row,'days':int((row['expires']-time.time())//86400)} for row in advanced.state('certificates_latest') or []],'disks':advanced.state('wear_latest') or []}
    raise ValueError('Unbekannte Wächter-Ansicht.')
