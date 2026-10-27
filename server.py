import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import threading
import time
import sys
import toolkit
from scan_index import FileIndex
import auth
import localization
import admin_client
import admin_demo
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = Path(__file__).parent
ROOTS = {"host": Path(os.getenv("HOST_ROOT", "/host")), "system": Path(os.getenv("SYSTEM_ROOT", "/system"))}
TOKEN = os.getenv("SERVERLOTSE_TOKEN", "")
DEMO = os.getenv("SERVERLOTSE_DEMO", "0") == "1"
JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)
MAX_FILES = None
CONTEXT = threading.local()
HOST_POWER_UNTIL = 0
ACTIONS = {"scan", "compare", "browse", "largest", "types", "search", "duplicates", "system", "mounts", "log", "docker", "docker_logs", "checklist", "copy_plan", "copy_apply"}


def admin_busy():
    if DEMO or not Path(os.getenv("SERVERLOTSE_ADMIN_SOCKET", "/admin/agent.sock")).exists(): return False
    return admin_client.request("/read", {"view": "status"}, TOKEN).get("busy", False)


def record_event(action, status, parameters=None, ident=None, result=""):
    if DEMO: return None
    try:
        return admin_client.request("/read", {"view": "event", "action": action, "status": status, "parameters": parameters or {}, "id": ident, "result": result}, TOKEN).get("id")
    except ValueError:
        return None


def host_request(endpoint, data=None):
    if DEMO:
        if endpoint == "/status":return {"enabled":True,"reboot":True,"shutdown":True,"demo":True}
        if endpoint == "/prepare":return {"nonce":"demo","action":data["action"],"confirmation":"REBOOT" if data["action"]=="reboot" else "SHUTDOWN","demo":True}
        return {"accepted":False,"demo":True,"note":"Demo: Es wurde keine Host-Aktion ausgeführt."}
    gateway=os.getenv("HOST_CONTROL_GATEWAY","")
    if not gateway:raise ValueError("Host-Steuerung ist nicht eingerichtet.")
    request=Request(gateway+endpoint,data=json.dumps(data).encode() if data is not None else None,headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"})
    try:
        with urlopen(request,timeout=12) as response:return json.loads(response.read(8192))
    except HTTPError as exc:
        try:detail=json.loads(exc.read(8192)).get("error","")
        except (ValueError,TypeError):detail=""
        raise ValueError(detail or "Host-Steuerung ist nicht erreichbar.") from None
    except OSError:
        raise ValueError("Host-Steuerung ist nicht erreichbar.") from None


def host_boot_ready():
    unit=ROOTS["host"] / "etc/systemd/system/serverlotse-view.service"
    enabled=ROOTS["host"] / "etc/systemd/system/multi-user.target.wants/serverlotse-view.service"
    return unit.is_file() and enabled.is_symlink()


def checkpoint(message=None):
    job_id = getattr(CONTEXT, "job_id", None)
    if job_id:
        with LOCK:
            job = JOBS[job_id]
            if job.get("cancel"):
                raise InterruptedError("Prüfung auf deinen Wunsch abgebrochen.")
            if message:
                job["progress"] = message[:300]


def resolve_path(view, value):
    if view not in ROOTS:
        raise ValueError("Unbekannte Ansicht")
    p = PurePosixPath(value)
    if not p.is_absolute() or ".." in p.parts or "\\" in value:
        raise ValueError("Bitte einen absoluten Linux-Pfad ohne .. verwenden.")
    base = ROOTS[view].resolve()
    target = base.joinpath(*p.parts[1:])
    current = base
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError("Symbolische Links werden zum Schutz der Pfadgrenzen nicht verfolgt.")
    if not target.is_dir():
        raise ValueError("Ordner nicht vorhanden oder nicht zugänglich.")
    if not target.resolve().is_relative_to(base):
        raise ValueError("Pfad außerhalb der freigegebenen Ansicht.")
    return target


def inventory(root):
    checkpoint("Ordner wird eingelesen")
    device = root.stat().st_dev
    files, errors, skipped, seen = FileIndex(), 0, 0, 0
    db=files.connection;db.execute('INSERT INTO pending(path) VALUES(?)',(str(root),))
    try:
        while True:
            checkpoint()
            next_directory=db.execute('SELECT id,path FROM pending ORDER BY id LIMIT 1').fetchone()
            if next_directory is None:break
            ident,directory=next_directory;db.execute('DELETE FROM pending WHERE id=?',(ident,))
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        seen += 1
                        if seen%250==0:checkpoint(f"{seen:,} Einträge untersucht")
                        if seen%5000==0:files.check_space()
                        try:
                            info = os.stat(entry.path, follow_symlinks=False) if os.name == "nt" else entry.stat(follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode) or info.st_dev != device:
                                skipped += 1
                            elif stat.S_ISDIR(info.st_mode):
                                db.execute('INSERT INTO pending(path) VALUES(?)',(entry.path,))
                            elif stat.S_ISREG(info.st_mode):
                                files.add(str(Path(entry.path).relative_to(root)),info)
                        except OSError:
                            errors += 1
            except InterruptedError:
                raise
            except OSError:
                errors += 1
        files.finish()
        return files, errors, skipped
    except BaseException:
        files.close();raise

def scan(view, path):
    root = resolve_path(view, path)
    files, errors, skipped = inventory(root)
    groups, seen = {}, set()
    for name, (size, blocks, dev, inode) in (files.items(unique=True) if isinstance(files,FileIndex) else files.items()):
        identity = (dev, inode)
        if not isinstance(files,FileIndex) and identity in seen:
            continue
        if not isinstance(files,FileIndex):seen.add(identity)
        group = name.split(os.sep)[0] if os.sep in name else "Dateien direkt in diesem Ordner"
        groups[group] = groups.get(group, 0) + (blocks * 512 if blocks is not None else size)
    return {"path": path, "view": view, "bytes": sum(groups.values()), "files": len(files), "errors": errors, "skipped": skipped,
            "rows": [{"name": k, "bytes": v} for k, v in sorted(groups.items(), key=lambda x: x[1], reverse=True)],
            "note": "Belegter Speicher; andere Dateisysteme und symbolische Links werden übersprungen. Fehler bedeuten: Ergebnis unvollständig."}


def digest(path):
    checkpoint()
    before = path.stat()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise OSError("Keine reguläre Datei")
        hasher = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            checkpoint()
            hasher.update(chunk)
        result = hasher.hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise OSError("Datei wurde während des Vergleichs verändert")
    return result


def compare(source_view, source, target_view, target):
    a, b = resolve_path(source_view, source), resolve_path(target_view, target)
    files, errors, skipped = inventory(a)
    rows, counts = [], {"same": 0, "missing": 0, "different": 0, "error": 0}
    for name, info in files.items():
        checkpoint(f"Vergleiche {name}")
        other = b / name
        try:
            current = b
            for part in Path(name).parts:
                current /= part
                if current.is_symlink():
                    raise OSError("Symbolischer Link im Ziel")
            try:other_info=other.stat()
            except FileNotFoundError:other_info=None
            if other_info is None:
                status = "missing"
            elif not stat.S_ISREG(other_info.st_mode):
                status = "different"
            elif other_info.st_size != info[0]:
                status = "different"
            else:
                status = "same" if digest(a / name) == digest(other) else "different"
        except InterruptedError:
            raise
        except OSError:
            status = "error"
        counts[status] += 1
        if status != "same" and len(rows) < 1000:
            rows.append({"name": name, "status": status, "bytes": info[0]})
    return {"counts": counts, "rows": rows, "errors": errors, "skipped": skipped,
            "complete": errors == 0 and skipped == 0 and counts["error"] == 0,
            "truncated": sum(v for k, v in counts.items() if k != "same") > len(rows),
            "note": "Einseitiger SHA-256-Vergleich: Prüft Quelldateien im Ziel. Zusätzliche Zieldateien werden nicht geprüft. Es wird nichts verändert."}


def overview():
    if DEMO:
        return {"demo": True, "disks": [{"name": "Systemplatte", "path": "/", "total": 235000000000, "used": 86000000000, "free": 138000000000}, {"name": "Datenplatte", "path": "/mnt/intenso2tb", "total": 2000000000000, "used": 640000000000, "free": 1360000000000}]}
    disks, seen = [], set()
    paths = ["/"] + [p for p in os.getenv("DATA_PATHS", "/mnt/intenso2tb").split(":") if p]
    for path in paths:
        try:
            resolved = resolve_path("host", path)
            dev = resolved.stat().st_dev
            if dev in seen:
                continue
            seen.add(dev)
            usage = shutil.disk_usage(resolved)
            disks.append({"name": "Systemplatte" if path == "/" else "Datenplatte", "path": path, "total": usage.total, "used": usage.used, "free": usage.free})
        except (OSError, ValueError):
            continue
    return {"demo": False, "disks": disks, "system_available": ROOTS["system"].is_dir()}


def execute(job_id, data):
    CONTEXT.job_id = job_id
    with LOCK:
        JOBS[job_id]["status"] = "running"
    audit_id = record_event(data["action"], "running", data)
    try:
        if DEMO:
            time.sleep(0.4)
            if data["action"] == "scan":
                result = {"bytes": 49000000000, "files": 14230, "errors": 0, "skipped": 2, "rows": [{"name": "nextcloud", "bytes": 36000000000}, {"name": "linkwarden", "bytes": 13000000000}], "note": "Beispieldaten – keine Verbindung zu deinem Server."}
            elif data["action"] == "compare":
                result = {"counts": {"same": 22110, "missing": 7, "different": 2, "error": 0}, "errors": 0, "skipped": 0, "complete": True, "rows": [{"name": "Android/boot.img", "status": "missing", "bytes": 14109864}, {"name": "Dokumente/Anleitung.pdf", "status": "different", "bytes": 340000}], "note": "Beispielvergleich – keine echten Dateien geprüft."}
            else:
                result = demo_tool(data)
        elif data["action"] == "scan":
            result = scan(data.get("view", "host"), data.get("path", "/"))
        elif data["action"] == "compare":
            result = compare(data.get("source_view", "system"), data["source"], data.get("target_view", "host"), data["target"])
        else:
            if data["action"] in ("copy_plan", "copy_apply"):
                import recovery
                result = recovery.run(sys.modules[__name__], data)
            else:
                result = toolkit.run(sys.modules[__name__], data)
        checkpoint()
        with LOCK:
            JOBS[job_id].update(status="done", result=result, finished=time.time())
    except InterruptedError as exc:
        with LOCK:
            JOBS[job_id].update(status="cancelled", error=str(exc), finished=time.time())
    except Exception as exc:
        with LOCK:
            JOBS[job_id].update(status="error", error=str(exc), finished=time.time())
    finally:
        if audit_id:
            with LOCK: finished_job = dict(JOBS[job_id])
            record_event(data["action"], finished_job["status"], ident=audit_id, result=finished_job.get("error", finished_job.get("result", {}).get("note", "")))
        CONTEXT.job_id = None


def demo_tool(data):
    action = data["action"]
    note = "DEMO: Beispieldaten. Keine Live-Verbindung zu deinem Server."
    if action == "log":
        result = toolkit.analyze_log(str(data.get("text", "")))
        result["note"] += " Analyse des eingefügten Textes; kein Hostzugriff."
        return result
    if action == "browse":
        return {"rows": [{"name": "nextcloud", "kind": "Ordner", "bytes": 4096, "rights": "drwxr-xr-x", "owner": "33:33", "modified": time.time()}, {"name": "linkwarden", "kind": "Ordner", "bytes": 4096, "rights": "drwxr-xr-x", "owner": "0:0", "modified": time.time()}], "note": note}
    if action in ("copy_plan", "copy_apply"):
        raise ValueError("Kopieren ist in der Demo deaktiviert.")
    if action == "duplicates":
        return {"rows": [{"name": "Fotos/Urlaub.jpg\nBackup/Urlaub.jpg", "count": 2, "bytes": 4500000}], "note": note}
    if action in ("largest", "search", "types"):
        return {"rows": [{"name": ".zip" if action == "types" else "Android/Backup.zip", "count": 18, "bytes": 4200000000}], "note": note}
    if action == "docker":
        return {"rows": [{"name": "nextcloud", "id": "d"*64, "value": "running", "image": "nextcloud", "mounts": "/mnt/intenso2tb/nextcloud → /var/www/html"}, {"name": "onlyoffice", "id": "e"*64, "value": "running", "image": "onlyoffice/documentserver", "mounts": "/mnt/intenso2tb/onlyoffice → /var/log/onlyoffice"}], "note": note}
    if action == "docker_logs":
        return {"rows": [], "text": "2026-10-24 INFO Bisync successful", "note": note}
    if action == "system":
        return {"rows": [{"name": "Laufzeit", "value": "0,15 Tage"}, {"name": "Arbeitsspeicher verfügbar", "value": "20 GiB"}, {"name": "Betriebssystem", "value": "DietPi / Debian"}], "note": note}
    if action == "mounts":
        return {"rows": [{"name": "/", "view": "host", "device": "2049", "value": "Erreichbar"}, {"name": "/mnt/intenso2tb", "view": "host", "device": "2065", "value": "Erreichbar"}], "note": note}
    return {"rows": [{"name": "Erst prüfen, dann handeln", "value": "Dateien vergleichen und Lesefehler beachten. Datenbanken separat sichern."}], "note": note}


class Handler(BaseHTTPRequestHandler):
    server_version = "ServerLotse/0.7.5"

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def send(self, status, body, content_type="application/json; charset=utf-8", cookie=None, style_nonce=None):
        if isinstance(body, dict):
            body = localization.payload(body, localization.language(self.headers.get("Accept-Language")))
        raw = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("X-Content-Type-Options", "nosniff")
        style_rule = "style-src 'self' 'nonce-"+style_nonce+"'; " if style_nonce else ""
        self.send_header("Content-Security-Policy", "default-src 'self'; "+style_rule+"frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return DEMO or bool(TOKEN and hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + TOKEN).encode())) or auth.valid(auth.from_header(self.headers.get("Cookie")), TOKEN)

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme in ("https", "http") and parsed.netloc.lower() == self.headers.get("Host", "").lower()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            return self.send(200, {"ok": True})
        if path.startswith("/api/"):
            if not self.authorized():
                return self.send(401, {"error": "Bitte den Zugangsschlüssel eingeben."})
            if path == "/api/admin/status":
                if DEMO:
                    return self.send(200, admin_demo.read({"view": "status"}))
                try:
                    return self.send(200, admin_client.request("/read", {"view": "status"}, TOKEN))
                except ValueError as exc:
                    return self.send(200, {"enabled": False, "note": str(exc)})
            if path == "/api/overview":
                return self.send(200, overview())
            if path == "/api/folders":
                query = parse_qs(urlsplit(self.path).query)
                view = query.get("view", ["host"])[0]
                folder = query.get("path", ["/"])[0]
                try:
                    if DEMO:
                        demo = {"/": ["boot", "etc", "mnt", "root", "var"], "/mnt": ["dietpi_userdata", "intenso2tb"], "/mnt/intenso2tb": ["googledrive", "linkwarden", "nextcloud", "serverlotse"], "/mnt/intenso2tb/nextcloud": ["config", "custom_apps", "data"], "/mnt/intenso2tb/googledrive": ["Dianne", "Kristina", "Paco", "_gsdata_"], "/root": [".cache"]}
                        return self.send(200, {"path": folder, "view": view, "folders": demo.get(folder, []), "errors": 0, "truncated": False})
                    return self.send(200, toolkit.folders(sys.modules[__name__], view, folder))
                except (ValueError, OSError) as exc:
                    return self.send(400, {"error": str(exc)})
            if path == "/api/jobs":
                with LOCK:
                    rows = [{k: v for k, v in job.items() if k not in ("result", "cancel")} for job in JOBS.values()]
                return self.send(200, {"rows": rows[::-1], "note": "Letzte 20 Aufgaben; Verlauf wird beim Containerneustart geleert."})
            if path == "/api/settings":
                return self.send(200, {"version": toolkit.VERSION, "demo": DEMO, "copy": os.getenv("COPY_ENABLED") == "1" and not DEMO, "docker": bool(os.getenv("DOCKER_GATEWAY")) or DEMO, "max_files": MAX_FILES})
            if path == "/api/host/status":
                try:
                    result=host_request("/status")
                    if not DEMO and not host_boot_ready():
                        result["reboot"]=False
                        result["note"]="Vor dem Neustart den Compose-Start-Helfer erfolgreich abschließen: docker compose up -d --build."
                    return self.send(200,result)
                except ValueError as exc:return self.send(503,{"error":str(exc)})
            if path.startswith("/api/jobs/"):
                with LOCK:
                    job = dict(JOBS.get(path.rsplit("/", 1)[-1], {}))
                return self.send(200 if job else 404, job or {"error": "Prüfung nicht gefunden"})
            return self.send(404, {"error": "Nicht gefunden"})
        assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/toolkit-ui.js": ("toolkit-ui.js", "text/javascript; charset=utf-8"), "/folder-picker.js": ("folder-picker.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"), "/locales.json": ("locales.json", "application/json; charset=utf-8")}
        assets["/session-ui.js"] = ("session-ui.js", "text/javascript; charset=utf-8")
        assets["/icons.js"] = ("icons.js", "text/javascript; charset=utf-8")
        assets["/folder-select.js"] = ("folder-select.js", "text/javascript; charset=utf-8")
        assets["/workspace-ui.js"] = ("workspace-ui.js", "text/javascript; charset=utf-8")
        assets["/admin-ui.js"] = ("admin-ui.js", "text/javascript; charset=utf-8")
        assets["/sensor-ui.js"] = ("sensor-ui.js", "text/javascript; charset=utf-8")
        assets["/workbench-ui.js"] = ("workbench-ui.js", "text/javascript; charset=utf-8")
        assets["/expert-ui.js"] = ("expert-ui.js", "text/javascript; charset=utf-8")
        assets["/navigation-ui.js"] = ("navigation-ui.js", "text/javascript; charset=utf-8")
        assets["/advanced-ui.js"] = ("advanced-ui.js", "text/javascript; charset=utf-8")
        for name, mime in {"terminal-ui.js":"text/javascript", "vendor/xterm.js":"text/javascript", "vendor/addon-fit.js":"text/javascript", "vendor/xterm.css":"text/css"}.items():
            assets["/"+name] = (name, mime+"; charset=utf-8")
        if path not in assets:
            return self.send(404, {"error": "Nicht gefunden"})
        name, mime = assets[path]
        if name == 'index.html':
            nonce = secrets.token_urlsafe(24)
            html = (BASE / 'static' / name).read_text(encoding='utf-8')
            html = html.replace('<head>', '<head><meta name="terminal-style-nonce" content="'+nonce+'">', 1)
            return self.send(200, html.encode(), mime, style_nonce=nonce)
        return self.send(200, (BASE / "static" / name).read_bytes(), mime)

    def do_POST(self):
        global HOST_POWER_UNTIL
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 524288:
                raise ValueError("Ungültige Anfragegröße")
            request_body = self.rfile.read(length)
        except (ValueError, OSError):
            return self.send(400, {"error": "Ungültige Anfragegröße"})
        if not self.same_origin():
            return self.send(403, {"error": "Anfrage von einer fremden Webseite abgelehnt."})
        if path == "/api/login":
            if not auth.allow_attempt(self.client_address[0]):
                return self.send(429, {"error": "Zu viele Anmeldeversuche. Bitte eine Minute warten."})
            try:
                if not 0 < length <= 4096:
                    raise ValueError("Ungültige Anmeldung")
                data = json.loads(request_body)
                if not isinstance(data, dict) or not isinstance(data.get("token"), str):
                    raise ValueError("Ungültige Anmeldung")
                if not TOKEN or not hmac.compare_digest(data["token"].encode(), TOKEN.encode()):
                    return self.send(401, {"error": "Ungültiger Zugangsschlüssel"})
                remember = data.get("remember") is True
                session, lifetime = auth.issue(TOKEN, remember)
                return self.send(200, {"ok": True}, cookie=auth.cookie(session, lifetime if remember else None))
            except (ValueError, TypeError):
                return self.send(400, {"error": "Ungültige Anmeldung"})
        if not self.authorized():
            return self.send(401, {"error": "Ungültiger Zugangsschlüssel"})
        if path == "/api/terminal":
            try:
                if DEMO: raise ValueError("Das interaktive Terminal ist in der Demo gesperrt.")
                data = json.loads(request_body)
                if not isinstance(data, dict): raise ValueError("Ungültige Anfrage")
                if data.get('action') not in {'prepare','start','poll','input','resize','close'}:
                    raise ValueError('Unbekannte Terminalaktion.')
                credential = auth.from_header(self.headers.get('Cookie')) or self.headers.get('Authorization', '')
                data['owner'] = hmac.new(TOKEN.encode(), credential.encode(), 'sha256').hexdigest()
                if data['action'] == 'start':
                    with LOCK:
                        if HOST_POWER_UNTIL > time.time() or any(j['status'] in ('queued','running') for j in JOBS.values()):
                            raise ValueError('Eine Aufgabe läuft bereits. Bitte Abschluss abwarten.')
                return self.send(200, admin_client.request('/terminal', data, TOKEN))
            except (ValueError, TypeError) as exc:
                return self.send(400, {'error':str(exc)})
        if path in ("/api/admin/read", "/api/admin/prepare", "/api/admin/execute"):
            try:
                data = json.loads(request_body)
                if not isinstance(data, dict): raise ValueError("Ungültige Anfrage")
                if DEMO:
                    if path.endswith("read"): return self.send(200, admin_demo.read(data))
                    if path.endswith("prepare"):
                        return self.send(200, {"nonce": "demo", "confirmation": "LOESCHEN" if data.get('operation') in {'volume_delete','lab_janitor'} else "AUSFUEHREN", "preview": admin_demo.safe_preview(data), "warnings": ["Demo: Es wird keine Host-Aktion ausgeführt."], "demo": True})
                    raise ValueError("Die Host-Verwaltung ist in der Demo gesperrt.")
                if path.endswith(("prepare", "execute")):
                    with LOCK:
                        if HOST_POWER_UNTIL > time.time() or any(j["status"] in ("queued", "running") for j in JOBS.values()):
                            raise ValueError("Eine Aufgabe oder Host-Aktion läuft bereits. Bitte Abschluss abwarten.")
                        if path.endswith("execute"):
                            return self.send(200, admin_client.request("/execute", data, TOKEN))
                return self.send(200, admin_client.request("/" + path.rsplit("/", 1)[-1], data, TOKEN))
            except (ValueError, TypeError) as exc:
                return self.send(400, {"error": str(exc)})
        if path in ("/api/host/prepare","/api/host/execute"):
            try:
                data=json.loads(request_body)
                if not isinstance(data,dict) or data.get("action") not in ("reboot","shutdown"):raise ValueError("Ungültige Host-Aktion")
                if data["action"]=="reboot" and not DEMO and not host_boot_ready():raise ValueError("Vor dem Neustart den Compose-Start-Helfer erfolgreich abschließen: docker compose up -d --build.")
                with LOCK:
                    if any(job["status"] in ("queued","running") for job in JOBS.values()):raise ValueError("Es läuft noch eine Aufgabe. Vor der Host-Aktion deren Abschluss abwarten.")
                    if HOST_POWER_UNTIL>time.time():raise ValueError("Eine Host-Aktion wurde bereits angefordert. Bitte warten.")
                    if admin_busy():raise ValueError("Eine Verwaltungsaktion läuft bereits. Bitte Abschluss abwarten.")
                    if path.endswith("execute") and not DEMO:
                        if Path(os.getenv("SERVERLOTSE_ADMIN_SOCKET", "/admin/agent.sock")).exists():
                            admin_client.request("/read", {"view": "power_reserve"}, TOKEN)
                        HOST_POWER_UNTIL=time.time()+120
                result=host_request("/prepare" if path.endswith("prepare") else "/execute",data)
                if path.endswith("execute"):
                    self.log_message("Host action: %s, accepted: %s",data["action"],result.get("accepted",False))
                    record_event("host_" + data["action"], "done" if result.get("accepted") else "error", result=result.get("note", ""))
                return self.send(200,result)
            except (ValueError,TypeError) as exc:return self.send(400,{"error":str(exc)})
        if path == "/api/logout":
            try:
                auth.revoke(auth.from_header(self.headers.get("Cookie")))
                return self.send(200, {"ok": True}, cookie=auth.cookie("", 0))
            except ValueError as exc:
                return self.send(429, {"error": str(exc)})
        if path.startswith("/api/cancel/"):
            with LOCK:
                job = JOBS.get(path.rsplit("/", 1)[-1])
                if not job:
                    return self.send(404, {"error": "Aufgabe nicht gefunden"})
                job["cancel"] = True
            return self.send(200, {"ok": True})
        if path != "/api/jobs":
            return self.send(404, {"error": "Nicht gefunden"})
        try:
            if not 0 < length <= 524288:
                raise ValueError("Ungültige Anfragegröße")
            data = json.loads(request_body)
            if not isinstance(data, dict) or data.get("action") not in ACTIONS:
                raise ValueError("Ungültige Prüfung")
            with LOCK:
                if HOST_POWER_UNTIL>time.time():return self.send(409,{"error":"Eine Host-Aktion wurde bereits angefordert. Bitte warten."})
                if admin_busy():return self.send(409,{"error":"Eine Verwaltungsaktion läuft bereits. Bitte Abschluss abwarten."})
                if any(j["status"] in ("queued", "running") for j in JOBS.values()):
                    return self.send(409, {"error": "Eine Prüfung läuft bereits. Bitte ihren Abschluss abwarten."})
                while len(JOBS) >= 20:
                    del JOBS[next(iter(JOBS))]
                job_id = secrets.token_hex(12)
                JOBS[job_id] = {"id": job_id, "action": data["action"], "status": "queued", "created": time.time(), "progress": "Wartet auf Start"}
            POOL.submit(execute, job_id, data)
            return self.send(202, {"id": job_id})
        except (ValueError, KeyError, TypeError) as exc:
            return self.send(400, {"error": str(exc)})


if __name__ == "__main__":
    if not DEMO and len(TOKEN) < 24:
        raise SystemExit("SERVERLOTSE_TOKEN muss mindestens 24 Zeichen enthalten.")
    ThreadingHTTPServer((os.getenv("BIND", "127.0.0.1" if DEMO else "0.0.0.0"), int(os.getenv("PORT", "8099"))), Handler).serve_forever()
