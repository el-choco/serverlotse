"""Host workshop: bounded inspection and explicit, reversible administration."""
import base64
import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import signal
import stat
import time
import admin_core as core
import advanced

OPS={'lab_cache','lab_apt_clean','lab_orphan_end','lab_panic','lab_panic_release',
     'lab_config_write','lab_config_keep','lab_config_undo','lab_cron_create','lab_cron_remove'}
CONFIGS={'nginx':('/etc/nginx/nginx.conf',['nginx','-t'],'nginx.service'),
         'ssh':('/etc/ssh/sshd_config',['sshd','-t'],'ssh.service')}


def hash_bytes(value):return hashlib.sha256(value).hexdigest()


def memory():
    result={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key,_,value=line.partition(':')
        if key in {'MemTotal','MemAvailable','Cached','SReclaimable','Buffers'}:result[key]=int(value.split()[0])*1024
    return result


def inode_radar():
    mounts=core.command(['findmnt','--json','--list','--output','TARGET,FSTYPE,SOURCE'])
    local={'ext2','ext3','ext4','xfs','btrfs','vfat','exfat','ntfs3','f2fs','zfs'};rows=[]
    for item in json.loads(mounts).get('filesystems',[])[:256]:
        if item.get('fstype') not in local:continue
        try:
            value=os.statvfs(item['target']);total=value.f_files;free=value.f_favail
            rows.append({'path':item['target'],'source':item['source'],'total':total,'free':free,
                         'percent':round((total-free)/total*100,1) if total else None})
        except OSError:continue
    return {'rows':rows,'note':'Inodes zählen Dateieinträge. Ein voller Zähler verhindert neue Dateien trotz freier Gigabytes.'}


def describe_cron(fields):
    if fields[0].startswith('@'):
        return {'@reboot':'Beim Systemstart','@daily':'Täglich','@hourly':'Stündlich','@weekly':'Wöchentlich','@monthly':'Monatlich','@yearly':'Jährlich'}.get(fields[0],fields[0])
    if len(fields)!=5:return 'Unbekannter Zeitplan'
    minute,hour,day,month,weekday=fields
    if fields==['*']*5:return 'Jede Minute'
    if minute.startswith('*/') and fields[1:]==['*']*4:return 'Alle '+minute[2:]+' Minuten'
    if minute.isdigit() and hour.isdigit() and fields[2:]==['*']*3:return 'Täglich um '+hour.zfill(2)+':'+minute.zfill(2)
    weekdays={'0':'Sonntag','1':'Montag','2':'Dienstag','3':'Mittwoch','4':'Donnerstag','5':'Freitag','6':'Samstag','7':'Sonntag'}
    if minute.isdigit() and hour.isdigit() and day==month=='*' and weekday in weekdays:
        return 'Jeden '+weekdays[weekday]+' um '+hour.zfill(2)+':'+minute.zfill(2)
    return 'Minute '+minute+' · Stunde '+hour+' · Tag '+day+' · Monat '+month+' · Wochentag '+weekday


def cron_rows():
    files=[(Path('/etc/crontab'),True)]
    for directory,system in [('/etc/cron.d',True),('/var/spool/cron/crontabs',False)]:
        root=Path(directory)
        if root.is_dir():files.extend((p,system) for p in sorted(root.iterdir())[:150] if p.is_file() and not p.is_symlink())
    rows=[]
    for path,system in files:
        if not path.is_file() or path.is_symlink() or path.stat().st_size>262144:continue
        for number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
            line=line.strip()
            if not line or line.startswith('#') or re.match(r'\w+\s*=',line):continue
            parts=line.split(None,6 if system else 5);count=1 if line.startswith('@') else 5
            # @daily has fewer schedule fields than a normal crontab.
            pieces=line.split(None,count+(1 if system else 0))
            if len(pieces)<count+1+(1 if system else 0):continue
            command=pieces[-1]
            try:program=Path(shlex.split(command)[0]).name
            except (ValueError,IndexError):program='Unbekannt'
            rows.append({'source':str(path)+':'+str(number),'user':pieces[count] if system else path.name,
                'schedule':describe_cron(pieces[:count]),'program':program,'outcome':'Unbekannt – Cron bestätigt keinen Exitcode.'})
    timers=core.command(['systemctl','list-timers','--all','--no-pager'],timeout=15)
    return {'rows':rows[:500],'timers':timers,'note':'Passwörter und Argumente werden nicht angezeigt. Cron-Startmeldungen belegen keinen erfolgreichen Abschluss.'}


JOB_PREFIX='serverlotse-job-'
CRON_DIR=Path('/etc/cron.d');UNIT_DIR=Path('/etc/systemd/system');JOB_SCRIPTS=Path('/usr/local/lib/serverlotse-jobs')
CRON_MACROS={'@reboot':None,'@hourly':'hourly','@daily':'daily','@weekly':'weekly','@monthly':'monthly','@yearly':'yearly'}
CRON_LIMITS=[(0,59),(0,23),(1,31),(1,12),(0,7)]
WEEKDAY_NAMES=['Sun','Mon','Tue','Wed','Thu','Fri','Sat','Sun']


def cron_schedule(value):
    fields=str(value or '').split()
    if len(fields)==1 and fields[0] in CRON_MACROS:return fields
    if len(fields)!=5:raise ValueError('Zeitplan mit fünf Feldern (Minute Stunde Tag Monat Wochentag) oder @daily usw. angeben.')
    for field,(low,high) in zip(fields,CRON_LIMITS):
        if not re.fullmatch(r'[0-9*,/-]{1,40}',field):raise ValueError('Ungültiges Zeitplanfeld: '+field)
        for part in field.split(','):
            base,slash,step=part.partition('/')
            if slash and (not step.isdigit() or not 1<=int(step)<=high or (base!='*' and '-' not in base)):raise ValueError('Ungültige Schrittweite: '+part)
            if base=='*':continue
            start,dash,end=base.partition('-')
            for number in [start]+([end] if dash else []):
                if not number.isdigit() or not low<=int(number)<=high:raise ValueError('Wert außerhalb des Bereichs: '+part)
            if dash and int(start)>int(end):raise ValueError('Bereich rückwärts: '+part)
    return fields


def calendar_part(field,first='0',names=None):
    # systemd OnCalendar: "a..b" for ranges, "start/step" for repetitions, names for weekdays.
    out=[]
    for part in field.split(','):
        base,slash,step=part.partition('/')
        if slash and (names or base!='*'):raise ValueError('Diese Schrittweite ist für Systemdienste nicht möglich; bitte als Liste angeben.')
        if base=='*':out.append(first+'/'+step if slash else '*');continue
        out.append('..'.join(names[int(v)] if names else v.zfill(2) for v in base.split('-')))
    return ','.join(out)


def on_calendar(fields):
    if len(fields)==1:return CRON_MACROS[fields[0]]
    minute,hour,day,month,weekday=fields
    if day!='*' and weekday!='*':raise ValueError('Tag und Wochentag gleichzeitig verhalten sich bei Cron anders als bei systemd. Bitte nur eines davon festlegen.')
    prefix=calendar_part(weekday,names=WEEKDAY_NAMES)+' ' if weekday!='*' else ''
    return prefix+'*-'+calendar_part(month,'1')+'-'+calendar_part(day,'1')+' '+calendar_part(hour)+':'+calendar_part(minute)+':00'


def managed_jobs():
    jobs=[]
    if CRON_DIR.is_dir():
        for path in sorted(CRON_DIR.glob(JOB_PREFIX+'*'))[:200]:
            if path.is_symlink() or not path.is_file():continue
            lines=[l for l in path.read_text(errors='replace').splitlines() if l.strip() and not l.startswith('#') and not re.match(r'\w+\s*=',l)]
            if not lines:continue
            count=1 if lines[-1].startswith('@') else 5;pieces=lines[-1].split(None,count+1)
            if len(pieces)<count+2:continue
            jobs.append({'name':path.name[len(JOB_PREFIX):],'kind':'cron','schedule':describe_cron(pieces[:count]),'user':pieces[count],'command':pieces[-1].replace('\\%','%')})
    if UNIT_DIR.is_dir():
        for path in sorted(UNIT_DIR.glob(JOB_PREFIX+'*.timer'))[:200]:
            if path.is_symlink() or not path.is_file():continue
            name=path.name[len(JOB_PREFIX):-len('.timer')];_,service,script=job_files(name,'systemd')
            calendar=re.search(r'^OnCalendar=(.+)$',path.read_text(errors='replace'),re.M)
            user=re.search(r'^User=(.+)$',service.read_text(errors='replace'),re.M) if service.is_file() else None
            lines=script.read_text(errors='replace').splitlines() if script.is_file() else ['?']
            jobs.append({'name':name,'kind':'systemd','schedule':calendar.group(1) if calendar else 'Beim Systemstart','user':user.group(1) if user else 'root','command':lines[-1]})
    return jobs


def job_files(name,kind):
    if kind=='cron':return [CRON_DIR/(JOB_PREFIX+name)]
    return [UNIT_DIR/(JOB_PREFIX+name+'.timer'),UNIT_DIR/(JOB_PREFIX+name+'.service'),JOB_SCRIPTS/(name+'.sh')]


def validate_job(data):
    name=str(data.get('name',''));kind=data.get('kind');command=data.get('command')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',name):raise ValueError('Name: Kleinbuchstaben, Ziffern und Bindestriche, maximal 40 Zeichen.')
    if kind not in {'cron','systemd'}:raise ValueError('Art wählen: Cron oder Systemdienst.')
    if not isinstance(command,str) or not command.strip() or len(command)>1000 or any(c in command for c in '\r\n\x00'):raise ValueError('Einzeiligen Befehl mit maximal 1000 Zeichen eingeben.')
    user=str(data.get('user') or 'root')
    import pwd
    try:pwd.getpwnam(user)
    except KeyError:raise ValueError('Benutzer existiert nicht: '+user) from None
    fields=cron_schedule(data.get('schedule'))
    if any(path.exists() for path in job_files(name,'cron')+job_files(name,'systemd')[:2]):raise ValueError('Ein ServerLotse-Auftrag mit diesem Namen existiert bereits.')
    plan={'name':name,'kind':kind,'command':command.strip(),'user':user,'schedule':' '.join(fields),'description':describe_cron(fields),'run_now':bool(data.get('run_now')) and kind=='systemd'}
    if kind=='systemd':
        plan['calendar']=on_calendar(fields)
        if plan['calendar']:core.command(['systemd-analyze','calendar',plan['calendar']],timeout=10)
    return plan


def create_job(p):
    name=p['name']
    if p['kind']=='cron':
        # In crontab lines an unescaped % ends the command and feeds the rest to stdin.
        line=p['schedule']+' '+p['user']+' '+p['command'].replace('%','\\%')
        text='# Angelegt von ServerLotse. Entfernen über Cronjobs in ServerLotse.\nSHELL=/bin/sh\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n'+line+'\n'
        advanced.atomic_write(CRON_DIR/(JOB_PREFIX+name),text.encode(),0o644)
        return {'name':name,'note':'Cron-Eintrag angelegt. Cron übernimmt ihn automatisch: '+p['description']+'.'}
    timer,service,script=job_files(name,'systemd')
    # The command lives in its own script so systemd's %-specifiers and quoting never reinterpret it.
    trigger='OnCalendar='+p['calendar']+'\nPersistent=true' if p['calendar'] else 'OnBootSec=1min'
    try:
        JOB_SCRIPTS.mkdir(mode=0o755,parents=True,exist_ok=True)
        advanced.atomic_write(script,('#!/bin/sh\n# Angelegt von ServerLotse\n'+p['command']+'\n').encode(),0o755)
        advanced.atomic_write(service,('[Unit]\nDescription=ServerLotse-Auftrag '+p['name']+'\n\n[Service]\nType=oneshot\nUser='+p['user']+'\nExecStart=/bin/sh '+str(script)+'\n').encode(),0o644)
        advanced.atomic_write(timer,('[Unit]\nDescription=Zeitplan für ServerLotse-Auftrag '+p['name']+'\n\n[Timer]\n'+trigger+'\n\n[Install]\nWantedBy=timers.target\n').encode(),0o644)
        core.command(['systemctl','daemon-reload'],timeout=30)
        core.command(['systemctl','enable','--now',timer.name],timeout=30)
        if p['run_now']:core.command(['systemctl','start','--no-block',service.name],timeout=30)
    except Exception:
        core.command(['systemctl','disable','--now',timer.name],timeout=30,allowed=(0,1,5))
        for path in (timer,service,script):
            with contextlib.suppress(FileNotFoundError):path.unlink()
        core.command(['systemctl','daemon-reload'],timeout=30,allowed=(0,1))
        raise
    return {'name':name,'note':'Systemdienst '+service.name+' mit Timer '+timer.name+' angelegt und aktiviert.'+(' Erster Lauf gestartet.' if p['run_now'] else '')}


def remove_job(p):
    name=p['name']
    if p['kind']=='systemd':
        timer,service,_=job_files(name,'systemd')
        core.command(['systemctl','disable','--now',timer.name],timeout=30,allowed=(0,1,5))
        core.command(['systemctl','stop',service.name],timeout=60,allowed=(0,1,5))
    for path in job_files(name,p['kind']):
        with contextlib.suppress(FileNotFoundError):path.unlink()
    if p['kind']=='systemd':core.command(['systemctl','daemon-reload'],timeout=30,allowed=(0,1))
    return {'name':name,'note':'Auftrag entfernt. Laufende Systemdienst-Befehle wurden gestoppt.'}


def process_identity(pid):
    raw=Path('/proc',str(pid),'stat').read_text();end=raw.rfind(')');parts=raw[end+2:].split()
    return {'pid':pid,'name':raw[raw.find('(')+1:end],'state':parts[0],'ppid':int(parts[1]),'start':parts[19]}


def orphans():
    import docker_tools
    existing={row['Id'] for row in docker_tools.inventory()};rows=[]
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        try:
            row=process_identity(int(directory.name))
            if row['state']=='Z':rows.append({**row,'candidate':False,'reason':'Zombie: bereits beendet; der Elternprozess muss ihn einsammeln.'});continue
            if row['ppid']!=1 or row['pid']<3:continue
            group=(directory/'cgroup').read_text();match=re.search(r'(?:docker[-/])([a-f0-9]{64})(?:\.scope|/|$)',group,re.M)
            if not match or match[1] in existing:continue
            safe=not re.search(r'(ssh|systemd|containerd|dockerd|serverlotse|dbus|init)',row['name'],re.I)
            rows.append({**row,'candidate':safe,'container':match[1],'reason':'Docker-Zuordnung fehlt; einzeln prüfen, kein Beweis für Entbehrlichkeit.'})
        except (OSError,ValueError,IndexError):continue
        if len(rows)>=200:break
    return {'rows':rows,'note':'PPID 1 allein ist normal und kein Löschkriterium. Zombies lassen sich nicht erneut töten.'}


def analyze_command(text):
    if not isinstance(text,str) or not 1<=len(text)<=4096:raise ValueError('Befehl mit maximal 4096 Zeichen angeben.')
    if any(c in text for c in '\n\r\x00;$`|&<>'):
        return {'supported':False,'note':'Shell-Verknüpfungen, Umleitungen und Ersetzungen werden nicht simuliert. Es wird nichts ausgeführt.'}
    try:parts=shlex.split(text)
    except ValueError:raise ValueError('Anführungszeichen sind nicht geschlossen.') from None
    if not parts:return {'supported':False,'note':'Kein Befehl.'}
    name=parts[0]
    if name not in {'rm','chmod','chown'}:return {'supported':False,'note':'Nur wörtliche rm-, chmod- und chown-Befehle werden erklärt. Keine Ausführung.'}
    flags=[p for p in parts[1:] if p.startswith('-') and p!='--'];args=[p for p in parts[1:] if not p.startswith('-')]
    description={'rm':'Entfernt Dateien oder Verzeichnisse endgültig ohne Papierkorb.',
        'chmod':'Ändert Zugriffsrechte; Schreib-, Lese- oder Ausführungszugriff kann verloren gehen.',
        'chown':'Ändert Eigentümer oder Gruppe; Dienste können danach den Zugriff verlieren.'}[name]
    value=None
    if name!='rm':
        if not args:raise ValueError('Rechte oder Eigentümer fehlen.')
        value=args.pop(0)
    paths=[]
    for arg in args[:100]:
        if any(c in arg for c in '*?[]{}~') or not arg.startswith('/'):
            paths.append({'path':arg,'status':'Nicht aufgelöst: Muster oder relativer Pfad'});continue
        try:
            path=core.local_path(arg);info=path.lstat();paths.append({'path':str(path),'type':'Ordner' if stat.S_ISDIR(info.st_mode) else 'Datei','bytes':info.st_size,'mode':oct(stat.S_IMODE(info.st_mode))[2:]})
        except (ValueError,OSError):paths.append({'path':arg,'status':'Nicht vorhanden oder nicht sicher auflösbar'})
    return {'supported':True,'command':name,'value':value,'flags':flags,'recursive':any('r' in f.lower() for f in flags),
            'description':description,'targets':paths,'note':'Erklärung, keine Sandbox und keine Ausführung. Rekursive Folgen und ACLs werden nicht vollständig vorausberechnet.'}


def apt_cleanup():
    text=core.command(['apt-get','-s','autoremove','--purge'],timeout=90)
    packages=sorted(set(re.findall(r'^(?:Remv|Purg)\s+(\S+)',text,re.M)))
    protected=re.compile(r'^(linux-|systemd|udev|dbus|openssh|dropbear|docker|containerd|runc|sudo|apt|dpkg|libc6|bash|coreutils|python3|network|ifupdown|iproute|dietpi|serverlotse)')
    blocked=[p for p in packages if protected.match(p)]
    if packages:
        status=core.command(['dpkg-query','-W','-f=${binary:Package}\t${Essential}\t${Priority}\n',*packages])
        for line in status.splitlines():
            parts=line.split('\t')
            if len(parts)==3 and (parts[1]=='yes' or parts[2] in {'required','important'}):blocked.append(parts[0])
    return {'packages':packages,'blocked':sorted(set(blocked)),'simulation':text,
            'note':'Kernel, Zugangs- und Systempakete bleiben geschützt. Auch alte Kernel werden hier bewusst nicht automatisch entfernt.'}


def config_path(kind):
    if kind not in CONFIGS:raise ValueError('Nur nginx.conf oder sshd_config auswählen.')
    path=core.local_path(CONFIGS[kind][0]);core.private_destination(path.parent);info=path.stat()
    if info.st_uid!=0 or info.st_mode&0o022 or not stat.S_ISREG(info.st_mode) or info.st_size>32768:raise ValueError('Konfiguration muss eine kleine, root-geschützte reguläre Datei sein.')
    return path


def ticket_path(ident):
    if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{24}',ident):raise ValueError('Ungültige Rücknahme-ID.')
    return core.STATE/('undo-'+ident+'.json')


@contextlib.contextmanager
def ticket_lock():
    import fcntl
    core.STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    with open(core.STATE/'undo.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def ticket(ident):
    path=ticket_path(ident)
    if path.is_symlink() or not path.is_file():raise ValueError('Rücknahme nicht vorhanden.')
    return json.loads(path.read_text())


def save_ticket(row):advanced.atomic_write(ticket_path(row['id']),json.dumps(row).encode(),0o600)


def rollback(ident,keep=False):
    with ticket_lock():
        row=ticket(ident)
        if row['status']!='pending':return {'status':row['status'],'id':ident}
        if keep:
            if time.time()>=row['expires']:raise ValueError('Frist abgelaufen; Rücknahme abwarten.')
            row['status']='kept'
        elif row['kind']=='panic':
            for family in ['inet','bridge']:core.command(['nft','delete','table',family,'serverlotse_panic'],allowed=(0,1))
            row['status']='reverted'
        else:
            path=config_path(row['kind'])
            if hash_bytes(path.read_bytes())!=row['after_hash']:
                row['status']='conflict';save_ticket(row);return {'status':'conflict','note':'Andere Änderung erkannt. Sicherung erhalten; kein blindes Überschreiben.'}
            advanced.atomic_write(path,base64.b64decode(row['backup']),row['mode'])
            _,check,service=CONFIGS[row['kind']]
            core.command(check);core.command(['systemctl','reload',service]);row['status']='reverted'
        save_ticket(row)
        advanced.log_event('lab_rollback',{'id':ident,'status':row['status']})
        return {'status':row['status'],'id':ident}


def arm(row,seconds):
    save_ticket(row)
    try:
        core.command(['systemd-run','--quiet','--unit=serverlotse-undo-'+row['id'],'--on-active='+str(seconds)+'s',
            '--timer-property=AccuracySec=1s','/usr/bin/python3','/usr/local/lib/serverlotse/expert_tools.py','--undo',row['id']],timeout=5)
    except Exception:
        row['status']='not_armed';save_ticket(row);raise


def panic_rules(addresses):
    ips=sorted(set(str(ipaddress.ip_address(value)) for value in addresses))
    if not 1<=len(ips)<=8:raise ValueError('Eine bis acht Verwaltungs-IP-Adressen angeben.')
    rules=['table inet serverlotse_panic {']
    for direction,hook,priority in [('in','input',-5),('out','output',-5),('forward','forward',-5)]:
        rules+=[' chain '+direction+' { type filter hook '+hook+' priority '+str(priority)+'; policy drop;',
                ' iifname "lo" accept' if direction!='out' else ' oifname "lo" accept']
        for ip in ips:
            family='ip6' if ':' in ip else 'ip'
            if direction!='out':rules.append(' '+family+' saddr '+ip+' accept')
            if direction!='in':rules.append(' '+family+' daddr '+ip+' accept')
        rules+=[' meta l4proto ipv6-icmp icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert, nd-router-solicit, nd-router-advert } accept',' }']
    rules+=['}', 'table bridge serverlotse_panic {',' chain forward { type filter hook forward priority -5; policy drop;',' ether type arp accept']
    for ip in ips:
        family='ip6' if ':' in ip else 'ip'
        rules+=[' '+family+' saddr '+ip+' accept',' '+family+' daddr '+ip+' accept']
    return '\n'.join(rules+[' }','}'])+'\n'


def validate(data):
    op=data['operation'];p={'operation':op}
    if op=='lab_cache':return p
    if op=='lab_apt_clean':
        result=apt_cleanup()
        if result['blocked']:raise ValueError('APT möchte geschützte Pakete entfernen: '+', '.join(result['blocked']))
        return {**p,**result}
    if op=='lab_orphan_end':
        pid=int(data.get('pid',0));row=next((r for r in orphans()['rows'] if r['pid']==pid and r['candidate']),None)
        if not row or not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):raise ValueError('Kein sicher adressierbarer verwaister Docker-Prozess.')
        return {**p,'pid':pid,'identity':row}
    if op=='lab_panic':
        if not shutil.which('nft'):raise ValueError('nftables zuerst über den Werkzeug-Installer installieren.')
        ips=data.get('addresses',[])
        if not isinstance(ips,list):raise ValueError('IP-Liste fehlt.')
        ips=sorted(set(str(ipaddress.ip_address(v)) for v in ips));rules=panic_rules(ips)
        if any(p.get('kind')=='panic' and p.get('status')=='pending' for p in pending()):raise ValueError('Notfallbremse ist bereits aktiv.')
        core.command(['nft','--check','--file','-'],input_text=rules)
        return {**p,'addresses':ips,'rules':rules,'seconds':60}
    if op in {'lab_panic_release','lab_config_keep','lab_config_undo'}:
        ident=data.get('id');row=ticket(ident)
        if row['status']!='pending':raise ValueError('Keine aktive Rücknahme mehr vorhanden.')
        if op=='lab_panic_release' and row['kind']!='panic':raise ValueError('Keine Notfallbremse.')
        if op=='lab_config_keep' and (row['kind']=='panic' or row['expires']<=time.time()):raise ValueError('Änderung kann nicht mehr beibehalten werden.')
        return {**p,'id':ident}
    if op=='lab_config_write':
        kind=data.get('kind');path=config_path(kind);text=data.get('config_text')
        if not isinstance(text,str) or not 1<=len(text.encode())<=32768 or '\x00' in text:raise ValueError('Konfiguration mit maximal 32 KiB eingeben.')
        if any(r.get('kind')==kind and r.get('status')=='pending' for r in pending()):raise ValueError('Eine Konfigurationsänderung wartet noch auf Bestätigung.')
        before=hash_bytes(path.read_bytes())
        if data.get('before_hash')!=before:raise ValueError('Konfiguration seit dem Laden verändert. Datei neu laden.')
        return {**p,'kind':kind,'config_text':text,'before_hash':before,'after_hash':hash_bytes(text.encode()),'seconds':30}
    if op=='lab_cron_create':return {**p,**validate_job(data)}
    if op=='lab_cron_remove':
        name=str(data.get('name',''));job=next((j for j in managed_jobs() if j['name']==name),None)
        if not job:raise ValueError('Nur von ServerLotse angelegte Aufträge können entfernt werden.')
        return {**p,'name':name,'kind':job['kind'],'schedule':job['schedule'],'command':job['command']}
    raise ValueError('Unbekanntes Host-Werkzeug.')


def pending():
    rows=[]
    if not core.STATE.is_dir():return rows
    for path in sorted(core.STATE.glob('undo-*.json'),key=lambda p:p.stat().st_mtime)[-100:]:
        try:
            if path.is_symlink():continue
            row=json.loads(path.read_text());rows.append({k:row[k] for k in ['id','kind','status','expires']})
        except (OSError,ValueError,KeyError):continue
    return rows


def apply(p):
    op=p['operation']
    if op=='lab_cache':
        before=memory();core.command(['sync'],timeout=60);Path('/proc/sys/vm/drop_caches').write_text('3\n')
        return {'before':before,'after':memory(),'note':'Nur wiederherstellbare Dateicaches freigegeben. Anwendungen behalten ihren RAM; Caches bauen sich bei Bedarf erneut auf.'}
    if op=='lab_apt_clean':
        fresh=apt_cleanup()
        if fresh['blocked'] or fresh['packages']!=p['packages']:raise ValueError('APT-Auswahl verändert. Neue Vorschau erstellen.')
        # Keep kernel and access packages out of auto-removal even if another
        # package manager changes auto flags between the check and APT's lock.
        protection='^(linux-|systemd|udev|dbus|openssh|dropbear|docker|containerd|runc|sudo|apt|dpkg|libc6|bash|coreutils|python3|network|ifupdown|iproute|dietpi|serverlotse)'
        text=core.command(['apt-get','--assume-yes','-o','APT::NeverAutoRemove::='+protection,'autoremove','--purge'],timeout=1800)
        core.command(['apt-get','clean'],timeout=120);return {'text':text,'packages':p['packages']}
    if op=='lab_orphan_end':
        fd=os.pidfd_open(p['pid'])
        try:
            if process_identity(p['pid'])!={k:p['identity'][k] for k in ['pid','name','state','ppid','start']}:raise ValueError('Prozess hat sich verändert.')
            signal.pidfd_send_signal(fd,signal.SIGTERM)
        finally:os.close(fd)
        return {'note':'SIGTERM an genau den bestätigten Prozess gesendet. Kein automatisches SIGKILL.'}
    if op in {'lab_config_keep','lab_config_undo','lab_panic_release'}:return rollback(p['id'],op=='lab_config_keep')
    if op=='lab_cron_create':return create_job(p)
    if op=='lab_cron_remove':return remove_job(p)
    ident=secrets.token_hex(12);row={'id':ident,'kind':'panic' if op=='lab_panic' else p['kind'],'status':'pending','expires':time.time()+p['seconds']}
    if op=='lab_panic':
        with ticket_lock():
            arm(row,p['seconds'])
            try:core.command(['nft','--file','-'],input_text=p['rules'])
            except Exception:
                for family in ['inet','bridge']:core.command(['nft','delete','table',family,'serverlotse_panic'],allowed=(0,1))
                row['status']='reverted';save_ticket(row);raise
        return {'id':ident,'expires':row['expires'],'note':'Zeitlich begrenzte Netzwerksperre aktiv. Automatische Freigabe nach 60 Sekunden; vorhandene Regeln bleiben bestehen. Verwaltungszugang sofort prüfen.'}
    path=config_path(p['kind']);original=path.read_bytes()
    row.update(backup=base64.b64encode(original).decode(),mode=stat.S_IMODE(path.stat().st_mode),after_hash=p['after_hash'])
    try:
        with ticket_lock():
            if hash_bytes(path.read_bytes())!=p['before_hash']:raise ValueError('Datei wurde vor dem Schreiben verändert.')
            arm(row,30);advanced.atomic_write(path,p['config_text'].encode(),row['mode'])
            _,check,service=CONFIGS[p['kind']]
            core.command(check,timeout=5);core.command(['systemctl','reload',service],timeout=10);core.command(['systemctl','is-active',service],timeout=5)
    except Exception:
        if not ticket_path(ident).exists():raise ValueError('Konfiguration wurde verändert; keine neue Datei geschrieben. Neu laden.') from None
        outcome=rollback(ident)
        if outcome['status']=='reverted':raise ValueError('Validierung oder Neuladen fehlgeschlagen. Ursprüngliche Konfiguration wurde zurückgespielt; Dienste prüfen.') from None
        raise ValueError('Änderung fehlgeschlagen. Rücknahme-Status und private Sicherung prüfen: '+outcome['status']) from None
    return {'id':ident,'expires':row['expires'],'note':'Neue Konfiguration geladen. Zugang prüfen und innerhalb von 30 Sekunden beibehalten, sonst wird automatisch zurückgenommen.'}


def read(data):
    view=data['view']
    if view=='lab_inodes':return inode_radar()
    if view=='lab_cron':return {**cron_rows(),'jobs':managed_jobs()}
    if view=='lab_orphans':return orphans()
    if view=='lab_analyze':return analyze_command(data.get('command'))
    if view=='lab_memory':return memory()
    if view=='lab_undo':return {'rows':pending()}
    if view=='lab_native_config':
        kind=data.get('kind','nginx');path=config_path(kind)
        return {'kind':kind,'path':str(path),'config_text':path.read_text(),'hash':hash_bytes(path.read_bytes())}
    if view=='lab_apt_cleanup':return apt_cleanup()
    raise ValueError('Unbekannte Host-Ansicht.')


if __name__=='__main__':
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--undo':rollback(sys.argv[2])
    else:raise SystemExit('Only --undo ID is supported.')
