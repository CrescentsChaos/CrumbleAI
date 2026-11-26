"""Keeping the memory true over time: incremental ingest, conflict resolution, corroboration, closing promises, consolidation.

    ingest(st, hist, ...)     read every message not yet read (the chat is the source of truth, so an edit or a rewind is detected and undone)
    commit(m, cands, ...)     write candidates: duplicates strengthen each other, conflicts are resolved by source reliability and chronology
    consolidate(m, turn)      fold a pile of old minor episodes into one digest; the originals go to the archive, nothing is lost
    visible(item, viewer)     what a given character may know: a whisper reaches only those it was whispered to

Conflict rules (nothing is silently discarded):
    same source reliability or a more reliable newer one  -> the newer statement wins; the older one is kept, marked `outdated`, linked by `sup`
    a less reliable newer statement (hearsay vs the user's own words) -> it is stored as `uncertain`; the reliable one stands
    two claims that accuse each other                       -> both are kept and marked `disputed`, with who said which
    a first-hand account that matches an earlier hearsay    -> the hearsay becomes `confirmed`, with `confirmed_by`
"""
import hashlib
import re

from . import entities as en, extract as ex, lexicon as lx, store

CP_EVERY = 25
DONE_CUE = re.compile(r"(?i)\b(?:met|arrived|kept|paid|returned|went|came|brought|delivered|finished|fulfilled|completed|showed up|was there|were there|did it|done|made it|got there|waited)\b")
BROKEN_CUE = re.compile(r"(?i)\b(?:broke (?:my|your|the|his|her|their) (?:promise|word|oath)|forgot|didn'?t show|never came|never showed|didn'?t come|stood (?:me|you|us) up|failed to|backed out|abandoned)\b")


def fp(m):
    return hashlib.sha1(f"{m.get('role')}|{m.get('name') or ''}|{str(m.get('content') or '')}".encode("utf-8", "ignore")).hexdigest()[:10]


def chain(msgs, at=None):
    """{index: running hash of the chat up to there}. Standard checkpoints are every CP_EVERY-th message and the last one; `at` asks for given indices instead."""
    h, out = hashlib.sha1(), {}
    want = set(at) if at is not None else None
    for i, m in enumerate(msgs):
        h.update(fp(m).encode())
        if (want is not None and i in want) or (want is None and (i % CP_EVERY == CP_EVERY - 1 or i == len(msgs) - 1)):
            out[i] = h.hexdigest()[:10]
    return out


def visible(item, viewer):
    """A memory restricted to some people (a whisper, a confided secret) is only known to them."""
    kb = item.get("known_by") or []
    if not kb or not viewer:
        return True
    v = {en._key(viewer), en._key(str(viewer).split(" ")[0]), en._key(en.C)}
    return any(en._key(k) in v for k in kb)


# ---- rollback: the chat was rewound or an old message was edited ----
def rollback(m, k):
    """Undo everything learned from message k onward (rule-derived memories only: what the user wrote by hand or what the model wrote stays)."""
    gone = [i for i in m["items"] if i.get("msg", -1) >= k and i.get("src") == "rule"]
    ids = {i["id"] for i in gone}
    if ids:
        for i in m["items"]:
            if i.get("sup") in ids:                        # what the removed memory had replaced is current again
                i["status"] = "confirmed"
                i.pop("sup", None)
            if i.get("confirmed_by") in ids:
                i["status"] = "uncertain"
                i.pop("confirmed_by", None)
            if i.get("closed_by") in ids:
                i["open"] = True
                for key in ("closed_by", "closed_turn", "outcome"):
                    i.pop(key, None)
        store.remove(m, ids, why="chat rewound or edited")
    for r in m.get("rels", []):
        if r.get("to") is not None and r["to"] >= k:
            r["to"] = None
    m["rels"] = [r for r in m.get("rels", []) if r.get("from", 0) < k or r.get("src") != "rule"]
    return len(ids)


# ---- writing ----
def _real(name, user, char):
    return {en.U: user, en.C: char}.get(name, name)


def _link_feeling(m, cand, item, last_ep):
    if cand["layer"] == "emotional" and last_ep and last_ep.get("msg") == cand["msg"]:
        item["link"] = last_ep["id"]


def _supersede(m, old, new):
    old["status"] = "outdated"
    old["sup"] = new["id"]
    new.setdefault("hist", []).append({"text": old["text"], "status": "outdated", "turn": old.get("turn", 0), "ts": old.get("ts", 0), "why": "replaced by a later statement"})
    del new["hist"][:-6]
    store._bump(m, old)


def _resolve_slot(m, cand, item, created):
    """The same fact about the same person stated twice with different content."""
    if not cand.get("slot") or not created:
        return
    for old in m["items"]:
        if old is item or old.get("slot") != cand["slot"] or old.get("status") == "outdated":
            continue
        if store.similar(old["text"], item["text"]) >= .7:
            continue
        ro, rn = store.reliability(old.get("rsrc") or old.get("src")), store.reliability(cand["rsrc"])
        if rn >= ro:
            _supersede(m, old, item)
        else:
            item["status"] = "uncertain"
            item["rsrc"] = cand["rsrc"]


def _corroborate(m, item):
    """A first-hand account of something that was earlier only reported by someone else confirms the report."""
    if item.get("kind") in ("claim", "hypothetical") or item.get("status") not in (None, "confirmed"):
        return
    subj = {en._key(item.get("who", ""))} | {en._key(a) for a in item.get("about") or []}
    for c in m["items"]:
        if c.get("kind") == "claim" and c.get("status") == "uncertain" and c["id"] != item["id"] and c.get("msg", -1) < item.get("msg", 0):
            if subj & ({en._key(c.get("who", ""))} | {en._key(a) for a in c.get("about") or []}) and store.similar(c["text"], item["text"]) >= .34:
                c["status"] = "confirmed"
                c["confirmed_by"] = item["id"]
                store._bump(m, c)


def _dispute(m, item, cand):
    """'Garrick is lying' against what Garrick claimed: both stay, neither is believed on its own."""
    if item.get("kind") != "claim" or not ex.ACCUSE.search(cand.get("evid", "")):
        return
    for tgt in item.get("about") or []:
        for c in m["items"]:
            if c is not item and c.get("kind") == "claim" and en._key(c.get("who", "")) == en._key(tgt) and c.get("status") in ("uncertain", "confirmed") and c.get("msg", -1) < item.get("msg", 0):
                for x, y in ((c, item), (item, c)):
                    x["status"] = "disputed"
                    x["disputes"] = sorted(set(x.get("disputes") or []) | {y["id"]})
                store._bump(m, c)


def _close_open(m, item, cand):
    """Something happened that settles an open promise or plan (kept or broken)."""
    if item.get("kind") in ("promise", "plan", "hypothetical", "claim") or cand["kind"] not in ("event", "fact", "gift", "body", "decision"):
        return
    txt = cand.get("evid", "")
    broken = bool(BROKEN_CUE.search(txt))
    if not (DONE_CUE.search(txt) or broken):
        return
    terms = set(lx.terms(txt))
    for o in m["items"]:
        if o.get("open") and o.get("msg", -1) < item.get("msg", 0) and o["id"] != item["id"]:
            ot = set(lx.terms(o.get("evid") or o["text"]))
            who = {en._key(o.get("who", ""))} | {en._key(a) for a in o.get("about") or []}
            if len(terms & ot) >= 2 or (len(terms & ot) >= 1 and who & ({en._key(cand["who"])} | {en._key(a) for a in cand["about"]})):
                o["open"] = False
                o["closed_by"] = item["id"]
                o["closed_turn"] = item.get("turn", 0)
                o["outcome"] = "broken" if broken else "kept"
                store._bump(m, o)


def commit(m, cands, user="", char="", *, viewer="", stamps=None, group=False):
    """Write candidate memories into the store. -> [items written or strengthened]"""
    out, last_ep, stamps = [], None, stamps or {}
    for c in cands:
        item_viewer = viewer or char
        probe = {"known_by": c.get("known_by") or []}
        if not visible(probe, item_viewer):
            continue                                   # this character was not there for it
        t = c["layer"]
        item, created = store.add(m, t, c["text"], subj=c.get("subj", "bond"), imp=c["imp"], emo=c.get("emo", ""), val=lx.emotion_group(c.get("emo", ""))[1] if c.get("emo") else 0.0,
                                  turn=c["msg"] + 1, ts=stamps.get(c["msg"]) or None, src="rule", pin=c.get("pin", False), kind=c["kind"], who=c["who"], about=c.get("about"),
                                  known_by=c.get("known_by"), status=c.get("status", "confirmed"), rsrc=c.get("rsrc", ""), open=c.get("open", False), when=c.get("when", ""),
                                  evid=c.get("evid", ""), msg=c["msg"], slot=c.get("slot", ""), obj=c.get("obj", ""), ctx=c.get("ctx", ""))
        if not item:
            continue
        if created and t == "episodic":
            last_ep = item
        if created:
            _link_feeling(m, c, item, last_ep)
            _resolve_slot(m, c, item, created)
            _corroborate(m, item)
            _dispute(m, item, c)
            _close_open(m, item, c)
        r = c.get("rel")
        if r:
            if r["kind"] in ("bond", "end"):
                en.link_rel(m, r["a"], r["b"], r["rel"], turn=c["msg"] + 1, ts=stamps.get(c["msg"]) or 0, src="rule", text=c["text"])
            for nm in (r["a"], r["b"]):
                if nm not in (en.U, en.C):
                    en.register(m, nm, turn=c["msg"] + 1)
        out.append(item)
    return out


# ---- ingest ----
def ingest(st, hist, user="", char="", *, group_names=(), viewer="", enabled=True):
    """Read every message of the chat that has not been read yet and write what deserves remembering.
    hist = the whole in-character chat. -> {"read": n messages, "added": [ids], "rolled_back": n}.
    Idempotent: calling it again with the same chat does nothing; an edited or removed message undoes what was learned from it."""
    m = store.ensure(st, user, char)
    msgs = [x for x in (hist or []) if isinstance(x, dict) and not x.get("ooc")]
    ing = m["ing"]
    n_old = int(ing.get("n", 0) or 0)
    old_cp = {int(k): v for k, v in (ing.get("cp") or {}).items() if str(k).isdigit()}
    cur = chain(msgs, at=set(old_cp))
    k = 0
    for idx in sorted(old_cp, reverse=True):          # the newest checkpoint the chat still agrees with: everything up to it is unchanged
        if idx < len(msgs) and idx < n_old and cur.get(idx) == old_cp[idx]:
            k = idx + 1
            break
    if not n_old:
        k = 0
    rolled = 0
    if k < n_old:
        rolled = rollback(m, k)
    before = {i["id"] for i in m["items"]}
    if not enabled:
        return {"read": 0, "added": [], "rolled_back": rolled}
    stamps = {i: x.get("ts") for i, x in enumerate(msgs) if x.get("ts")}
    new = msgs[k:]
    if new:
        cands = ex.read(new, user, char, m, start=k, group_names=group_names, prev=msgs[k - 1] if k > 0 else None)
        commit(m, cands, user, char, viewer=viewer or char, stamps=stamps, group=bool(group_names))
    ing["n"], ing["cp"] = len(msgs), {str(i): h for i, h in chain(msgs).items()}
    m["turn"] = max(m.get("turn", 0), len(msgs))
    consolidate(m, len(msgs))
    store.compact(m, len(msgs))
    store.decay(m, len(msgs))
    st["facts"] = store.user_facts_mirror(m)
    if rolled or len(new):
        m["rev"] = m.get("rev", 0) + 1
    return {"read": len(new), "added": [i["id"] for i in m["items"] if i["id"] not in before], "rolled_back": rolled}


# ---- consolidation ----
def consolidate(m, turn, min_group=4, min_age=80):
    """Fold old, minor, unremarkable episodes of the same person and stretch of the story into one digest. The originals are archived, never deleted."""
    if len([i for i in m["items"] if i["t"] == "episodic"]) < 40:
        return 0
    groups = {}
    for i in m["items"]:
        if (i["t"] == "episodic" and i.get("kind") in ("event", "claim", "hypothetical", None, "") and not store._protected(i, turn) and i.get("imp", .5) < .55
                and turn - i.get("turn", 0) >= min_age and i.get("src") in ("rule", "promoted", "auto-lite")):
            groups.setdefault((i.get("who", ""), i.get("turn", 0) // 40), []).append(i)
    made = 0
    for (who, _), items in groups.items():
        if len(items) < min_group:
            continue
        items.sort(key=lambda i: i.get("turn", 0))
        keep = sorted(items, key=lambda i: -i.get("imp", .5))[:5]
        keep.sort(key=lambda i: i.get("turn", 0))
        text = "Earlier minor moments" + (f" ({who})" if who else "") + ": " + " | ".join(ex.clip(i["text"], 60) for i in keep)
        d, _ = store.add(m, "episodic", text[:240], imp=max(i.get("imp", .5) for i in items), turn=items[-1].get("turn", 0), ts=items[-1].get("ts", 0), src="consolidated", kind="digest",
                         who=who, about=sorted({a for i in items for a in i.get("about") or []})[:5], status="confirmed")
        if d:
            d["merged"] = [i["id"] for i in items]
            store.archive_items(m, items, "consolidated into " + d["id"])
            ids = {i["id"] for i in items}
            m["items"] = [i for i in m["items"] if i["id"] not in ids]
            made += 1
    return made
