from collections import Counter, defaultdict
import fnmatch
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.request import urlopen

VERSION = "0.7.5"


def folders(core, view, path):
    root = core.resolve_path(view, path)
    names, errors, truncated = [], 0, False
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= 10000:
                truncated = True
                break
            try:
                if not entry.is_symlink() and entry.is_dir(follow_symlinks=False):
                    names.append(entry.name)
            except OSError:
                errors += 1
    names.sort(key=str.casefold)
    return {"path": path, "view": view, "folders": names, "errors": errors, "truncated": truncated}


def redact(text):
    text = re.sub(r"(?i)(bearer\s+)[\w.\-+/=]+", r"\1[VERBORGEN]", text)
    text = re.sub(r'''(?i)((?:password|passwd|secret|token|api[_-]?key|authorization|jwt_secret)\s*[=:]\s*["']?)[^\s,"'}]+''', r"\1[VERBORGEN]", text)
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[VERBORGEN]@", text)
    return text


def browse(core, data):
    view, path = data.get("view", "host"), data.get("path", "/")
    root = core.resolve_path(view, path)
    rows, errors = [], 0
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= 10000:
                return {"rows": rows, "errors": errors, "truncated": True, "note": "Maximal 10.000 Einträge. Bitte einen kleineren Ordner wählen."}
            try:
                info = os.stat(entry.path, follow_symlinks=False)
                kind = "Link" if stat.S_ISLNK(info.st_mode) else "Ordner" if stat.S_ISDIR(info.st_mode) else "Datei" if stat.S_ISREG(info.st_mode) else "Spezialdatei"
                rows.append({"name": entry.name, "kind": kind, "bytes": info.st_size, "modified": info.st_mtime,
                             "rights": stat.filemode(info.st_mode), "owner": f"{info.st_uid}:{info.st_gid}"})
            except OSError:
                errors += 1
    rows.sort(key=lambda r: (r["kind"] != "Ordner", r["name"].casefold()))
    return {"rows": rows, "path": path, "view": view, "errors": errors, "note": "Ordnergrößen sind hier Metadaten, keine rekursive Belegung. Ordner anklicken zum Öffnen."}


def files_tool(core, data):
    root = core.resolve_path(data.get("view", "host"), data.get("path", "/"))
    files, errors, skipped = core.inventory(root)
    action = data["action"]
    note = "Andere Dateisysteme und Links werden übersprungen. Keine Dateien verändert."
    if action == "largest":
        rows = [{"name": n, "bytes": v[0]} for n, v in heapq.nlargest(200,files.items(),key=lambda p:p[1][0])]
    elif action == "search":
        pattern = str(data.get("pattern", "*"))[:200].casefold()
        rows = []
        for n,v in files.items():
            if fnmatch.fnmatchcase(n.casefold(),pattern) or fnmatch.fnmatchcase(Path(n).name.casefold(),pattern):
                if len(rows)<1000:rows.append({'name':n,'bytes':v[0]})
        note += " Dateinamen-Suche; Wildcards * und ? erlaubt. Maximal 1.000 Treffer."
    elif action == "types":
        if hasattr(files,'types'):
            return {'rows':files.types(),'errors':errors,'skipped':skipped,'files':len(files),'note':note+' Logische Dateigrößen; Hardlinks können mehrfach zählen. Maximal 1.000 Dateitypen.'}
        buckets = defaultdict(lambda: [0, 0])
        for n, v in files.items():
            key = Path(n).suffix.lower() or "Ohne Endung"
            buckets[key][0] += v[0]
            buckets[key][1] += 1
        rows = [{"name": k, "bytes": v[0], "count": v[1]} for k, v in sorted(buckets.items(), key=lambda p: p[1][0], reverse=True)]
        note += " Logische Dateigrößen; Hardlinks können mehrfach zählen."
    elif action == "duplicates":
        if hasattr(files,'duplicates'):
            rows,extra_errors=files.duplicates(root,core.digest,core.checkpoint)
            return {'rows':rows,'errors':errors+extra_errors,'skipped':skipped,'files':len(files),'note':note+' SHA-256-Gruppen; Hardlinks zählen einmal. Maximal 200 Gruppen und 100 Pfade pro Gruppe. Keine Löschung.'}
        sizes, seen = defaultdict(list), set()
        for n, v in files.items():
            if v[0] and (v[2], v[3]) not in seen:
                sizes[v[0]].append(n)
                seen.add((v[2], v[3]))
        rows = []
        for size, names in sizes.items():
            if len(names) < 2:
                continue
            hashes = defaultdict(list)
            for n in names:
                core.checkpoint(f"Inhalt prüfen: {n}")
                try:
                    hashes[core.digest(root / n)].append(n)
                except InterruptedError:
                    raise
                except OSError:
                    errors += 1
            for names in hashes.values():
                if len(names) > 1:
                    rows.append({"name": "\n".join(names[:100]), "count": len(names), "bytes": size * (len(names) - 1)})
        rows.sort(key=lambda r: r["bytes"], reverse=True)
        note += " SHA-256-Gruppen; Hardlinks zählen einmal. Angezeigte Ersparnis ist theoretisch, kein Löschvorschlag. Pro Gruppe höchstens 100 Pfade."
        rows = rows[:200]
    else:
        raise ValueError("Unbekanntes Dateiwerkzeug")
    return {"rows": rows, "errors": errors, "skipped": skipped, "files": len(files), "note": note}


def system_report(core):
    rows = []
    def read(path):
        try:
            p = core.resolve_path("host", str(Path(path).parent).replace("\\", "/")) / Path(path).name
            if p.is_symlink():
                return ""
            return p.read_text(errors="replace")[:100000]
        except (OSError, ValueError):
            return ""
    uptime = read("/proc/uptime").split()
    rows.append({"name": "Laufzeit", "value": f"{float(uptime[0]) / 86400:.2f} Tage" if uptime else "Nicht verfügbar"})
    rows.append({"name": "Last (1 / 5 / 15 Minuten)", "value": " / ".join(read("/proc/loadavg").split()[:3]) or "Nicht verfügbar"})
    mem = {}
    for line in read("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        nums = value.split()
        if nums and nums[0].isdigit():
            mem[key] = int(nums[0]) * 1024
    for key, label in [("MemTotal", "Arbeitsspeicher gesamt"), ("MemAvailable", "Arbeitsspeicher verfügbar"), ("SwapTotal", "Swap gesamt")]:
        rows.append({"name": label, "value": f"{mem[key] / 1073741824:.2f} GiB" if key in mem else "Nicht verfügbar"})
    osinfo = read("/etc/os-release")
    match = re.search(r'^PRETTY_NAME="?([^"\n]+)', osinfo, re.M)
    rows.append({"name": "Betriebssystem", "value": match[1] if match else "Nicht verfügbar"})
    rows.append({"name": "Kernel", "value": read("/proc/sys/kernel/osrelease").strip() or "Nicht verfügbar"})
    findings = []
    for disk in core.overview()["disks"]:
        percent = disk["used"] / disk["total"] * 100
        if percent > 85:
            findings.append(f"{disk['path']}: {percent:.0f} % belegt. Große Ordner und verdeckte Systemdaten untersuchen.")
    if mem.get("MemAvailable", 2**60) < 512 * 1024**2:
        findings.append("Weniger als 512 MiB Arbeitsspeicher verfügbar. Containerbedarf und Hostprozesse prüfen.")
    return {"rows": rows, "findings": findings, "note": "Messwerte aus Host-/proc. Keine Aussage über systemd-, Festplatten- oder Dienstgesundheit allein aus diesen Werten."}


def mounts(core):
    result = []
    for view in ("host", "system"):
        base = core.ROOTS[view]
        if not base.is_dir():
            continue
        paths = ["/"] + [p for p in os.getenv("DATA_PATHS", "/mnt/intenso2tb").split(":") if p]
        for path in paths:
            try:
                p = core.resolve_path(view, path)
                info = p.stat()
                result.append({"name": path, "view": view, "device": str(info.st_dev), "value": "schreibgeschützte Ansicht", "bytes": core.shutil.disk_usage(p).used})
            except (OSError, ValueError):
                result.append({"name": path, "view": view, "device": "—", "value": "Nicht erreichbar"})
    findings = []
    host_rows = [r for r in result if r["view"] == "host"]
    root = next((r for r in host_rows if r["name"] == "/"), {})
    for row in host_rows:
        if row["name"] != "/" and row["device"] == root.get("device"):
            findings.append(f"{row['name']} liegt auf demselben Dateisystem wie /. Eine erwartete Datenplatte könnte fehlen; Bind-Mounts sind ebenfalls möglich.")
    return {"rows": result, "findings": findings, "note": "Dateisystemkennung aus stat(), kein Gerätename. Unterschiedliche Kennungen bedeuten unterschiedliche Dateisysteme."}


RULES = [
    (r"no space left|disk full|ENOSPC", "Speicherplatz oder Inodes erschöpft", "Systemplatte, Inodes und verdeckte Daten prüfen."),
    (r"prior lock file|valid lock file found", "Rclone-Sperre", "Laufenden Abgleich ausschließen. Sperre nicht während eines aktiven Laufs entfernen."),
    (r"cannot find prior|must run --resync", "Bisync-Zustand fehlt", "Arbeitsordner und gespeicherte Listen prüfen; keinen automatischen Resync erzwingen."),
    (r"org.freedesktop.systemd1|failed to create session|system scope bus", "Systemverwaltung nicht erreichbar", "Laufzeit und systemd-Status über die Hostkonsole prüfen."),
    (r"504|gateway time.?out", "Zeitüberschreitung am Proxy", "Zieldienst intern und danach den Proxy prüfen."),
    (r"connection refused", "Verbindung abgelehnt", "Dienststatus, Zieladresse und Port prüfen."),
    (r"could not resolve|name resolution|ENOTFOUND", "Namensauflösung fehlgeschlagen", "DNS-Konfiguration und Erreichbarkeit im Container prüfen."),
    (r"permission denied|zugriff verweigert|EACCES", "Zugriff verweigert", "Benutzer, Dateirechte und Cloud-Zugriff prüfen; keine pauschalen chmod-Änderungen."),
    (r"out of memory|oom.?kill|cannot allocate memory", "Hinweis auf Speichermangel", "Verfügbaren RAM und Containerlimits prüfen."),
    (r"redis.*(lost|error|refused)|read error on connection", "Redis-Verbindung gestört", "Redis-Container, Speicher und Netzwerk prüfen."),
    (r"read.only file system", "Dateisystem schreibgeschützt", "Host-Einhängung und Kernelmeldungen prüfen; Ursache vor einem Remount klären."),
    (r"bisync successful", "Bisync erfolgreich abgeschlossen", "Dieser Logeintrag bestätigt einen abgeschlossenen Abgleich."),
]


def analyze_log(text):
    text = text[:500000]
    findings = []
    lines = text.splitlines()
    for pattern, title, advice in RULES:
        matching = [line for line in lines if re.search(pattern, line, re.I)]
        if matching:
            findings.append({"name": title, "count": len(matching), "value": advice, "evidence": redact(matching[-1])[:500]})
    return {"rows": findings, "note": "Musterbasierte Hinweise, keine bewiesene Ursache. Alte und neue Einträge nach Zeitstempel unterscheiden. Zugangsdaten werden bestmöglich maskiert; keine vollständige Geheimnis-Erkennung."}


def docker_report(data):
    gateway = os.getenv("DOCKER_GATEWAY", "")
    if not gateway:
        return {"rows": [], "note": "Docker-Modul nicht verbunden. Optional compose.docker.yaml aktivieren; siehe Anleitung."}
    endpoint = "/containers" if data["action"] == "docker" else "/logs?id=" + str(data.get("container", ""))
    with urlopen(gateway + endpoint, timeout=12) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def run(core, data):
    action = data["action"]
    if action == "browse":
        return browse(core, data)
    if action in ("largest", "search", "types", "duplicates"):
        return files_tool(core, data)
    if action == "system":
        return system_report(core)
    if action == "mounts":
        return mounts(core)
    if action == "log":
        return analyze_log(str(data.get("text", "")))
    if action in ("docker", "docker_logs"):
        return docker_report(data)
    if action == "checklist":
        return {"rows": [
            {"name": "Systemplatte voll", "value": "Systemansicht → /mnt untersuchen. Danach größte Dateien und Dateitypen prüfen."},
            {"name": "Dateien vermisst", "value": "Dateibrowser → GoodSync _saved_, Nextcloud-Papierkorb und verdeckte Daten prüfen. Anschließend Inhaltsvergleich."},
            {"name": "Container öffnet nicht", "value": "Docker-Status und Logs prüfen. Speicher und Einbindungen kontrollieren. Erreichbarkeit allein ist kein Gesundheitsnachweis."},
            {"name": "Vor einer Bereinigung", "value": "Quelle und Ziel eindeutig zuordnen. Backup anlegen, Inhaltsvergleich durchführen, Lesefehler ausschließen. Datenbanken separat sichern."}], "note": "Geführte Prüfschritte. Es werden keine Befehle automatisch ausgeführt."}
    raise ValueError("Unbekanntes Werkzeug")
