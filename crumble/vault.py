"""The memory vault: the server's own durable copy of every chat's memory.

Before this, the memory lived only in the browser's copy of the chat and was written to disk by whatever the page sent. A cleared browser, a
second device, a failed save or a crash in the middle of a write could erase it, with no copy anywhere. Now the server keeps one per
(owner, chat, character) under data/memory/:

    <key>.json            the memory (mem + chronicle + keeper), with a checksum
    <key>.json.bak1..4    rolling backups of earlier good versions
    <key>.journal.jsonl   an append-only log of what changed (an audit trail, never read back automatically)
    data/trash/           what was retired on purpose (a deleted chat's memory); nothing is ever unlinked

Writes are atomic (temp file, fsync, rename), so a crash leaves either the old or the new file, never half of one. A file that fails its
checksum or does not parse is set aside as *.corrupt-<time> and the newest backup that verifies is used instead. The page's copy and
the vault's copy are merged item by item, so an empty or stale page can never wipe memory; only a deliberate deletion (a tombstone) removes one.
"""
import copy
import hashlib
import json
import os
import re
import shutil
import threading
import time

from .config import ROOT

DIR = ROOT / "data" / "memory"
TRASH = ROOT / "data" / "trash"
BACKUPS = 4
BAK_EVERY_S = 20
_LOCK = threading.RLock()


def key(owner, chat_id, char_id):
    """A filesystem-safe vault key. owner is 'host' or a guest's id."""
    clean = lambda x: re.sub(r"[^\w-]", "_", str(x or "x"))[:60]
    return f"{clean(owner or 'host')}__{clean(chat_id)}__{clean(char_id)}"


def _p(k):
    DIR.mkdir(parents=True, exist_ok=True)
    return DIR / f"{k}.json"


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read(path):
    """-> (payload, None) if the file is whole and its checksum agrees, else (None, reason)."""
    try:
        env = json.loads(path.read_text(encoding="utf-8"))
        payload = env["data"]
        if env.get("sha") != _digest(payload):
            return None, "checksum mismatch"
        return payload, None
    except FileNotFoundError:
        return None, "missing"
    except Exception as e:
        return None, f"unreadable: {e}"


def atomic_write(path, text):
    """Write so that a crash leaves the old file or the new one, never a torn one."""
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _rotate(path):
    b1 = path.with_name(path.name + ".bak1")
    if not path.exists() or _read(path)[0] is None:
        return                                     # never promote a damaged file to a backup
    if b1.exists() and time.time() - b1.stat().st_mtime < BAK_EVERY_S:
        return
    for n in range(BACKUPS, 1, -1):
        src = path.with_name(path.name + f".bak{n - 1}")
        if src.exists():
            os.replace(src, path.with_name(path.name + f".bak{n}"))
    shutil.copy2(path, b1)


def load(k):
    """The newest good version of this memory, or None. A damaged file is set aside (kept), never deleted or overwritten blindly."""
    with _LOCK:
        path = _p(k)
        payload, why = _read(path)
        if payload is not None:
            return payload
        if why != "missing":
            try:
                os.replace(path, path.with_name(path.name + f".corrupt-{int(time.time())}"))
            except OSError:
                pass
        for n in range(1, BACKUPS + 1):
            payload, _ = _read(path.with_name(path.name + f".bak{n}"))
            if payload is not None:
                return payload
        return None


def save(k, mem=None, chron=None, keep=None):
    """Merge into the vault (never replace blindly) and write atomically. -> the stored payload."""
    with _LOCK:
        cur = load(k) or {}
        out = {"mem": cur.get("mem"), "chron": cur.get("chron"), "keep": cur.get("keep")}
        if isinstance(mem, dict):
            out["mem"] = merge_mem(mem, cur.get("mem"))
        if isinstance(chron, dict) and (not isinstance(out["chron"], dict) or chron.get("covered", 0) >= out["chron"].get("covered", 0)):
            out["chron"] = copy.deepcopy(chron)
        if isinstance(keep, dict) and (not isinstance(out["keep"], dict) or _keep_size(keep) >= _keep_size(out["keep"])):
            out["keep"] = copy.deepcopy(keep)
        out["saved"] = int(time.time() * 1000)
        path = _p(k)
        _rotate(path)
        atomic_write(path, json.dumps({"v": 1, "sha": _digest(out), "data": out}, ensure_ascii=False))
        _journal(k, cur.get("mem"), out["mem"])
        return out


def _keep_size(k):
    return len(json.dumps(k, ensure_ascii=False)) if isinstance(k, dict) else 0


def _journal(k, before, after):
    try:
        b = {i["id"] for i in (before or {}).get("items", [])}
        a = {i["id"] for i in (after or {}).get("items", [])}
        if a == b and (before or {}).get("rev") == (after or {}).get("rev"):
            return
        f = DIR / f"{k}.journal.jsonl"
        if f.exists() and f.stat().st_size > 1_000_000:
            os.replace(f, f.with_name(f.name + ".old"))
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": int(time.time()), "rev": (after or {}).get("rev"), "added": sorted(a - b)[:40], "removed": sorted(b - a)[:40]}) + "\n")
    except Exception:
        pass


# ---- merging the page's copy with the vault's ----
def merge_mem(a, b, turns=None):
    """Item-level merge of two copies of one memory store. a = the newer-looking copy (the page's), b = the other (the vault's).
    An item missing from one side is kept unless it was deliberately deleted (tombstone) or, with `turns`, it comes from a message that no longer exists."""
    if not isinstance(a, dict) and not isinstance(b, dict):
        return {}
    if not isinstance(b, dict):
        return copy.deepcopy(a)
    if not isinstance(a, dict):
        a = {}
    if not a:
        return copy.deepcopy(b) if turns is None else _clip_turns(copy.deepcopy(b), turns)
    if a.get("rev", 0) >= b.get("rev", 0):
        base, other = copy.deepcopy(a), b
    else:
        base, other = copy.deepcopy(b), a
    tomb = set(a.get("tomb") or []) | set(b.get("tomb") or [])
    items, seen = {}, {}
    for src in (base, other):
        for i in src.get("items", []):
            if not isinstance(i, dict) or i.get("id") in tomb:
                continue
            if turns is not None and src is other and i.get("turn", 0) > turns:
                continue
            cur = items.get(i["id"])
            if cur is None:
                items[i["id"]] = copy.deepcopy(i)
            elif cur.get("text") != i.get("text") and cur.get("ver", 1) == i.get("ver", 1) and cur.get("upd") == i.get("upd"):
                base["seq"] = max(base.get("seq", 0), other.get("seq", 0)) + 1       # the same id was minted twice for different memories: keep both
                j = copy.deepcopy(i)
                j["id"] = f"{i['t'][0]}{base['seq']}"
                items[j["id"]] = j
            elif (i.get("ver", 1), i.get("upd", 0)) > (cur.get("ver", 1), cur.get("upd", 0)):
                items[i["id"]] = copy.deepcopy(i)
    base["items"] = sorted(items.values(), key=lambda i: (i.get("turn", 0), i.get("ts", 0)))
    base["tomb"] = sorted(tomb)[-800:]
    base["seq"] = max(a.get("seq", 0), b.get("seq", 0), base.get("seq", 0))
    base["rev"] = max(a.get("rev", 0), b.get("rev", 0))
    ents = {}
    for src in (other, base):
        for k, e in (src.get("ents") or {}).items():
            if k not in ents or e.get("n", 0) >= ents[k].get("n", 0):
                ents[k] = copy.deepcopy(e)
    base["ents"] = ents
    rels, seen_r = [], set()
    for r in (base.get("rels") or []) + (other.get("rels") or []):
        kk = (r.get("a"), r.get("b"), r.get("rel"), r.get("from"))
        if kk not in seen_r:
            seen_r.add(kk)
            rels.append(r)
    base["rels"] = rels[-160:]
    arch, seen_a = [], set()
    for r in (base.get("archive") or []) + (other.get("archive") or []):
        kk = (r.get("id"), r.get("at"))
        if kk not in seen_a:
            seen_a.add(kk)
            arch.append(r)
    base["archive"] = arch[-500:]
    return base


def _clip_turns(m, turns):
    m["items"] = [i for i in m.get("items", []) if i.get("turn", 0) <= turns]
    return m


def restore_into(k, state, turns=None):
    """Bring back what the page's state is missing. Mutates state. -> {"items": n memories brought back, "chron": bool, "keep": bool}"""
    v = load(k)
    out = {"items": 0, "chron": False, "keep": False}
    if not v:
        return out
    cur = state.get("mem") if isinstance(state.get("mem"), dict) else None
    before = {i.get("id") for i in (cur or {}).get("items", [])}
    if isinstance(v.get("mem"), dict):
        merged = merge_mem(cur or {}, v["mem"], turns)
        state["mem"] = merged
        out["items"] = len({i["id"] for i in merged.get("items", [])} - before)
    c = v.get("chron")
    if isinstance(c, dict) and (not isinstance(state.get("chron"), dict) or c.get("covered", 0) > state["chron"].get("covered", 0)) and (turns is None or c.get("covered", 0) <= turns):
        state["chron"], out["chron"] = copy.deepcopy(c), True
    kp = v.get("keep")
    if isinstance(kp, dict) and not isinstance(state.get("keep"), dict):
        state["keep"], out["keep"] = copy.deepcopy(kp), True
    return out


def protect_state(owner, chat_id, cid, state, turns=None):
    """Called when the page saves a chat: make sure a stale or empty page cannot clobber the vault, and keep the vault current.
    Handles one-to-one chats (state.mem) and groups (state.members[id].mem). Mutates and returns state."""
    if not isinstance(state, dict) or not chat_id:
        return state
    try:
        if isinstance(state.get("members"), dict):
            for mid, ms in state["members"].items():
                if isinstance(ms, dict):
                    k = key(owner, chat_id, mid)
                    restore_into(k, ms, turns)
                    if isinstance(ms.get("mem"), dict):
                        save(k, mem=ms["mem"], chron=ms.get("chron"), keep=ms.get("keep"))
        else:
            k = key(owner, chat_id, cid)
            restore_into(k, state, turns)
            if isinstance(state.get("mem"), dict):
                save(k, mem=state["mem"], chron=state.get("chron"), keep=state.get("keep"))
    except Exception:
        pass          # the vault must never stop a chat from being saved
    return state


# ---- safety net ----
def retire(owner, chat_id):
    """A chat was deleted on purpose: move its memory files to data/trash instead of destroying them."""
    clean = lambda x: re.sub(r"[^\w-]", "_", str(x or "x"))[:60]
    prefix = f"{clean(owner or 'host')}__{clean(chat_id)}__"
    TRASH.mkdir(parents=True, exist_ok=True)
    n = 0
    with _LOCK:
        if DIR.exists():
            for f in list(DIR.glob(prefix + "*")):
                os.replace(f, TRASH / f"{int(time.time())}-{f.name}")
                n += 1
    return n


def backups(k):
    p = _p(k)
    return [{"n": n, "ok": _read(p.with_name(p.name + f".bak{n}"))[0] is not None} for n in range(1, BACKUPS + 1) if p.with_name(p.name + f".bak{n}").exists()]


def restore_backup(k, n=1):
    """Roll the vault back to backup n (the current file is itself kept as a corrupt-/pre-restore copy first)."""
    with _LOCK:
        p = _p(k)
        src = p.with_name(p.name + f".bak{int(n)}")
        payload, why = _read(src)
        if payload is None:
            return False
        if p.exists():
            shutil.copy2(p, p.with_name(p.name + f".pre-restore-{int(time.time())}"))
        atomic_write(p, json.dumps({"v": 1, "sha": _digest(payload), "data": payload}, ensure_ascii=False))
        return True
