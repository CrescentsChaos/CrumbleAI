"""Running the model: token budgeting, sampling, and the full reply pipeline."""
import re
import time

from . import personality, recall
from .config import CH, LLM, US
from .prompt import build_messages, cue_text
from .rp.narrator import NARR_ID
from .rp.ooc import KINDS as OOC_KINDS, clean_notes, finish_ooc, ooc_messages, ooc_words
from .textutil import THINK, finish_reply, human_gap, similar, want_words


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


def run_llm(msgs, samp, stop, cap, send=None):
    """Stream tokens internally (so Stop works and progress can be shown) but hand back only the finished text."""
    t0, txt, fin, n = time.time(), "", None, 0
    for ch in LLM["obj"].create_chat_completion(messages=msgs, stream=True, max_tokens=cap, stop=stop, **samp):
        c = ch["choices"][0]
        d = c["delta"].get("content")
        if d:
            txt += d
            n += 1
            if send and n % 6 == 0:
                send({"p": "think" if txt.rfind("<think>") > txt.rfind("</think>") else "reply", "n": n})
        if c.get("finish_reason"):
            fin = c["finish_reason"]
    return txt, fin, n, time.time() - t0


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
        raw, fin, ntoks, secs = run_llm(msgs, samp, stop, budget, send)
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
    hist = [m for m in hist if not m.get("ooc")]   # out-of-character talk is never heard by the characters (the author's notes carry what matters)
    mode = p.get("mode", "story")
    n_ctx = LLM["n_ctx"]
    start = int(b.get("from") or 0)
    turns = int(b.get("turn") or len(hist))   # position in the whole chat, which out-of-character messages also count toward
    hist = hist[start:] if 0 < start < len(hist) else hist
    last_user = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
    lo, hi = want_words(mode, p.get("length", "auto"), last_user)
    if grp:
        lo, hi = max(6, int(lo * .7)), max(14, int(hi * .75))
        if cid == NARR_ID and p.get("length", "auto") == "auto":
            lo, hi = 35, 110
    if kind == "continue":
        lo, hi = 25, 90
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
    elif grp:
        tail = cue_text(b, c)
    own = [m for m in hist if m["role"] == "assistant" and (not grp or m.get("cid") == cid)]
    prevs = [THINK.sub("", m["content"]) for m in own][-3:]
    others = [m.get("name") or "" for m in (grp or {}).get("members", []) if m.get("id") != cid and m.get("name")] + ([] if not grp or cid == NARR_ID else ["Narrator"])
    stop = ["\n" + user + ":", "\n" + user + " :", "\n**" + user + ":"] + [s for o_ in others for s in ("\n" + o_ + ":", "\n**" + o_ + ":")]
    samp = sampler(p)
    pcfg = personality.settings(p.get("pers"))
    guard_on = personality.active(c, pcfg) and pcfg["guard"] and kind in ("reply", "nudge")
    rcfg = recall.settings(p.get("mem"))
    rc = None   # search the memory once per reply (the retries below reuse it)
    if rcfg["on"] and cid != NARR_ID:
        rc = recall.select(b.get("state"), hist, user=user, char=c.get("name") or "Character", cfg=rcfg, turn=turns,
                           known_extra=[m_.get("name") for m_ in (grp or {}).get("members", [])])
    pool = []
    best, retry_note, tries, dropped, used = None, "", 0, 0, 0
    for attempt in range(3):
        tries = attempt
        o = dict(state=b.get("state"), persona=b.get("persona"), scene=b.get("scene"), clock=b.get("clock"),
                 gap_s=b.get("gap_s"), mode=mode, actions=p.get("actions", True), realism=p.get("realism", True),
                 natural=p.get("natural", 2), think=think, fold=p.get("fold", False), words=(lo, hi), tail=tail,
                 retry_note=retry_note, group=grp, rp=b.get("rp"), own=own, pers=p.get("pers"), mem=p.get("mem"), recall=rc, turn=turns,
                 ooc=clean_notes((b.get("ooc") or {}).get("notes")))
        msgs = build_messages(c, user, hist, o)
        budget = cap + (1500 if think else 0)
        used, dropped = fit(msgs, n_ctx - budget - 16)
        budget = max(128, min(budget, n_ctx - used - 16))
        raw, fin, ntoks, secs = run_llm(msgs, samp, stop, budget, send)
        r = finish_reply(raw, fin, user, c.get("name") or "Character", mode, others)
        r.update(tok=ntoks, ms=int(secs * 1000), finish=fin)
        if grp and (b.get("cue") or {}).get("pass") and re.fullmatch(r"\W*(?:pass|silent|stays? silent)\W*", r["text"].lower()):
            return {"pass": True, "text": "", "think": "", "tok": ntoks, "ms": r["ms"], "ctx_used": used, "ctx": n_ctx, "dropped": dropped}
        if r["empty"]:  # thinking ate the whole budget, or nothing came back: try again without thinking
            think = False
            continue
        best = r
        pg = personality.check_reply(c, b.get("state"), r["text"], [THINK.sub("", m["content"]) for m in own][-6:], mode, pcfg) if guard_on else None
        if pg:
            r["pers"] = {"score": pg["score"], "flags": pg["flags"], "retries": attempt}
            pool.append(r)
        ai_hard = bool(personality.lexicon.AI_HARD.search(r["text"]))
        ai_soft = bool(personality.lexicon.AI_SOFT.search(r["text"]))
        notes = []
        if (ai_hard or ai_soft) and attempt < 2:
            notes.append(f"CRITICAL: Do NOT talk like an AI assistant or chatbot (no 'How are you doing today?', 'casual conversation', 'I'm here if you'd like to chat', 'What brings you here?'). You are {c.get('name') or 'Character'}, a living person in this scene. Speak and act strictly from their perspective.")
        elif kind == "reply" and attempt < 2 and similar(r["text"], prevs):
            samp = dict(samp, temperature=min(1.4, samp["temperature"] + .15), repeat_penalty=samp["repeat_penalty"] + .05)
            notes.append("Your last attempt was too close to an earlier reply. Say something clearly different.")
        elif pg and pg["retry"] and attempt < 2 and pg["note"]:
            notes.append(pg["note"])
        if notes:
            retry_note = " ".join(notes)
            continue
        break
    if len(pool) > 1:    # out of attempts: keep the reply that stayed most in character
        best = max(pool, key=lambda x: x["pers"]["score"])
        best["pers"]["retries"] = tries
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
    best.update(ctx_used=used, ctx=n_ctx, dropped=dropped, retries=tries)
    if rc is not None:
        best.update(recalled=rc["ids"], recall=[{"id": t["id"], "t": t["t"], "why": t["why"]} for t in rc["trace"]])
    return best
