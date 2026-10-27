import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import subprocess
import threading
import time

KEY=os.getenv("SERVERLOTSE_TOKEN", "")
ENABLED=os.getenv("HOST_CONTROL_ENABLED", "0")=="1"
PENDING={}
GUARD=threading.Lock()
CONFIRM={"reboot":"REBOOT", "shutdown":"SHUTDOWN"}


def dbus(method,*arguments):
    command=["dbus-send","--system","--print-reply","--reply-timeout=8000","--dest=org.freedesktop.login1","/org/freedesktop/login1","org.freedesktop.login1.Manager."+method,*arguments]
    result=subprocess.run(command,capture_output=True,text=True,timeout=10,check=False)
    if result.returncode:raise ValueError("Host-Steuerung nicht erreichbar oder nicht erlaubt. D-Bus und systemd-logind prüfen.")
    return result.stdout


def capabilities():
    if not ENABLED:return {"enabled":False,"reboot":False,"shutdown":False}
    return {"enabled":True,"reboot":'string "yes"' in dbus("CanReboot"),"shutdown":'string "yes"' in dbus("CanPowerOff")}


def prepare(action):
    if action not in CONFIRM or not ENABLED:raise ValueError("Host-Aktion nicht freigeschaltet.")
    if not capabilities().get(action):raise ValueError("Host-Aktion nicht erlaubt oder nicht verfügbar.")
    with GUARD:
        for nonce,item in list(PENDING.items()):
            if item["expires"]<time.time():del PENDING[nonce]
        if len(PENDING)>=20:raise ValueError("Zu viele offene Bestätigungen. Bitte eine Minute warten.")
        nonce=secrets.token_hex(24);PENDING[nonce]={"action":action,"expires":time.time()+60}
    return {"nonce":nonce,"action":action,"confirmation":CONFIRM[action],"expires_in":60}


def execute(data):
    action=data.get("action")
    if not ENABLED or action not in CONFIRM or data.get("confirmation")!=CONFIRM[action]:raise ValueError("Host-Aktion muss ausdrücklich bestätigt werden.")
    with GUARD:
        item=PENDING.pop(data.get("nonce",""),None)
        if not item or item["action"]!=action or item["expires"]<time.time():raise ValueError("Bestätigung abgelaufen oder bereits verwendet.")
        PENDING.clear();scheduled=int(time.time())+15
        dbus("ScheduleShutdown","string:"+("reboot" if action=="reboot" else "poweroff"),"uint64:"+str(scheduled*1000000))
    return {"accepted":True,"action":action,"scheduled":scheduled,"note":"Host-Aktion angenommen. Der Server wird in etwa 15 Sekunden heruntergefahren. Dies bestätigt noch nicht den erfolgreichen Abschluss."}


class Control(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(12)

    def respond(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)

    def allowed(self):
        return bool(KEY and hmac.compare_digest(self.headers.get("Authorization","").encode(),("Bearer "+KEY).encode()))

    def do_GET(self):
        if not self.allowed():return self.respond(401,{"error":"Nicht autorisiert"})
        if self.path!="/status":return self.respond(404,{"error":"Nicht gefunden"})
        try:self.respond(200,capabilities())
        except (OSError,ValueError,subprocess.TimeoutExpired):self.respond(503,{"error":"Host-Steuerung nicht erreichbar oder nicht erlaubt. D-Bus und systemd-logind prüfen."})

    def do_POST(self):
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=4096:raise ValueError("Ungültige Anfragegröße")
            raw=self.rfile.read(length)
            if not self.allowed():return self.respond(401,{"error":"Nicht autorisiert"})
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError("Ungültige Host-Aktion")
            if self.path=="/prepare":result=prepare(data.get("action"))
            elif self.path=="/execute":result=execute(data)
            else:return self.respond(404,{"error":"Nicht gefunden"})
            self.respond(200,result)
        except (ValueError,TypeError) as exc:self.respond(400,{"error":str(exc)})
        except (OSError,subprocess.TimeoutExpired):self.respond(503,{"error":"Host-Steuerung nicht erreichbar oder nicht erlaubt. D-Bus und systemd-logind prüfen."})


if __name__=="__main__":
    if len(KEY)<24:raise SystemExit("SERVERLOTSE_TOKEN fehlt")
    ThreadingHTTPServer(("0.0.0.0",8110),Control).serve_forever()
