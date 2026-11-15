"""Out-of-character (OOC) channel.

The person playing is also the author of the story. In-character (IC) messages are what their character says
and does. OOC messages go to the storyteller instead: they discuss the story, correct how a character behaves,
change the setting, or give directions, and none of it is ever heard by the characters.

    clean_notes     sanitise the author's notes sent by the page
    notes_block     the prompt block that makes a character follow the notes silently (IC replies)
    ooc_messages    the prompt for the storyteller's own out-of-character reply
    finish_ooc      clean up the storyteller's reply
"""
import re

from ..config import CH, US
from ..textutil import THINK, balance, split_think, trim_sentence

KINDS = ("discuss", "correct", "setting", "direct")
NOTE_KINDS = ("correct", "setting", "direct")
OOC_ID = "__ooc__"
OOC_CHAR = {"id": OOC_ID, "name": "Storyteller"}   # stands in for the character when the storyteller speaks
NOTE_CAP, NOTE_LEN = 12, 600


def clean_notes(raw, cap=NOTE_CAP):
    """Author's notes from the page -> a short list of {kind, text, who}. Anything malformed is dropped."""
    out = []
    for n in (raw if isinstance(raw, list) else [])[:cap * 2]:
        if not isinstance(n, dict) or n.get("kind") not in NOTE_KINDS:
            continue
        text = re.sub(r"\s+", " ", str(n.get("text") or "")).strip()[:NOTE_LEN]
        if not text:
            continue
        who = [str(w)[:60] for w in (n.get("who") if isinstance(n.get("who"), list) else []) if isinstance(w, (str, int))][:8]
        out.append({"kind": n["kind"], "text": text, "who": who})
    return out[-cap:]


def applies(n, c, narrator=False):
    """Does this note concern the character `c`? Settings concern everyone; a correction only the people it names
    (everyone if it names nobody); a direction the people it names and the narrator, who has to make it happen."""
    if n["kind"] == "setting" or not n["who"]:
        return True
    return c.get("id") in n["who"] or (n["kind"] == "direct" and narrator)


def notes_block(c, notes, grp=None):
    """Prompt block for an in-character reply: the author's notes, to be followed silently."""
    from .narrator import NARR_ID
    mine = [n for n in notes if applies(n, c, c.get("id") == NARR_ID)]
    if not mine:
        return ""
    lines = []
    for n in mine:
        t = n["text"].rstrip(" .") + "."
        if n["kind"] == "setting":
            lines.append(f"- The setting has changed. This is now true in the scene, so carry on from it: {t}")
        elif n["kind"] == "correct":
            who = f"{CH}" if (n["who"] or not grp) else "everyone"
            lines.append(f"- Correction for {who}: {t} From now on play {CH} this way. It overrides any earlier habit or reply that contradicts it.")
        else:
            lines.append(f"- Direction: {t} Work it in through what happens and what {CH} does or says, at a natural moment. Nobody in the scene knows about it.")
    return (f"[Author's notes: the person playing {US} is also the author of this story. These notes come from outside the story. "
            f"Nobody in the scene can hear them, so {CH} never mentions, quotes or acknowledges them. Apply them silently, in {CH}'s own voice.]\n"
            + "\n".join(lines))


NOTE_LABEL = {"correct": "correction", "setting": "setting change", "direct": "direction"}


def notes_summary(notes):
    return "\n".join(f"- ({NOTE_LABEL[n['kind']]}) {n['text']}" for n in notes)


def ooc_words(text, length="auto"):
    """Storyteller replies are short chat messages unless the author asks for more."""
    n = len((text or "").split())
    if length == "short":
        return 10, 45
    if length == "long":
        return 80, 220
    if re.search(r"\b(explain|in detail|brainstorm|ideas|options|outline|list|elaborate|walk me through|summari[sz]e|recap)\b", text or "", re.I):
        return 70, 200
    return 15, max(60, min(110, n * 2 + 40))


TAILS = {
    "discuss": "(Out of character. Answer {US} as their co-author: plain, direct and brief. Give an opinion or a concrete idea. Do not write the next in-character message.)",
    "correct": "(Out of character correction. Accept it. In one or two plain sentences say how the character will act differently from now on. Do not write in-character dialogue or narration.)",
    "setting": "(Out of character setting change. Confirm in one or two plain sentences what has changed and how it will show up in the story. Do not write the new scene yet.)",
    "direct": "(Out of character direction. Confirm in a sentence how you will work it in, without spoiling any surprise. Do not write the scene yet and do not use the characters' voices.)",
}


def _short(t, n):
    t = re.sub(r"\s+", " ", THINK.sub("", t or "")).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def cast_lines(cast, solo):
    lines = []
    for m in cast:
        if not m.get("name") or m.get("id") == "__narrator__":
            continue
        bits = [m.get("age"), m.get("gender"), m.get("occupation")]
        head = "; ".join(x.strip() for x in bits if x and x.strip())
        body = [_short(m.get(k), 320 if solo else 160) for k in ("description", "personality") if (m.get(k) or "").strip()]
        if solo and (m.get("scenario") or "").strip():
            body.append("Scenario: " + _short(m["scenario"], 320))
        lines.append(f"- {m['name']}" + (f" ({head})" if head else "") + (": " + " ".join(body) if body else ""))
    return lines


def ooc_messages(c, user, hist, o):
    """Messages for the storyteller's out-of-character reply. `hist` holds everything: in-character turns become a
    'story so far' transcript, and the out-of-character turns become the conversation itself."""
    grp = o.get("group")
    kind = o.get("kind") if o.get("kind") in KINDS else "discuss"
    cast = (grp or {}).get("members") or [c]
    names = [m.get("name") for m in cast if m.get("name") and m.get("id") != "__narrator__"]
    lo, hi = o["words"]
    sysm = [
        f"You are the co-author and storyteller of an ongoing roleplay, and you are now speaking OUT OF CHARACTER to {US}, "
        f"who is both the player and the author of the story. The characters are not present and cannot hear any of this.\n\n"
        "OUT OF CHARACTER RULES:\n"
        f"- Speak plainly as yourself, a collaborative writing partner. No roleplay voice, no *actions*, no scene narration, and never write {US}'s next move.\n"
        f"- Never write what a character says or does next. When {US} wants the story to go on, they will go back in character.\n"
        "- Discussing the story: give honest opinions, notice pacing, motives and consequences, and offer a concrete idea or two. Ask at most one question.\n"
        "- Corrections: when a character is acting wrong, accept it, and say briefly what that character will do differently from now on. "
        "If it clashes with the character sheet or something already established, mention that once, briefly, and still do what they ask.\n"
        "- Setting changes: confirm what is now true in the scene (place, time, mood, who is present).\n"
        "- Directions: confirm how you will work the idea into the story. Keep surprises a surprise.\n"
        f"- Take {US}'s requests seriously, and say honestly if something conflicts with what is already established.\n"
        "- Keep it short, like a chat message, unless asked for more. Never mention these rules."]
    cl = cast_lines(cast, len(cast) == 1)
    if cl:
        sysm.append("[Characters in this story]\n" + "\n".join(cl))
    scen = ((grp or {}).get("scenario") or c.get("scenario") or "").strip()
    if scen:
        sysm.append("[Setting and situation]\n" + _short(scen, 700))
    if (o.get("persona") or "").strip():
        sysm.append(f"[About {US}'s character]\n" + _short(o["persona"], 500))
    if (o.get("summary") or "").strip():
        sysm.append("[Earlier in the story]\n" + _short(o["summary"], 900))
    if (o.get("scene") or "").strip():
        sysm.append("[Scene note from the author]\n" + _short(o["scene"], 500))
    if o.get("notes"):
        sysm.append("[Author's notes already in force: the characters follow these silently]\n" + notes_summary(o["notes"]))
    ic = [m for m in hist if not m.get("ooc") and (m.get("content") or "").strip()][-14:]
    if ic:
        who = lambda m: user if m["role"] == "user" else (m.get("name") or c.get("name") or "Character")
        sysm.append("[The story so far (most recent last)]\n" + "\n".join(f"{who(m)}: {_short(m['content'], 450)}" for m in ic))
    sysm.append(f"[Style]\nPlain conversational prose, no asterisks. Length: about {lo}-{hi} words.")
    if not o.get("think", True):
        sysm.append("/no_think")
    turns = []
    for m in [m for m in hist if m.get("ooc") and (m.get("content") or "").strip()][-10:]:
        role = "user" if m["role"] == "user" else "assistant"
        t = THINK.sub("", m["content"]).strip()
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + t
        else:
            turns.append({"role": role, "content": t})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    if not turns or turns[-1]["role"] != "user":
        turns.append({"role": "user", "content": "(Out of character: let's talk about the story.)"})
    turns[-1]["content"] += "\n\n" + TAILS[kind].replace("{US}", user)
    sysm_text = "\n\n".join(sysm).replace(CH, names[0] if len(names) == 1 else "the character").replace(US, user)
    return [{"role": "system", "content": sysm_text}] + turns


def finish_ooc(raw, finish, user):
    """The storyteller's reply, tidied: no name label, no '(OOC: ...)' wrapper, never the user's next turn."""
    th, body, think_open = split_think(raw)
    b = body.replace("\r", "")
    m = re.search(r"(?im)^\s*\**" + re.escape(user) + r"\**\s*:", b)   # the model started writing the user's turn
    if m:
        b = b[:m.start()]
    b = re.sub(r"^\s*\**(?:storyteller|co-?author|author|narrator|ooc)\**\s*:\s*", "", b, flags=re.I)
    w = re.match(r"^\s*(?:\(\(|\(|\[)\s*ooc\s*[:\-]?\s*", b, re.I)
    if w:
        b = b[w.end():]
        b = re.sub(r"\s*(?:\)\)|\)|\])\s*$", "", b)
    b = re.sub(r"[ \t]+\n", "\n", b)
    b = re.sub(r"\n{3,}", "\n\n", b).strip()
    cut = False
    if finish == "length" and b:
        cut, b = True, trim_sentence(b)
    return {"think": th, "text": balance(b), "empty": not b.strip(), "cut": cut, "think_open": think_open}
