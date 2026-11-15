"""Mood, affection and long-term memory: the small model calls that run after each reply."""
import copy
import difflib
import re
import time

from . import personality, recall
from .config import EMO, LLM, LOCK
from .textutil import THINK, loose_json, trim_sentence


POS = "thank love great awesome amazing happy glad sweet nice miss proud cute best haha lol appreciate".split()
NEG = "hate stupid idiot shut ugly boring worst annoying useless dumb liar sucks".split()


def _ask(prompt, max_tokens=380):
    """One plain model call (used by the memory system for important moments)."""
    with LOCK:
        r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": prompt}], temperature=.3, max_tokens=max_tokens)
    return THINK.sub("", r["choices"][0]["message"]["content"])


def track(b):
    c, user, hist, st = b["char"], b["user"], b["history"][-6:], dict(b.get("state") or {})
    rcfg = recall.settings(b.get("mem"))
    if rcfg["on"] and isinstance(st.get("mem"), dict):
        st["mem"] = copy.deepcopy(st["mem"])
    n = c.get("name") or "Character"
    aff, facts = int(st.get("affection", 50)), [str(f) for f in st.get("facts", [])]
    convo = "\n".join(f"{(m.get('name') or n) if m['role'] == 'assistant' else user}: {THINK.sub('', m['content'])[:500]}" for m in hist)
    ask = (f"You track the inner state of a roleplay character named {n}. Personality: {(c.get('personality') or c.get('description') or '')[:400]}\n"
           f"Previous mood: {st.get('mood', 'neutral')}. Affection toward {user} (0-100): {aff}.\n"
           f"Facts already known about {user}: {'; '.join(facts[-15:]) or 'none'}\n\nLatest messages:\n{convo}\n\n"
           f"Reply with ONLY a JSON object: {{\"mood\": one lowercase word for how {n} feels now, \"energy\": \"low\" or \"medium\" or \"high\", "
           f"\"affection_delta\": integer from -5 to 5 (how this exchange changed {n}'s feelings toward {user}; 0 if nothing changed), "
           f"\"thought\": \"one short private first-person thought of {n}, max 20 words\", "
           f"\"facts\": [new durable facts {n} learned about {user} in these messages; empty list if none]}}. /no_think")
    pcfg = personality.settings(b.get("pers"))
    pers_on = personality.active(c, pcfg)
    if pers_on:
        prof = personality.profile_for(c)
        if prof["summary"]:
            ask = ask.replace("Reply with ONLY a JSON object:", f"Temperament: {prof['summary']}. Reply with ONLY a JSON object:", 1)
        if pcfg["canon"]:
            ask = ask.replace("]}. /no_think", f"], \"self_facts\": [durable things {n} said about themself in these messages (job, history, likes, dislikes, habits, promises); empty list if none]}}. /no_think")
    if rcfg["on"]:   # short-term memory and a memorability rating ride along in the same call: no extra cost per reply
        ask = ask.replace("]}. /no_think", f"], \"scene\": \"one short sentence: where {n} and {user} are and what is going on right now (max 20 words)\", "
                                           f"\"event\": \"one short sentence on what just happened in this exchange, or empty if nothing notable (max 18 words)\", "
                                           f"\"importance\": integer 0-10 (how memorable this exchange is for {n}; 0 for small talk, 8+ for gifts, promises, fights, confessions)}}. /no_think")
    with LOCK:
        r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}], temperature=.4,
                                              max_tokens=(360 if pers_on else 300) + (110 if rcfg["on"] else 0))
    txt = r["choices"][0]["message"]["content"]
    try:
        j = loose_json(txt)
    except Exception:
        last = next((m["content"].lower() for m in reversed(hist) if m["role"] == "user"), "")
        d = sum(w in last for w in POS) - 2 * sum(w in last for w in NEG)
        j = {"affection_delta": max(-3, min(2, d)), "mood": st.get("mood", "neutral"), "thought": "", "facts": []}
    mood = re.sub(r"[^a-z]", "", str(j.get("mood", "neutral")).lower())[:14] or "neutral"
    try:
        delta = max(-5, min(5, int(j.get("affection_delta", 0))))
    except Exception:
        delta = 0
    energy = j.get("energy") if j.get("energy") in ("low", "medium", "high") else st.get("energy", "medium")
    mood_before = st.get("mood", "neutral")
    score = None
    if pers_on and (pcfg["dyn"] or pcfg["canon"]):   # the personality bounds and shapes what the model proposed
        res = personality.after_turn(c, st, j, mood, delta, b["history"], user, pcfg)
        mood, delta, st["pers"], score = res["mood"], res["delta"], res["pers"], res["score"]
        energy = res["energy"] or energy
    st.update(mood=mood, emoji=EMO.get(mood, "🙂"), affection=max(0, min(100, aff + delta)), energy=energy)
    new = j.get("facts") if isinstance(j.get("facts"), list) else []
    for f in new[:3]:
        f = str(f).strip().rstrip(".")
        if 3 < len(f) < 160 and not any(difflib.SequenceMatcher(None, f.lower(), o.lower()).ratio() > .8 for o in facts):
            facts.append(f)
    st["facts"] = facts[-40:]
    thought = str(j.get("thought", "")).strip()[:200]
    st["log"] = (st.get("log") or [])[-59:] + [{"ts": int(time.time() * 1000), "mood": mood, "emoji": st["emoji"],
                                                  "aff": st["affection"], "thought": thought}]
    if score is not None:
        st["log"][-1]["score"] = score
    out = {"state": st, "thought": thought, "delta": delta}
    if rcfg["on"]:   # hierarchical memory: short-term, semantic facts, and (for important moments) an episode + its feeling
        turn = int(b.get("turn") or ((st.get("mem") or {}).get("turn", 0) + 2))
        rec = recall.update(st, j, b["history"], user=user, char=n, persona=(c.get("personality") or c.get("description") or ""), cfg=rcfg,
                            turn=turn, delta=delta, mood_before=mood_before, mood_after=mood, ask=_ask, used=b.get("used") or [])
        out.update(mem_added=rec["added"], moment=rec["moment"]["score"])
    return out


def identity_line(c, n):
    """Fixed facts from the sheet, so the summary copies them instead of guessing (small models love to invent ages)."""
    bits = [f"{l}: {str(c.get(k)).strip()}" for k, l in (("age", "age"), ("gender", "gender"), ("species", "species"), ("occupation", "occupation"))
            if str(c.get(k) or "").strip()]
    return (f"Fixed facts about {n} from the character sheet (copy them exactly, never change them): " + "; ".join(bits) + ".\n") if bits else ""


def summarize(b):
    c, user = b["char"], b["user"]
    n = c.get("name") or "Character"
    convo = "\n".join(f"{(m.get('name') or n) if m['role'] == 'assistant' else user}: {THINK.sub('', m['content'])[:700]}" for m in b["history"])
    ask = (identity_line(c, n) + f"Previous memory notes: {b.get('summary') or 'none'}\n\nNew events to fold in:\n{convo}\n\n"
           f"Update the memory using the conversation above. Return only these sections and fields, in this order:\n"
           f"CHARACTERS\n{n}: [important traits, facts, and current situation]\n{user}: [important traits, facts, and current situation]\n"
           "SETTING & STATE\nLocation: [where they are]\nCurrent State: [what is happening now]\n"
           "RELATIONSHIP DYNAMIC\nPrimary Dynamic: [how their relationship currently works and how it has changed]\n"
           "Tone: [the emotional tone between them]\n"
           "PIVOTAL MOMENTS\n- [important events, statements, or promises; include prior pivotal moments that still matter]\n"
           "Keep every heading and field, use concise specific details, and write \"Not established\" when the chat does not provide an answer. "
           "Never guess or estimate anyone's age: only write an age if it is in the fixed facts, the previous notes or the chat itself. "
           "Fold the new events into the previous notes without losing still-relevant facts. No preamble. /no_think")
    with LOCK:
        r = LLM["obj"].create_chat_completion(messages=[{"role": "user", "content": ask}], temperature=.3, max_tokens=450)
    ch = r["choices"][0]
    txt = THINK.sub("", ch["message"]["content"]).strip()
    return trim_sentence(txt) if ch.get("finish_reason") == "length" else txt


def memorize(b):
    """Build memories from a chat that already exists (the Memory tab's "Build memories from this chat")."""
    c, user, st = b["char"], b["user"], copy.deepcopy(dict(b.get("state") or {}))
    rcfg = recall.settings(dict(b.get("mem") or {}, on=True))
    res = recall.backfill(st, b.get("history") or [], user=user, char=c.get("name") or "Character",
                          persona=(c.get("personality") or c.get("description") or ""), cfg=rcfg, ask=_ask, max_calls=int(b.get("max_calls") or 8))
    return {"state": st, "added": len(res["added"]), "calls": res["calls"], "scanned": res["scanned"]}
