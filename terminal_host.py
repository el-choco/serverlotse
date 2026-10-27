"""Interactive Linux PTYs. No SSH, TCP listener, output history or command log."""
import base64
import os
import secrets
import signal
import subprocess
import sys
import threading
import time

LOCK = threading.RLock()
SESSIONS = {}
PREVIEWS = {}
LIMIT = 512 * 1024
IDLE = 900
LIFETIME = 14400


def dimensions(data):
    cols, rows = int(data.get('cols', 100)), int(data.get('rows', 30))
    if not 20 <= cols <= 400 or not 5 <= rows <= 150:
        raise ValueError('Ungültige Terminalgröße.')
    return cols, rows


def event(ident, status):
    import admin_core as core
    with core.db() as db:
        db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',
                   (secrets.token_hex(16), time.time(), 'terminal', '{}', status, 'Terminal '+ident[:8]+': '+status))


class Session:
    def __init__(self, owner, cols, rows):
        import pty
        self.owner = owner
        self.ident = secrets.token_urlsafe(32)
        self.born = self.active = self.seen = time.monotonic()
        self.buffer = bytearray()
        self.offset = 0
        self.closed = False
        self.lock = threading.RLock()
        self.master, slave = pty.openpty()
        self.process = None
        try:
            self.resize(cols, rows)
            self.process = subprocess.Popen([sys.executable, os.path.abspath(__file__), '--child', str(slave)],
                pass_fds=(slave,), start_new_session=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={**os.environ, 'TERM':'xterm-256color', 'COLORTERM':'truecolor', 'HOME':'/root',
                     'USER':'root', 'LOGNAME':'root', 'HISTFILE':'/dev/null', 'SHELL':'/bin/bash'})
        except Exception:
            os.close(self.master)
            raise
        finally:
            os.close(slave)
        os.set_blocking(self.master, False)
        threading.Thread(target=self.reader, daemon=True).start()

    def resize(self, cols, rows):
        import fcntl
        import struct
        import termios
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))

    def reader(self):
        import select
        try:
            while not self.closed:
                if select.select([self.master], [], [], .2)[0]:
                    try: raw = os.read(self.master, 32768)
                    except BlockingIOError: continue
                    if not raw: break
                    with self.lock:
                        self.buffer.extend(raw)
                        excess = max(0, len(self.buffer)-LIMIT)
                        if excess:
                            del self.buffer[:excess]
                            self.offset += excess
        except OSError:
            pass
        finally:
            self.close()

    def close(self):
        with self.lock:
            if self.closed: return
            self.closed = True
            try: os.close(self.master)  # Hang up controlling TTY, including foreground jobs.
            except OSError: pass
            if self.process:
                try: os.killpg(self.process.pid, signal.SIGHUP)
                except ProcessLookupError: pass
                try: self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try: os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    self.process.wait(timeout=2)
            event(self.ident, 'closed')


def reap():
    now = time.monotonic()
    for ident, session in list(SESSIONS.items()):
        if now-session.active > IDLE or now-session.born > LIFETIME or now-session.seen > 60:
            session.close()
            del SESSIONS[ident]


def maintenance():
    while True:
        time.sleep(5)
        with LOCK: reap()


def count():
    with LOCK:
        return sum(not session.closed for session in SESSIONS.values())


def request(data):
    import admin_core as core
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Das interaktive Host-Terminal benötigt Linux und den aktualisierten Root-Helfer.')
    owner = data.get('owner', '')
    if not isinstance(owner, str) or len(owner) != 64: raise ValueError('Ungültige Terminalsitzung.')
    action = data.get('action')
    with LOCK:
        reap()
        now = time.monotonic()
        for key, (_, deadline) in list(PREVIEWS.items()):
            if now > deadline: del PREVIEWS[key]
        if action == 'prepare':
            if len(PREVIEWS) >= 20: raise ValueError('Zu viele Terminalanfragen.')
            nonce = secrets.token_urlsafe(32)
            PREVIEWS[nonce] = (owner, now+60)
            return {'nonce':nonce}
        if action == 'start':
            cols, rows = dimensions(data)
            preview = PREVIEWS.pop(str(data.get('nonce', '')), None)
            if not preview or preview[0] != owner or preview[1] < now or data.get('confirmation') != 'ROOT':
                raise ValueError('Terminalbestätigung ungültig oder abgelaufen.')
            if core.MUTEX.locked() or core.POWER_UNTIL > time.time():
                raise ValueError('Eine Host-Aktion läuft bereits. Bitte Abschluss abwarten.')
            if len(SESSIONS) >= 2: raise ValueError('Maximal zwei Terminalsitzungen gleichzeitig.')
            session = Session(owner, cols, rows)
            SESSIONS[session.ident] = session
            event(session.ident, 'opened')
            return {'id':session.ident}
        session = SESSIONS.get(str(data.get('id', '')))
        if not session or session.owner != owner: raise ValueError('Terminalsitzung nicht mehr verfügbar.')
        session.seen = now
        if action == 'close':
            session.close(); del SESSIONS[session.ident]
            return {'closed':True}
        with session.lock:
            if action == 'poll':
                cursor = int(data.get('cursor', 0))
                end = session.offset + len(session.buffer)
                if cursor < 0 or cursor > end: raise ValueError('Ungültige Terminalposition.')
                start = max(cursor, session.offset)
                raw = bytes(session.buffer[start-session.offset:start-session.offset+32768])
                return {'data':base64.b64encode(raw).decode(), 'cursor':start+len(raw),
                        'lost':cursor < session.offset, 'closed':session.closed and start+len(raw) == end}
            if session.closed: raise ValueError('Terminalsitzung beendet.')
            if action == 'input':
                raw = base64.b64decode(data.get('data', ''), validate=True)
                if not 0 < len(raw) <= 4096: raise ValueError('Terminaleingabe zu groß.')
                # Nonblocking, acknowledge actual bytes so the browser can retry the remainder.
                try: count = os.write(session.master, raw)
                except BlockingIOError: count = 0
                session.active = now
                return {'written':count}
            if action == 'resize':
                session.resize(*dimensions(data)); return {'ok':True}
        raise ValueError('Unbekannte Terminalaktion.')


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--child':
    import fcntl
    import termios
    fd = int(sys.argv[2])
    fcntl.ioctl(fd, termios.TIOCSCTTY, 0)
    for target in (0, 1, 2): os.dup2(fd, target)
    if fd > 2: os.close(fd)
    os.chdir('/root')
    os.execv('/bin/bash', ['bash', '-il'])
