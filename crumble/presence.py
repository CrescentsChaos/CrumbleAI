"""Who is here and what are they doing: one model call per stretch of story time (the page keeps the answer in the chat).

The server only runs the call and bounds the answer; story/doing.py writes the question and reads the answer, places.py knows the cast of a place.
A place's characters are the people who live or turn up there. They are not always in, and nobody has a fixed daily timetable: the model decides,
from the sheet, the scene, the hour and the weather, who is around, what each is doing and how each reacts to the visitor.
"""
from . import ambience, places, simtime, story
from .config import LLM, LOCK
from .story import doing
from .storage import get_char, get_group

MAX_ASK = 8          # people asked about in one call (a bigger cast rotates)


def _hist(b):
    return [dict(m, content=str(m.get("content", ""))[:3000]) for m in (b.get("history") or [])[-300:] if isinstance(m, dict) and not m.get("ooc")]


def run(b, call=None):
    """-> {people: {id: item}, key, turn, ids, clock, ai}. `call(prompt) -> text` is the model (tests pass a fake); it defaults to the loaded one."""
    hist = _hist(b)
    turn = int(b.get("turn") or len(hist))
    spec = b.get("place") if isinstance(b.get("place"), dict) else None
    card = places.get(spec.get("id")) if spec else None
    g = get_group(str(b.get("group"))) if b.get("group") else None
    ids = []
    if card:
        ids += list(card["characters"])
    if g:
        ids += [i for i in g.get("members", [])]
    ids += [str(i) for i in (b.get("cids") or [])]
    ids = [i for i in dict.fromkeys(ids) if get_char(i)]
    scene = str(b.get("scene") or "")[:400]
    scen = (g or {}).get("scenario") or (get_char(ids[0]).get("scenario") if ids else "") or ""
    full = scen + (" " + str(b.get("story_start") or "")[:80] if b.get("story_start") else "")
    notes = [{"kind": "setting", "text": scene}] if scene else []
    sim = simtime.derive(hist, full, notes) or simtime.from_clock(str(b.get("clock") or ""))
    k = doing.key(card["id"] if card else "", sim, turn, scene)
    have = b.get("have") if isinstance(b.get("have"), dict) else None
    same = have and sorted(have.get("ids") or []) == sorted(ids)
    if not b.get("force") and same and not doing.stale(have, card["id"] if card else "", sim, turn, scene):
        return {"fresh": True, "key": k, "turn": int(have.get("turn") or turn)}
    ask_ids = doing.pick(ids, f"{k}", MAX_ASK)
    loc = places.context({"id": card["id"], "since": 0}, turn) if card else None
    scfg = story.settings(b.get("story"))
    amb = ambience.derive(hist, full, notes + ([places.note(loc)] if loc else []), sim)
    texts = [full] + [m.get("content") or "" for m in hist[-8:]]
    wx = story.sky(sim, amb, texts, (card or {}).get("name", "") + full[:200], scfg) if scfg["on"] else None
    prev = b.get("prev") if isinstance(b.get("prev"), dict) else {}
    user = str(b.get("user") or "the visitor")[:40]
    people = [get_char(i) for i in ask_ids]
    recent = [f"{'You' if m.get('role') == 'user' else (m.get('name') or 'They')}: {m.get('content', '')}" for m in hist[-6:]]
    out, ai = {}, False
    call = call or _model()
    if call is not None and people:
        prompt = doing.ask(people, card, sim, (wx or {}).get("weather", ""), recent, scene, prev, user, bool(b.get("arriving")),
                           setting=((amb.get("place") or {}).get("name") or "") if not card else "")
        try:
            out = doing.parse(call(prompt), ask_ids)
            ai = bool(out)
        except Exception:
            out = {}
    if not out:
        out = doing.fallback(ask_ids, f"{b.get('seed') or ''}:{k}", bool(card))
    elif card:
        for i in ask_ids:       # asked about but left out of the answer: not heard from, so not around
            out.setdefault(i, doing.clean({"id": i, "here": False}, i))
    for i in ids:
        if i not in out:        # not asked about this time (a big cast): keep what the page already had, else not around
            old = prev.get(i)
            out[i] = doing.clean(old, i) if isinstance(old, dict) else doing.clean({"id": i, "here": False}, i)
    return {"people": out, "key": k, "turn": turn, "ids": ids, "clock": (sim or {}).get("clock", ""), "ai": ai}


def _model():
    obj = LLM.get("obj")
    if not obj:
        return None

    def call(prompt):
        with LOCK:
            r = obj.create_chat_completion(messages=[{"role": "user", "content": prompt + "\n/no_think"}], temperature=.8, max_tokens=min(600, LLM["n_ctx"] // 4))
        return r["choices"][0]["message"]["content"]
    return call
