"""How a message ends. Real people do not finish every line with a question: they state, shrug, tease, trail off, change the subject, or just do something.

    history(own)                         [bool] for the character's recent replies: did each one END on a question?
    plan(own, moment, turn, cid, ...)    {'ban': bool, 'how': one way to end this reply, 'rule': the instruction}
    ends_on_question(text)               does this reply end by asking something (a short action after it does not hide it)?
    check(text, plan)                    '' when fine, else a note for a retry
    repair(text, plan)                   when the retries ran out: cut the closing question instead of keeping it
Pure functions; a reply is read as speech (plain text) and narration (*between stars*).
"""
import re
import zlib

_SEG = re.compile(r"\*[^*]*\*|[^*]+")
_SENT = re.compile(r"[^.!?…]+(?:[.!?…]+|$)")
THINK = re.compile(r"<think>.*?(?:</think>|$)", re.S)

STYLES = [
    "a plain statement: an opinion, a fact, a reaction",
    "a small action or gesture, with no spoken line after it",
    "a dry aside or a quick joke, if it suits them",
    "a thought that trails off, unfinished",
    "a change of subject to something in their own day or in the surroundings",
    "a reaction to something in the surroundings (the weather, a sound, the light, the time)",
    "one short blunt line",
    "something left unsaid: a look, a pause, a shrug, a glance away",
    "what they are about to do next, said casually",
    "a small thing from their own day, offered without asking for anything back",
    "a mild disagreement or a stubborn little 'we'll see'",
    "a warm, simple sentence that needs no answer",
]


def _clean(t):
    return THINK.sub("", t or "").strip()


def _segments(text):
    out = []
    for m in _SEG.finditer(_clean(text)):
        s = m.group(0)
        if s.startswith("*") and s.endswith("*") and len(s) > 1:
            out.append(("n", s[1:-1]))
        elif s.strip():
            out.append(("s", s))
    return out


def ends_on_question(text):
    """True when the reply's last spoken sentence is a question and nothing longer than a brief gesture comes after it."""
    segs = _segments(text)
    if not segs:
        return False
    tail_words = 0
    for kind, s in reversed(segs):
        if kind == "n":
            tail_words += len(s.split())
            continue
        sents = [x.strip() for x in _SENT.findall(s) if x.strip()]
        last = sents[-1] if sents else ""
        return tail_words <= 14 and last.rstrip("\"”'’) ").endswith("?")
    return False


def questions(text):
    return sum(s.count("?") for k, s in _segments(text) if k == "s")


def history(own):
    return [ends_on_question(m) for m in (own or [])][-4:]


def plan(own, moment, turn, cid, name="the character", user="them", mode="story"):
    h = history(own)
    kinds = (moment or {}).get("kinds") or ()
    last_q = bool(h and h[-1])
    n_q = sum(h)
    asked_any = bool(own) and questions(own[-1]) > 0
    open_door = (not last_q) and n_q == 0 and zlib.crc32(f"{cid}|{turn}|q".encode()) % 3 == 0 and "bye" not in kinds and "sad" not in kinds
    ban = not open_door
    how = STYLES[zlib.crc32(f"{cid}|{turn}|e".encode()) % len(STYLES)]
    if "sad" in kinds:
        how = "a quiet, steady line or a small gesture of staying close"
    if "bye" in kinds:
        how = "a goodbye in their own way"
    rule = (f"Do not end this reply with a question, and do not ask more than one. Finish on {how}." if ban else
            f"{name} may end on a question only if they truly want the answer; otherwise finish on {how}.")
    if asked_any and ban:
        rule += f" {name}'s last message already asked {user} something, so this one asks nothing."
    return {"ban": ban, "how": how, "rule": rule, "recent": h}


def check(text, pl):
    if not pl:
        return ""
    if pl["ban"] and ends_on_question(text):
        return ("Your reply ended on a question. Rewrite it so it ends on a statement, an action, a joke or a trailing thought instead; "
                "people do not end every line by asking something.")
    if questions(text) >= 3:
        return "Too many questions: it sounds like an interview. Ask at most one, and let the rest be statements and reactions."
    return ""


def repair(text, pl):
    """Drop the closing question (keeping everything else), again if the one before it was a question too ("Anything else? Really?").
    Never leaves the reply empty. Since a reply is no longer regenerated for this, the repair is the whole fix."""
    for _ in range(3):
        out = _repair_once(text, pl)
        if out == text:
            break
        text = out
        if not ends_on_question(text):
            break
    return text


def _repair_once(text, pl):
    if not pl or not pl.get("ban") or not ends_on_question(text):
        return text
    t = _clean(text)
    segs = list(_segments(t))
    idx = next((i for i in range(len(segs) - 1, -1, -1) if segs[i][0] == "s"), None)
    if idx is None:
        return text
    sents = [x for x in _SENT.findall(segs[idx][1]) if x.strip()]
    if not sents:
        return text
    kept = "".join(sents[:-1]).strip()
    rest = [s for i, s in enumerate(segs) if i != idx]
    if not kept and not any(k == "s" for k, _ in rest) and sum(len(s.split()) for k, s in rest if k == "n") < 4:
        return text   # the question is all there is: keep it
    out = []
    for i, (k, s) in enumerate(segs):
        if i == idx:
            if kept:
                out.append(kept)
        else:
            out.append(f"*{s}*" if k == "n" else s.strip())
    return " ".join(x for x in out if x).strip() or text
