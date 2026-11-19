"""Voice: a fingerprint of how the character writes, and a guard that scores a finished reply against it."""
import re
import statistics

from . import canon as cn
from . import lexicon as lx
from . import register as rg


def spoken(text):
    t = re.sub(r"\*[^*\n]*\*", " ", text or "")
    return re.sub(r"\([^)\n]*\)", " ", t).strip()


def metrics(text):
    s = spoken(text)
    words = re.findall(r"[\w']+", s)
    sents = [x for x in re.split(r"(?<=[.!?…])\s+", s) if x.strip()] or [s]
    n = max(1, len(words))
    return {"words": len(words), "sents": len(sents),
            "excl": s.count("!") / max(1, len(sents)), "emoji": len(lx.EMOJI.findall(s)),
            "contr": 100 * len(lx.CONTRACTION.findall(s)) / n, "ellipsis": s.count("...") + s.count("…"),
            "caps_start": sum(1 for x in sents if x.strip()[:1].isupper()) / max(1, len(sents))}


def example_lines(c):
    """The character's own lines from the example dialogue."""
    name = re.escape((c.get("name") or "").strip())
    pat = r"\s*(?:\{\{char\}\}|%s)\s*:\s*(.*)" % name if name else r"\s*\{\{char\}\}\s*:\s*(.*)"
    mine, cur = [], None
    for ln in (c.get("mes_example") or "").replace("\r", "").split("\n"):
        m = re.match(pat, ln, re.I)
        if m:
            cur = True
            mine.append(m.group(1))
        elif re.match(r"\s*(?:\{\{user\}\}|<START>|[A-Z][\w ]{0,20}):", ln):
            cur = False
        elif cur and ln.strip():
            mine[-1] += " " + ln.strip()
    return [x for x in mine if spoken(x)]


def fingerprint(c):
    lines = example_lines(c)
    if len(lines) < 2:
        return None
    ms = [metrics(x) for x in lines]
    return {"n": len(ms), "words": statistics.median(m["words"] for m in ms),
            "excl": sum(m["excl"] for m in ms) / len(ms), "emoji": sum(m["emoji"] for m in ms) / len(ms),
            "contr": sum(m["contr"] for m in ms) / len(ms)}


def check(c, prof, text, own, mode="story", canon=None, fp=None, threshold=65):
    """Score a reply 0-100 for staying in character. -> {'score','flags':[str],'retry':bool,'hard':bool,'note':str}"""
    t, voice, rules = prof["traits"], prof["voice"], prof["rules"]
    s, m = spoken(text), metrics(text)
    found = []      # (penalty, flag, instruction for a retry)
    hard = False    # the reply is plainly not in the register the sheet requires: worth a re-roll even in Quick mode

    if lx.AI_HARD.search(text):
        found.append((100, "breaks character (talks like an AI)", f"CRITICAL: Never mention being an AI, bot, chatbot, or assistant. You are {c.get('name') or 'Character'}, a living person in the scene. Speak strictly as this character."))
    elif lx.AI_SOFT.search(text):
        # count how many distinct AI-assistant patterns appear
        ai_hits = len(lx.AI_SOFT.findall(text))
        penalty = min(80, 50 + 15 * (ai_hits - 1))
        found.append((penalty, "assistant-style phrasing", f"Do not talk like a helpful assistant or chatbot. Never say 'How are you doing today?', 'casual conversation', 'I'm here if you'd like to chat', 'What brings you here today?'. You are {c.get('name') or 'Character'}. Stay completely in character in the scene."))
    reg = rg.detect(c, mode)
    if reg:
        rf, hard = rg.audit(reg, text)
        found += rf
    if lx.LIST_LINE.search(text):
        found.append((15, "uses list or heading formatting", "Write in natural speech, not lists or headings."))

    if s and m["words"] >= 12:
        casual, formal = t["formality"] <= 35, t["formality"] >= 70
        if casual and not m["contr"] and not lx.SLANG.search(s) and lx.FORMAL_MARK.search(s):
            found.append((14, "too formal for this character", "Speak casually: contractions, short sentences, no stiff words."))
        elif formal and (m["contr"] > 6 or len(lx.SLANG.findall(s)) >= 2):
            found.append((14, "too casual for this character", "Speak more formally and properly, without slang."))
        elif fp and fp["contr"] >= 3 and m["words"] >= 20 and m["contr"] == 0:
            found.append((8, "stiffer than their usual voice", "Use contractions the way this character normally does."))
    if (t["expressiveness"] <= 30 or t["extraversion"] <= 25) and m["excl"] > .5 and m["words"] >= 6:
        found.append((10, "more excitable than this character", "Understate it: fewer exclamation marks, flatter delivery."))
    if m["emoji"] and (voice["no_emoji"] or (t["formality"] >= 65 and not voice["emoji"]) or (fp and fp["emoji"] == 0 and m["emoji"] >= 2)):
        found.append((12, "emoji out of character", "Do not use emoji."))
    if t["agreeableness"] <= 30 and len(lx.GUSH.findall(s)) >= 2:
        found.append((10, "gushes more than this character would", "Be drier and less effusive; this character does not gush."))
    if t["agreeableness"] >= 75 and lx.HARSH.search(s):
        found.append((12, "harsher than this character", "Keep it gentle: this character does not insult people."))

    base = [metrics(x)["words"] for x in (own or [])[-6:] if x.strip()]
    ref = statistics.median(base) if len(base) >= 3 else (fp["words"] if fp else None)
    if ref and m["words"] >= 8:
        if m["words"] > max(30, 3 * ref):
            found.append((10, "much longer than their usual replies", f"Keep it short, around {int(ref * 1.5)} words."))
        elif ref >= 12 and m["words"] < ref / 5:
            found.append((5, "much shorter than usual", ""))

    for ln in rules["never"]:
        low = ln.lower()
        if re.search(r"swear|curs|profan|foul", low) and lx.PROFANITY.search(s):
            found.append((25, "breaks a rule: " + ln[:50], "Rule: " + ln))
        elif "emoji" in low and m["emoji"]:
            found.append((20, "breaks a rule: " + ln[:50], "Rule: " + ln))
        elif re.search(r"\b(?:say|says|use|uses|word|phrase|call)\b", low):
            for q in re.findall(r"[\"“']([^\"”']{2,30})[\"”']", ln):
                if q.lower() in s.lower():
                    found.append((25, f"said '{q}' against a rule", "Rule: " + ln))
    for ln in rules["always"]:
        if re.search(r"lowercase|no caps", ln.lower()) and m["words"] >= 6 and m["caps_start"] > .5:
            found.append((10, "not in lowercase", "Rule: " + ln))
    if voice["lowercase"] and mode == "text" and m["words"] >= 6 and m["caps_start"] > .6:
        found.append((8, "capitalised like a formal writer", "Text in lowercase, the way this character does."))

    for old, new in cn.contradictions(text, canon)[:2]:
        found.append((30, f"contradicts earlier: '{old[:50]}'", f"Stay consistent with what you said before: \"{old}\"."))

    found.sort(key=lambda x: -x[0])
    score = max(0, 100 - sum(p for p, _, _ in found))
    notes = [fix for _, _, fix in found if fix][:3]
    return {"score": score, "flags": [f for _, f, _ in found][:4], "retry": score < threshold, "hard": hard and score < threshold,
            "note": ("Your last attempt was off-voice. " + " ".join(notes)) if notes else ""}
