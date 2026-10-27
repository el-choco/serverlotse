import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
from urllib.parse import parse_qs, urlsplit
from toolkit import redact


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(8)
        self.sock.connect("/var/run/docker.sock")


def docker(path):
    conn = UnixConnection("localhost")
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024 or response.status != 200:
            raise ValueError("Docker-Antwort zu groß oder nicht erfolgreich")
        return raw
    finally:
        conn.close()


def decode_logs(raw):
    chunks, offset = [], 0
    while offset + 8 <= len(raw) and raw[offset] in (0, 1, 2) and raw[offset + 1:offset + 4] == b"\0\0\0":
        size = int.from_bytes(raw[offset + 4:offset + 8], "big")
        chunks.append(raw[offset + 8:offset + 8 + size])
        offset += 8 + size
    return (b"".join(chunks) if chunks else raw).decode(errors="replace")[-200000:]


class Reader(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/containers":
                containers = json.loads(docker("/containers/json?all=1"))
                rows = [{"id": c["Id"], "name": ", ".join(n.lstrip("/") for n in c.get("Names", [])), "image": c.get("Image", ""), "value": c.get("Status", ""), "state": c.get("State", ""), "mounts": "; ".join(f"{m.get('Source', '?')} → {m.get('Destination', '?')}" for m in c.get("Mounts", []))} for c in containers[:500]]
                result = {"rows": rows, "note": "Docker-Leseansicht. Kein Starten, Stoppen, Exec oder Ändern. 'Up' allein bestätigt keine Anwendungsfunktion."}
            elif parsed.path == "/logs":
                identifier = parse_qs(parsed.query).get("id", [""])[0]
                if not re.fullmatch(r"[a-f0-9]{64}", identifier):
                    raise ValueError("Ungültige Container-ID")
                text = decode_logs(docker(f"/containers/{identifier}/logs?stdout=1&stderr=1&tail=150&timestamps=1"))
                result = {"text": redact(text), "rows": [], "note": "Letzte 150 Logzeilen, maximal 200.000 Zeichen. Geheimnisse werden bestmöglich maskiert."}
            else:
                self.send_error(404)
                return
            raw = json.dumps(result).encode()
            self.send_response(200)
        except Exception:
            raw = json.dumps({"error": "Docker-Lesezugriff fehlgeschlagen. Socket, Logging-Treiber und Container-ID prüfen."}).encode()
            self.send_response(502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8100), Reader).serve_forever()
