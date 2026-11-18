"""Writing memories.

After every exchange (no extra model call):
    short-term   the scene and a one-line event from the mood tracker's JSON go into the short-term buffer
    semantic     lasting facts the tracker found, plus the ones plainly stated ("I hate being interrupted")
Only after an IMPORTANT moment (a gift, a promise, a fight, a confession... or the user saying "remember this"):
    one extra model call writes the episode, how the character felt about it, and any durable facts.
    If the model gives nothing usable, a plain note of the moment is kept instead, so nothing important is lost.
Events that fall out of the short-term buffer and were worth keeping are promoted to episodic memory.
"""
import re

from ..textutil import THINK, loose_json
from . import analyze, lexicon as lx, store
from .retrieve import DEPTH


def _one_line(x, n=160):
    return re.sub(r"\s+", " ", re.sub(r"\*[^*\n]*\*", " ", str(x or ""))).strip(" \"'")[:n]


def _last(hist, role):
    return next((x for x in reversed(hist or []) if x.get("role") == role and (x.get("content") or "").strip()), None)


def _plain(m):
    return THINK.sub("", (m or {}).get("content", "")).strip()


def prompt(name, user, persona, convo, known):
    """The consolidation ask. Contains the word JSON on purpose: it is a structured request."""
    return (f"You are the long-term memory of a roleplay character named {name}. {('Personality: ' + persona[:300]) if persona else ''}\n"
            f"Something important may have just happened between {name} and {user}.\n"
            f"Already remembered: {'; '.join(known) or 'nothing'}\n\nLatest messages:\n{convo}\n\n"
            f"Write the memories {name} should keep. Reply with ONLY a JSON object: "
            f"{{\"episode\": \"one concrete sentence: who did what (empty if nothing worth remembering)\", "
            f"\"people\": [\"names of others involved, not {name} or {user}\"], "
            f"\"importance\": integer 1-10, "
            f"\"emotion\": \"one lowercase word for what {name} felt\", "
            f"\"feeling\": \"one sentence on how {name} felt about it, like '{name} felt embarrassed when {user} found out' (empty if no strong feeling)\", "
            f"\"facts\": [\"new lasting facts about {user}, {name} or their relationship; empty list if none\"]}}. /no_think")


def _convo(hist, name, user, n=6):
    return "\n".join(f"{(m.get('name') or name) if m['role'] == 'assistant' else user}: {THINK.sub('', m['content'])[:450]}"
                     for m in (hist or [])[-n:] if (m.get("content") or "").strip())


def _parse(txt, user, char):
    try:
        j = loose_json(txt)
    except Exception:
        return None
    ph = lambda t: store.placeholders(_one_line(t, 220), user, char)
    skip = {(user or "").lower(), (char or "").lower()}
    try:
        imp = max(0.0, min(1.0, float(j.get("importance")) / 10))
    except (TypeError, ValueError):
        imp = None
    emo = re.sub(r"[^a-z]", "", str(j.get("emotion", "")).lower())[:14]
    facts = [ph(f if isinstance(f, str) else (f or {}).get("text", "")) for f in (j.get("facts") if isinstance(j.get("facts"), list) else [])[:3]]
    return {"episode": ph(j.get("episode")), "feeling": ph(j.get("feeling")), "emo": emo, "imp": imp, "facts": [f for f in facts if f],
            "people": [str(p).strip() for p in (j.get("people") if isinstance(j.get("people"), list) else []) if str(p).strip().lower() not in skip][:4]}


def _write_moment(m, mem, mom, user_text, mood, *, turn, ts, src="auto", guard=None):
    """Store the episode (+ the feeling that goes with it) from the model's JSON, or from plain heuristics."""
    if mem and len(mem["episode"]) >= 8:
        ep_text, people, imp = mem["episode"], mem["people"], max(.5, .5 * (mem["imp"] if mem["imp"] is not None else mom["score"]) + .5 * mom["score"])
    else:
        ep_text, people, imp, mem, src = analyze.fallback_episode(user_text, mom["cats"]), [], max(.5, mom["score"]), mem or {}, "auto-lite"
    if not ep_text:
        return []
    gd = guard or (lambda t, k: t)
    ep_text = gd(ep_text, "episode")
    if not ep_text:
        return []
    ep, _ = store.add(m, "episodic", ep_text, imp=min(1.0, imp), people=people, turn=turn, ts=ts, src=src)
    out = [ep]
    emo = mem.get("emo") or (mood if lx.is_strong(mood) else "")
    feeling = mem.get("feeling") or (f"{{{{char}}}} felt {emo} about it." if emo and src == "auto-lite" else "")
    feeling = gd(feeling, "feeling") if feeling else feeling
    if feeling and len(feeling) >= 8 and ep:
        g, v = lx.emotion_group(emo)
        fe, _ = store.add(m, "emotional", feeling, imp=min(1.0, imp), emo=emo, val=v, link=ep["id"], turn=turn, ts=ts, src=src)
        out.append(fe)
    for f in mem.get("facts", []):
        f = gd(f, "fact")
        if not f:
            continue
        fi, subj = analyze.classify_fact(f)
        out.append(store.add(m, "semantic", f, subj=subj, imp=fi, turn=turn, ts=ts, src=src)[0])
    return out


def update(st, j, hist, *, user, char, persona="", cfg, turn, delta=0, mood_before="", mood_after="", ask=None, used=(), guard=None):
    """Everything memory does after a reply. Mutates st["mem"] (and st["facts"], kept in step for the old flat list).
    -> {"added": [ids], "moment": {...}}"""
    m = store.ensure(st, user, char)
    m["turn"] = turn
    store.touch(m, used, turn)
    before = {i["id"] for i in m["items"]}
    j = j if isinstance(j, dict) else {}
    lu, la = _last(hist, "user"), _last(hist, "assistant")
    user_text, reply_text = _plain(lu), _plain(la)
    ts = (la or {}).get("ts") or store.now_ms()
    ph = lambda t, n=160: store.placeholders(_one_line(t, n), user, char)
    mom = analyze.moment(user_text, reply_text, delta, mood_before, mood_after, j.get("importance"))
    gd = guard or (lambda t, k: t)
    # short-term
    scene, event = gd(ph(j.get("scene")), "scene") if ph(j.get("scene")) else "", gd(ph(j.get("event")), "event") if ph(j.get("event")) else ""
    if scene:
        m["scene"] = scene
    promoted = store.push_recent(m, event, mom["score"], turn) if event else []
    # semantic: what the tracker found + what the user plainly said
    for f in (j.get("facts") if isinstance(j.get("facts"), list) else [])[:3]:
        f = gd(ph(f, 140), "fact")
        if f and len(f) >= 6:
            fi, subj = analyze.classify_fact(f)
            store.add(m, "semantic", f, subj=subj, imp=fi, turn=turn, ts=ts)
    for f, fi, subj in analyze.user_facts(user_text):
        store.add(m, "semantic", f, subj=subj, imp=fi, turn=turn, ts=ts)
    # an important moment: episode + feeling (+ facts)
    if cfg.get("learn", True) and mom["score"] >= DEPTH[cfg.get("depth", "standard")]["sens"] and user_text:
        mem = None
        if ask:
            try:
                mem = _parse(ask(prompt(char, user, persona, _convo(hist, char, user), [store.resolve(i["text"], user, char) for i in
                                                                                       sorted((x for x in m["items"] if x["t"] == "semantic"), key=lambda x: -x.get("imp", 0))[:8]]), 380), user, char)
            except Exception:
                mem = None
        _write_moment(m, mem, mom, user_text, mood_after, turn=turn, ts=ts, guard=guard)
    for r in promoted:    # fell out of the short-term buffer and was worth keeping
        if r["imp"] >= .45 and gd(r["text"], "episode"):
            store.add(m, "episodic", r["text"], imp=r["imp"] * .9, turn=r["turn"], ts=r["ts"], src="promoted")
    store.compact(m, turn)
    st["facts"] = store.user_facts_mirror(m)
    return {"added": [i["id"] for i in m["items"] if i["id"] not in before], "moment": mom}


def backfill(st, hist, *, user, char, persona="", cfg, ask, max_calls=8, guard=None):
    """Build memories from a chat that already exists: scan it in windows, ask the model only about the moments
    that look important. -> {"added": [ids], "calls": n, "scanned": n}"""
    m = store.ensure(st, user, char)
    gate = DEPTH[cfg.get("depth", "standard")]["sens"]
    msgs = [x for x in (hist or []) if (x.get("content") or "").strip()]
    before = {i["id"] for i in m["items"]}
    calls, k, covered = 0, 0, 0
    while k < len(msgs) and calls < max_calls:
        win = msgs[k:k + 6]
        lu = _last(win, "user")
        idx = max((n for n, x in enumerate(win) if x is lu), default=-1)
        reply = next((_plain(x) for x in win[idx + 1:] if x.get("role") == "assistant"), "") if idx >= 0 else ""
        mom = analyze.moment(_plain(lu), reply, 0, "", "", None) if lu else {"score": 0, "cats": [], "explicit": False}
        end = k + len(win)
        if mom["score"] >= gate and end > covered:
            mem = None
            try:
                mem = _parse(ask(prompt(char, user, persona, _convo(win, char, user), []), 380), user, char)
            except Exception:
                mem = None
            _write_moment(m, mem, dict(mom, score=max(mom["score"], .55)), _plain(lu), "", turn=end, ts=(win[-1].get("ts") or store.now_ms()), guard=guard)
            calls += 1
            covered = end
            k = end
        else:
            k += 4
        for f, fi, subj in analyze.user_facts(_plain(lu)) if lu else []:
            store.add(m, "semantic", f, subj=subj, imp=fi, turn=end, ts=win[-1].get("ts") or store.now_ms())
    m["turn"] = max(m["turn"], len(msgs))
    store.compact(m, m["turn"])
    st["facts"] = store.user_facts_mirror(m)
    return {"added": [i["id"] for i in m["items"] if i["id"] not in before], "calls": calls, "scanned": len(msgs)}
