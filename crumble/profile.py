"""Who you are: your name, a few lines about you, your stats, skills and gear.

These used to live only in the browser (localStorage), so a new browser, a cleared cache or a different address (a share link changes
every time) started again as "User". Now the host keeps them in data/profiles/<owner>.json and the page loads them at start and saves
them as you type. The host is "host"; each guest has their own file (by the guest's id), so nobody reads or overwrites anybody else's.
"""
import json
import re

from .config import ROOT
from .storage import rj, wj

FIELDS = {"uname": 60, "persona": 4000, "ustats": 200, "ugear": 400, "uskills": 2000}


def _file(a):
    who = "host" if (a or {}).get("role") == "admin" else re.sub(r"\W", "", str((a or {}).get("uid") or "")) or ""
    return (ROOT / "data" / "profiles" / f"{who}.json") if who else None


def clean(b):
    """Only the known fields, as short plain text (a missing field is simply absent, so it never wipes what is saved)."""
    b = b if isinstance(b, dict) else {}
    return {k: str(b[k]).replace("\r", "")[:n] for k, n in FIELDS.items() if k in b and b[k] is not None}


def load(a):
    f = _file(a)
    return clean(rj(f, {})) if f else {}


def save(a, b):
    """Merge what the page sent into the saved profile and return the whole profile."""
    f = _file(a)
    if not f:
        return {}
    cur = load(a)
    cur.update(clean(b))
    f.parent.mkdir(parents=True, exist_ok=True)
    wj(f, cur)
    return cur


# ---------------------------------------------------------------- settings (the page's U options and P sampling values)
MAX_SETTINGS = 200_000      # bytes of JSON per owner


def _sfile(a):
    f = _file(a)
    return f.with_name(f.stem + ".settings.json") if f else None


def _plain(d, depth=0):
    """Only JSON-plain values (text, numbers, booleans, lists and objects of those), bounded: the page is trusted with nothing else."""
    if isinstance(d, bool) or d is None or isinstance(d, (int, float)):
        return d
    if isinstance(d, str):
        return d[:20000]
    if depth > 4:
        return None
    if isinstance(d, list):
        return [_plain(x, depth + 1) for x in d[:200]]
    if isinstance(d, dict):
        return {str(k)[:60]: _plain(v, depth + 1) for k, v in list(d.items())[:300]}
    return None


def load_settings(a):
    f = _sfile(a)
    j = rj(f, {}) if f else {}
    return {"U": _plain(j.get("U")) if isinstance(j.get("U"), dict) else {}, "P": _plain(j.get("P")) if isinstance(j.get("P"), dict) else {}}


def save_settings(a, b):
    f = _sfile(a)
    if not f:
        return {"U": {}, "P": {}}
    b = b if isinstance(b, dict) else {}
    out = {"U": _plain(b.get("U")) if isinstance(b.get("U"), dict) else {}, "P": _plain(b.get("P")) if isinstance(b.get("P"), dict) else {}}
    if len(json.dumps(out)) > MAX_SETTINGS:
        return load_settings(a)
    f.parent.mkdir(parents=True, exist_ok=True)
    wj(f, out)
    return out
