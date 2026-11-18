"""The cast ledger: who is who in this chat, derived from the sheet, the persona and the user's own messages.

It is rebuilt from the chat each turn (cheap), so editing, deleting, swiping or rewinding messages can never leave
it stale. It answers, without asking the model: what are the user's and the character's names (and did anyone
correct them), what genders are established, which people are merely mentioned, which things the user said about
their own life, whether the latest message changed the subject, and whether the user is asking for something
nobody ever told the character."""
import re

from ..config import CH, US
from ..recall import lexicon as lx
from ..textutil import THINK
from . import claims as cl
from .common import first_name, norm, speech_only
from .names import PRON, guess_gender, parse_gender, rel_gender, relations_in, self_gender, sheet_people, user_names, char_names_said

DEFAULT_NAMES = {"", "user", "you"}
WH = re.compile(r"^\W*(?:what|which|who|whom|whose|when|where|how (?:old|many|much|long|often|tall|far)|do you (?:remember|know|recall)|did (?:i|we)|"
                r"remember|can you (?:tell|remember)|is it true|was it|am i|have i)\b", re.I)
PERSONAL = re.compile(r"\b(?:i|my|mine|me|i'm|i've|i'd)\b", re.I)
OPINION = re.compile(r"\b(?:do you think|should i|would you|could you|will you|can you (?:help|come|stop|please)|how do you|are you|what (?:should|would|do you))\b", re.I)
REACH = re.compile(r"\b(?:remember|told you|i said|did i (?:say|tell|mention)|what did i|i mentioned|you (?:know|said))\b", re.I)
SHIFT = re.compile(r"\b(?:anyway|by the way|btw|changing (?:the )?(?:subject|topic)|different (?:question|topic)|unrelated|on another note|speaking of|"
                   r"new topic|random question|never ?mind|forget (?:that|it)|moving on)\b", re.I)
DONT_KNOW = re.compile(r"(?:\b(?:don'?t|do not|can'?t|cannot|never|haven'?t|didn'?t|doesn'?t|won'?t|not)\b\W+(?:\w+\W+){0,2}(?:know|remember|recall|told|mention(?:ed)?|said|sure|certain)\b"
                       r"|\bno idea\b|\bwouldn'?t know\b|\bslipped my mind\b|\bnot sure\b)", re.I)
ADMIT = re.compile(DONT_KNOW.pattern + r"|\btell me\b|\bremind me\b|\byou never\b|\bi wonder\b", re.I)   # admitting, or asking the user, instead of making it up
CORRECT = re.compile(r"\b(?:actually|wrong|mistaken|misremember|not what you|didn'?t say|that'?s not|no[,.]|you (?:said|told me)|hated?|hates?|dislikes?|never)\b", re.I)


def _plain(m):
    return THINK.sub("", (m or {}).get("content", "") or "").strip()


def _g_of(c):
    g = parse_gender((c or {}).get("gender"))
    return g or guess_gender(" ".join(str((c or {}).get(k) or "") for k in ("description", "personality", "appearance"))[:900])


def build(c, user, hist, persona="", state=None, grp=None):
    """-> ledger dict. hist = the whole in-character chat (not the trimmed prompt window)."""
    char = (c or {}).get("name") or "Character"
    ui = (user or "User").strip() or "User"
    umsgs = [(i, _plain(m)) for i, m in enumerate(hist or []) if m.get("role") == "user" and _plain(m)]
    texts = [t for _, t in umsgs]
    seed = (state or {}).get("cast") if isinstance((state or {}).get("cast"), dict) else {}   # only for helper calls that see a short window
    said, wrong = user_names(texts)
    said = said or str(seed.get("un") or "")
    wrong = set(wrong) | set(seed.get("wrong") or [])
    wrong = {w for w in wrong if w.lower() != (said or ui).lower()}
    default_ui = ui.lower() in DEFAULT_NAMES
    pref = said or ui
    ug = None
    for t in texts:            # what the user says about themself, the latest statement wins
        ug = self_gender(t) or ug
    ug = ug or seed.get("ug") or parse_gender((persona or "").split(".")[0])
    slip, no = char_names_said(texts, char)
    members = {first_name((m or {}).get("name")).lower() for m in (grp or {}).get("members", [])}
    others = {}

    def put(name, rel, owner):
        k = name.lower()
        if k in {first_name(char).lower(), char.lower(), pref.lower(), ui.lower()} or k in members or k in DEFAULT_NAMES:
            return
        o = others.setdefault(k, {"name": name, "rel": rel, "owner": owner, "g": rel_gender(rel)})
        if o["rel"] in ("", None):
            o["rel"] = rel
        o["g"] = o["g"] or rel_gender(rel)

    for n, rel in sheet_people(c):
        put(n, rel, "char")
    for t in texts:
        for n, rel in relations_in(t):
            put(n, rel, "user")
    pers = persona or ""
    for n, rel in relations_in(pers):
        put(n, rel, "user")
    claims = cl.extract(umsgs, others, pers)
    age = re.search(r"\d{1,3}", str((c or {}).get("age") or ""))
    led = {"char": {"name": char, "g": _g_of(c), "slip": sorted(slip), "no": sorted(no), "age": age.group(0) if age else ""},
           "user": {"name": pref, "ui": ui, "g": ug, "wrong": sorted(wrong), "default_ui": default_ui and not said},
           "others": others, "claims": claims, "n_user": len(umsgs), "rel": [], "tail": [], "fresh": False, "probe": {},
           "seed": {"un": said, "ug": ug, "wrong": sorted(wrong)}}
    return led


def user_labels(led):
    u = led["user"]
    return [n for n in dict.fromkeys([u["name"], u["ui"]]) if n and n.lower() not in DEFAULT_NAMES] or [u["name"]]


def analyze(led, hist, known=(), kind="reply"):
    """Look at the latest user message: relevant claims, topic change, recall question, premises, nothing-on-record."""
    last_i = max((i for i, m in enumerate(hist or []) if m.get("role") == "user" and _plain(m)), default=None)
    if kind not in ("reply", "resume") or last_i is None or last_i != len(hist) - 1 and kind == "reply":
        return led
    q = speech_only(_plain(hist[last_i]))
    qt = set(lx.terms(q)) - cl.GENERIC
    led["rel"] = cl.relevant(led["claims"], q, skip_turn=last_i)
    prev = " ".join(_plain(m) for m in hist[max(0, last_i - 2):last_i])
    pt = set(lx.terms(speech_only(prev)))
    explicit = bool(SHIFT.search(q))
    led["fresh"] = bool(led["n_user"] >= 2 and prev.strip() and not REACH.search(q) and (explicit or (len(qt) >= 1 and not (qt & pt))))
    is_q = q.rstrip().endswith("?") or bool(WH.match(q))
    asks_me = bool(PERSONAL.search(q)) or any(re.search(r"(?<![\w'])" + re.escape(o["name"]) + r"(?![\w'])", q) for o in led["others"].values() if o["owner"] == "user")
    recall_q = is_q and (asks_me or bool(REACH.search(q))) and not OPINION.search(q)
    premise = next((c for c in led["rel"] if REACH.search(q) and cl.conflict(c["quote"], q)), None) if REACH.search(q) else None
    kn = set()
    for t in known:
        kn |= set(lx.terms(speech_only(t)))
    unknown = recall_q and not led["rel"] and not (qt & kn) and not re.search(r"(?i)\bwho am i\b|\bmy name\b|\bwhat am i called\b", q)
    led["probe"] = {"question": is_q, "recall": recall_q, "premise": premise, "unknown": bool(unknown), "q": q}
    return led


def render_who(led):
    """The compact cast block (about 100 tokens)."""
    ch, us = led["char"], led["user"]
    lines = ["[Who's who - fixed facts; never mix these people up]"]
    lines.append(f"- You are {CH}" + (f" ({PRON[ch['g']]})" if ch["g"] else "") + f". You are talking with {US}"
                 + (f" (whose name in the chat is also {us['ui']})" if us["ui"].lower() not in DEFAULT_NAMES and us["name"].lower() != us["ui"].lower() else "") + ".")
    lines.append(f"- {US} is {PRON[us['g']] if us['g'] else 'of a gender that has NOT been stated: never assume it; address them as \"you\" or by name and never write he/she for them'}.")
    if us["wrong"]:
        lines.append(f"- {US} is NOT called {', '.join(us['wrong'])}. Always call them {US}.")
    if ch["slip"] or ch["no"]:
        bad = ", ".join(sorted(set(ch["slip"]) | set(ch["no"])))
        lines.append(f"- You are {CH}, not {bad}. If {US} mixes it up, correct them in character.")
    ppl = []
    for o in led["others"].values():
        who = (US + "'s" if o["owner"] == "user" else CH + "'s") + f" {o['rel']}" if o.get("rel") else "mentioned"
        ppl.append(f"{o['name']} ({who}" + (f", {PRON[o['g']]}" if o["g"] else "") + ")")
    if ppl:
        lines.append("- Other people (talked about, NOT you, NOT " + US + ", not in the room unless the scene shows it): " + "; ".join(ppl[:8]) + ".")
    lines.append(f"- Never speak as, for or turn into {US} or any of them. What {US} says about their own life (past, family, tastes, injuries) belongs to {US}, "
                 f"never to {CH}. Do not invent shared memories that were not shown.")
    return "\n".join(lines)


def render_claims(led, limit=4):
    rows = []
    for c in led["rel"][:limit]:
        who = US if c["owner"] == "user" else f"{US} about {c['owner']}"
        rows.append(f'- {who}: "{cl.clip(c["quote"])}"')
    if not rows:
        return ""
    return f"[What {US} actually told {CH} - exact words. They win over any memory, summary or earlier reply that disagrees]\n" + "\n".join(rows)


def tail_notes(led):
    """Short end-of-prompt notes (where small models listen): the exact facts for a recall question, a false premise,
    nothing on record, or a changed subject."""
    p, out = led.get("probe") or {}, []
    if not p:
        return out
    if p.get("premise"):
        out.append(f"{US} says they told you something that is not what they said: they actually said \"{cl.clip(p['premise']['quote'], 140)}\". "
                   f"Set it straight in character. Do not just agree.")
    if p.get("unknown"):
        out.append(f"{US} never told {CH} this and it is not in {CH}'s memory, so {CH} does not know it. Say so the way {CH} would (or ask), and do not make up an answer.")
    elif (p.get("recall") or p.get("question")) and led["rel"]:
        out.append("Exact facts for this question, use them as given:\n" + "\n".join(
            f'- {US if c["owner"] == "user" else US + " about " + c["owner"]}: "{cl.clip(c["quote"], 150)}"' for c in led["rel"][:3]))
    if led.get("fresh") and not out:
        out.append(f"{US} just changed the subject. Answer their latest message first (\"{cl.clip(p.get('q', ''), 110)}\") and drop the earlier topic unless they return to it.")
    return out


def strip_characters(summary):
    """The old summary template had a CHARACTERS section of per-person facts, which is where ownership errors crept in.
    The ledger replaces it, so it is left out of the prompt."""
    return re.sub(r"(?ms)^[ \t]*CHARACTERS[ \t]*:?[ \t]*\n.*?(?=^[ \t]*[A-Z][A-Z &]{4,}[ \t]*:?[ \t]*$|\Z)", "", str(summary or "")).strip()


def roster(led):
    """One line with real names, for the small helper prompts (mood tracker, summariser, memory writer)."""
    ch, us = led["char"], led["user"]
    g = PRON[us["g"]] if us["g"] else "gender NOT stated (use they/them, never he/she)"
    bits = [f"{ch['name']} is the character" + (f" ({PRON[ch['g']]})" if ch["g"] else ""), f"{us['name']} is the user ({g})"]
    ppl = [f"{o['name']} ({(us['name'] + chr(39) + 's') if o['owner'] == 'user' else (ch['name'] + chr(39) + 's')} {o['rel']})" if o.get("rel") else o["name"] for o in led["others"].values()]
    if ppl:
        bits.append("only talked about, never present or speaking: " + "; ".join(ppl[:8]))
    return "Who's who: " + ". ".join(bits) + "."
