import hashlib
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import time

PLANS = {}


def require_enabled():
    if os.getenv("COPY_ENABLED") != "1":
        raise ValueError("Kopieren ist deaktiviert. Optionales Rettungsmodul einrichten; siehe Anleitung.")


def open_directory(base, parts=(), create=False):
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            if part in ("", ".", "..") or "/" in part or "\\" in part:
                raise ValueError("Ungültiger Pfadbestandteil")
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def run(core, data):
    require_enabled()
    if data["action"] == "copy_plan":
        view, path = data.get("view", "system"), data["path"]
        source = core.resolve_path(view, path)
        files, errors, skipped = core.inventory(source)
        if errors or skipped:
            raise ValueError("Quelle enthält Lesefehler, Links oder andere Dateisysteme. Einen eindeutigen Unterordner wählen.")
        if not files or len(files) > 10000:
            raise ValueError("Für einen Kopierplan 1 bis 10.000 Dateien auswählen.")
        rows = []
        for name, info in files.items():
            core.checkpoint(f"Kopierplan prüfen: {name}")
            rows.append({"name": name, "bytes": info[0], "sha256": core.digest(source / name)})
        plan_id = secrets.token_hex(12)
        folder = "rettung-" + time.strftime("%Y%m%d-%H%M%S") + "-" + plan_id[:6]
        for key in list(PLANS):
            if PLANS[key]["expires"] < time.time():
                del PLANS[key]
        if len(PLANS) >= 10:
            del PLANS[next(iter(PLANS))]
        PLANS[plan_id] = {"view": view, "path": path, "files": rows, "folder": folder, "expires": time.time() + 1800}
        return {"plan_id": plan_id, "rows": [{"name": "Quelldateien", "value": str(len(rows))}, {"name": "Datenmenge", "bytes": sum(r["bytes"] for r in rows)}, {"name": "Neuer Zielordner", "value": folder}], "note": "Plan gültig für 30 Minuten. Kopiert nur in den freigegebenen Rettungsordner. Kein Überschreiben und kein Löschen; leere Ordner und Metadaten werden nicht gesichert."}
    if data.get("confirmation") != "KOPIEREN":
        raise ValueError("Kopiervorschau muss mit KOPIEREN bestätigt werden.")
    plan = PLANS.pop(data.get("plan_id", ""), None)
    if not plan or plan["expires"] < time.time():
        raise ValueError("Kopierplan abgelaufen oder bereits verwendet. Neuen Plan erstellen.")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("Sicheres Kopieren wird nur unter Linux unterstützt.")
    recovery_root = Path(os.getenv("RECOVERY_ROOT", "/recovery"))
    if recovery_root.is_symlink() or not recovery_root.is_dir():
        raise ValueError("Rettungsordner fehlt oder ist ein Link.")
    total = sum(r["bytes"] for r in plan["files"])
    if core.shutil.disk_usage(recovery_root).free < total + 64 * 1024**2:
        raise ValueError("Nicht genug Platz im Rettungsordner.")
    source_fd = open_directory(core.ROOTS[plan["view"]], PurePosixPath(plan["path"]).parts[1:])
    try:
        root_fd = open_directory(recovery_root)
    except BaseException:
        os.close(source_fd)
        raise
    count = 0
    try:
        os.mkdir(plan["folder"], mode=0o700, dir_fd=root_fd)
        destination_fd = os.open(plan["folder"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            for row in plan["files"]:
                core.checkpoint(f"Kopiere und prüfe {count + 1}/{len(plan['files'])}: {row['name']}")
                parts = Path(row["name"]).parts
                src_parent = os.dup(source_fd)
                try:
                    for part in parts[:-1]:
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=src_parent)
                        os.close(src_parent)
                        src_parent = child
                    src = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src_parent)
                    with os.fdopen(src, "rb") as reader:
                        info = os.fstat(reader.fileno())
                        if not stat.S_ISREG(info.st_mode):
                            raise ValueError("Quelle ist keine reguläre Datei")
                        parent = os.dup(destination_fd)
                        try:
                            for part in parts[:-1]:
                                try:
                                    os.mkdir(part, mode=0o700, dir_fd=parent)
                                except FileExistsError:
                                    pass
                                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                                os.close(parent)
                                parent = child
                            temporary = ".serverlotse-" + secrets.token_hex(8) + ".part"
                            out = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                            with os.fdopen(out, "w+b") as writer:
                                hasher = hashlib.sha256()
                                copied = 0
                                while chunk := reader.read(1024 * 1024):
                                    core.checkpoint()
                                    copied += len(chunk)
                                    if copied > row["bytes"]:
                                        raise ValueError("Quelldatei ist seit der Vorschau gewachsen. Kopie abgebrochen.")
                                    writer.write(chunk)
                                    hasher.update(chunk)
                                if hasher.hexdigest() != row["sha256"]:
                                    raise ValueError("Quelldatei hat sich seit der Vorschau verändert. Teilkopie bleibt als .part erhalten.")
                                writer.flush()
                                os.fsync(writer.fileno())
                                writer.seek(0)
                                if hashlib.file_digest(writer, "sha256").hexdigest() != row["sha256"]:
                                    raise ValueError("Prüfsumme im Ziel stimmt nicht überein.")
                            os.link(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                            os.unlink(temporary, dir_fd=parent)
                            os.fsync(parent)
                            count += 1
                        finally:
                            os.close(parent)
                finally:
                    os.close(src_parent)
        finally:
            os.close(destination_fd)
    finally:
        os.close(root_fd)
        os.close(source_fd)
    return {"rows": [{"name": "Geprüft kopierte Dateien", "value": str(count)}, {"name": "Rettungsordner", "value": plan["folder"]}], "note": "Kopie mit SHA-256 verifiziert. Originale unverändert. Keine Datenbanksicherung und keine Übernahme von Eigentümer, Rechten oder Zeitstempeln."}
