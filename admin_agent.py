import hmac
import json
import os
from pathlib import Path
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler
import admin_core as core
import sensors
import automation
import terminal_host
import guardian
import docker_tools

TOKEN_FILE = Path(os.getenv("SERVERLOTSE_TOKEN_FILE", "/etc/serverlotse/admin.token"))
SOCKET = os.getenv("SERVERLOTSE_ADMIN_SOCKET", "/run/serverlotse-admin/agent.sock")
READ_LIMIT = threading.BoundedSemaphore(3)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def setup(self):
        super().setup(); self.connection.settimeout(15)
    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        if self.path not in {"/read", "/prepare", "/execute", "/terminal"}: return self.reply(404, {"error": "Nicht gefunden"})
        try:
            token = TOKEN_FILE.read_text().strip()
            if len(token) < 24 or not hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer "+token).encode()):
                return self.reply(401, {"error": "Ungültiger Zugangsschlüssel"})
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 64000: raise ValueError("Ungültige Anfragegröße")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError("Ungültige Anfrage")
            if not READ_LIMIT.acquire(blocking=False): return self.reply(429, {"error": "Host-Helfer ist beschäftigt."})
            try:
                result = {"/read": core.read, "/prepare": core.prepare, "/execute": core.execute, "/terminal": terminal_host.request}[self.path](data)
                return self.reply(200, result)
            finally: READ_LIMIT.release()
        except (ValueError, TypeError, KeyError, OSError) as exc:
            return self.reply(400, {"error": str(exc)})


class UnixHTTP(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def scheduler():
    while True:
        time.sleep(30)
        try: core.schedule_tick()
        except Exception: pass


if __name__ == "__main__":
    os.umask(0o077)
    core.initialize()
    parent = Path(SOCKET).parent; parent.mkdir(mode=0o700, exist_ok=True)
    path = Path(SOCKET)
    if path.exists(): path.unlink()
    with UnixHTTP(SOCKET, Handler) as http:
        path.chmod(0o600)
        threading.Thread(target=scheduler, daemon=True).start()
        threading.Thread(target=sensors.monitor, daemon=True).start()
        threading.Thread(target=automation.loop, daemon=True).start()
        threading.Thread(target=terminal_host.maintenance, daemon=True).start()
        threading.Thread(target=guardian.loop, daemon=True).start()
        threading.Thread(target=guardian.process_loop, daemon=True).start()
        threading.Thread(target=docker_tools.monitor, daemon=True).start()
        import network_extras
        threading.Thread(target=network_extras.loop, daemon=True).start()
        http.serve_forever()
