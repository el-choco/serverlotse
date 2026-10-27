import configparser
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import admin_core as core
import sensors
import toolkit

OPS={'shell_run','docker_clean','volume_delete','firewall_rule','settings_save','webhook_test',
     'update_policy','proxy_apply','bundle_run','remote_save','heal_resume','tool_install','process_signal'}
VIEWS={'advanced_settings','advanced_tools','advanced_remotes','advanced_updates','advanced_heal'}
SECRET_KEYS={'webhook_url','telegram_token','telegram_chat','access_key','secret_key','ddns_token','ddns_password','config_text','encoded_data','compose_document','backup'}
DEFAULTS={'enabled':False,'notify_cpu':True,'notify_ram':True,'notify_ssh':False,'cpu':90,'ram':90,
          'hold_seconds':60,'cooldown_minutes':15,'ssh_failures':10,'webhook_kind':'discord',
          'heal_containers':[],'heal_services':[],'janitor':False,'janitor_hour':3,'rclone_config':''}


def config(raw=False):
    with core.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS advanced_config(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT)')
        row=db.execute('SELECT data FROM advanced_config WHERE id=1').fetchone()
    data={**copy.deepcopy(DEFAULTS),**(json.loads(row['data']) if row else {})}
    return data if raw else public(data)


def public(data,audit=False):
    if isinstance(data,list):return [public(item,audit) for item in data]
    if not isinstance(data,dict):return data
    result={}
    for key,value in data.items():
        if key=='env_updates' and isinstance(value,dict):result[key]={name:('[entfernen]' if item is None else '••••••') for name,item in value.items()}
        elif key in SECRET_KEYS:
            if value:result[key+'_configured']=True
            if key=='webhook_url' and value:result['webhook_host']=urlsplit(value).hostname
        elif audit and key=='command':result[key]='[Root-Befehl nicht gespeichert]'
        else:result[key]=public(value,audit)
    return result


def save_config(data):
    config()
    stored={k:v for k,v in data.items() if k!='clear_webhook'}
    with core.db() as db:db.execute('INSERT OR REPLACE INTO advanced_config VALUES(1,?)',(json.dumps(stored),))


def state(key,value=None):
    with core.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS automation_state(name TEXT PRIMARY KEY,data TEXT)')
        if value is not None:
            db.execute('INSERT OR REPLACE INTO automation_state VALUES(?,?)',(key,json.dumps(value)));return value
        row=db.execute('SELECT data FROM automation_state WHERE name=?',(key,)).fetchone()
    return json.loads(row['data']) if row else None


def log_event(operation,result,status='done'):
    with core.db() as db:db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),time.time(),operation,'{}',status,toolkit.redact(str(result))[:64000]))


def normalize_config(data):
    if not isinstance(data,dict):raise ValueError('Ungültige Automatik-Einstellungen.')
    current=config(True);result=dict(current)
    for key in ['enabled','notify_cpu','notify_ram','notify_ssh','janitor']:
        if key in data:result[key]=data[key] is True
    for key,low,high in [('cpu',1,100),('ram',1,100),('hold_seconds',10,3600),('cooldown_minutes',1,1440),('ssh_failures',3,1000),('janitor_hour',0,23)]:
        value=int(data.get(key,current[key]))
        if not low<=value<=high:raise ValueError('Ungültiger Grenzwert: '+key)
        result[key]=value
    kind=data.get('webhook_kind',current['webhook_kind'])
    if kind not in {'discord','telegram','generic'}:raise ValueError('Ungültiger Webhook-Typ.')
    result['webhook_kind']=kind
    for key in ['webhook_url','telegram_token','telegram_chat']:
        if data.get(key):result[key]=str(data[key]).strip()
    if data.get('clear_webhook') is True:
        for key in ['webhook_url','telegram_token','telegram_chat']:result.pop(key,None)
    result['clear_webhook']=data.get('clear_webhook') is True
    url=result.get('webhook_url','')
    if url:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or len(url)>2048:raise ValueError('Webhook benötigt eine HTTPS-Adresse ohne Benutzerinformationen.')
        if kind=='discord' and (parsed.hostname not in {'discord.com','discordapp.com'} or not parsed.path.startswith('/api/webhooks/')):raise ValueError('Eine Discord-Webhook-Adresse verwenden.')
    if result.get('telegram_token') and not re.fullmatch(r'\d{5,20}:[A-Za-z0-9_-]{20,100}',result['telegram_token']):raise ValueError('Ungültiger Telegram-Bot-Token.')
    if result.get('telegram_chat') and not re.fullmatch(r'-?\d{1,25}',result['telegram_chat']):raise ValueError('Numerische Telegram-Chat-ID angeben.')
    for key in ['heal_containers','heal_services']:
        values=data.get(key,current[key])
        if not isinstance(values,list) or len(values)>30:raise ValueError('Maximal 30 Auto-Heiler-Ziele.')
        for target in values:
            pattern=r'[a-f0-9]{64}' if key=='heal_containers' else r'[A-Za-z0-9_@.:-]+\.service'
            if not isinstance(target,str) or not re.fullmatch(pattern,target):raise ValueError('Ungültiges Auto-Heiler-Ziel.')
            if result['enabled']:
                if key=='heal_containers':core.validate({'operation':'container','container':target,'verb':'restart'})
                else:core.validate({'operation':'service','name':target,'verb':'restart'})
        result[key]=list(dict.fromkeys(values))
    path=str(data.get('rclone_config',current['rclone_config']))
    if path and (path!=current['rclone_config'] or result['enabled']):check_rclone_config(path)
    result['rclone_config']=path
    return result


def file_hash(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def atomic_write(path,payload,mode=None):
    core.local_path(str(path),existing=False);core.private_destination(path.parent)
    existing=path.stat() if path.exists() else None
    permissions=mode if mode is not None else stat.S_IMODE(existing.st_mode) if existing else 0o644
    fd,name=tempfile.mkstemp(prefix='.serverlotse-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            if hasattr(os,'fchown'):
                uid,gid=(0,0) if permissions==0o600 else (existing.st_uid,existing.st_gid) if existing else (0,0)
                os.fchown(stream.fileno(),uid,gid)
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,permissions);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def validate(data):
    op=data['operation'];p={'operation':op}
    if op=='shell_run':
        text=data.get('command','')
        if not isinstance(text,str) or not 1<=len(text)<=4096 or '\x00' in text:raise ValueError('Befehl mit maximal 4096 Zeichen angeben.')
        p['command']=text
    elif op=='process_signal':
        pid=int(data.get('pid',0));verb=data.get('verb')
        if pid<=1 or pid==os.getpid() or verb not in {'term','stop','continue','kill'}:raise ValueError('Ungültiger Prozess oder Aktion.')
        if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):raise ValueError('Sichere Prozessaktionen benötigen Linux mit pidfd-Unterstützung.')
        row=next((row for row in sensors.processes()['rows'] if row['pid']==pid),None)
        if not row:raise ValueError('Prozess nicht mehr vorhanden.')
        if not 1000<=row['uid']<65534 or row['name'] in {'sshd','dropbear','systemd','dockerd','containerd','systemd-logind'}:raise ValueError('Root-, System- und Zugangsprozesse bleiben in der Prozessübersicht geschützt.')
        p.update(pid=pid,verb=verb,start=row['start'],uid=row['uid'],name=row['name'])
    elif op=='docker_clean':p['minimum_age_hours']=168
    elif op=='volume_delete':
        name=data.get('name','')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,250}',name):raise ValueError('Ungültiger Volumename.')
        if name not in sensors.unused(core)['volumes']:raise ValueError('Volume wird verwendet oder ist nicht vorhanden.')
        p.update(name=name,irreversible=True)
    elif op=='firewall_rule':
        port=int(data.get('port',0));protocol=data.get('protocol','tcp');verb=data.get('verb','allow')
        if not 1<=port<=65535 or protocol not in {'tcp','udp'} or verb not in {'allow','close'}:raise ValueError('Ungültige Portregel.')
        report=sensors.firewall(core)
        if report['backend']!='ufw' or 'Status: active' not in report['text']:raise ValueError('UFW muss bereits aktiv sein. Kein automatisches Aktivieren über Fernzugriff.')
        ssh_ports={int(line.split()[1]) for line in core.command([shutil.which('sshd') or '/usr/sbin/sshd','-T']).splitlines() if line.startswith('port ')}
        if verb=='close' and port in ssh_ports|{22,23,443,18099}:raise ValueError('SSH- und Verwaltungsports sind gegen Schließen geschützt.')
        p.update(port=port,protocol=protocol,verb=verb,state_hash=hashlib.sha256(report['text'].encode()).hexdigest())
        p['simulation']=core.command(['ufw','--dry-run',*(['delete'] if verb=='close' else []),'allow',f'{port}/{protocol}'])
    elif op=='settings_save':
        p['existing_config_hash']=hashlib.sha256(json.dumps(config(True),sort_keys=True).encode()).hexdigest()
        p['settings']=normalize_config(data.get('settings',{}))
    elif op=='webhook_test':
        cfg=config(True)
        ready=bool(cfg.get('telegram_token') and cfg.get('telegram_chat')) if cfg['webhook_kind']=='telegram' else bool(cfg.get('webhook_url'))
        if not ready:raise ValueError('Zuerst einen Webhook konfigurieren.')
        p['webhook_kind']=cfg['webhook_kind']
        p['destination']=('Telegram …'+cfg['telegram_chat'][-4:]) if cfg['webhook_kind']=='telegram' else urlsplit(cfg['webhook_url']).hostname
        p['existing_config_hash']=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
    elif op=='heal_resume':
        target=data.get('target')
        if target not in config(True)['heal_containers']+config(True)['heal_services']:raise ValueError('Kein konfiguriertes Auto-Heiler-Ziel.')
        p['target']=target
    elif op=='update_policy':
        if not shutil.which('unattended-upgrade'):raise ValueError('Auf dem Host fehlt unattended-upgrades. Zuerst über die Paketverwaltung installieren.')
        hour=int(data.get('hour',3));minute=int(data.get('minute',0))
        if not 0<=hour<=23 or not 0<=minute<=59:raise ValueError('Ungültige Uhrzeit.')
        p.update(enabled=data.get('enabled') is True,hour=hour,minute=minute,existing_hash=file_hash(Path('/etc/apt/apt.conf.d/99serverlotse-security')),
                 existing_timer_hash=file_hash(Path('/etc/systemd/system/apt-daily-upgrade.timer.d/serverlotse.conf')))
    elif op=='tool_install':
        package=data.get('package')
        if package not in {'unattended-upgrades','rclone','smartmontools','acl','certbot','speedtest-cli','logrotate','openssl','nftables'}:raise ValueError('Dieses Paket wird nicht über den Werkzeug-Installer angeboten.')
        p.update(package=package,simulation=core.command(['apt-get','-s','install',package],timeout=90))
    elif op=='proxy_apply':
        info=sensors.proxy_template(data);engine=data.get('engine','caddy')
        if engine not in {'caddy','nginx'}:raise ValueError('Caddy oder Nginx auswählen.')
        if data.get('acme_consent') is not True:raise ValueError('ACME-Nutzungsbedingungen und Veröffentlichung des Domainnamens zuerst bestätigen.')
        p['acme_consent']=True
        domain=str(data['domain']).lower()
        if engine=='caddy':
            if not shutil.which('caddy'):raise ValueError('Caddy ist auf dem Host nicht installiert.')
            path=core.local_path('/etc/caddy/Caddyfile');core.private_destination(path.parent)
            info=path.stat()
            if info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Caddy-Konfiguration muss root gehören und darf für Gruppe/andere nicht beschreibbar sein.')
            if domain in path.read_text():raise ValueError('Domain steht bereits in der Konfiguration; kein Überschreiben.')
            p['existing_hash']=file_hash(path)
        else:
            if not shutil.which('nginx') or not shutil.which('certbot'):raise ValueError('Nginx und Certbot müssen auf dem Host installiert sein.')
            core.private_destination(Path('/etc/nginx/sites-available'));core.private_destination(Path('/etc/nginx/sites-enabled'))
            if domain in core.command(['nginx','-T']):raise ValueError('Domain steht bereits in der Nginx-Konfiguration.')
            if (Path('/etc/nginx/sites-available')/('serverlotse-'+domain+'.conf')).exists():raise ValueError('Konfigurationsdatei existiert bereits.')
            email=str(data.get('email',''))
            if not re.fullmatch(r'[^\s@]{1,100}@[^\s@]{1,150}\.[A-Za-z]{2,63}',email):raise ValueError('E-Mail für das Zertifikatskonto angeben.')
            p.update(email=email,acme_consent=True)
        p.update(engine=engine,domain=domain,upstream=str(data['upstream']))
    elif op=='bundle_run':
        import bundle_backup
        p.update(bundle_backup.validate(data))
    elif op=='remote_save':p.update(validate_remote(data))
    else:raise ValueError('Unbekannte Verwaltungsaktion.')
    return p


def warnings(plan):
    op=plan['operation']
    notes=['Diese Erweiterung greift mit Administratorrechten auf den Host zu.']
    if op=='shell_run':notes+=['Freie Root-Befehle können sämtliche Daten und Dienste verändern. Keine interaktive Sitzung; nach 120 Sekunden wird die Prozessgruppe beendet. Befehle werden nicht dauerhaft gespeichert, Ausgaben nur bestmöglich maskiert.']
    if op=='process_signal':notes+=['Sendet ein Signal an genau diesen Benutzerprozess. Beenden oder Erzwingen kann ungespeicherte Arbeit verlieren. Ein angefordertes Signal bestätigt noch nicht, dass der Prozess beendet ist.']
    if op=='volume_delete':notes+=['Dieses Volume wird endgültig gelöscht. Nicht referenziert heißt nicht leer. Ein vorhandenes Backup vorher prüfen.']
    if op=='docker_clean':notes+=['Entfernt unbenutzte dangling Images und Build-Cache, die älter als sieben Tage sind. Keine Volumes, gestoppten Container oder Netzwerke. Es gibt keine exakte Dry-Run-Platzgarantie.']
    if op=='firewall_rule':notes+=['Firewallregeln können Zugänge unterbrechen. Schließen entfernt eine einfache UFW-Allow-Regel; andere Regeln oder Docker-Portfreigaben können Zugriff weiterhin erlauben.']
    if op=='settings_save':notes+=['Automatik ist nur bei aktiviertem Hauptschalter wirksam. Benachrichtigungen übertragen Hostname und Mess-/Fehlerzahlen an das konfigurierte Ziel. Auto-Heiler starten nur ausgewählte Ziele neu, mit Wiederanlaufgrenze.']
    if op=='webhook_test':notes+=['Sendet jetzt eine Testnachricht mit dem Hostnamen an das hinterlegte externe Ziel.']
    if op=='update_policy':notes+=['Richtet einen nächtlichen Sicherheitsupdate-Zeitplan auf diesem Host ein. Keine automatischen Neustarts. Änderungen an Paketkonfigurationen können trotzdem Dienste neu starten.']
    if op=='tool_install':notes+=['Installiert das gewählte Paket mit seinen Abhängigkeiten über APT. Paket-Skripte können Dienste starten. Keine Entfernung bestehender Pakete.']
    if op=='proxy_apply':notes+=['Verändert den nativen Proxy dieses Hosts und lädt ihn neu. Zertifikatsanfragen veröffentlichen den Domainnamen in Certificate-Transparency-Logs. DNS und öffentliche Ports müssen stimmen. Nginx Proxy Manager wird nicht verändert.']
    if op=='bundle_run':notes+=['Erstellt eine neue .tar.gz-Sicherung. SQL ist ein logischer Snapshot transaktionaler Tabellen; Dateien und Datenbank sind kein gemeinsamer atomarer Snapshot. Ein Remote-Ziel lädt die fertige Sicherung extern hoch. Archive sind nicht verschlüsselt; Zugriffsrechte des Ziels prüfen.']
    if op=='remote_save':notes+=['Speichert Zugangsdaten im root-lesbaren rclone-Profil. Noch kein Verbindungsaufbau oder Upload. SSH-Hostschlüssel werden bei SFTP geprüft.']
    return notes


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def notify(text,cfg=None):
    cfg=cfg or config(True);kind=cfg['webhook_kind']
    if kind=='telegram':
        if not cfg.get('telegram_token') or not cfg.get('telegram_chat'):raise ValueError('Telegram ist nicht vollständig konfiguriert.')
        url='https://api.telegram.org/bot'+cfg['telegram_token']+'/sendMessage';payload={'chat_id':cfg['telegram_chat'],'text':text[:1800]}
    else:
        url=cfg.get('webhook_url','')
        if not url:raise ValueError('Kein Webhook eingerichtet.')
        payload={'content':text[:1800],'allowed_mentions':{'parse':[]}} if kind=='discord' else {'message':text[:1800],'source':'ServerLotse'}
    try:
        request=Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':'ServerLotse/0.6'})
        with build_opener(NoRedirect).open(request,timeout=8) as response:response.read(4096)
    except Exception:raise ValueError('Webhook-Versand fehlgeschlagen. Adresse, Berechtigung und Internetzugang prüfen.') from None


def remote_args():
    path=config(True).get('rclone_config')
    if not path and Path('/etc/serverlotse/remotes.conf').exists():path='/etc/serverlotse/remotes.conf'
    if path:check_rclone_config(path)
    return ['--config',path] if path else []


def check_rclone_config(value):
    path=core.local_path(value)
    if not path.is_file():raise ValueError('rclone-Konfiguration ist keine Datei.')
    core.private_destination(path.parent)
    info=path.stat()
    if info.st_uid!=0 or info.st_mode&0o022:raise ValueError('rclone-Konfiguration muss root gehören und darf für Gruppe/andere nicht beschreibbar sein.')
    return path


def remote_list():return core.command(['rclone',*remote_args(),'listremotes']).splitlines()


def validate_remote(data):
    name=str(data.get('name',''));provider=data.get('provider')
    if not re.fullmatch(r'serverlotse_[A-Za-z0-9_-]{1,50}',name):raise ValueError('Remote-Name muss mit serverlotse_ beginnen.')
    if provider not in {'sftp','s3'}:raise ValueError('SFTP oder S3 auswählen.')
    p={'name':name,'provider':provider}
    path=Path('/etc/serverlotse/remotes.conf');core.local_path(str(path),existing=False);p['existing_hash']=file_hash(path)
    parser=configparser.ConfigParser(interpolation=None)
    if path.exists():parser.read(path)
    if parser.has_section(name):raise ValueError('Remote existiert bereits. Kein Überschreiben vorhandener Profile.')
    if provider=='sftp':
        host=str(data.get('host',''));user=str(data.get('user',''));port=int(data.get('port',22))
        if not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}',host) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',user) or user.startswith('-') or not 1<=port<=65535:raise ValueError('Ungültige SFTP-Verbindungsdaten.')
        for key in ['key_file','known_hosts_file']:
            value=core.local_path(str(data.get(key,'')))
            if not value.is_file():raise ValueError('SSH-Schlüssel und known_hosts müssen vorhandene Dateien sein.')
            core.private_destination(value.parent)
            info=value.stat()
            if info.st_uid!=0 or info.st_mode&0o022 or (key=='key_file' and info.st_mode&0o077):raise ValueError('SSH-Dateien müssen root gehören; der private Schlüssel braucht ausschließlich root-Leserechte (z. B. 600).')
            p[key]=str(value)
        p.update(host=host,user=user,port=port)
    else:
        endpoint=str(data.get('endpoint',''));region=str(data.get('region','us-east-1'))
        if endpoint:
            parsed=urlsplit(endpoint)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}:raise ValueError('S3-Endpunkt als HTTPS-Adresse angeben.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',region):raise ValueError('Ungültige S3-Region.')
        for key in ['access_key','secret_key']:
            value=data.get(key,'')
            if not isinstance(value,str) or not 1<=len(value)<=512 or any(ord(c)<32 for c in value):raise ValueError('S3-Zugangsdaten fehlen oder sind ungültig.')
            p[key]=value
        p.update(endpoint=endpoint,region=region)
    return p


def save_remote(plan):
    path=Path('/etc/serverlotse/remotes.conf');parser=configparser.ConfigParser(interpolation=None)
    if path.exists():parser.read(path)
    if parser.has_section(plan['name']):raise ValueError('Remote existiert bereits.')
    if plan['provider']=='sftp':values={'type':'sftp',**{key:str(plan[key]) for key in ['host','user','port','key_file','known_hosts_file']}}
    else:values={'type':'s3','provider':'Other' if plan['endpoint'] else 'AWS','env_auth':'false','access_key_id':plan['access_key'],'secret_access_key':plan['secret_key'],'region':plan['region'],'endpoint':plan['endpoint']}
    parser[plan['name']]=values
    import io
    stream=io.StringIO();parser.write(stream)
    path.parent.mkdir(mode=0o700,exist_ok=True);atomic_write(path,stream.getvalue().encode(),0o600)
    cfg=config(True);cfg['rclone_config']=str(path);save_config(cfg)
    return {'remote':plan['name']+':','config':str(path),'note':'Remote-Profil gespeichert und für neue ServerLotse-Remote-Backups ausgewählt. Vorhandene rclone-Dienste und Synchronisationen wurden nicht verändert.'}


def apply(plan):
    op=plan['operation']
    if op=='shell_run':
        try:output=core.command(['/bin/sh','-lc',plan['command']],timeout=120)
        except ValueError as exc:raise ValueError(toolkit.redact(str(exc))) from None
        return {'text':toolkit.redact(output),'note':'Root-Befehl beendet. Keine interaktive Sitzung. Hintergrundprozesse können die Sitzung überleben.'}
    if op=='process_signal':
        fd=os.pidfd_open(plan['pid'])
        try:
            row=next((row for row in sensors.processes()['rows'] if row['pid']==plan['pid']),None)
            if not row or row['start']!=plan['start'] or row['uid']!=plan['uid']:raise ValueError('Prozess wurde ersetzt. Neue Vorschau erforderlich.')
            name={'term':'SIGTERM','stop':'SIGSTOP','continue':'SIGCONT','kill':'SIGKILL'}[plan['verb']]
            signal.pidfd_send_signal(fd,getattr(signal,name))
        finally:os.close(fd)
        return {'pid':plan['pid'],'signal':plan['verb'],'note':'Signal angefordert. Prozesszustand erneut prüfen.'}
    if op=='docker_clean':return {'images':core.command(['docker','image','prune','--force','--filter','until=168h'],timeout=600),'cache':core.command(['docker','builder','prune','--force','--filter','until=168h'],timeout=600)}
    if op=='volume_delete':return {'text':core.command(['docker','volume','rm',plan['name']],timeout=120)}
    if op=='firewall_rule':return {'text':core.command(['ufw','--force',*(['delete'] if plan['verb']=='close' else []),'allow',f"{plan['port']}/{plan['protocol']}"]),'note':'UFW-Regel geändert. Andere Freigaben und Docker-Ports separat prüfen.'}
    if op=='settings_save':save_config(plan['settings']);return {'note':'Einstellungen gespeichert. Automatik wirkt nur mit aktiviertem Hauptschalter.'}
    if op=='webhook_test':
        import socket
        notify('ServerLotse: Testbenachrichtigung von '+socket.gethostname());return {'note':'Testbenachrichtigung gesendet.'}
    if op=='heal_resume':state('suppressed:'+plan['target'],False);state('attempts:'+plan['target'],[]);return {'note':'Auto-Heiler-Sperre für dieses Ziel zurückgesetzt.'}
    if op=='update_policy':return apply_update_policy(plan)
    if op=='tool_install':return {'text':core.command(['apt-get','--assume-yes','--no-remove','-o','Dpkg::Options::=--force-confold','install',plan['package']],timeout=3600)}
    if op=='proxy_apply':
        import proxy_control
        return proxy_control.apply(plan)
    if op=='bundle_run':
        import bundle_backup
        return bundle_backup.apply(plan)
    if op=='remote_save':return save_remote(plan)
    raise ValueError('Unbekannte Erweiterungsaktion.')


def update_policy_text(plan):
    policy='// ServerLotse\nAPT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "'+('1' if plan['enabled'] else '0')+'";\nUnattended-Upgrade::Automatic-Reboot "false";\n'
    policy+='#clear Unattended-Upgrade::Allowed-Origins;\n#clear Unattended-Upgrade::Origins-Pattern;\nUnattended-Upgrade::Origins-Pattern { "origin=Debian,codename=${distro_codename}-security,label=Debian-Security"; "origin=Debian,codename=${distro_codename},label=Debian-Security"; "origin=Ubuntu,archive=${distro_codename}-security"; };\n'
    return policy


def apply_update_policy(plan):
    folder=Path('/etc/apt/apt.conf.d');core.private_destination(folder);path=folder/'99serverlotse-security'
    if path.exists() and not path.read_text().startswith('// ServerLotse'):raise ValueError('Fremde Konfiguration wird nicht überschrieben.')
    policy=update_policy_text(plan)
    if path.exists():(core.STATE/('apt-policy-'+secrets.token_hex(8)+'.bak')).write_bytes(path.read_bytes())
    atomic_write(path,policy.encode())
    directory=Path('/etc/systemd/system/apt-daily-upgrade.timer.d');directory.mkdir(parents=True,mode=0o755,exist_ok=True)
    timer=directory/'serverlotse.conf';core.local_path(str(timer),existing=False)
    atomic_write(timer,f"# ServerLotse\n[Timer]\nOnCalendar=\nOnCalendar=*-*-* {plan['hour']:02}:{plan['minute']:02}:00\nRandomizedDelaySec=0\nPersistent=true\n".encode())
    core.command(['systemctl','daemon-reload']);core.command(['systemctl','enable','--now','apt-daily-upgrade.timer']);core.command(['systemctl','restart','apt-daily-upgrade.timer'])
    return {'note':'Sicherheitsupdate-Zeitplan gespeichert. Keine automatischen Reboots. Vorhandene spätere APT-Konfigurationen können die Richtlinie beeinflussen.'}


def read(data):
    view=data['view']
    if view=='advanced_settings':return config()
    if view=='advanced_tools':return {'tools':{name:bool(shutil.which(name)) for name in ['ufw','sshd','rclone','caddy','nginx','certbot','unattended-upgrade']}}
    if view=='advanced_remotes':return {'remotes':remote_list(),'config':remote_args()}
    if view=='advanced_updates':
        path=Path('/etc/apt/apt.conf.d/99serverlotse-security');policy=path.read_text() if path.exists() else ''
        timer=Path('/etc/systemd/system/apt-daily-upgrade.timer.d/serverlotse.conf');text=timer.read_text() if timer.exists() else ''
        match=re.search(r'OnCalendar=\*-\*-\* (\d{2}):(\d{2}):00',text)
        return {'installed':bool(shutil.which('unattended-upgrade')),'timers':core.command(['systemctl','list-timers','apt-daily-upgrade.timer','--no-pager']),
                'policy':policy,'enabled':bool(re.search(r'APT::Periodic::Unattended-Upgrade\s+"1"',policy)),
                'hour':int(match[1]) if match else 3,'minute':int(match[2]) if match else 0}
    if view=='advanced_heal':
        cfg=config(True);targets=cfg['heal_containers']+cfg['heal_services']
        rows=[]
        for target in targets:
            name=target
            if re.fullmatch(r'[a-f0-9]{64}',target):
                try:name=core.command(['docker','inspect','--type','container','--format','{{.Name}}',target]).strip().lstrip('/')
                except ValueError:name=target[:12]
            rows.append({'target':target,'name':name,'suppressed':bool(state('suppressed:'+target)),'attempts':state('attempts:'+target) or []})
        return {'rows':rows}
    raise ValueError('Unbekannte Erweiterungsansicht.')
