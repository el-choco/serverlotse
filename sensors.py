"""Read-only sensors and diagnostics. No mutation or arbitrary command endpoint."""
from collections import deque
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
from urllib.parse import urlsplit

HISTORY = deque(maxlen=720)
LOCK = threading.Lock()
PREVIOUS = {}
PROCESS_PREVIOUS = {}
LAST_ERROR = ''
COMMANDS = {
    'uptime': ['uptime'],
    'disk': ['df','-hT'],
    'inodes': ['df','-i'],
    'memory': ['free','-h'],
    'addresses': ['ip','-brief','address'],
    'routes': ['ip','route','show'],
    'ports': ['ss','-lntup'],
    'failed': ['systemctl','--failed','--no-pager'],
    'boot_errors': ['journalctl','-b','-p','err','-n','100','--no-pager'],
    'docker_space': ['docker','system','df'],
}
VIEWS = {'sensor_live','sensor_processes','sensor_logs','sensor_ssh','sensor_firewall',
         'sensor_fail2ban','sensor_unused','sensor_console','sensor_capabilities','sensor_proxy'}


def proxy_template(data):
    domain=str(data.get('domain','')).lower()
    if not re.fullmatch(r'(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',domain):raise ValueError('Öffentlichen Domainnamen ohne Pfad angeben.')
    upstream=str(data.get('upstream',''));parsed=urlsplit(upstream)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:raise ValueError('Upstream als http://IP:Port oder https://Hostname:Port angeben.')
    if not re.fullmatch(r'[a-zA-Z0-9.:[\]-]+',parsed.netloc):raise ValueError('Ungültiger Upstream.')
    try:port=parsed.port
    except ValueError:raise ValueError('Ungültiger Upstream-Port.') from None
    if port is not None and not 1<=port<=65535:raise ValueError('Ungültiger Upstream-Port.')
    caddy=f'{domain} {{\n    tls {{\n        ca https://acme-v02.api.letsencrypt.org/directory\n    }}\n    reverse_proxy {upstream.rstrip("/")}\n}}\n'
    nginx=f'server {{\n    listen 80;\n    server_name {domain};\n    location / {{\n        proxy_pass {upstream.rstrip("/")};\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-Proto $scheme;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n    }}\n}}\n'
    return {'caddy':caddy,'nginx':nginx,'note':'Vorlagen, keine Installation. Caddy kann nach manueller Aktivierung Zertifikate anfordern, wenn DNS und Port 80/443 stimmen. Die Nginx-Vorlage ist HTTP ohne Zertifikate. Vorhandener Nginx Proxy Manager wird nicht verändert.'}


def cpu_values(text):
    result={}
    for line in text.splitlines():
        parts=line.split()
        if parts and re.fullmatch(r'cpu\d*',parts[0]):
            values=[int(v) for v in parts[1:9]]
            if len(values)>=4:result[parts[0]]=(sum(values),values[3]+(values[4] if len(values)>4 else 0))
    return result


def cpu_percent(before,after):
    total=after[0]-before[0];idle=after[1]-before[1]
    return round(max(0,min(100,(total-idle)/total*100)),2) if total>0 else None


def temperatures():
    values=[]
    for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try:
            value=int(path.read_text())/1000
            if -20<value<150:values.append({'name':path.parent.joinpath('type').read_text().strip(),'celsius':value})
        except (OSError,ValueError):pass
    if not values:
        for path in Path('/sys/class/hwmon').glob('hwmon*/temp*_input'):
            try:
                value=int(path.read_text())/1000
                label=path.with_name(path.name.replace('_input','_label'))
                name=label.read_text().strip() if label.exists() else path.parent.joinpath('name').read_text().strip()
                if -20<value<150:values.append({'name':name,'celsius':value})
            except (OSError,ValueError):pass
    return values[:32]


def collect():
    now=time.time();current=cpu_values(Path('/proc/stat').read_text())
    memory={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key,value=line.split(':',1)
        if key in {'MemTotal','MemAvailable','SwapTotal','SwapFree'}:memory[key]=int(value.split()[0])*1024
    net={}
    for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
        name,values=line.split(':',1);numbers=values.split()
        if name.strip()!='lo':net[name.strip()]=(int(numbers[0]),int(numbers[8]))
    temps=temperatures()
    with LOCK:
        previous=PREVIOUS.get('cpu',{})
        cpus={name:cpu_percent(previous[name],value) if name in previous else None for name,value in current.items()}
        elapsed=now-PREVIOUS.get('time',now)
        rates={name:{'rx':max(0,(value[0]-PREVIOUS.get('net',{}).get(name,value)[0])/elapsed) if elapsed>0 else None,
                     'tx':max(0,(value[1]-PREVIOUS.get('net',{}).get(name,value)[1])/elapsed) if elapsed>0 else None} for name,value in net.items()}
        latest={'time':now,'cpu':cpus.get('cpu'),'cores':{k:v for k,v in cpus.items() if k!='cpu'},'memory':memory,
                'ram_percent':round((1-memory['MemAvailable']/memory['MemTotal'])*100,2),
                'swap_percent':round((1-memory.get('SwapFree',0)/memory['SwapTotal'])*100,2) if memory.get('SwapTotal') else 0,
                'temperatures':temps,'network':rates}
        HISTORY.append({'time':now,'cpu':latest['cpu'],'ram':latest['ram_percent'],'swap':latest['swap_percent'],
                        'temperature':max((t['celsius'] for t in temps),default=None),
                        'rx':sum(r['rx'] or 0 for r in rates.values()) if elapsed>0 else None,
                        'tx':sum(r['tx'] or 0 for r in rates.values()) if elapsed>0 else None})
        PREVIOUS.update(cpu=current,time=now,net=net,latest=latest)
    return latest


def monitor():
    global LAST_ERROR
    while True:
        try:collect();LAST_ERROR=''
        except (OSError,ValueError,KeyError,IndexError) as exc:LAST_ERROR=type(exc).__name__
        time.sleep(5)


def parse_process(text,pid,uid,page_size):
    end=text.rfind(')');parts=text[end+2:].split()
    return {'pid':pid,'name':text[text.index('(')+1:end],'state':parts[0],
            'ticks':int(parts[11])+int(parts[12]),'rss':max(0,int(parts[21]))*page_size,
            'start':int(parts[19]),'uid':uid}


def processes():
    rows=[];now=time.monotonic();ticks=os.sysconf('SC_CLK_TCK');page_size=os.sysconf('SC_PAGE_SIZE')
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        try:
            pid=int(directory.name);row=parse_process((directory/'stat').read_text(),pid,directory.stat().st_uid,page_size)
            with LOCK:
                previous=PROCESS_PREVIOUS.get(pid)
                value=max(0,(row['ticks']-previous[1])/ticks/(now-previous[2])*100) if previous and previous[0]==row['start'] and now>previous[2] else None
                PROCESS_PREVIOUS[pid]=(row['start'],row['ticks'],now)
            row['cpu']=round(value,2) if value is not None else None;row.pop('ticks');rows.append(row)
        except (OSError,ValueError,IndexError):continue
    existing={r['pid'] for r in rows}
    with LOCK:
        for pid in list(PROCESS_PREVIOUS):
            if pid not in existing:PROCESS_PREVIOUS.pop(pid,None)
    return {'rows':sorted(rows,key=lambda r:r['rss'],reverse=True)[:1000], 'total':len(rows),
            'note':'Prozess-CPU benötigt zwei Abfragen. 100 % entspricht einem vollständig belegten CPU-Kern. Maximal 1.000 Prozesse werden angezeigt.'}


def log_tail(core,data):
    names={'syslog':'/var/log/syslog','auth':'/var/log/auth.log','nginx':'/var/log/nginx/error.log','apache':'/var/log/apache2/error.log'}
    key=data.get('log','journal');needle=str(data.get('filter',''))[:200]
    if key=='journal':text=core.command(['journalctl','-n','300','--no-pager','-o','short-iso'],timeout=15)
    else:
        if key not in names:raise ValueError('Unbekannte Logquelle.')
        path=core.local_path(names[key]);fd=core.secure_open(path,os.O_RDONLY|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Keine reguläre Logdatei.')
            stream.seek(0,2);end=stream.tell();start=max(0,end-128000);stream.seek(start)
            text=stream.read(128000).decode('utf-8','replace')
            if start:text=text.partition('\n')[2]
    lines=text.splitlines()[-300:]
    if needle:lines=[line for line in lines if needle.casefold() in line.casefold()]
    import toolkit
    return {'text':toolkit.redact('\n'.join(lines)),'time':time.time(),
            'note':'Live-Nachführung alle 3 Sekunden; begrenztes Logende, kein vollständiger Export. Zugangsdaten werden nur bestmöglich maskiert.'}


def ssh(core):
    output=core.command([shutil.which('sshd') or '/usr/sbin/sshd','-T'],timeout=15)
    values=dict(line.split(' ',1) for line in output.splitlines() if ' ' in line)
    checks=[('permitrootlogin','no'),('passwordauthentication','no'),('pubkeyauthentication','yes')]
    return {'rows':[{'name':name,'value':values.get(name,'unknown'),'recommended':wanted,'attention':values.get(name)!=wanted} for name,wanted in checks],
            'port':values.get('port'),'note':'Effektive Standardkonfiguration von sshd -T. Match-Blöcke und Portweiterleitungen können abweichen. Es wird nichts an SSH geändert.'}


def firewall(core):
    if shutil.which('ufw'):return {'backend':'ufw','text':core.command(['ufw','status','numbered']),
                                 'note':'UFW-Regeln können veröffentlichte Docker-Ports nicht zuverlässig abschirmen. Zugriff von außen separat testen.'}
    if shutil.which('iptables-save'):return {'backend':'iptables','text':core.command(['iptables-save']), 'note':'Lesende Übersicht; Regeln werden nicht verändert.'}
    if shutil.which('nft'):return {'backend':'nftables','text':core.command(['nft','list','ruleset']), 'note':'Lesende Übersicht; Regeln werden nicht verändert.'}
    return {'backend':'none','text':'Kein unterstütztes Firewall-Werkzeug vorhanden.'}


def fail2ban(core,data):
    jail=data.get('jail','')
    if not isinstance(jail,str) or (jail and not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]{0,79}',jail)):raise ValueError('Ungültiger Jailname.')
    output=core.command(['fail2ban-client','status',*([jail] if jail else [])])
    jails=[]
    if not jail:
        for line in output.splitlines():
            if 'Jail list:' in line:jails=[v.strip() for v in line.split('Jail list:',1)[1].split(',') if re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v.strip())]
    return {'text':output,'jails':jails}


def unused(core):
    volumes=core.command(['docker','volume','ls','--filter','dangling=true','--format','{{.Name}}']).splitlines()
    images=core.command(['docker','image','ls','--filter','dangling=true','--no-trunc','--format','{{.ID}}']).splitlines()
    return {'volumes':volumes,'images':sorted(set(images)),'text':core.command(['docker','system','df']),
            'note':'Nicht referenziert heißt nicht leer oder entbehrlich. Volumes können Datenbanken und Dateien enthalten. Diese Ansicht löscht nichts.'}


def read(core,data):
    view=data.get('view')
    if view=='sensor_live':
        with LOCK:return {'rows':list(HISTORY),'latest':PREVIOUS.get('latest'),'error':LAST_ERROR or None,
                          'note':'Messung alle 5 Sekunden; bis zu eine Stunde Verlauf im Arbeitsspeicher. Fehlende Temperaturwerte bleiben unbekannt.'}
    if view=='sensor_processes':return processes()
    if view=='sensor_logs':return log_tail(core,data)
    if view=='sensor_ssh':return ssh(core)
    if view=='sensor_firewall':return firewall(core)
    if view=='sensor_fail2ban':return fail2ban(core,data)
    if view=='sensor_unused':return unused(core)
    if view=='sensor_console':
        key=data.get('command')
        if not isinstance(key,str) or key not in COMMANDS:raise ValueError('Nur die angebotenen Diagnosebefehle sind erlaubt.')
        import toolkit
        return {'command':COMMANDS[key],'text':toolkit.redact(core.command(COMMANDS[key],timeout=20)),
                'note':'Lesende Diagnose-Konsole. Keine freie Shell und keine verändernden Befehle.'}
    if view=='sensor_proxy':return proxy_template(data)
    if view=='sensor_capabilities':
        return {'commands':list(COMMANDS),'tools':{name:bool(shutil.which(name)) for name in ['sshd','ufw','iptables-save','nft','fail2ban-client','docker']}}
    raise ValueError('Unbekannte Sensoransicht.')
