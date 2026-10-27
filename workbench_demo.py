"""Clearly marked local fixtures only. No host or network imports."""
import math
import time

DEMO_ID='d'*64


def read(data):
    view=data['view'];now=time.time()
    if view=='lab_memory':return {'MemTotal':8*1024**3,'MemAvailable':5*1024**3,'Cached':2*1024**3,'Buffers':64*1024**2,'SReclaimable':128*1024**2}
    if view=='lab_inodes':return {'rows':[{'path':'/','source':'/dev/demo1','total':1000000,'free':920000,'percent':8},{'path':'/mnt/daten','source':'/dev/demo2','total':5000000,'free':500000,'percent':90}], 'note':'DEMO: erfundene Dateieintragsbelegung, keine Host-Messung.'}
    if view=='lab_inode_watch':return {'enabled':False,'threshold':90}
    if view=='lab_cron':return {'rows':[{'source':'/etc/cron.d/beispiel:1','user':'root','schedule':'Jeden Dienstag um 03:00','program':'backup','outcome':'Unbekannt – Cron bestätigt keinen Exitcode.'}], 'timers':'DEMO · beispiel-backup.timer · next 03:00', 'note':'DEMO: keine echten Zeitpläne oder Argumente.','jobs':[{'name':'nachtsicherung','kind':'systemd','schedule':'*-*-* 02:30:00','user':'root','command':'/usr/local/bin/sicherung.sh'},{'name':'cache-leeren','kind':'cron','schedule':'Jeden Sonntag um 04:00','user':'www-data','command':'php /var/www/occ cache:clear'}]}
    if view=='lab_orphans':return {'rows':[{'pid':4321,'name':'beispiel-worker','state':'Z','candidate':False,'reason':'Zombie: bereits beendet; der Elternprozess muss ihn einsammeln.'}], 'note':'DEMO: kein echter Prozess und keine Beendigung.'}
    if view=='lab_analyze':return {'supported':True,'command':'chmod','targets':[], 'note':'DEMO: Es wird kein Befehl ausgeführt.'}
    if view=='lab_undo':return {'rows':[], 'note':'DEMO: keine Host-Timer.'}
    if view=='lab_native_config':return {'config_text':'# DEMO: Beispielkonfiguration\n','hash':'demo'}
    if view=='lab_apt_cleanup':return {'simulation':'DEMO: Purg example-unused [1.0]','packages':['example-unused'],'blocked':[], 'note':'DEMO: keine Paketänderung.'}
    if view=='lab_ddns':return {'config':{'enabled':False,'provider':'cloudflare','record_type':'A','domain':'app.example.com','zone':'example.com','zone_id':'','record_id':'','interval':15,'consent':False},'last':None}
    if view=='lab_domain_targets':return {'rows':[{'container':DEMO_ID,'name':'beispiel-web','upstream':'http://127.0.0.1:8080'}]}
    if view=='lab_dns_check':return {'addresses':['192.0.2.10']}
    if view=='lab_firewall_map':return {'firewall':{'text':'DEMO: allow 443/tcp','note':'DEMO: keine echten Regeln.'},'ports':'DEMO: LISTEN :443','containers':read({'view':'lab_domain_targets'})['rows'],'note':'Regelübersicht und Listener, keine vollständige Paketsimulation. Docker-Ports können UFW umgehen; leere Regelanzeige beweist keine Sperre.'}
    if view=='lab_volumes':return {'rows':[{'name':'demo-data','driver':'local'}]}
    if view=='lab_volume_files':
        if data.get('file'):return {'path':'config.txt','config_text':'# DEMO\n','file_state':{}}
        return {'path':'','rows':[{'name':'config.txt','bytes':2048,'directory':False,'regular':True,'link':False}],'note':'DEMO: keine Datei wird gelesen oder verändert.'}
    if view=='lab_builder_load':return {'directory':'/mnt/daten','name':'meine-app','services':[{'name':'web','image':'nginx:stable-alpine','port':'8080','target':'80','bind':'127.0.0.1','volume_target':'/usr/share/nginx/html','environment':{}}]}
    if view=='lab_trivy_result':return {'counts':{'CRITICAL':1,'HIGH':2,'MEDIUM':4,'LOW':2,'UNKNOWN':0},'findings':[{'VulnerabilityID':'DEMO-CVE','PkgName':'beispiel','InstalledVersion':'1.0','FixedVersion':'1.1','Severity':'HIGH'}],'note':'DEMO: erfundene Befunde, kein echter Scan.'}
    if view=='lab_docker':
        history=[{'time':now-15*(120-i),'cpu':12+8*math.sin(i/9),'memory_percent':18+i/30,'memory':'340 MiB / 2 GiB'} for i in range(120)]
        return {'rows':[{'id':DEMO_ID,'name':'beispiel-web','state':'running','status':'Up 2 hours (healthy)','image':'nginx:stable-alpine','protected':False,'update':None}],
                'stats':[{**history[-1],'id':DEMO_ID,'name':'beispiel-web'}],'history':{DEMO_ID:history},'note':'DEMO: Beispieldaten, keine Messung auf deinem Server.','error':''}
    if view=='lab_health':return {'started':'2026-10-25T12:00:00Z','restarts':0,'oom':False,'health':'healthy','failing':0,'checks':[]}
    if view=='lab_environment':return {'rows':[{'key':'TZ','value':'Europe/Berlin','masked':False},{'key':'DB_PASSWORD','value':'••••••','masked':True}],
        'compose':True,'files':'/mnt/apps/compose.yaml','directory':'/mnt/apps','note':'DEMO: sensible Werte bleiben maskiert.'}
    if view=='lab_networks':return {'networks':[{'id':'a'*64,'name':'demo-front','driver':'bridge','internal':False},{'id':'b'*64,'name':'demo-back','driver':'bridge','internal':True}],
        'containers':[{'id':DEMO_ID,'name':'beispiel-web','networks':['demo-front','demo-back']},{'id':'c'*64,'name':'beispiel-db','networks':['demo-back']}],
        'note':'DEMO: Netzwerkmitgliedschaften; keine gemessenen Verbindungen.'}
    if view=='lab_ports':return {'available':True,'conflicts':[],'port':int(data.get('port',8088)),'bind':'127.0.0.1'}
    if view=='lab_dotenv':return {'path':str(data.get('path','.env')),'rows':[{'key':'DB_PASSWORD','value':'••••••','masked':True}]}
    if view=='lab_guardian':return {'settings':{'enabled':False,'fim':False,'fim_paths':['/etc/passwd','/etc/group'],'certificates':False,'http':False,'http_targets':[],
        'oom':False,'logrotate':False,'rotation_configs':[],'log_megabytes':500,'speedtest':False,'speedtest_hours':24,'speedtest_consent':False,'speedtest_driver':'community','peak_cpu':90},
        'fim':[],'baseline':False,'last_error':{},'http':[],'speedtests':[],'tools':{'speedtest-cli':False,'speedtest':False,'openssl':True,'logrotate':True,'smartctl':True}}
    if view=='lab_sessions':return {'rows':[{'Id':'3','Name':'root','RemoteHost':'192.0.2.10','TTY':'pts/1'}],'terminals':[],'note':'DEMO: keine echte Sitzung.'}
    if view=='lab_certificates':return {'rows':[{'subject':'CN=example.com','days':12,'expires':now+12*86400,'path':'/etc/letsencrypt/live/example.com/fullchain.pem','fingerprint':'demo'}],
        'note':'DEMO: Beispielzertifikat, keine echte Ablaufwarnung.'}
    if view=='lab_disks':return {'rows':[{'path':'/dev/nvme0n1','model':'Demo SSD','remaining':94,'source':'NVMe Percentage Used','passed':True}],
        'note':'DEMO: Endurance ist eine Schätzung, keine Ausfallvorhersage.'}
    if view=='lab_history':return {'peaks':[{'time':now-3600,'cpu':98,'processes':[{'pid':1234,'name':'beispiel-worker','cpu':380,'uid':1000}]}],
        'oom':[{'key':'demo','time':now-7200,'source':'Docker','text':'beispiel-worker · OOMKilled=true (DEMO)'}],'warning':'','note':'DEMO: erfundene Beispielereignisse.'}
    if view=='lab_backup_options':return {'backups':[],'images':[]}
    if view=='lab_logs':return {'rows':[{'path':'/var/log/nginx/access.log','bytes':750*1024**2}],'available':True,'configs':['/etc/logrotate.d/nginx'],'note':'DEMO: keine Logdatei wird verändert.'}
    if view=='lab_summary':return {'certificates':read({'view':'lab_certificates'})['rows'],'disks':read({'view':'lab_disks'})['rows']}
    raise ValueError('Unbekannte Demo-Ansicht.')
