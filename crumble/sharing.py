"""Hosting for other people: guest sessions, password, queue, LAN addresses."""
import socket
import threading

from .config import ROOT
from .storage import rj, wj

SESSF, SHAREF = ROOT/"data"/"sessions.json", ROOT/"data"/"share.json"
SHARE = {"on": False, "listen": False, "password": "", "port": 8000, "max": 8}
SESS = {k: dict(v, busy=False) for k, v in (rj(SESSF, {}) or {}).items()}  # session id -> {uid, name, seen}
FAILS, QUEUE, QL = {}, {"n": 0}, threading.Lock()
LOCAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
FWD = ("X-Forwarded-For", "Forwarded", "CF-Connecting-IP", "X-Real-IP", "Via", "X-Forwarded-Host")
MAX_BODY, MAX_QUEUE = 3_000_000, 12


def save_share():
    wj(SHAREF, {"password": SHARE["password"], "max": SHARE["max"]})
    wj(SESSF, {k: {x: v[x] for x in ("uid", "name", "seen")} for k, v in SESS.items()})


def my_ips():
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        ips.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except Exception:
        pass
    return ips


MYIPS = my_ips()


def lan_urls(port):
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; this just reveals the outgoing interface
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        ips.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except Exception:
        pass
    return [f"http://{ip}:{port}" for ip in sorted(ips) if not ip.startswith("127.")]
