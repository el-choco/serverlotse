import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import subprocess
import tarfile
import tempfile
import time
import admin_core as core


def validate(data):
    import advanced
    p=core.validate_backup(data)
    container=str(data.get('container',''));database=str(data.get('database',''));user=str(data.get('db_user','root'))
    if bool(container)!=bool(database):raise ValueError('Datenbank und Container gemeinsam angeben oder beide leer lassen.')
    if container:
        if not re.fullmatch(r'[a-f0-9]{64}',container) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',database) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',user):raise ValueError('Ungültige Datenbankangaben.')
        core.command(['docker','inspect','--type','container','--format','{{.Id}}',container])
    remote=str(data.get('remote',''))
    if remote:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}:[A-Za-z0-9_./ -]{0,500}',remote) or '..' in remote.partition(':')[2].split('/'):raise ValueError('Remote als profil:bucket/ordner ohne .. angeben.')
        if remote.partition(':')[0]+':' not in advanced.remote_list():raise ValueError('Remote-Profil nicht gefunden.')
    args=advanced.remote_args() if remote else []
    path=args[1] if args else ''
    p.update(container=container,database=database,db_user=user,remote=remote,rclone_config=path,
             remote_config_hash=advanced.file_hash(Path(path)) if path else None)
    return p


def database_dump(plan,path):
    script=('if [ "$1" = root ]; then export MYSQL_PWD="${MYSQL_ROOT_PASSWORD:-$MARIADB_ROOT_PASSWORD}"; '
            'else export MYSQL_PWD="${MYSQL_PASSWORD:-$MARIADB_PASSWORD}"; fi; '
            'if command -v mariadb-dump >/dev/null; then tool=mariadb-dump; else tool=mysqldump; fi; '
            'exec "$tool" --user="$1" --single-transaction --routines --events --triggers --databases "$2"')
    with path.open('xb') as output,tempfile.TemporaryFile() as errors:
        process=subprocess.Popen(['docker','exec',plan['container'],'/bin/sh','-c',script,'sh',plan['db_user'],plan['database']],
                                 stdin=subprocess.DEVNULL,stdout=output,stderr=errors,env=core.ENV,start_new_session=True)
        problem=None;deadline=time.monotonic()+900
        while process.poll() is None:
            if time.monotonic()>deadline:problem='Datenbankexport hat das Zeitlimit erreicht.';break
            if shutil.disk_usage(path.parent).free<256*1024*1024:problem='Zu wenig freier Platz für den Datenbankexport.';break
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
        if problem:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise ValueError(problem+' Ein abgebrochener docker-exec kann im Container noch laufen; dort prüfen.')
        if process.returncode:raise ValueError('Datenbankexport fehlgeschlagen. Container, Datenbank, Benutzer und dessen Passwort-Umgebungsvariable prüfen.')
        if output.tell()==0:raise ValueError('Datenbankexport war leer; Sicherung wurde abgebrochen.')
        output.flush();os.fsync(output.fileno())


def compressed_copy(source,destination,dump=None,database=''):
    partial=destination.with_suffix('.gz.partial')
    with tarfile.open(source,'r:') as original,tarfile.open(partial,'w:gz') as compressed:
        member=original.getmember('manifest.json')
        if member.size>32_000_000:raise ValueError('Manifest zu groß.')
        manifest=json.load(original.extractfile(member))
        class SpaceReader:
            def __init__(self,stream):self.stream=stream;self.read_bytes=4*1024*1024
            def read(self,size=-1):
                if self.read_bytes>=4*1024*1024:
                    if shutil.disk_usage(destination.parent).free<256*1024*1024:raise ValueError('Zu wenig freier Platz während der Komprimierung.')
                    self.read_bytes=0
                chunk=self.stream.read(size);self.read_bytes+=len(chunk);return chunk
        for member in original:
            if member.name!='manifest.json':compressed.addfile(member,SpaceReader(original.extractfile(member)) if member.isfile() else None)
        if dump:
            key='__serverlotse_database__/'+database+'.sql'
            if key in manifest['files']:raise ValueError('Reservierter Datenbankpfad existiert bereits in der Quelle.')
            hasher=hashlib.sha256()
            with dump.open('rb') as stream:
                while chunk:=stream.read(1024*1024):hasher.update(chunk)
            item=tarfile.TarInfo('files/'+key);item.size=dump.stat().st_size;item.mode=0o600
            with dump.open('rb') as stream:compressed.addfile(item,SpaceReader(stream))
            manifest['files'][key]={'size':item.size,'sha256':hasher.hexdigest()}
        payload=json.dumps(manifest).encode()
        if len(payload)>32_000_000:raise ValueError('Sicherungsmanifest zu groß.')
        item=tarfile.TarInfo('manifest.json');item.size=len(payload);item.mode=0o600;compressed.addfile(item,io.BytesIO(payload))
    with partial.open('r+b') as stream:os.fsync(stream.fileno())
    os.link(partial,destination);partial.unlink()


def run(plan):
    import advanced
    core.backup_paths(plan)
    with tempfile.TemporaryDirectory(prefix='.serverlotse-bundle-',dir=plan['destination']) as work:
        dump=Path(work)/'database.sql'
        if plan.get('container'):database_dump(plan,dump)
        base={k:v for k,v in plan.items() if k!='bundle'}
        result=core.backup_run(base)
        source=Path(plan['destination'])/result['archive'];destination=source.with_suffix('.tar.gz')
        compressed_copy(source,destination,dump if plan.get('container') else None,plan.get('database',''))
        checked=core.verify_archive(plan,destination.name)
        source.unlink()
        if dump.exists():dump.unlink()
        uploaded=None
        if plan.get('remote'):
            if plan.get('rclone_config'):advanced.check_rclone_config(plan['rclone_config'])
            args=['--config',plan['rclone_config']] if plan.get('rclone_config') else []
            uploaded=plan['remote'].rstrip('/')+'/'+destination.name
            try:core.command(['rclone',*args,'copyto',str(destination),uploaded,'--immutable'],timeout=7200)
            except ValueError:
                raise ValueError('Lokale Sicherung erfolgreich unter '+str(destination)+', Remote-Upload fehlgeschlagen. Aktionsstatus ist Fehler; lokale Sicherung bleibt erhalten.') from None
        return {**checked,'archive':str(destination),'remote':uploaded,'skipped':result['skipped'],
                'note':'Komprimierte Sicherung gegen Manifest geprüft. Datenbankexport und Dateikopie sind kein gemeinsamer atomarer Snapshot. SQL nur wiederhergestellt, nicht automatisch importiert.'}


def apply(plan):
    ident=secrets.token_hex(12)
    cfg={k:v for k,v in plan.items() if k not in {'operation','remote_config_hash'}}
    cfg['bundle']=True
    with core.db() as db:db.execute('INSERT INTO backups VALUES(?,?,?)',(ident,json.dumps(cfg),time.time()+cfg['hours']*3600))
    return run({**cfg,'id':ident})
