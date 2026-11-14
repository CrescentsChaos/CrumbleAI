"""Choosing which memories reach the prompt. No model calls: it is a small search engine over the memory store.

    1. read the latest user message           who / what / which kind of event / which feeling is it about?
    2. search every memory                    topic words (rarer words count more), people, event type, feeling, mood
    3. rank                                   relevance, recency (per layer), importance (+ pins, + how often it came up)
    4. inject only the most useful            a budget of items and characters, per-layer caps, no near-duplicates
"""
import math
import time

from ..config import CH, US
from ..textutil import THINK, human_gap
from . import analyze, lexicon as lx, store

DEPTH = {"light": dict(items=4, chars=520, core=2, sens=.65), "standard": dict(items=7, chars=950, core=3, sens=.55),
         "deep": dict(items=10, chars=1500, core=4, sens=.45)}
HALF_TURNS = {"episodic": 90, "semantic": 400, "emotional": 160}     # recency half-life in chat messages, per layer
HALF_DAYS = {"episodic": 20, "semantic": 180, "emotional": 45}       # ...and in real days (coming back after a long gap)
MIN_REL = .16          # below this a memory is not "about" the message at all
W_REL, W_REC, W_IMP = .50, .20, .30
RECENT_TURNS = 20      # short-term events older than this stop being "just happened"
AMBIENT_TURNS = 14     # a big moment this fresh still colours the next replies even if nobody mentions it


def settings(p):
    p = p or {}
    depth = p.get("depth") if p.get("depth") in DEPTH else "standard"
    return {"on": bool(p.get("on")), "depth": depth, "learn": bool(p.get("learn", True))}


def view(st, user="", char=""):
    """The memory store of a state, read-only. Chats from before this feature are read through their old flat facts."""
    m = (st or {}).get("mem")
    if isinstance(m, dict) and m.get("legacy"):
        return m
    tmp = {"facts": (st or {}).get("facts"), "mem": dict(m) if isinstance(m, dict) else None}
    return store.ensure(tmp, user, char)


def _recency(i, turn, now):
    t = i["t"]
    r_turn = .5 ** (max(0, turn - i.get("turn", 0)) / HALF_TURNS[t])
    if not i.get("ts"):
        return r_turn
    r_time = .5 ** (max(0.0, (now - i["ts"]) / 86400000) / HALF_DAYS[t])
    return .65 * r_turn + .35 * r_time


def _importance(i):
    return min(1.0, i.get("imp", .5) + .05 * min(i.get("n", 0), 4) + (.15 if i.get("pin") else 0))


def _idf(items):
    df, n = {}, max(1, len(items))
    for i in items:
        for s in set(lx.terms(i["text"])):
            df[s] = df.get(s, 0) + 1
    return {s: 1 + math.log(1 + n / (1 + c)) for s, c in df.items()}


def _relevance(i, q, idf):
    """-> (0..1, [why])  — topic words, people, event type and feeling, combined so any one strong signal is enough."""
    why, keep = [], 1.0
    raw = sum(idf.get(s, 1.0) * q["terms"][s] for s in set(lx.terms(i["text"])) if s in q["terms"])
    if raw:
        keep *= 1 - raw / (raw + 2.5)
        why.append("topic")
    if q["people"] and {p.lower() for p in q["people"]} & {p.lower() for p in (i.get("people") or [])}:
        keep *= .5
        why.append("person")
    if q["events"] and set(q["events"]) & set(lx.categories(i["text"])):
        keep *= .4
        why.append("event")
    g, v = lx.emotion_group(i.get("emo", ""))
    if i["t"] == "emotional" or i.get("emo"):
        if g and any(g == qg for qg, _ in q["emo"]):
            keep *= .5
            why.append("feeling")
        elif g and q["mood"][0] and g == q["mood"][0]:
            keep *= .7
            why.append("mood")
        elif abs(i.get("val", v)) > .3 and abs(q["mood"][1]) > .3 and (i.get("val", v) > 0) == (q["mood"][1] > 0):
            keep *= .85
            why.append("mood")
    return 1 - keep, why


def rank(m, q, turn, now):
    """Every memory with its scores, best first. -> [{item, score, rel, rec, imp, why}]"""
    idf = _idf(m["items"])
    out = []
    for i in m["items"]:
        rel, why = _relevance(i, q, idf)
        rec, imp = _recency(i, turn, now), _importance(i)
        score = W_REL * rel + W_REC * rec + W_IMP * imp
        if q["reach"] and i["t"] == "episodic":
            score *= 1.2
        if i.get("last") and turn - i["last"] <= 2 and rel < .5:    # it was just used: let something else have a turn
            score *= .85
        out.append({"item": i, "score": round(score, 4), "rel": round(rel, 3), "rec": round(rec, 3), "imp": round(imp, 3), "why": why})
    return sorted(out, key=lambda r: -r["score"])


def _ago(i, now):
    if not i.get("ts"):
        return ""
    g = human_gap((now - i["ts"]) / 1000)
    return f" ({g} ago)" if g and (now - i["ts"]) >= 2 * 3600 * 1000 else ""


def short_term(m, turn):
    """Scene + the last few events: the immediate, still-unfolding situation."""
    lines = []
    if (m.get("scene") or "").strip():
        lines.append("Scene: " + m["scene"].strip())
    ev = [r["text"] for r in m.get("recent", []) if turn - r.get("turn", 0) <= RECENT_TURNS][-3:]
    if ev:
        lines.append("Just happened: " + "; ".join(ev))
    return lines


def _query_for(hist, m, st, user, char, known_extra):
    msgs = [x for x in (hist or []) if (x.get("content") or "").strip()]
    last_user = next((x for x in reversed(msgs) if x.get("role") == "user"), None)
    text = (last_user or {}).get("content", "")
    ctx = [(THINK.sub("", x["content"])[:400], w) for x, w in zip(reversed([x for x in msgs if x is not last_user][-2:]), (.35, .2))]
    if (m.get("scene") or "").strip():
        ctx.append((m["scene"], .3))
    known = analyze.known_people(m["items"], skip=(user, char)) + [n for n in known_extra if n]
    return analyze.query(text, ctx, (st or {}).get("mood", ""), known, skip=(user, char))


def select(st, hist, *, user="", char="", cfg=None, turn=None, now=None, known_extra=()):
    """What goes into the prompt this turn.
    -> {block, short, ids, trace, q}   block = the memory text ("" if nothing earned a place), short = lines for the scene
    section, ids = what was used (so recalling it can strengthen it), trace = why each one was picked."""
    cfg = cfg or settings({"on": True})
    m = view(st, user, char)
    turn = (m.get("turn", 0) + 1) if turn is None else int(turn)
    now = now or store.now_ms()
    d = DEPTH[cfg["depth"]]
    q = _query_for(hist, m, st, user, char, known_extra)
    ranked = rank(m, q, turn, now)
    items_cap, chars = d["items"] + (2 if q["reach"] else 0), int(d["chars"] * (1.3 if q["reach"] else 1))
    caps = {"episodic": max(2, round(items_cap * .5)), "semantic": max(2, round(items_cap * .55)), "emotional": max(1, round(items_cap * .3))}
    chosen, used, spent = [], {t: 0 for t in caps}, 0

    def take(r, reason, force=False):
        nonlocal spent
        i, cost = r["item"], len(r["item"]["text"]) + 24
        if i["id"] in {c[0]["item"]["id"] for c in chosen} or len(chosen) >= items_cap:
            return False
        if not force and (used[i["t"]] >= caps[i["t"]] or spent + cost > chars):
            return False
        if any(store.similar(i["text"], c[0]["item"]["text"]) >= .6 for c in chosen):
            return False
        chosen.append((r, reason))
        used[i["t"]] += 1
        spent += cost
        return True

    core = sorted((r for r in ranked if r["item"].get("pin") or (r["item"]["t"] == "semantic" and r["item"].get("imp", 0) >= .85)),
                  key=lambda r: -r["item"].get("imp", 0))
    for r in core[:d["core"]]:
        take(r, "always", force=True)
    ambient = 0
    for r in ranked:
        if len(chosen) >= items_cap:
            break
        if r["rel"] >= MIN_REL:
            take(r, "+".join(r["why"]) or "relevant")
        elif (r["item"]["t"] != "semantic" and r["imp"] >= .7 and turn - r["item"].get("turn", 0) <= AMBIENT_TURNS
              and ambient < (2 if cfg["depth"] == "deep" else 1)):
            ambient += take(r, "just happened")    # still colours the mood even if nobody mentioned it
    by_id = {r["item"]["id"]: r for r in ranked}
    for r, _ in list(chosen):    # an event brings the feeling it left behind
        if r["item"]["t"] == "episodic":
            for e in m["items"]:
                if e["t"] == "emotional" and e.get("link") == r["item"]["id"] and e["id"] in by_id:
                    take(by_id[e["id"]], "linked feeling", force=len(chosen) < items_cap)
    short = short_term(m, turn)
    if not chosen:
        return {"block": "", "short": short, "ids": [], "trace": [], "q": _public_q(q)}
    groups = {"episodic": [], "semantic": [], "emotional": []}
    for r, _ in sorted(chosen, key=lambda c: c[0]["item"].get("turn", 0)):
        i = r["item"]
        groups[i["t"]].append(f"- {i['text']}" + (_ago(i, now) if i["t"] == "episodic" else ""))
    parts = [f"[What {CH} remembers - let it shape the reply only where it fits the moment; never recite it]"]
    for t, head in (("episodic", f"What happened between {CH} and {US}:"), ("semantic", f"What {CH} knows:"), ("emotional", f"How {CH} remembers feeling:")):
        if groups[t]:
            parts += [head] + groups[t]
    trace = [{"id": r["item"]["id"], "t": r["item"]["t"], "text": r["item"]["text"], "why": reason, "score": r["score"],
              "rel": r["rel"], "rec": r["rec"], "imp": r["imp"]} for r, reason in chosen]
    return {"block": "\n".join(parts), "short": short, "ids": [t["id"] for t in trace], "trace": trace, "q": _public_q(q)}


def _public_q(q):
    return {"people": q["people"], "events": q["events"], "emo": [g for g, _ in q["emo"]], "reach": q["reach"],
            "topics": [s for s, _ in q["terms"].most_common(8)]}
