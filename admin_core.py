import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import threading
import time

STATE = Path(os.getenv("SERVERLOTSE_STATE", "/var/lib/serverlotse"))
MUTEX = threading.Lock()
PREVIEWS = {}
PREVIEW_LOCK = threading.Lock()
POWER_UNTIL = 0
OPS = {"service", "updates_refresh", "updates_install", "mount", "unmount",
       "user_create", "user_edit", "group_create", "permissions", "container",
       "backup_save", "backup_run", "backup_verify", "backup_restore", "backup_toggle"}
ADVANCED_OPS = {'shell_run','docker_clean','volume_delete','firewall_rule','settings_save','webhook_test',
                'update_policy','proxy_apply','bundle_run','remote_save','heal_resume','tool_install','process_signal'}
OPS |= ADVANCED_OPS
LAB_OPS={'lab_janitor','lab_clone','lab_env','lab_template','lab_dotenv','lab_compose','lab_registry',
         'lab_settings','lab_baseline','lab_session_end','lab_http','lab_speedtest','lab_rotate','lab_restore_test'}
LAB_OPS |= {'lab_cache','lab_apt_clean','lab_orphan_end','lab_panic','lab_panic_release','lab_config_write','lab_config_keep','lab_config_undo','lab_ddns_save','lab_ddns_update','lab_domain_proxy','lab_inode_watch','lab_builder','lab_volume_write','lab_trivy','lab_cron_create','lab_cron_remove'}
OPS |= LAB_OPS
ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "SYSTEMD_PAGER": "cat", "DEBIAN_FRONTEND": "noninteractive"}
ENV['DOCKER_HOST']='unix:///var/run/docker.sock'
for _docker_option in ('DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
    ENV.pop(_docker_option,None)


def command(args, timeout=25, input_text=None, allowed=(0,)):
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(args, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, env=ENV, start_new_session=True)
        except FileNotFoundError:
            raise ValueError("Benötigtes Programm fehlt: " + args[0]) from None
        try:
            process.communicate(input_text.encode() if input_text is not None else None, timeout=timeout)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise ValueError("Zeitlimit erreicht. Zustand vor einem erneuten Versuch prüfen.") from None
        output.seek(0)
        text = output.read(2_000_001).decode("utf-8", "replace")
        if len(text) > 2_000_000:
            raise ValueError("Ausgabe zu groß. Prüfung auf dem Host erforderlich.")
        if process.returncode not in allowed:
            if input_text is not None:
                raise ValueError("Benutzeraktion fehlgeschlagen. Host-Protokoll prüfen.")
            raise ValueError(text[-5000:] or "Host-Befehl fehlgeschlagen.")
        return text


@contextlib.contextmanager
def db():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(STATE / "admin.sqlite3", timeout=20)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
      CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, created REAL, operation TEXT,
        parameters TEXT, status TEXT, result TEXT);
      CREATE TABLE IF NOT EXISTS backups(id TEXT PRIMARY KEY, config TEXT, next_run REAL);
    """)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    with db() as connection:
        connection.execute("UPDATE audit SET status='interrupted', result=? WHERE status IN ('queued','running')",
                           ('Host-Helfer wurde unterbrochen. Zustand prüfen, bevor die Aktion erneut ausgeführt wird.',))


def clean(data, audit=False):
    result = {k: v for k, v in data.items() if k not in {"password", "nonce", "confirmation"}}
    if data.get('password'): result['password_change'] = True
    import advanced
    return advanced.public(result, audit=audit)


def audit_rows():
    with db() as connection:
        return {"rows": [dict(row) for row in connection.execute("SELECT id,created,operation,status,substr(result,1,2000) AS result FROM audit ORDER BY created DESC LIMIT 200")]}


def audit_detail(ident):
    if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{24}", ident): raise ValueError("Ungültige Protokollkennung.")
    with db() as connection:
        row = connection.execute("SELECT * FROM audit WHERE id=?", (ident,)).fetchone()
    if not row: raise ValueError("Protokolleintrag nicht gefunden.")
    result = dict(row); result['parameters'] = json.loads(result['parameters'])
    return result


def checked_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", value):
        raise ValueError("Name: Kleinbuchstaben, Zahlen, _ oder -, maximal 31 Zeichen.")
    return value


def local_path(value, existing=True):
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value or len(value) > 4096:
        raise ValueError("Absoluten Host-Pfad angeben.")
    path = Path(value)
    if ".." in path.parts or any(ord(c) < 32 for c in value):
        raise ValueError("Ungültiger Pfad.")
    for current in [path, *path.parents]:
        if current.is_symlink():
            raise ValueError("Symbolische Links sind hier nicht erlaubt.")
    if existing and not path.exists():
        raise ValueError("Pfad existiert nicht.")
    return path


def identity(path):
    info = path.stat()
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]


def secure_open(path, flags):
    path = Path(path)
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = next_fd
        return os.open(path.name or ".", flags | os.O_NOFOLLOW, dir_fd=directory)
    finally: os.close(directory)


def private_destination(path):
    for current in [path, *path.parents]:
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("Sicherungs- und Wiederherstellungsziel braucht root-eigene Ordner ohne Schreibrecht für Gruppe/andere (z. B. 755 oder 700), auch in übergeordneten Ordnern.")


def volume_identity(path):
    row = json.loads(command(["findmnt", "--json", "--target", str(path), "--output", "UUID,SOURCE,TARGET,FSTYPE"]))["filesystems"][0]
    return {"uuid": row.get("uuid"), "source": row.get("source"), "target": row.get("target"), "fstype": row.get("fstype")}


def mounts():
    return json.loads(command(["findmnt", "--json", "--list", "--output", "SOURCE,TARGET,FSTYPE,OPTIONS,UUID"]))["filesystems"]


def disks():
    raw = json.loads(command(["lsblk", "--json", "--bytes", "--output", "PATH,TYPE,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,RO"]))
    rows = []
    def visit(nodes):
        for node in nodes:
            row = {k: v for k, v in node.items() if k != "children"}
            points = [p for p in row.get("mountpoints", []) if p]
            row["usage"] = []
            for point in points:
                if point.startswith("/"):
                    try:
                        usage = shutil.disk_usage(point)
                        row["usage"].append({"path": point, "used": usage.used, "free": usage.free,
                                             "percent": round(usage.used / usage.total * 100, 1)})
                    except OSError:
                        pass
            rows.append(row)
            visit(node.get("children", []))
    visit(raw["blockdevices"])
    return {"rows": rows, "mounts": mounts(), "smart_available": bool(shutil.which("smartctl"))}


def block_device(value):
    if not isinstance(value, str) or not re.fullmatch(r"/dev/[a-zA-Z0-9_/-]+", value):
        raise ValueError("Ungültiger Datenträger.")
    rows = disks()["rows"]
    item = next((r for r in rows if r["path"] == value), None)
    if not item or not stat.S_ISBLK(Path(value).stat().st_mode):
        raise ValueError("Kein vorhandenes Blockgerät.")
    return item


def smart(value):
    block_device(value)
    text = command(["smartctl", "--json", "--all", value], timeout=45, allowed=tuple(range(256)))
    return json.loads(text)


def system_snapshot():
    load = os.getloadavg()
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            memory[key] = int(value.strip().split()[0]) * 1024
    failed = command(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"])
    journal = command(["journalctl", "-b", "-p", "err", "-n", "60", "--no-pager", "-o", "short-iso"], timeout=15)
    findings = []
    if failed.strip(): findings.append({"level": "warning", "code": "failed_services", "meaning": "Fehlgeschlagene Dienste", "next": "Dienste öffnen und den betroffenen Dienst prüfen."})
    if load[0] > (os.cpu_count() or 1) * 1.5: findings.append({"level": "warning", "code": "load", "meaning": "Hohe Systemlast", "next": "Docker-Ressourcen und laufende Sicherungen prüfen."})
    if memory.get("MemAvailable", 0) < memory.get("MemTotal", 1) * .1: findings.append({"level": "warning", "code": "memory", "meaning": "Wenig freier Arbeitsspeicher", "next": "Container-Ressourcen prüfen; keinen Cache blind löschen."})
    for row in disks()["rows"]:
        for usage in row["usage"]:
            if usage["percent"] >= 85:
                findings.append({"level": "critical" if usage["percent"] >= 95 else "warning", "code": "space", "meaning": "Datenträger fast voll", "path": usage["path"], "next": "Speicher untersuchen und große Ordner vergleichen."})
    for point in ("/", "/var", "/mnt"):
        info = os.statvfs(point)
        if info.f_files and info.f_favail / info.f_files < .1:
            findings.append({"level": "warning", "code": "inodes", "meaning": "Wenig freie Dateieinträge", "path": point, "next": "Viele kleine Dateien oder Container-Protokolle untersuchen."})
    return {"hostname": socket.gethostname(), "uptime": float(Path("/proc/uptime").read_text().split()[0]),
            "load": load, "cpus": os.cpu_count(), "memory": memory, "findings": findings,
            "failed": failed, "journal": journal, "reboot_required": Path("/var/run/reboot-required").exists(),
            "note": "Momentaufnahme; keine Garantie für einen fehlerfreien Server."}


def services():
    files = command(["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"])
    active = command(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"])
    states = {}
    for line in active.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0].endswith(".service"):
            states[fields[0]] = {"active": fields[2], "sub": fields[3]}
    units=list(states)
    for offset in range(0,len(units),100):
        info=command(['systemctl','show','--property=Id,ActiveEnterTimestamp','--',*units[offset:offset+100]],allowed=(0,1))
        for block in info.strip().split('\n\n'):
            values=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
            if values.get('Id') in states:states[values['Id']]['started']=values.get('ActiveEnterTimestamp','')
    return {"rows": [{"name": p[0], "autostart": p[1], **states.get(p[0], {"active": "inactive"})}
                     for line in files.splitlines() if len(p := line.split()) >= 2]}


def service_details(name):
    validate_service(name)
    return {"properties": command(["systemctl", "show", name, "--property=Id,ActiveState,SubState,UnitFileState,Result,NRestarts,Description,ActiveEnterTimestamp,ExecMainStartTimestamp,ExecMainStatus,MemoryCurrent,CPUUsageNSec"]),
            "journal": command(["journalctl", "-u", name, "-n", "80", "--no-pager", "-o", "short-iso"])}


def validate_service(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_@.:-]+\.service", name):
        raise ValueError("Ungültiger Dienstname.")
    if name not in {r["name"] for r in services()["rows"]}:
        raise ValueError("Dienst nicht vorhanden.")


def users():
    import pwd
    import grp
    groups = grp.getgrall()
    rows = []
    for user in pwd.getpwall():
        memberships = [g.gr_name for g in groups if user.pw_name in g.gr_mem or g.gr_gid == user.pw_gid]
        rows.append({"name": user.pw_name, "uid": user.pw_uid, "gid": user.pw_gid,
                     "home": user.pw_dir, "shell": user.pw_shell, "groups": memberships,
                     "editable": 1000 <= user.pw_uid < 65534})
    return {"rows": rows, "groups": [{"name": g.gr_name, "gid": g.gr_gid} for g in groups]}


def rights(value):
    path = local_path(value)
    import pwd
    import grp
    rows = []
    for part in reversed([path, *path.parents]):
        info = part.stat()
        try: owner = pwd.getpwuid(info.st_uid).pw_name
        except KeyError: owner = str(info.st_uid)
        try: group = grp.getgrgid(info.st_gid).gr_name
        except KeyError: group = str(info.st_gid)
        rows.append({"path": str(part), "mode": oct(stat.S_IMODE(info.st_mode))[2:], "rights": stat.filemode(info.st_mode), "owner": owner, "group": group})
    acl = command(["getfacl", "--absolute-names", "--", str(path)]) if shutil.which("getfacl") else "ACL-Werkzeug nicht installiert. ACLs wurden nicht geprüft."
    return {"rows": rows, "acl": acl, "note": "Bei Ordnern bedeutet x: betreten. Zugriff braucht x auf allen übergeordneten Ordnern. ACLs, Gruppen, schreibgeschützte Mounts und Container-UIDs können das Ergebnis zusätzlich beeinflussen."}


def network():
    return {"addresses": json.loads(command(["ip", "-json", "address", "show"])),
            "routes": json.loads(command(["ip", "-json", "route", "show"])),
            "ports": command(["ss", "-lntup"]),
            "dns": Path("/etc/resolv.conf").read_text()[:16000]}


def probe(host, port):
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,253}", host):
        raise ValueError("Hostname oder IP-Adresse angeben.")
    try: port = int(port)
    except (ValueError, TypeError): raise ValueError("Ungültiger Port.") from None
    if not 1 <= port <= 65535: raise ValueError("Port muss zwischen 1 und 65535 liegen.")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        lines = command(["getent", "--", "ahosts", host], timeout=8).splitlines()
        addresses = sorted({line.split()[0] for line in lines if line.split()})
    if not addresses: raise ValueError("DNS-Auflösung lieferte keine Adresse.")
    for address in addresses:
        if ipaddress.ip_address(address).is_multicast or ipaddress.ip_address(address).is_unspecified:
            raise ValueError("Diese Zieladresse ist nicht erlaubt.")
    started = time.monotonic()
    errors = []
    for address in addresses[:4]:
        try:
            with socket.create_connection((address, port), timeout=3): pass
            return {"addresses": addresses, "connected_address": address, "reachable": True, "milliseconds": round((time.monotonic()-started)*1000)}
        except OSError as exc: errors.append(str(exc))
    return {"addresses": addresses, "reachable": False, "error": "; ".join(errors)}


def containers():
    lines = command(["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])
    resources = command(["docker", "stats", "--no-stream", "--no-trunc", "--format", "{{json .}}"], timeout=35)
    return {"rows": [json.loads(line) for line in lines.splitlines() if line],
            "resources": [json.loads(line) for line in resources.splitlines() if line]}


def updates():
    if not shutil.which("apt-get"): raise ValueError("Updateverwaltung unterstützt derzeit Debian/DietPi/Ubuntu mit APT.")
    return {"simulation": command(["apt-get", "-s", "upgrade"], timeout=90),
            "note": "Simulation anhand der vorhandenen Paketlisten. Zuerst Paketlisten aktualisieren. Keine Distributionsaktualisierung."}


def backup_configs():
    with db() as connection:
        return {"rows": [{**json.loads(r["config"]), "id": r["id"], "next_run": r["next_run"]}
                         for r in connection.execute("SELECT * FROM backups")]}


def config(backup_id):
    if not isinstance(backup_id, str) or not re.fullmatch(r"[a-f0-9]{24}", backup_id): raise ValueError("Ungültige Sicherungskennung.")
    with db() as connection:
        row = connection.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not row: raise ValueError("Sicherung nicht gefunden.")
    return {**json.loads(row["config"]), "id": row["id"], "next_run": row["next_run"]}


def validate_backup(data):
    source, destination = local_path(data.get("source")), local_path(data.get("destination"))
    if not source.is_dir() or not destination.is_dir() or source == Path("/"):
        raise ValueError("Quelle und Sicherungsziel müssen vorhandene Ordner sein; / ist keine Sicherungsquelle.")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Quelle und Ziel dürfen nicht ineinander liegen.")
    private_destination(destination)
    if any(source == p or p in source.parents for p in map(Path, ["/proc", "/sys", "/dev", "/run", "/var/lib/serverlotse"])):
        raise ValueError("Virtuelle oder Verwaltungsdaten sind keine Sicherungsquelle.")
    hours = int(data.get("hours", 24))
    if not 1 <= hours <= 8760: raise ValueError("Intervall: 1 bis 8760 Stunden.")
    name = data.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name): raise ValueError("Sicherungsnamen angeben.")
    return {"name": name, "source": str(source), "destination": str(destination), "hours": hours,
            "enabled": data.get("enabled") is True, "source_volume": volume_identity(source),
            "destination_volume": volume_identity(destination)}


def backup_paths(cfg):
    source, dest = local_path(cfg["source"]), local_path(cfg["destination"])
    private_destination(dest)
    if not same_volume(cfg["source_volume"],volume_identity(source)) or not same_volume(cfg["destination_volume"],volume_identity(dest)):
        raise ValueError("Datenträgerzuordnung geändert oder Platte nicht eingehängt. Sicherung gestoppt.")
    return source, dest


def same_volume(expected,actual):
    if expected.get('uuid') and actual.get('uuid'):
        return all(expected.get(key)==actual.get(key) for key in ['uuid','target','fstype'])
    return expected==actual


def backup_archives(backup_id):
    cfg = config(backup_id)
    _, dest = backup_paths(cfg)
    rows = []
    for p in [*dest.glob("serverlotse-" + backup_id + "-*.tar"), *dest.glob("serverlotse-" + backup_id + "-*.tar.gz")]:
        if not p.is_symlink() and p.is_file(): rows.append({"name": p.name, "bytes": p.stat().st_size, "modified": p.stat().st_mtime})
    return {"rows": sorted(rows, key=lambda r: r["modified"], reverse=True)[:100]}


def backup_run(cfg):
    if cfg.get('bundle'):
        import bundle_backup
        return bundle_backup.run(cfg)
    source, dest = backup_paths(cfg)
    final = dest / ("serverlotse-" + cfg["id"] + "-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3) + ".tar")
    partial = final.with_suffix(".partial")
    manifest, count, skipped, manifest_size = {}, 0, 0, 0
    source_device = source.stat().st_dev
    try:
        with partial.open("xb") as raw, tarfile.open(fileobj=raw, mode="w") as archive:
            source_fd = secure_open(source, os.O_RDONLY | os.O_DIRECTORY)
            for directory, dirs, files, directory_fd in os.fwalk(".", follow_symlinks=False, dir_fd=source_fd):
                base = Path(directory)
                safe = []
                for name in dirs:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) and info.st_dev == source_device: safe.append(name)
                    else: skipped += 1
                dirs[:] = safe
                for name in files:
                    path = base/name
                    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if not stat.S_ISREG(before.st_mode) or before.st_dev != source_device:
                        skipped += 1
                        continue
                    count += 1
                    if count > 250000: raise ValueError("Sicherung überschreitet 250.000 Dateien.")
                    if shutil.disk_usage(dest).free < before.st_size + 64*1024*1024: raise ValueError("Zu wenig freier Platz für die Sicherung.")
                    relative = path.as_posix()
                    manifest_size += len(relative.encode('utf-8')) + 160
                    if manifest_size > 32_000_000: raise ValueError("Sicherungsmanifest zu groß.")
                    with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd), "rb") as stream:
                        opened = os.fstat(stream.fileno())
                        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino): raise ValueError("Datei während der Sicherung verändert.")
                        hasher = hashlib.sha256()
                        class Reader:
                            def read(self, n=-1):
                                chunk = stream.read(n); hasher.update(chunk); return chunk
                        member = tarfile.TarInfo("files/" + relative)
                        member.size, member.mtime, member.mode = before.st_size, int(before.st_mtime), 0o600
                        archive.addfile(member, Reader())
                        after = os.fstat(stream.fileno())
                        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns): raise ValueError("Datei während der Sicherung verändert; Teilsicherung verwerfen.")
                    manifest[relative] = {"size": before.st_size, "sha256": hasher.hexdigest()}
            import io
            payload = json.dumps({"version": 1, "source": str(source), "files": manifest, "skipped": skipped}).encode()
            if len(payload)>32_000_000:raise ValueError('Sicherungsmanifest zu groß.')
            member = tarfile.TarInfo("manifest.json"); member.size = len(payload); member.mode = 0o600
            archive.addfile(member, io.BytesIO(payload))
            raw.flush(); os.fsync(raw.fileno())
        os.close(source_fd); source_fd = None
        with partial.open("r+b") as persisted:
            os.fsync(persisted.fileno())
        os.link(partial, final); partial.unlink()
    except Exception:
        raise
    finally:
        if 'source_fd' in locals() and source_fd is not None: os.close(source_fd)
    return {"archive": final.name, "files": count, "skipped": skipped,
            "note": "Dateisicherung erstellt. Keine konsistente Datenbanksicherung; Datenbanken vorher anhalten oder separat exportieren. Leere Ordner, ACLs und Eigentümer werden nicht gesichert."}


def archive_file(cfg, name):
    if not isinstance(name, str) or not re.fullmatch(r"serverlotse-"+cfg["id"]+r"-[0-9]{8}-[0-9]{6}-[a-f0-9]{6}\.tar(?:\.gz)?", name): raise ValueError("Ungültiges Archiv.")
    _, dest = backup_paths(cfg)
    return local_path(str(dest/name))


def verify_archive(cfg, name, restore=None):
    archive_path = archive_file(cfg, name)
    checked = 0
    with tarfile.open(archive_path, "r:*") as archive:
        member = archive.getmember("manifest.json")
        if not member.isfile() or member.size > 32_000_000: raise ValueError("Ungültiges Manifest.")
        manifest = json.load(archive.extractfile(member))
        entries = manifest.get("files", {})
        if not isinstance(entries, dict) or len(entries) > 250000: raise ValueError("Ungültiges Manifest.")
        seen = set()
        for member in archive:
            if member.name == "manifest.json": continue
            if not member.isfile() or not member.name.startswith("files/"): raise ValueError("Unsicherer Archiveintrag.")
            relative = member.name[6:]
            from pathlib import PurePosixPath
            rel = PurePosixPath(relative)
            if rel.is_absolute() or ".." in rel.parts or "\\" in relative or relative not in entries or relative in seen: raise ValueError("Unsicherer Archiveintrag.")
            expected = entries[relative]
            if member.size != expected["size"]: raise ValueError("Archivgröße stimmt nicht mit Manifest überein.")
            seen.add(relative)
            stream = archive.extractfile(member)
            target = None
            if restore is not None:
                if shutil.disk_usage(restore).free < member.size + 64*1024*1024: raise ValueError("Zu wenig freier Platz für die Wiederherstellung.")
                path = restore.joinpath(*rel.parts)
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target = path.open("xb")
            hasher = hashlib.sha256()
            try:
                while chunk := stream.read(1024*1024):
                    hasher.update(chunk)
                    if target: target.write(chunk)
                if target: target.flush(); os.fsync(target.fileno())
            finally:
                if target: target.close()
            if hasher.hexdigest() != expected["sha256"]: raise ValueError("Prüfsumme stimmt nicht: " + relative)
            checked += 1
        if seen != set(entries): raise ValueError("Dateien fehlen im Archiv.")
    return {"verified": True, "files": checked, "restored_to": str(restore) if restore else None,
            "note": "Alle gespeicherten Dateiinhalte gegen das Archivmanifest geprüft. Dies bestätigt weder die ursprüngliche Vollständigkeit noch die Konsistenz von Datenbanken."}


def validate(data):
    if not isinstance(data, dict) or data.get("operation") not in OPS: raise ValueError("Unbekannte Verwaltungsaktion.")
    if data['operation'] in LAB_OPS:
        import workbench
        return workbench.validate(data)
    op = data["operation"]
    if op in ADVANCED_OPS:
        import advanced
        return advanced.validate(data)
    p = {"operation": op}
    if op == "service":
        name = data.get("name"); validate_service(name)
        verb = data.get("verb")
        if verb not in {"start", "stop", "restart", "enable", "disable"}: raise ValueError("Ungültige Dienstaktion.")
        protected = {"ssh.service", "sshd.service", "dropbear.service", "docker.service", "containerd.service", "dbus.service", "systemd-logind.service", "networking.service", "NetworkManager.service", "systemd-networkd.service"}
        if (name in protected or name.startswith(("serverlotse", "systemd-", "ssh@", "sshd@", "dropbear@"))) and verb != "start": raise ValueError("Dieser Zugangsdienst ist gegen Unterbrechungen geschützt.")
        p.update(name=name, verb=verb)
    elif op.startswith("updates_"):
        p["simulation"] = updates()["simulation"]
        if op == "updates_install" and re.search(r"^(Remv|Conf) (openssh|dropbear|systemd|docker|containerd)", p["simulation"], re.M):
            raise ValueError("Update verändert zentrale Zugangsdienste. Wartung über einen separaten Konsolenzugang durchführen.")
    elif op == "mount":
        disk = block_device(data.get("device"))
        if disk.get("type") not in {"part", "disk"} or not disk.get("fstype") or disk.get("fstype") not in {"ext4", "ext3", "ext2", "xfs", "btrfs", "vfat", "exfat", "ntfs", "ntfs3"}: raise ValueError("Nur vorhandene normale Dateisysteme werden unterstützt; kein Formatieren, RAID oder LVM.")
        if disk.get("mountpoints") and any(disk["mountpoints"]): raise ValueError("Datenträger ist bereits eingehängt.")
        name = checked_name(data.get("name"))
        target = local_path("/mnt/" + name, existing=False)
        private_destination(target.parent)
        if target.exists(): private_destination(target)
        if target.exists() and (not target.is_dir() or any(target.iterdir())): raise ValueError("Einhängepunkt muss leer sein.")
        uuid = disk.get("uuid")
        if not isinstance(uuid, str) or not re.fullmatch(r"[A-Za-z0-9-]{4,80}", uuid): raise ValueError("Eindeutige Dateisystem-UUID erforderlich.")
        if sum(1 for row in disks()["rows"] if row.get("uuid") == uuid) != 1: raise ValueError("UUID ist nicht eindeutig.")
        fstab = Path("/etc/fstab").read_text()
        if any(uuid in line or str(target) in line.split() for line in fstab.splitlines() if line.strip() and not line.lstrip().startswith("#")):
            raise ValueError("Datenträger oder Ziel steht bereits in fstab. Vorhandenen Eintrag zuerst prüfen.")
        p.update(device=disk["path"], uuid=uuid, name=name, path=str(target), fstype=disk["fstype"], persistent=data.get("persistent") is True, fstab_hash=hashlib.sha256(fstab.encode()).hexdigest())
    elif op == "unmount":
        path = local_path(data.get("path"))
        points = mounts()
        if not any(r["target"] == str(path) for r in points): raise ValueError("Kein Einhängepunkt.")
        if path.parent != Path("/mnt") or path.name in {"dietpi_userdata"} or not path.name: raise ValueError("Nur direkte Daten-Mounts unter /mnt können ausgehängt werden.")
        if any(Path(r["target"]) != path and path in Path(r["target"]).parents for r in points): raise ValueError("Weitere Dateisysteme sind darunter eingehängt.")
        busy_mount(path)
        p.update(path=str(path), identity=identity(path))
    elif op in {"user_create", "user_edit", "group_create"}:
        name = checked_name(data.get("name")); p["name"] = name
        import pwd
        import grp
        if op == "group_create":
            if any(g.gr_name == name for g in grp.getgrall()): raise ValueError("Gruppe existiert bereits.")
        elif op == "user_create":
            if any(u.pw_name == name for u in pwd.getpwall()): raise ValueError("Benutzer existiert bereits.")
            p["login"] = data.get("login") is True
            p["shell"] = "/bin/bash" if p["login"] else "/usr/sbin/nologin"
        else:
            try: user = pwd.getpwnam(name)
            except KeyError: raise ValueError("Benutzer existiert nicht.") from None
            if not 1000 <= user.pw_uid < 65534: raise ValueError("Systemkonten und root bleiben geschützt.")
            p["uid"] = user.pw_uid
            p["lock_action"] = data.get("lock_action", "keep")
            if p["lock_action"] not in {"keep", "lock", "unlock"}: raise ValueError("Ungültige Kontosperre.")
            p["login"] = data.get("login") is True
            p["shell"] = "/bin/bash" if p["login"] else "/usr/sbin/nologin"
        if op != "group_create":
            names = data.get("groups", [])
            if not isinstance(names, list) or len(names) > 30: raise ValueError("Ungültige Gruppenliste.")
            available = {g.gr_name for g in grp.getgrall()}
            if any(checked_name(g) not in available for g in names): raise ValueError("Gruppe nicht vorhanden.")
            if set(names) & {"root", "sudo", "wheel", "docker", "disk", "shadow", "lxd", "adm"}: raise ValueError("Administrative Gruppen können hier nicht vergeben werden.")
            p["groups"] = names
            password = data.get("password", "")
            if password:
                if not isinstance(password, str) or not 12 <= len(password) <= 256 or any(c in password for c in "\r\n\x00:"): raise ValueError("Passwort: 12 bis 256 Zeichen ohne Zeilenumbruch oder Doppelpunkt.")
                p["password"] = password
    elif op == "permissions":
        path = local_path(data.get("path"))
        if path == Path("/") or not (Path("/mnt") in path.parents or Path("/home") in path.parents or Path("/srv") in path.parents): raise ValueError("Rechteänderungen sind auf Datenpfade unter /mnt, /home und /srv begrenzt.")
        if not re.fullmatch(r"[0-7]{3}", str(data.get("mode", ""))): raise ValueError("Dreistellige Rechte, z. B. 750, angeben. Keine Sonderbits.")
        import pwd
        import grp
        try:
            uid = pwd.getpwnam(checked_name(data.get("owner"))).pw_uid
            gid = grp.getgrnam(checked_name(data.get("group"))).gr_gid
        except KeyError: raise ValueError("Eigentümer oder Gruppe fehlt.") from None
        p.update(path=str(path), mode=data["mode"], owner=data["owner"], group=data["group"], uid=uid, gid=gid, identity=identity(path))
    elif op == "container":
        container = data.get("container", "")
        if not re.fullmatch(r"[a-f0-9]{64}", container): raise ValueError("Vollständige Containerkennung erforderlich.")
        details = json.loads(command(["docker", "inspect", "--type", "container", container]))[0]
        name = details.get("Name", "").lstrip("/")
        if "serverlotse" in name.lower() or details.get("Config", {}).get("Labels", {}).get("com.docker.compose.service") in {"serverlotse", "docker-reader", "host-control"}: raise ValueError("ServerLotse-eigene Container sind geschützt.")
        if data.get("verb") not in {"start", "stop", "restart"}: raise ValueError("Ungültige Containeraktion.")
        p.update(container=container, name=name, verb=data["verb"])
    elif op == "backup_save":
        p.update(validate_backup(data))
    else:
        cfg = config(data.get("id")); backup_paths(cfg)
        p.update(id=cfg["id"], name=cfg["name"], config_hash=hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest())
        if op in {"backup_verify", "backup_restore"}:
            archive_file(cfg, data.get("archive")); p["archive"] = data["archive"]
        if op == "backup_restore":
            target = local_path(data.get("target"))
            if not target.is_dir() or target == Path("/"): raise ValueError("Separaten Wiederherstellungsordner wählen.")
            private_destination(target)
            p.update(target=str(target), target_identity=identity(target))
        if op == "backup_toggle": p["enabled"] = data.get("enabled") is True
    return p


def busy_mount(path):
    ids = command(["docker", "ps", "-aq"]).split() if shutil.which("docker") else []
    for offset in range(0, len(ids), 100):
        for item in json.loads(command(["docker", "inspect", *ids[offset:offset+100]])):
            if not item.get("State", {}).get("Running"):
                continue
            for mount in item.get("Mounts", []):
                source = Path(mount.get("Source", "/"))
                if source == path or path in source.parents:
                    raise ValueError("Datenträger wird von einem Container verwendet: " + item.get("Name", ""))
    for cfg in backup_configs()["rows"]:
        if cfg["enabled"] and any(Path(cfg[k]) == path or path in Path(cfg[k]).parents for k in ("source", "destination")):
            raise ValueError("Aktiver Sicherungsplan verwendet diesen Datenträger.")


def prepare(data):
    plan = validate(data)
    nonce = secrets.token_hex(24)
    with PREVIEW_LOCK:
        for key, item in list(PREVIEWS.items()):
            if item["expires"] < time.time(): del PREVIEWS[key]
        if len(PREVIEWS) >= 30: raise ValueError("Zu viele offene Vorschauen.")
        PREVIEWS[nonce] = {"plan": plan, "expires": time.time()+120}
    return {"nonce": nonce, "expires": 120, "confirmation": "LOESCHEN" if plan['operation'] in {'volume_delete','lab_janitor'} else "AUSFUEHREN", "preview": clean(plan),
            "warnings": warnings(plan)}


def warnings(plan):
    op = plan["operation"]
    base = ["Die Aktion verändert den Host und wird dauerhaft protokolliert."]
    if op in LAB_OPS:
        import workbench
        return base + workbench.warnings(plan)
    if op in ADVANCED_OPS:
        import advanced
        return base + advanced.warnings(plan)
    if op in {"updates_install", "service", "container"}: base.append("Dienste und Verbindungen können unterbrochen werden. Ein Konsolenzugang sollte verfügbar sein.")
    if op == "updates_install": base.append("Nur apt-get upgrade, keine Paketentfernung. Paketkonfiguration kann manuelle Nacharbeit erfordern. Vorher Sicherung anlegen.")
    if op == "unmount": base.append("Kein erzwungenes oder verzögertes Aushängen. Bei belegtem Laufwerk bricht die Aktion ab. Ein vorhandener Autostart-Eintrag bleibt bestehen.")
    if op == "mount": base.append("Der Name bezeichnet den Einhängepunkt unter /mnt; das Dateisystemlabel wird nicht verändert. Bestehende Dateien bleiben erhalten.")
    if op in {"backup_save", "backup_run"}: base.append("Dateisicherung ohne Datenbank-Snapshot. Leere Ordner, ACLs, Eigentümer, Links und weitere Dateisysteme werden nicht gesichert. Keine automatische Löschung alter Archive.")
    if op == "backup_save" and plan['source_volume'] == plan['destination_volume']: base.append("Quelle und Sicherungsziel liegen auf demselben Dateisystem. Das schützt nicht vor einem Ausfall dieses Datenträgers.")
    if op == "backup_restore": base.append("Wiederherstellung in einen neuen privaten Unterordner. Bestehende Dateien werden nicht überschrieben. Bei Fehlern bleiben Teilkopien erhalten.")
    if op == "permissions": base.append("Nur dieser eine Pfad, nicht rekursiv. ACLs können zusätzlich gelten; Zugriff von Apps kann sich ändern.")
    if op == "user_edit": base.append("Zusätzliche Gruppen werden ergänzt. Bestehende Gruppen bleiben erhalten; keine Vergabe administrativer Gruppen.")
    return base


def apply_plan(p):
    op = p["operation"]
    if op in LAB_OPS:
        import workbench
        return workbench.apply(p)
    if op in ADVANCED_OPS:
        import advanced
        return advanced.apply(p)
    if op == "service":
        result={"text": command(["systemctl", p["verb"], p["name"]], timeout=120)}
        if p['verb']=='stop':
            import advanced
            advanced.state('suppressed:'+p['name'],True)
        return result
    if op == "updates_refresh": return {"text": command(["apt-get", "update"], timeout=900)}
    if op == "updates_install":
        if updates()["simulation"] != p["simulation"]: raise ValueError("Paketplan verändert. Neue Vorschau erforderlich.")
        return {"text": command(["apt-get", "--assume-yes", "--no-remove", "-o", "Dpkg::Options::=--force-confold", "upgrade"], timeout=7200)}
    if op == "mount":
        target = local_path(p["path"], existing=False)
        target.mkdir(exist_ok=True)
        if any(target.iterdir()): raise ValueError("Einhängepunkt ist nicht mehr leer.")
        command(["mount", "-o", "nosuid,nodev", "--", "UUID="+p["uuid"], str(target)], timeout=60)
        if p["persistent"]:
            fstab = Path("/etc/fstab")
            old = fstab.read_bytes()
            if hashlib.sha256(old).hexdigest() != p["fstab_hash"]: raise ValueError("Eingehängt, aber fstab wurde zwischenzeitlich geändert. Kein Autostart-Eintrag geschrieben.")
            backup = STATE / ("fstab-"+secrets.token_hex(8)+".bak"); backup.write_bytes(old); backup.chmod(0o600)
            line = f"\n# ServerLotse\nUUID={p['uuid']} {target} {p['fstype']} defaults,nofail,nosuid,nodev,x-systemd.device-timeout=10s 0 0\n"
            fd, name = tempfile.mkstemp(prefix=".serverlotse-fstab-", dir="/etc")
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(old + line.encode()); stream.flush(); os.fsync(stream.fileno())
                os.chmod(name, stat.S_IMODE(fstab.stat().st_mode))
                command(["findmnt", "--verify", "--tab-file", name], timeout=30)
                os.replace(name, fstab)
                command(["systemctl", "daemon-reload"])
            finally:
                if os.path.exists(name): os.unlink(name)
        return {"mounted": str(target), "persistent": p["persistent"]}
    if op == "unmount":
        busy_mount(Path(p["path"]))
        return {"text": command(["umount", "--", p["path"]], timeout=60)}
    if op == "group_create": return {"text": command(["groupadd", p["name"]])}
    if op in {"user_create", "user_edit"}:
        args = ["useradd", "--create-home", "--shell", p["shell"]] if op == "user_create" else ["usermod", "--shell", p["shell"]]
        if p["groups"]: args += (["--groups"] if op == "user_create" else ["--append", "--groups"]) + [",".join(p["groups"])]
        command(args + [p["name"]])
        if p.get("password"): command(["chpasswd"], input_text=p["name"]+":"+p["password"]+"\n")
        if op == "user_edit" and p["lock_action"] != "keep": command(["usermod", "--lock" if p["lock_action"] == "lock" else "--unlock", p["name"]])
        return {"name": p["name"], "note": "Benutzer gespeichert. Kontosperre betrifft Passwortanmeldung; vorhandene SSH-Schlüssel können weiter gelten."}
    if op == "permissions":
        path = local_path(p["path"])
        fd = secure_open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid] != p["identity"]: raise ValueError("Datei verändert. Neue Vorschau erforderlich.")
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)): raise ValueError("Nur reguläre Dateien und Ordner.")
            os.fchown(fd, p["uid"], p["gid"]); os.fchmod(fd, int(p["mode"], 8))
        finally: os.close(fd)
        return {"path": str(path), "mode": p["mode"]}
    if op == "container":
        result={"text": command(["docker", p["verb"], *(["--time", "30"] if p["verb"] in {"stop", "restart"} else []), p["container"]], timeout=120)}
        if p['verb']=='stop':
            import advanced
            advanced.state('suppressed:'+p['container'],True)
        return result
    if op == "backup_save":
        ident = secrets.token_hex(12)
        cfg = {k:v for k,v in p.items() if k != "operation"}
        with db() as connection: connection.execute("INSERT INTO backups VALUES (?,?,?)", (ident, json.dumps(cfg), time.time()+cfg["hours"]*3600))
        return {"id": ident, "note": "Sicherungsplan gespeichert."}
    cfg = config(p["id"])
    if op == "backup_toggle":
        cfg.pop("id"); cfg.pop("next_run"); cfg["enabled"] = p["enabled"]
        with db() as connection: connection.execute("UPDATE backups SET config=?,next_run=? WHERE id=?", (json.dumps(cfg), time.time()+cfg["hours"]*3600, p["id"]))
        return {"enabled": p["enabled"]}
    if op == "backup_run": return backup_run(cfg)
    if op == "backup_verify": return verify_archive(cfg, p["archive"])
    if op == "backup_restore":
        target = local_path(p["target"])
        if identity(target) != p["target_identity"]: raise ValueError("Ziel verändert. Neue Vorschau erforderlich.")
        verify_archive(cfg, p["archive"])
        restore = target / ("serverlotse-restore-" + secrets.token_hex(12))
        restore.mkdir(mode=0o700)
        return verify_archive(cfg, p["archive"], restore)
    raise ValueError("Unbekannte Aktion.")


def worker(ident, plan):
    with db() as connection: connection.execute("UPDATE audit SET status='running' WHERE id=?", (ident,))
    try:
        current = validate(plan)
        if current != plan: raise ValueError("Zustand verändert. Neue Vorschau erforderlich.")
        result = apply_plan(plan)
        status, output = "done", json.dumps(result, ensure_ascii=False)
        if len(output)>64000:output=json.dumps({'truncated':True,'tail':output[-24000:]},ensure_ascii=False)
    except Exception as exc:
        status, output = "error", str(exc)
    finally:
        try:
            with db() as connection: connection.execute("UPDATE audit SET status=?,result=? WHERE id=?", (status, output[-64000:], ident))
        finally: MUTEX.release()


def enqueue(plan):
    if not MUTEX.acquire(blocking=False): raise ValueError("Eine Verwaltungsaktion läuft bereits. Abschluss im Aktionsprotokoll abwarten.")
    ident = secrets.token_hex(12)
    try:
        if POWER_UNTIL > time.time(): raise ValueError("Eine Host-Aktion wurde bereits angefordert. Bitte warten.")
        with db() as connection: connection.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", (ident, time.time(), plan["operation"], json.dumps(clean(plan, audit=True)), "queued", ""))
        threading.Thread(target=worker, args=(ident, plan), daemon=True).start()
    except Exception:
        MUTEX.release(); raise
    return {"id": ident, "status": "queued"}


def execute(data):
    with PREVIEW_LOCK:
        prepared = PREVIEWS.get(data.get("nonce", ""))
        if not prepared or prepared["expires"] < time.time():
            PREVIEWS.pop(data.get('nonce',''),None)
            raise ValueError("Vorschau abgelaufen oder bereits verwendet.")
        word='LOESCHEN' if prepared['plan']['operation'] in {'volume_delete','lab_janitor'} else 'AUSFUEHREN'
        if data.get('confirmation')!=word:raise ValueError('Bestätigung fehlt.')
        PREVIEWS.pop(data['nonce'])
    return enqueue(prepared["plan"])


def schedule_tick():
    with PREVIEW_LOCK:
        for key, item in list(PREVIEWS.items()):
            if item['expires'] < time.time(): del PREVIEWS[key]
    if MUTEX.locked(): return
    if POWER_UNTIL > time.time(): return
    for cfg in backup_configs()["rows"]:
        if cfg["enabled"] and cfg["next_run"] <= time.time():
            with db() as connection: connection.execute("UPDATE backups SET next_run=? WHERE id=?", (time.time()+cfg["hours"]*3600, cfg["id"]))
            try:
                plan = validate({"operation": "backup_run", "id": cfg["id"]})
                enqueue(plan)
            except Exception as exc:
                with db() as connection: connection.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", (secrets.token_hex(12), time.time(), "backup_run", json.dumps({"id":cfg["id"]}), "error", str(exc)))
            break


def read(data):
    global POWER_UNTIL
    action = data.get("view")
    if isinstance(action,str) and action.startswith('lab_'):
        import workbench
        return workbench.read(data)
    if isinstance(action, str) and action.startswith('advanced_'):
        import advanced
        return advanced.read(data)
    if isinstance(action, str) and action.startswith('sensor_'):
        import sensors
        return sensors.read(__import__(__name__), data)
    if action == "power_reserve":
        if not MUTEX.acquire(blocking=False): raise ValueError("Eine Verwaltungsaktion läuft bereits. Bitte Abschluss abwarten.")
        try: POWER_UNTIL = time.time()+120
        finally: MUTEX.release()
        return {"reserved": True}
    if action == "power_release":
        POWER_UNTIL = 0
        return {"reserved": False}
    if action == "event":
        allowed = {"scan", "compare", "browse", "largest", "types", "search", "duplicates", "system", "mounts", "log", "docker", "docker_logs", "checklist", "copy_plan", "copy_apply", "host_reboot", "host_shutdown"}
        if data.get("action") not in allowed or data.get("status") not in {"running", "done", "error", "cancelled"}: raise ValueError("Ungültiger Protokolleintrag.")
        ident = data.get("id") or secrets.token_hex(12)
        if not re.fullmatch(r"[a-f0-9]{24}", ident): raise ValueError("Ungültige Protokollkennung.")
        with db() as connection:
            if data.get("id"):
                connection.execute("UPDATE audit SET status=?,result=? WHERE id=? AND operation=?", (data["status"], str(data.get("result", ""))[:4000], ident, data["action"]))
            else:
                parameters = {k:v for k,v in data.get("parameters", {}).items() if k in {"path", "view", "source", "target", "source_view", "target_view", "container", "plan_id"}}
                connection.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", (ident,time.time(),data["action"],json.dumps(parameters),data["status"],str(data.get("result", ""))[:4000]))
        return {"id":ident}
    if action == "status":
        return {"enabled": True, "version": "0.7.5", "sensors": True, "advanced": True, "terminal": True, "workbench": True, "terminal_sessions": __import__("terminal_host").count(), "busy": MUTEX.locked(), "hostname": socket.gethostname(), "tools": {name: bool(shutil.which(name)) for name in ["apt-get", "systemctl", "lsblk", "smartctl", "getfacl", "docker", "ip", "ss", "useradd", "chpasswd"]}}
    if action == "health": return system_snapshot()
    if action == "services": return services()
    if action == "service": return service_details(data.get("name"))
    if action == "updates": return updates()
    if action == "disks": return disks()
    if action == "smart": return smart(data.get("device"))
    if action == "network": return network()
    if action == "probe": return probe(data.get("host"), data.get("port"))
    if action == "users": return users()
    if action == "rights": return rights(data.get("path"))
    if action == "containers": return containers()
    if action == "backups": return backup_configs()
    if action == "archives": return backup_archives(data.get("id"))
    if action == "audit": return audit_rows()
    if action == "audit_detail": return audit_detail(data.get("id"))
    raise ValueError("Unbekannte Verwaltungsansicht.")
