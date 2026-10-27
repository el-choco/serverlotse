import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import time
import admin_core as core
import docker_tools


def validate(data):
    cfg=core.config(data.get('id'))
    if not cfg.get('bundle') or not cfg.get('container') or not cfg.get('database'):
        raise ValueError('Eine komprimierte Dateisicherung mit SQL-Export wählen.')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}',cfg['database']):raise ValueError('Ungültiger Datenbankname.')
    archive=core.archive_file(cfg,data.get('archive'))
    image_id=str(data.get('image',''))
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',image_id):raise ValueError('Eine vorhandene lokale MySQL-/MariaDB-Image-ID wählen.')
    image=docker_tools.api('GET','/images/'+image_id+'/json')
    tags=image.get('RepoTags') or []
    if not any(re.fullmatch(r'(?:docker\.io/library/)?(?:mysql|mariadb):[^\s]+',tag) for tag in tags):
        raise ValueError('Nur bereits vorhandene offizielle MySQL-/MariaDB-Images für den Test verwenden.')
    info=archive.stat()
    return {'operation':'lab_restore_test','id':data['id'],'archive':archive.name,'image':image_id,'database':cfg['database'],
            'archive_identity':[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]}


def apply(plan):
    cfg=core.config(plan['id']);checked=core.verify_archive(cfg,plan['archive'])
    archive=core.archive_file(cfg,plan['archive']);name='serverlotse-restore-test-'+secrets.token_hex(8)
    created=None
    with tempfile.TemporaryDirectory(prefix='.serverlotse-sql-test-',dir=archive.parent) as temp:
        sql=Path(temp)/'restore.sql';found=False
        with tarfile.open(archive,'r:*') as tar:
            target='files/__serverlotse_database__/'+plan['database']+'.sql'
            for member in tar:
                if member.name!=target:continue
                if not member.isfile() or member.size>512*1024**2:raise ValueError('SQL-Test unterstützt Exporte bis 512 MiB.')
                if shutil.disk_usage(archive.parent).free<member.size+256*1024**2:raise ValueError('Zu wenig Platz für den isolierten SQL-Test.')
                with sql.open('xb') as output,tar.extractfile(member) as source:shutil.copyfileobj(source,output,1024*1024)
                found=True;break
        if not found:raise ValueError('SQL-Datei fehlt im verifizierten Archiv.')
        spec={'Image':plan['image'],'Env':['MYSQL_ALLOW_EMPTY_PASSWORD=yes','MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=yes'],
              'Labels':{'serverlotse.restore-test':'true'},
              'HostConfig':{'NetworkMode':'none','Memory':1024**3,'PidsLimit':128,'NanoCpus':1000000000,
                  'ReadonlyRootfs':True,'Tmpfs':{'/var/lib/mysql':'rw,nosuid,nodev,size=1073741824',
                      '/var/lib/mysql-files':'rw,nosuid,nodev,size=67108864','/tmp':'rw,nosuid,nodev,size=67108864',
                      '/run':'rw,nosuid,nodev,size=33554432'},'LogConfig':{'Type':'json-file','Config':{'max-size':'5m','max-file':'1'}},
                  'SecurityOpt':['no-new-privileges:true'],'CapDrop':['ALL'],'CapAdd':['CHOWN','SETUID','SETGID','DAC_OVERRIDE'],
                  'RestartPolicy':{'Name':'no'}},'NetworkDisabled':True}
        try:
            created=docker_tools.ident(docker_tools.api('POST','/containers/create?name='+name,spec)['Id'])
            docker_tools.api('POST','/containers/'+created+'/start')
            deadline=time.monotonic()+120
            script='if command -v mariadb-admin >/dev/null; then exec mariadb-admin --user=root ping --silent; else exec mysqladmin --user=root ping --silent; fi'
            while True:
                try:core.command(['docker','exec',created,'/bin/sh','-c',script],timeout=8);break
                except ValueError:
                    if time.monotonic()>deadline:raise ValueError('Temporäre Datenbank wurde nicht bereit; keine Live-Datenbank verändert.') from None
                    time.sleep(2)
            client='if command -v mariadb >/dev/null; then exec mariadb --user=root; else exec mysql --user=root; fi'
            with sql.open('rb') as source,tempfile.TemporaryFile() as output:
                process=subprocess.Popen(['docker','exec','-i',created,'/bin/sh','-c',client],stdin=source,stdout=output,stderr=subprocess.STDOUT,env=core.ENV)
                try:process.wait(timeout=180)
                except subprocess.TimeoutExpired:process.kill();process.wait();raise ValueError('SQL-Import im Testcontainer hat das Zeitlimit erreicht.') from None
                if process.returncode:raise ValueError('SQL-Import im Wegwerf-Container fehlgeschlagen. Export ist für dieses Datenbank-Image nicht wiederherstellbar; Rohdaten werden nicht protokolliert.')
            query='SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='+"'"+plan['database']+"';"
            tool='mariadb' if any('mariadb:' in tag for tag in docker_tools.api('GET','/images/'+plan['image']+'/json').get('RepoTags') or []) else 'mysql'
            count=core.command(['docker','exec',created,tool,'--user=root','--batch','--skip-column-names','--execute',query],timeout=20).strip()
            if not count.isdigit():raise ValueError('SQL-Test lieferte keine eindeutige Tabellenzahl.')
            return {**checked,'tables':int(count),'image':plan['image'],
                'note':'Manifest und tatsächlicher SQL-Import in isolierter Wegwerf-Datenbank geprüft. Keine App-Funktionsprüfung oder Garantie eines konsistenten gemeinsamen Datei-/DB-Snapshots.'}
        finally:
            if created:
                try:
                    info=docker_tools.inspect(created,False)
                    if (info.get('Config',{}).get('Labels') or {}).get('serverlotse.restore-test')!='true':raise ValueError('Testlabel verändert.')
                    docker_tools.api('DELETE','/containers/'+created+'?force=true&v=true')
                except Exception:raise ValueError('Testcontainer konnte nicht sicher bereinigt werden. Diese konkrete ID prüfen: '+created) from None
