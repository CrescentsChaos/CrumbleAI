"""Running the model: token budgeting, sampling, and the full reply pipeline."""
import json
import os
import re
import time

from . import ambience, chronicle, director, identity, keeper, leak, personality, places, recall, repeat, simtime, story
from .config import CH, LLM, ROOT, US
from .prompt import build_messages, cue_text
from .rp.narrator import NARR_ID
from .rp.ooc import KINDS as OOC_KINDS, clean_notes, finish_ooc, ooc_messages, ooc_words
from .recall import lexicon as lx
from .recall import store as rstore
from .textutil import THINK, cap_reply, finish_reply, human_gap, preview_reply, similar, want_words


# Retries (a whole new generation: it doubles the wait, and the bill with an online model) are for hard failures only.
# Everything else is repaired in place (echo, AI-speak, a closing question, register) or flagged on the reply and left alone.
# Rule names are what tools/retry_stats.py counts in data/retry_log.jsonl; to bring a noisy-but-wanted rule back as a retry, add its name to SOFT_RETRY.
HARD_RETRY = {"user_voice", "leak", "scrubbed", "echo_all",         # wrote as the user, instruction/prompt text, nothing real left after the repair
              "identity_speaks_for_user", "identity_impersonation", "identity_wrong_name",   # whose turn / who is who ...
              "identity_contradiction", "identity_ignored_fact", "identity_invented", "identity_premise",   # ... and what is on the record
              "persona_hard", "dup", "pattern_open"}                                # a sheet's mandatory voice broken, a near-verbatim repeat. (An empty reply always retries.)
QUICK_SKIP = set()      # rules Quick mode would only flag, never retry (empty: a repeated line or a broken voice is still worth a second generation)
SOFT_RETRY = set()                                                  # e.g. {"time", "env", "ai_speak", "persona", "identity_misgender", "parrot", "repeat", "ending"}; never used in Quick mode
TIME_BUDGET = 2.0                                                    # all attempts together may not take more than this many times the first one
RETRY_LOG = os.environ.get("CRUMBLE_RETRY_LOG", "1") != "0"


def log_retries(entry):
    """One JSON line per reply that tripped any rule: names and timings only, never the text."""
    if not RETRY_LOG:
        return
    try:
        f = ROOT / "data" / "retry_log.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size > 1_000_000:
            f.replace(f.with_suffix(".old"))
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def ntok(txt):
    try:
        return len(LLM["obj"].tokenize(txt.encode("utf-8", "ignore"), add_bos=False)) + 6
    except Exception:
        return len(txt) // 3 + 6


def fit(msgs, room):
    """Drop the oldest chat turns until the prompt leaves `room` tokens. Returns (tokens used, messages dropped)."""
    cnt = [ntok(m["content"]) for m in msgs]
    dropped = 0
    while len(msgs) > 3 and sum(cnt) > room:
        del msgs[1], cnt[1]
        dropped += 1
    return sum(cnt), dropped


def sampler(p):
    s = dict(temperature=float(p.get("temperature", .8)), top_p=float(p.get("top_p", .95)),
             top_k=int(p.get("top_k", 40)), min_p=float(p.get("min_p", .05)),
             repeat_penalty=float(p.get("repeat_penalty", 1.1)),
             presence_penalty=float(p.get("presence_penalty", 0)), frequency_penalty=float(p.get("frequency_penalty", 0)))
    if int(p.get("seed", -1)) >= 0:
        s["seed"] = int(p["seed"])
    return s


HOLD = 14   # characters kept back from the live preview: a stop phrase ("\nUser:") is cut off by the model, but its first letters may already have been generated


def run_llm(msgs, samp, stop, cap, send=None, live=False, view=None):
    """Run the model. With live=True the text is also streamed to the page as it is written; the finished text
    (after clean-up, repairs and any retries) always follows in the final message, so the preview can never leave a wrong reply behind.
    With view=<function>, the preview is that function applied to the text so far ({"t": whole preview}): the page then shows the same
    clean-up and length cap as the finished reply, so a short reply is never written long on screen and then cut back."""
    t0, txt, fin, n, out, last, sent = time.time(), "", None, 0, 0, 0.0, ""
    t_first = None

    def push(upto):
        nonlocal out, sent
        if view:
            try:
                t = view(txt[:upto])
            except Exception:
                return
            if t != sent:
                send({"t": t})
                sent = t
        else:
            send({"d": txt[out:upto]})
        out = upto

    for ch in LLM["obj"].create_chat_completion(messages=msgs, stream=True, max_tokens=cap, stop=stop, **samp):
        c = ch["choices"][0]
        d = c["delta"].get("content")
        if d:
            if t_first is None:
                t_first = time.time() - t0
            txt += d
            n += 1
            if send and n % 6 == 0:
                send({"p": "think" if txt.rfind("<think>") > txt.rfind("</think>") else "reply", "n": n})
            if send and live:
                now = time.time()
                if n <= 2 or now - last > .045:     # a few tokens per message: smooth on the page, light on the socket
                    upto = len(txt) - HOLD
                    if upto > out:
                        push(upto)
                        last = now
        if c.get("finish_reason"):
            fin = c["finish_reason"]
    if send and live and view:
        push(len(txt))     # the held-back tail, so the preview is complete before the finished reply arrives
    total = time.time() - t0
    if n and os.environ.get("CRUMBLE_TIMING", "1") != "0":
        gen = max(total - (t_first or 0), .001)
        print(f"[reply] waited {t_first or 0:.1f}s for the first word (the model reading the prompt), then {n} tokens at {n / gen:.1f}/s = {gen:.1f}s writing; total {total:.1f}s")
    TIMING.update(first=round(t_first or 0, 2), total=round(total, 2), tok=n)
    return txt, fin, n, total


TIMING = {}


def ooc_reply(b, send):
    """The storyteller answers out of character: discussion, or the acknowledgement of a correction, setting change or direction.
    One short generation: no personality guard, no repetition checks, and 'assistant' talk is fine here."""
    p, c, user, hist = b["params"], b["char"], b["user"], b["history"]
    oo = b.get("ooc") or {}
    kind = oo.get("kind") if oo.get("kind") in OOC_KINDS else "discuss"
    n_ctx = LLM["n_ctx"]
    last_user = next((m["content"] for m in reversed(hist) if m["role"] == "user" and m.get("ooc")), "")
    lo, hi = ooc_words(last_user, p.get("length", "auto"))
    cap = min(max(int(hi * 2.6) + 60, 160), max(256, n_ctx // 2), max(int(p.get("max_tokens", 512)), 160))
    think = bool(p.get("think", True))
    stop = ["\n" + user + ":", "\n" + user + " :", "\n**" + user + ":"]
    samp = sampler(p)
    best, used, dropped = None, 0, 0
    for _ in range(2):
        o = dict(group=b.get("grp"), kind=kind, notes=clean_notes(oo.get("notes")), scene=b.get("scene"), persona=b.get("persona"),
                 summary=(b.get("state") or {}).get("summary"), words=(lo, hi), think=think)
        msgs = ooc_messages(c, user, hist, o)
        budget = cap + (1500 if think else 0)
        used, dropped = fit(msgs, n_ctx - budget - 16)
        budget = max(128, min(budget, n_ctx - used - 16))
        if send and p.get("stream"):
            send({"rs": 1})
        raw, fin, ntoks, secs = run_llm(msgs, samp, stop, budget, send, bool(p.get("stream")))
        r = finish_ooc(raw, fin, user)
        r.update(tok=ntoks, ms=int(secs * 1000), finish=fin)
        if r["empty"]:   # thinking ate the whole budget, or nothing came back: try again without thinking
            think = False
            continue
        best = r
        break
    if not best:
        raise RuntimeError("The model returned an empty reply. Try again, or turn Thinking off.")
    best.update(ctx_used=used, ctx=n_ctx, dropped=dropped, kind=kind)
    return best


def generate_reply(b, send):
    p, c, user, hist = b["params"], b["char"], b["user"], b["history"]
    grp = b.get("grp")
    cid = c.get("id")
    kind = b.get("kind", "reply")
    if kind == "ooc":
        return ooc_reply(b, send)
    rp_in = b.get("rp") or {}
    if rp_in.get("on", True) and ((rp_in.get("state") or {}).get("body") or {}).get(cid, {}).get("dead") and kind != "ooc":
        return {"pass": True, "dead": True, "text": "", "think": "", "tok": 0, "ms": 0, "ctx_used": 0, "ctx": LLM["n_ctx"], "dropped": 0}   # the dead do not speak
    hist = [m for m in hist if not m.get("ooc")]   # out-of-character talk is never heard by the characters (the author's notes carry what matters)
    mode = p.get("mode", "story")
    n_ctx = LLM["n_ctx"]                    # the model's whole window: no hard ceiling (the governor below still squeezes if the prompt gets heavy)
    start = int(b.get("from") or 0)
    turns = int(b.get("turn") or len(hist))   # position in the whole chat, which out-of-character messages also count toward
    full = hist                                # the whole in-character chat: identity, names and what the user said are read from all of it
    hist = hist[start:] if 0 < start < len(hist) else hist
    trimmed = len(full) > len(hist)
    led, id_tail = None, []
    if cid != NARR_ID:
        led = identity.build(c, user, full, persona=b.get("persona"), grp=grp)   # derived from the whole chat: edits and rewinds can never leave it stale
        user = led["user"]["name"]             # the name the user asked for in the chat (or the one set in the UI)
    last_user = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
    lo, hi = want_words(mode, p.get("length", "auto"), last_user)
    if grp:
        lo, hi = max(6, int(lo * .7)), max(14, int(hi * .75))
        if cid == NARR_ID and p.get("length", "auto") == "auto":
            lo, hi = 35, 110
    if kind == "continue":
        lo, hi = 25, 90
    dcfg = director.settings(p.get("dyn"))
    dplan = None
    if dcfg["on"] and cid != NARR_ID and kind in ("reply", "nudge", "resume"):
        st_ = b.get("state") or {}
        dplan = director.plan(c, st_, hist, mode=mode, length=p.get("length", "auto"), level=dcfg["level"], turn=int(b.get("turn") or len(hist)),
                              key=b.get("chat_id") or cid, variant=len(b.get("avoid") or []), kind=kind, chron=st_.get("chron") if isinstance(st_.get("chron"), dict) else None, group=bool(grp))
        if dplan["band"] and p.get("length", "auto") == "auto":
            lo, hi = dplan["band"]
            if grp:
                lo, hi = max(6, int(lo * .7)), max(14, int(hi * .75))
            if kind == "nudge":
                lo, hi = min(lo, 30 if mode != "text" else 14), min(hi, 60 if mode != "text" else 28)
            hi = max(hi, lo + 4)
    cap = min(max(int(p.get("max_tokens", 512)), int(hi * 2.6) + 40), max(256, n_ctx // 2))
    think = bool(p.get("think", True))
    tail = None
    if kind == "continue":
        tail = "(Continue your last message from exactly where it ended. Do not repeat anything already written; add a little more and end cleanly.)"
    elif kind == "resume":
        tail = (f"(The author has just stepped out of the story to set things up. Carry the scene on from the latest moment, "
                f"working in the author's notes. Write only {CH}'s next message.)")
    elif kind == "nudge":
        g = human_gap(b.get("gap_s")) or "a little while"
        tail = (f"({US} has not replied for {g}. Write {CH}'s natural follow-up, the way this person would: "
                "a short nudge, a new thought, or a reaction to the silence. Do not scold them.)")
        if dcfg["on"] and cid != NARR_ID:      # the character opens a conversation with something of their own
            ini = director.initiate("return" if b.get("reason") == "return" else "idle", c, b.get("state") or {}, hist, gap_s=b.get("gap_s") or 0, key=b.get("chat_id") or cid,
                                    turn=int(b.get("turn") or len(hist)), chron=(b.get("state") or {}).get("chron") if isinstance((b.get("state") or {}).get("chron"), dict) else None,
                                    mode=mode, variant=len(b.get("avoid") or []))
            tail = ini["tail"]
            dplan = dict(dplan or {"band": None, "len": None, "tone": None, "quirk": None, "block": "", "tail": "", "dyn": {}}, dyn=dict((dplan or {}).get("dyn") or {}, **ini["dyn"]))
    elif grp:
        tail = places.visit_tail(b, CH, US) if b.get("visit") else cue_text(b, c)     # a resident of the place joining a one-to-one chat
    own = [m for m in hist if m["role"] == "assistant" and (not grp or m.get("cid") == cid)]
    prevs = [THINK.sub("", m["content"]) for m in own][-4:]
    # what was already said in this scene by anyone else (a group), and the alternatives already written for a swipe: a reply that
    # repeats them is a mistake even in Quick mode
    spoken_by_others = [THINK.sub("", m["content"]) for m in hist[-8:] if grp and m["role"] == "assistant" and m.get("cid") != cid][-4:]
    seen_before = prevs + spoken_by_others + [str(x) for x in (b.get("avoid") or [])][:6]
    others = [m.get("name") or "" for m in (grp or {}).get("members", []) if m.get("id") != cid and m.get("name")] + ([] if not grp or cid == NARR_ID else ["Narrator"])
    if led:    # a line that starts 'Nadia:' or '<other name for the user>:' is the model writing someone else's turn
        others += [o["name"] for o in led["others"].values()] + [n for n in identity.user_labels(led) if n != user]
    stop = ["\n" + user + ":", "\n" + user + " :", "\n**" + user + ":"] + [s for o_ in others for s in ("\n" + o_ + ":", "\n**" + o_ + ":")]
    stop += ["<<PRIVATE", "[Reply as", "[As ", "(Write only", "\n=== ", "=== PRIVATE", "\nSETTING & STATE", "\nRELATIONSHIP DYNAMIC", "\nPIVOTAL MOMENTS",
             "\nLocation:", "\nCurrent State:", "\nPrimary Dynamic:", "\n[Right now", "\n[Scene]"]      # the model starts echoing an instruction: cut it off right there
    # story time: derived from the whole chat (scenario, messages, author's settings), so the character lives by the story's clock, not the PC's
    notes_ = clean_notes((b.get("ooc") or {}).get("notes"))
    sim = simtime.derive(full, (grp or {}).get("scenario") or c.get("scenario") or "", notes_ + ([{"kind": "setting", "text": b["scene"]}] if b.get("scene") else []))
    s_start = str(b.get("story_start") or "")[:80]
    if s_start:      # the author set the story clock by hand ("Tuesday 7:40 AM"): it is where the story begins
        sim = simtime.derive(full, ((grp or {}).get("scenario") or c.get("scenario") or "") + " " + s_start, notes_ + ([{"kind": "setting", "text": b["scene"]}] if b.get("scene") else [])) or sim
    if not sim and b.get("clock"):     # the story never says what time it is: with "time aware" on, follow the real clock
        sim = simtime.from_clock(b["clock"])
    gap_s = sim["elapsed"] if sim else b.get("gap_s")
    loc = places.context(b.get("place"), turns)     # the location card this chat stands in (the page sends {id, since}; the server reads the card itself)
    amb = ambience.derive(full, (grp or {}).get("scenario") or c.get("scenario") or "", notes_ + ([{"kind": "setting", "text": b["scene"]}] if b.get("scene") else []) + ([places.note(loc)] if loc else []), sim)
    scfg = story.settings(p.get("story"))
    scen_ = (grp or {}).get("scenario") or c.get("scenario") or ""
    wx = story.sky(sim, amb, [scen_] + [m_.get("content") or "" for m_ in full[-8:]], ((grp or {}).get("name") or c.get("name") or "") + scen_[:200], scfg) if scfg["on"] else None
    if wx and wx["src"] == "dynamic":      # the day's own weather joins the scene, so the physics, the checks and the retries all see the same sky
        amb = dict(amb, weather=wx["weather"])
    sto = story.build(c, user, b.get("state") or {}, hist, sim, amb, (b.get("rp") or {}).get("state") or {}, p.get("story"), turns, [THINK.sub("", m["content"]) for m in own][-6:],
                      mode, grp, (b.get("state") or {}).get("chron") if isinstance((b.get("state") or {}).get("chron"), dict) else None,
                      str((b.get("rp") or {}).get("uskills") or ""), str((b.get("rp") or {}).get("ugear") or ""), wx, (grp or {}).get("members"), narrator=(cid == NARR_ID), loc=loc, doing=story.doing_mod.clean_map(b.get("doing"))) if scfg["on"] else dict(places.standalone(loc, CH, US, turns), info={"on": False})
    if kind not in ("reply", "nudge", "resume"):
        sto = dict(sto, tail="", plan=None)
    if p.get("length", "auto") == "auto" and kind in ("reply", "nudge"):   # room for atmosphere in a horror or intimate beat
        k = ambience.boost(amb)
        lo, hi = int(lo * (1 + (k - 1) / 2)), int(hi * k)
    samp = sampler(p)
    reg = personality.register.detect(c, mode) if cid != NARR_ID else None
    if reg and reg["kind"] == "archaic":     # repeat_penalty taxes the repeated "thou / thy / thee" the register depends on
        samp["repeat_penalty"] = min(samp["repeat_penalty"], 1.05)
    pcfg = personality.settings(p.get("pers"))
    guard_on = personality.active(c, pcfg) and pcfg["guard"] and kind in ("reply", "nudge")
    rcfg = recall.settings(p.get("mem"))
    veto, known = None, [(b.get("state") or {}).get("summary") or "", b.get("persona") or ""]
    if led:
        identity.analyze(led, full, known, kind)      # relevant claims, topic change (first pass: before the memory search)
        cts = [(set(lx.terms(x["quote"])), x["quote"]) for x in led["claims"]]

        def veto(text):   # a stored memory that disagrees with the user's own words is not shown
            t = rstore.resolve(text, user, c.get("name") or "Character")
            tt = set(lx.terms(t))
            return any(ct & tt and identity.claims.conflict(q, t) for ct, q in cts)
    rc = None   # search the memory once per reply (the retries below reuse it)
    if rcfg["on"] and cid != NARR_ID:
        rc = recall.select(b.get("state"), hist, user=user, char=c.get("name") or "Character", cfg=rcfg, turn=turns,
                           known_extra=[m_.get("name") for m_ in (grp or {}).get("members", [])], fresh=bool(led and led["fresh"]), veto=veto)
    if led:   # now that the memory search is done, "does anyone know this?" can include what it found
        identity.analyze(led, full, known + [t_["text"] for t_ in (rc or {}).get("trace", [])] + list((rc or {}).get("short", [])), kind)
        id_tail = identity.tail_notes(led)
    chron = (b.get("state") or {}).get("chron") if isinstance((b.get("state") or {}).get("chron"), dict) else None
    qtxt = " ".join(str(m.get("content") or "") for m in hist[-3:])
    chron_add = []
    pool, id_pool, cands, grams = [], [], [], None
    best, retry_note, tries, dropped, used = None, "", 0, 0, 0
    tlog, spent, first_wall, last_wall = [], 0.0, 0.0, 0.0   # what fired, and the time the attempts took
    quick = bool(p.get("quick", False))   # Quick replies: at most one re-roll, and only for real mistakes (not for style nits)
    tries_max = 2 if quick else 3
    for attempt in range(tries_max):
        tries = attempt
        t_att = time.monotonic()
        o = dict(state=b.get("state"), persona=b.get("persona"), scene=b.get("scene"), clock=b.get("clock"), sim=sim, amb=amb,
                 gap_s=gap_s, mode=mode, actions=p.get("actions", True), realism=p.get("realism", True),
                 natural=p.get("natural", 2), think=think, fast=bool(p.get("fast", False)), fold=p.get("fold", False), words=(lo, hi), length=p.get("length", "auto"), tail=tail,
                 retry_note=retry_note, group=grp, rp=b.get("rp"), own=own, pers=p.get("pers"), mem=p.get("mem"), recall=rc, turn=turns,
                 ledger=led, id_tail=id_tail, full=full, trimmed=trimmed, story=sto,
                 ooc=clean_notes((b.get("ooc") or {}).get("notes")), private=[], dir=dplan)
        budget = cap + (1500 if think else 0)
        level = 0
        while True:     # the context governor: if the prompt is heavy, carry less of the bulky layers (never the details: those live in the chronicle)
            plan = chronicle.budget(n_ctx, budget, level)
            h_use, h_drop = chronicle.trim_history(hist, plan["hist"], key=(cid, level, len(full) - len(hist)))
            lines = chronicle.pick(chron, qtxt, turns, plan["chron"], veto) if chron else []
            kb = keeper.render((b.get("state") or {}).get("keep"), qtxt, turns, int(plan["chron"] * .9), user, c.get("name") or "Character") if cid != NARR_ID else ""
            pb = keeper.past_block(b.get("past"), user, c.get("name") or "Character", 240 if level < 2 else 0) if cid != NARR_ID and not grp else ""
            o.update(squeeze=plan, chron_block=chronicle.render(lines, user, c.get("name") or "Character"), keep_block=kb, past_block=pb, private=[])
            msgs = build_messages(c, user, h_use, o)
            if sum(ntok(m["content"]) for m in msgs) <= plan["target"] or level >= 3:
                break
            level += 1
        grams = leak.corpus(o["private"])      # the private background of this attempt, to notice a reply that copies it
        used, dropped = fit(msgs, plan["room"])
        if h_drop:      # messages that left the window: make sure their details are in the chronicle (the page keeps them for the next track)
            cov = (chron or {}).get("covered", 0)
            chron_add = [f for f in chronicle.extract(h_drop, user, c.get("name") or "Character", start) if f["turn"] >= cov]
        dropped += len(h_drop)
        budget = max(128, min(budget, n_ctx - used - 16))
        if send and p.get("stream"):
            send({"rs": attempt + 1})    # a new attempt starts: the page clears its live preview
        def view(t):   # what the page may show while the reply is still being written
            return preview_reply(t, user, c.get("name") or "Character", mode, others, p.get("actions", True), p.get("length", "auto"), hi,
                                 kind in ("reply", "resume", "nudge"))
        raw, fin, ntoks, secs = run_llm(msgs, samp, stop, budget, send, bool(p.get("stream")), view)
        r = finish_reply(raw, fin, user, c.get("name") or "Character", mode, others, narrate=p.get("actions", True), private=grams)
        if kind in ("reply", "resume", "nudge") and not r["empty"]:
            r["text"] = cap_reply(r["text"], mode, p.get("length", "auto"), hi)
        r.update(tok=ntoks, ms=int(secs * 1000), finish=fin)
        if grp and (b.get("cue") or {}).get("pass") and re.fullmatch(r"\W*(?:pass|silent|stays? silent)\W*", r["text"].lower()):
            return {"pass": True, "text": "", "think": "", "tok": ntoks, "ms": r["ms"], "ctx_used": used, "ctx": n_ctx, "dropped": dropped}
        if r["empty"]:  # thinking ate the whole budget, or nothing came back: try again without thinking (always allowed: there is nothing to show)
            dt = time.monotonic() - t_att
            spent += dt
            first_wall = first_wall or dt
            last_wall = dt
            tlog.append(dict(attempt=attempt, rules=["empty"], retried=attempt < tries_max - 1, why_not="" if attempt < tries_max - 1 else "cap", ms=int(dt * 1000)))
            think = False
            if r.get("leak"):
                retry_note = "Your last attempt was only instruction text. Write what the character says and does, nothing else."
            elif r.get("scrubbed"):
                retry_note = ("Your last attempt was only field names, headings, times or ratings. Write what the character says and does in the story, "
                              "and show feelings and time through behaviour and words.")
            continue
        best = r
        r["_rep"] = repeat.worst(r["text"], seen_before)[0] if kind in ("reply", "resume", "nudge") else 0.0
        cands.append(r)
        ig = identity.check(r["text"], led, mode) if led and kind in ("reply", "resume", "nudge") else None
        pre_ig = r["text"]
        if ig:
            r["text"] = ig["text"]                     # repairable slips (the model wrote the user's lines) are cut out right away
            r["_ni"] = len(ig["issues"])
            id_pool.append(r)
            if ig["issues"]:
                r["identity"] = ig["issues"]
        pg = personality.check_reply(c, b.get("state"), r["text"], [THINK.sub("", m["content"]) for m in own][-6:], mode, pcfg) if guard_on else None
        if pg:
            r["pers"] = {"score": pg["score"], "flags": pg["flags"], "retries": attempt}
            pool.append(r)
        ai_hard = bool(personality.lexicon.AI_HARD.search(r["text"]))
        ai_soft = bool(personality.lexicon.AI_SOFT.search(r["text"]))
        cn = c.get("name") or "Character"
        fired = []      # (rule, note for a retry): every check that tripped on this attempt, whether or not it earns a retry
        if r.get("flip"):    # the reply was headed 'Reply as <the user>': the model took the user's seat
            fired.append(("user_voice", f"You are {cn}, not {user}. {user} is the other person; never write as {user}."))
        elif r.get("leak"):
            fired.append(("leak", "Do not write brackets, labels or instructions. Output only what the character says and does."))
        if r["scrubbed"] and len(r["text"].split()) < 4:     # echoed state is only a hard failure when nothing real is left
            fired.append(("scrubbed", f"Do not write field names, headings, times, moods, ratings or scene summaries. {cn} only says and does things in the story; "
                                      "show feelings and time through behaviour and words."))
        elif r["echo"]:      # copied private background: cut the copied sentences now; only a reply that was mostly a copy is worth a retry
            fixed = leak.drop_echo_sentences(r["text"], grams) if grams else r["text"]
            if fixed.strip():
                r["text"] = fixed
            fired.append(("echo_all" if len(fixed.split()) < 4 else "echo",
                          f"You copied wording from your private background. Never quote it; say it in {cn}'s own words, or leave it out."))
        tn = simtime.time_note(r["text"], sim) if kind in ("reply", "nudge") else ""
        if tn:
            fired.append(("time", tn))
        qn = story.check(r["text"], sto.get("plan")) if kind in ("reply", "nudge", "resume") and scfg["endings"] else ""
        if qn:
            fired.append(("ending", qn))       # story.repair cuts an unwanted closing question below
        en = ambience.env_note(r["text"], amb, sim) if kind in ("reply", "nudge") else ""
        if en:
            fired.append(("env", en))
        if kind == "reply" and last_user and similar(r["text"], [last_user]) and len(last_user.split()) > 3:
            fired.append(("parrot", f"You repeated {user}'s own message. Respond as {cn} with your own words, thoughts and decision."))
        for code in (ig["issues"] if ig else []):
            # the user's lines cut out of the reply are already repaired; every other slip needs a new generation (a wrong pronoun is only flagged)
            fired.append(("identity_user_cut" if code == "speaks_for_user" and r["text"] != pre_ig else "identity_" + code, ig["note"]))
        if ai_hard or ai_soft:                 # the assistant sentences are cut out of the final reply below
            fired.append(("ai_speak", f"CRITICAL: Do NOT talk like an AI assistant or chatbot (no 'How are you doing today?', 'casual conversation', 'I'm here if you'd like to chat', 'What brings you here?'). You are {cn}, a living person in this scene. Speak and act strictly from their perspective."))
        elif pg and pg["retry"] and pg["note"]:
            fired.append(("persona_hard" if pg.get("hard") else "persona", pg["note"]))
        pi = director.pattern_issue(r["text"], prevs, mode) if dcfg["on"] and kind in ("reply", "resume", "nudge") else None
        if pi:
            fired.append((pi, f"Your last attempt opened with the same words as one of {cn}'s recent messages. Open with something different."))
        if r["_rep"] >= repeat.SOFT:
            who = "someone else in the scene" if grp and repeat.worst(r["text"], spoken_by_others)[0] >= repeat.SOFT else f"{cn}'s own earlier message"
            fired.append(("dup" if r["_rep"] >= repeat.HARD else "repeat",
                          f"Your last attempt repeated what was already said by {who}. Say something clearly different: a new beat, new words, a new action."))
        dt = time.monotonic() - t_att
        spent += dt
        first_wall = first_wall or dt
        last_wall = dt
        todo = [(rl, nt) for rl, nt in fired if (rl in HARD_RETRY and not (quick and rl in QUICK_SKIP)) or (rl in SOFT_RETRY and not quick)]
        r["_hard"] = sum(1 for rl, _ in fired if rl in HARD_RETRY)
        r["_fired"] = [rl for rl, _ in fired]
        why_not = ""
        if todo:
            if attempt >= tries_max - 1:
                why_not = "cap"
            elif spent + min(first_wall, last_wall) > TIME_BUDGET * first_wall:      # the next attempt would break the time budget
                why_not = "budget"
        if fired:
            tlog.append(dict(attempt=attempt, rules=[rl for rl, _ in fired], retried=bool(todo) and not why_not, why_not=why_not, ms=int(dt * 1000)))
        if todo and not why_not:
            if any(rl in ("dup", "repeat") for rl, _ in todo):
                samp = dict(samp, temperature=min(1.4, samp["temperature"] + .15), repeat_penalty=min(1.5, samp["repeat_penalty"] + .05))
            retry_note = " ".join(dict.fromkeys(nt for _, nt in todo if nt))
            continue
        break
    if id_pool:          # out of attempts: prefer the attempts with the fewest identity mistakes
        fewest = min(x["_ni"] for x in id_pool)
        if best and best.get("_ni", 0) > fewest:
            best = [x for x in id_pool if x["_ni"] == fewest][-1]
        pool = [x for x in pool if x.get("_ni", 0) == fewest]
    if len(pool) > 1:    # out of attempts: keep the reply that stayed most in character
        best = max(pool, key=lambda x: x["pers"]["score"])
        best["pers"]["retries"] = tries
    clean = [x for x in cands if not x.get("_hard")]
    if best and best.get("_hard") and clean:      # a later attempt that failed hard (no retry left) loses to an earlier one that did not
        best = clean[-1]
    if best and (personality.lexicon.AI_HARD.search(best["text"]) or personality.lexicon.AI_SOFT.search(best["text"])):
        # Clean out any AI confession / assistant sentences if they persisted across retries
        cleaned_sents = [s for s in re.split(r"(?<=[.!?…])\s+", best["text"])
                         if not (personality.lexicon.AI_HARD.search(s) or personality.lexicon.AI_SOFT.search(s))]
        best["text"] = " ".join(cleaned_sents).strip()
        if not best["text"]:
            cname = c.get("name") or "Character"
            best["text"] = f"*{cname} looks at {user}, unsure of what to say.*"
    if not best:
        raise RuntimeError("The model returned an empty reply. Try again, or turn Thinking off.")
    if len(cands) > 1 and best.get("_rep", 0) >= repeat.SOFT:   # out of attempts: the least repetitive one wins
        alt = min(cands, key=lambda x: x["_rep"])
        if alt["_rep"] + .1 <= best["_rep"]:
            best = alt
    if grp and best.get("_rep", 0) >= repeat.HARD and (b.get("cue") or {}).get("why") not in ("mention", "react") and repeat.worst(best["text"], spoken_by_others)[0] >= repeat.HARD:
        return {"pass": True, "text": "", "think": "", "tok": best.get("tok", 0), "ms": best.get("ms", 0), "ctx_used": used, "ctx": n_ctx, "dropped": dropped}   # someone just said exactly this: stay quiet
    if best.get("echo") and grams:   # retries ran out: take out only the sentences that are almost entirely copied
        best["text"] = leak.drop_echo_sentences(best["text"], grams)
    if scfg["endings"] and kind in ("reply", "nudge", "resume") and sto.get("plan"):
        best["text"] = story.repair(best["text"], sto["plan"])      # out of attempts: a closing question that is not wanted is cut, never kept
    best["world"] = sto.get("info") or {}
    if dplan and dplan.get("dyn"):
        best["dyn"] = dict(dplan["dyn"], len=director.len_class(best["text"], mode))
    if reg and kind in ("reply", "resume", "nudge", "continue"):
        best["text"] = personality.register.repair(best["text"], reg)   # whatever else slipped, a formal or archaic voice never keeps contractions
    best.pop("_ni", None)
    best.pop("_rep", None)
    best.pop("_hard", None)
    best["flags"] = sorted(set(best.pop("_fired", []) or []))      # what tripped on the reply that was kept: flagged, not retried
    best["retry_log"] = tlog
    if tlog:
        log_retries(dict(t=int(time.time()), kind=kind, mode=mode, attempts=tries + 1, ms=int(spent * 1000), events=tlog, kept=best["flags"]))
    best["leaks"] = sorted(set(best.pop("scrubbed", []) or []) | ({"echo"} if best.pop("echo", None) else set()))
    best.pop("scrubbed_text", None)
    best.update(ctx_used=used, ctx=n_ctx, dropped=dropped, retries=tries, squeeze=level, chron_add=chron_add,
                chron_used=[i["id"] for i in lines] if chron else [])
    if rc is not None:
        best.update(recalled=rc["ids"], recall=[{"id": t["id"], "t": t["t"], "why": t["why"]} for t in rc["trace"]])
    return best
