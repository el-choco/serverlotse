"""Container-to-host relay; only the private Unix socket is reachable."""
import http.client
import json
import os
import socket


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        if not hasattr(socket, "AF_UNIX"):
            raise OSError("Unix-Sockets benötigen Linux.")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(os.getenv("SERVERLOTSE_ADMIN_SOCKET", "/admin/agent.sock"))


def request(endpoint, data, token):
    if endpoint not in {"/read", "/prepare", "/execute", "/terminal"}: raise ValueError("Unbekannte Verwaltungsaktion.")
    connection = UnixConnection("localhost", timeout=110)
    try:
        connection.request("POST", endpoint, json.dumps(data), {"Authorization": "Bearer "+token, "Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(2_500_001)
        if len(raw) > 2_500_000: raise ValueError("Host-Ausgabe zu groß.")
        body = json.loads(raw)
        if response.status != 200: raise ValueError(body.get("error", "Host-Helfer meldet einen Fehler."))
        return body
    except (OSError, http.client.HTTPException):
        raise ValueError("Host-Verwaltung ist nicht erreichbar. docker compose up -d --build starten und die host-bootstrap-Logs prüfen.") from None
    finally: connection.close()
