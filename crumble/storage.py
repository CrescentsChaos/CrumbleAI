"""Reading and writing characters, groups and chats on disk."""
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

from .config import CHARS, CHATS, GROUPS, KEYS


def rj(p, default=None):
    """Read JSON. A file that is damaged (a crash mid-write on an older version) is set aside and the last good backup is used,
    instead of the chat silently turning into an empty one that the next save would overwrite."""
    p = Path(p)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:
        pass
    for n in (1, 2):
        try:
            j = json.loads(p.with_name(p.name + f".bak{n}").read_text(encoding="utf-8"))
        except Exception:
            continue
        try:
            os.replace(p, p.with_name(p.name + f".corrupt-{int(time.time())}"))
        except OSError:
            pass
        return j
    return default


def wj(p, obj):
    """Write JSON atomically (temp file, fsync, rename) and keep the previous good version as .bak1/.bak2 (at most one rotation per 30 s)."""
    p = Path(p)
    text = json.dumps(obj, indent=1, ensure_ascii=False)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    if p.exists() and p.suffix == ".json" and p.parent.parent.name == "chats":
        b1 = p.with_name(p.name + ".bak1")
        try:
            json.loads(p.read_text(encoding="utf-8"))
            if not b1.exists() or time.time() - b1.stat().st_mtime > 30:
                if b1.exists():
                    os.replace(b1, p.with_name(p.name + ".bak2"))
                shutil.copy2(p, b1)
        except Exception:
            pass
    os.replace(tmp, p)


def slug(s):
    return re.sub(r"\W+", "_", s or "").strip("_").lower() or uuid.uuid4().hex[:8]


def from_card(j, stem):
    """A Tavern card V2 (as dropped straight into data/characters) -> Crumble's flat character format."""
    d = j.get("data") if isinstance(j.get("data"), dict) else j
    x = (d.get("extensions") or {}).get("hearth") or {}
    c = {k: "" for k in KEYS}
    c.update({k: str(v) for k, v in x.items() if k in KEYS})
    c.update(name=d.get("name") or stem, description=d.get("description", ""), personality=d.get("personality", ""),
             scenario=d.get("scenario", ""), first_mes=d.get("first_mes", ""), mes_example=d.get("mes_example", ""),
             system_prompt=d.get("system_prompt", ""), post_history=d.get("post_history_instructions", ""),
             notes=d.get("creator_notes", ""), alts="\n---\n".join(d.get("alternate_greetings") or []),
             tags=", ".join(d.get("tags") or []))
    c["lore"] = [{"keys": ", ".join(e.get("keys") or []), "content": e.get("content", "")}
                 for e in (d.get("character_book") or {}).get("entries", [])]
    c["avatar"] = x.get("avatar", "")
    c["id"] = slug(stem)
    return c


def load_chars():
    out = []
    for f in sorted(CHARS.glob("*.json")):
        j = rj(f)
        if not isinstance(j, dict):
            continue
        if not j.get("id") or isinstance(j.get("data"), dict):  # a raw card: convert it once, keep the original as .bak
            c = from_card(j, f.stem)
            if (CHARS/f"{c['id']}.json").exists() and (CHARS/f"{c['id']}.json") != f:
                c["id"] += "_" + uuid.uuid4().hex[:4]
            wj(CHARS/f"{c['id']}.json", c)
            if f.name != f"{c['id']}.json":
                f.replace(f.with_suffix(".json.bak"))
            j = c
        out.append(j)
    return out


def cdir(cid, make=True):
    d = CHATS/cid
    old = CHATS/f"{cid}.json"
    if make:
        d.mkdir(parents=True, exist_ok=True)
        if old.exists():  # migrate the single-chat file from the first version
            wj(d/"main.json", {"id": "main", "title": "Chat 1", "updated": old.stat().st_mtime, "history": rj(old, [])})
            old.unlink()
    return d


def chat_list(cid):
    if (CHATS/f"{cid}.json").exists():
        cdir(cid)
    out = []
    for f in (CHATS/cid).glob("*.json"):
        c = rj(f)
        if c:
            out.append({"id": c["id"], "title": c.get("title") or "New chat",
                        "updated": c.get("updated", 0), "n": len(c.get("history", []))})
    return sorted(out, key=lambda x: -x["updated"])


PUBLIC = ("name", "tags", "description", "first_mes", "alts", "gender", "age", "occupation")  # all a guest may see of a character


def pub(c):
    """A character as guests see it: enough to pick and greet, never the prompt, secrets or backstory."""
    out = {k: (c.get(k, "") if k in PUBLIC else "") for k in KEYS}
    out.update(id=c["id"], avatar=c.get("avatar", ""), lore=[], start_place=c.get("start_place", ""))
    return out


def get_char(cid):
    return next((c for c in load_chars() if c["id"] == cid), None)


def load_groups():
    out = []
    for f in sorted(GROUPS.glob("*.json")):
        j = rj(f)
        if isinstance(j, dict) and j.get("id"):
            out.append(j)
    return out


def get_group(gid):
    if str(gid or "").startswith("pl_"):      # a visit to a place: the place card is the group (nothing is stored for it, only its chats)
        from . import places
        return places.scene_group(gid)
    return rj(GROUPS/f"{gid}.json") if re.fullmatch(r"\w+", str(gid or "")) else None


def group_members(g):
    return [c for c in (get_char(i) for i in g.get("members", [])) if c]
