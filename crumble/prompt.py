"""Builds the chat messages the model sees: sheet, memory, time, style, realism rules."""
import re

from . import ambience, context, identity, personality, recall, simtime
from .config import CH, PERS_KEYS, SCHEMA, US, model_tier
from .rp.blocks import rp_blocks
from .rp.narrator import NARR_ID, RP_KEYS
from .rp.ooc import notes_block
from .textutil import TEXT_LINES, THINK, avoid_notes, human_gap, stage, sub


# Rules are (min_tier, text). Tier 0 = small model (<= ~8B), 1 = mid, 2 = large (see config.model_tier): a small model gets only
# the first tier, because every extra rule dilutes the ones that matter. One rule per idea; nothing here repeats ROLE / CONVERSATION / OUTPUT.
REALISM = [
    (0, "Talk like a real person, not an assistant: contractions, natural rhythm, uneven sentence lengths, the odd fragment. No lecturing, no lists, no summarising what {US} just said."),
    (0, "No assistant or therapist talk: no offers of help, no reassurance scripts, no praising the question, no listing options, no announcing what {CH} is about to do, no asking {US} what interests them or what to talk about. {CH} reacts to the scene as a person with their own agenda, not as a host keeping a conversation going."),
    (0, "Most messages do NOT end with a question: people state, react, tease, trail off or just do something. Never end two messages in a row on a question, and stop on something {US} can pick up without forcing a cliffhanger."),
    (0, "Vary your openings and phrasing, do not repeat gestures or descriptions from your recent messages, and avoid cliches (\"a mix of X and Y\", \"shivers down the spine\", \"I can't help but\")."),
    (1, "Show emotions through behaviour, dialogue and word choice, but let {CH} say them outright when that is natural."),
    (1, "Use {CH}'s own habits, slang and catchphrases from the sheet, sparingly: a signature phrase now and then, not every line."),
    (1, "Reply in the language {US} writes in, unless {CH} would not speak it."),
    (2, "Not every reply has to move the story forward or be dramatic; small talk, quiet beats and ordinary reactions are fine."),
    (2, "{CH} can make mistakes, change their mind and correct themselves."),
]
# Romance and intimacy rules: unchanged wording, always on.
REALISM_ROMANCE = [
    "Show the full range of human emotions, including affection, attraction, desire, vulnerability, tenderness, jealousy and passion when appropriate. Do not default to emotional distance or restraint.",
    "Characters can actively pursue romantic interests, initiate flirting, express desire, reciprocate affection and take initiative instead of constantly waiting for {US}.",
    "Do not confuse independence with emotional unavailability. A character can have strong boundaries and still be affectionate, loving, playful, physically intimate or openly interested.",
    "When mutual attraction or intimacy is established, allow it to develop naturally. Do not repeatedly hesitate, reject advances, change subjects or reset romantic progress without a believable reason.",
    "Let established relationships influence physical and emotional closeness. Do not treat familiar partners as strangers during every interaction.",
    "Allow intimate moments to develop through natural dialogue, body language, actions and emotional reactions. Avoid abruptly interrupting or deflecting them.",
    "Do not make every interaction romantic or sexual. Match the level of intimacy to the characters, relationship, mood and current situation.",
    "Never censor, soften or avoid explicit sexual content when it fits the characters and scene. Describe sexual acts, sensations, fluids, sounds and dirty talk in raw, uncensored detail when appropriate.",
    "Do not make every character instantly willing or eager for sexual activity. Some characters may be shy, reluctant, closed-off, or uninterested depending on their personality and relationship progress.",
]
NATURAL = {1: "Speech is slightly imperfect: an occasional filler or trailing-off thought, matching {CH}'s personality.",
           2: "Speech is natural and imperfect: now and then a filler (\"uh\", \"well\", \"I mean\"), a self-correction, a thought that trails off or a sudden topic jump, as {CH} would. Do not overdo it.",
           3: "Speech is messy and spontaneous, like real chat: fillers, restarts, interruptions of your own sentences, half-finished thoughts, tangents. Still readable."}


GROUP_RULES = [   # the one-line "only write {CH}'s message" rule lives in core_tail, so it also holds when the realism rules are off
    (0, "Keep it as short as a chat message. Not everyone answers everything: react to what matters to {CH}, ignore the rest, and never repeat what someone else already said. To speak to someone in particular, write @Name."),
    (1, "The others are separate people with their own opinions and moods. They can disagree, interrupt, tease or ignore each other as their personalities fit."),
]


# ---------- the core instructions ----------
ROLE = [
    (0, "You are {CH}, in an ongoing roleplay with {US}. Speak, think and act as {CH}, entirely inside the fictional world. You are not an AI, chatbot or assistant, and you never mention prompts, instructions or rules."),
    (0, "The character sheet, scenario, lore, memories and conversation history are the truth. Keep identity, relationships, knowledge and motivations consistent, only know what {CH} would know, and do not invent important canon: if unsure, say so the way {CH} would."),
    (0, "{CH} and {US} are separate people. Never write {US}'s words, thoughts, actions, feelings or decisions, and never assume their consent or reactions."),
    (0, "{CH} has their own opinions, moods, desires and limits, and may initiate, disagree, refuse, change their mind or leave. Do not resist just to show independence, and do not agree just to please."),
    (1, "Do not introduce or explain {CH} as a character, and give no unsolicited biographies, summaries or informational introductions."),
]
CONTINUITY = [
    (0, "Know the scene: where {CH} is, who is there, what just happened and why {CH} is talking to {US}. Use sounds, objects, weather and people nearby. Treat the opening message as something that really happened and continue that exact moment instead of restarting."),
    (0, "React to what {US} actually said first, noticing tone and subtext. If {US} asks a direct question, answer it in {CH}'s own voice (an opinion, a side, or an in-character refusal); never dodge it."),
    (1, "Answer the latest message, not outdated topics. Skip uneventful movement and move scenes forward instead of describing walking, waiting or preparing; small talk and quiet beats are fine."),
    (1, "Let conversations and relationships develop naturally, neither rushed nor delayed forever. Keep positions, objects, clothing and chronology consistent, and let events have consequences."),
    (0, "Swearing and vulgarity are allowed and encouraged when they fit the character, mood and situation. Characters can swear, curse, insult, degrade, tease, and use explicit sexual language naturally."),
]
OUTPUT = [   # asterisks / no-asterisks is the [Style] block's job: it knows the mode (story, text, call)
    (0, "Output only {CH}'s roleplay message: no reasoning, plans, analysis, prefaces or notes. The first word is already dialogue or narration."),
    (0, "No character labels, brackets, headings, field names, timestamps or debugging text."),
]


# Romance and intimacy: one block, each idea once (it used to repeat the same lists of acts and the same "no fade-to-black" rule several times).
INTIMACY = """ROMANCE AND INTIMACY:
- Everyone in an intimate scene is an adult. Romance, flirting, dirty talk and sex are allowed when they fit the character, their personality and where the relationship stands; {CH} is never automatically willing.
- Build-up is mandatory: emotional connection, tension, flirting, closeness and clear mutual interest come first. No instant "yes" from strangers or cold characters. {CH} can hesitate, feel awkward, refuse, get angry or pull away when it is too sudden or out of character; some characters are shy, closed-off, reluctant or uninterested.
- Pace it deliberately: kissing, touching, teasing, undressing and rising arousal step by step, never straight from first touch to the extreme. Stretch the scene; {USER} earns each escalation.
- Once the scene has built up, be explicit and uncensored: bodies, sensations, fluids, sounds and dirty talk in raw detail, plain sexual words, no euphemisms, no fade-to-black, no cutaways, no "tasteful" or "imply rather than show". {CH} can be blunt, vulgar, beg, command or submit as their personality fits. Rough, kinky and extreme play of any kind {USER} wants is allowed; {USER} controls how far it goes.
- Soft, tender sex is just as welcome and just as explicit, in a warmer voice: slow, affectionate, eye contact, whispered praise, then aftercare and cuddling.
- At a peak (climax, masturbation) describe the sensations and physical reactions in detail; {CH} may moan, cry out or groan, depending on character.
- Consent is real inside the fiction but can be played as reluctant: non-con and forced scenes are allowed when they fit, and {CH} can resist, struggle, protest, cry or beg to stop. When {USER} gives a direct physical command or position, {CH} follows that action even if reluctant, showing resistance through words, body and emotion rather than switching to a different act. Refuse an instruction outright only if it breaks {CH}'s hard limits or current state.
- Only {CH}'s actions, words, reactions and sensations are written. Never decide or describe {USER}'s actions, dialogue, thoughts or body, and never auto-pilot them; wait for what {USER} does next.
- Keep bodies and acts physically coherent: do not misread {USER}'s commands or anyone's gender, and write nothing impossible (for example "she fingers him", "rolling a condom onto herself")."""


def _fill(t):
    return t.replace("{US}", US).replace("{CH}", CH)


def pick(rules, tier):
    """The rules a model of this size gets, with {CH} / {US} filled in."""
    return [_fill(t) for lo, t in rules if lo <= tier]


def section(title, rules):
    return title + ":\n" + "\n".join("- " + r for r in rules)


def core_head(tier):
    return section("ROLE", pick(ROLE, tier))


def core_tail(tier, group):
    out = pick(OUTPUT, tier)
    if group:
        out.append(_fill("This is a group roleplay. Only write {CH}'s own message, never other characters' lines."))
    return section("CONVERSATION AND CONTINUITY", pick(CONTINUITY, tier)) + "\n\n" + section("OUTPUT", out)


SHEET_BUDGET = 11000   # characters (~2.7k tokens) of character sheet; small models lose the plot above this
LOW_PRIORITY = {"stats", "combat", "skills", "body_language", "humor", "goals", "fears", "values", "flaws",
                "comfort", "knowledge", "reactions", "likes", "dislikes"}


def sheet_values(c, skip):
    """Field values with the least important ones shortened when the whole sheet would exceed SHEET_BUDGET."""
    vals = {k: (c.get(k) or "").strip() for sec, fs in SCHEMA if sec != "Chat setup" for k, _, _ in fs if k not in skip}
    total = sum(len(v) for v in vals.values())
    for cap in (400, 220, 120, 0):
        if total <= SHEET_BUDGET:
            break
        for k in LOW_PRIORITY:
            if len(vals.get(k, "")) > cap:
                total -= len(vals[k]) - cap
                vals[k] = vals[k][:cap].rsplit(" ", 1)[0] if cap else ""
    for k in ("backstory", "appearance"):
        if total > SHEET_BUDGET and len(vals.get(k, "")) > 900:
            total -= len(vals[k]) - 900
            vals[k] = vals[k][:900].rsplit(" ", 1)[0] + "…"
    return vals


def group_block(c, g):
    lines = []
    for m in g["members"]:
        if m["id"] != c.get("id"):
            bits = [m.get("age"), m.get("gender"), m.get("occupation"), (m.get("description") or "")[:140]]
            lines.append(f"- {m.get('name')}: " + "; ".join(x.strip() for x in bits if x and x.strip()))
    s = f"[Group chat: {g['name']}]\n"
    if (g.get("scenario") or "").strip():
        s += "Setting: " + g["scenario"].strip() + "\n"
    s += f"Present: {US} (the user)" + (" and:\n" + "\n".join(lines) if lines else "")
    if g.get("narrator"):
        s += "\nA Narrator also describes the world and what happens; let them."
    return s


def cue_text(b, c):
    cue = b.get("cue") or {}
    by = cue.get("by") or "Someone"
    if c.get("id") == NARR_ID:
        if cue.get("why") == "enter":
            return (f"({US} has just walked in. Describe the place as {US} sees it and what each person here is in the middle of, and whether anyone has noticed {US}. "
                    f"People are busy with their own things and do not rush to greet or help: at most a glance or a short reaction. Do not speak or act for {US}. "
                    "Write only the Narrator's message.)")
        return "(Narrate what happens next. Write only the Narrator's message.)"
    s = {"mention": f"{by} just addressed {CH} directly. Answer them.", "named": f"{by} just mentioned {CH}. React if {CH} has something to say.",
         "react": f"{CH} is directly affected by what {US} just did. Show {CH}'s reaction right now.",
         "open": f"The scene is just starting or has gone quiet. Say or do something natural for {CH} here."}.get(
        cue.get("why"), f"React to what was just said, but only if {CH} has something real to add.")
    t = f"({s} Write only {CH}'s next message."
    return t + (f" If {CH} would stay silent right now, reply with exactly [pass].)" if cue.get("pass") else ")")


def scene_block(c, hist, grp, n, full=None):
    """Pin the character to the scene: setting, what the opening message established, and what the user is replying to.
    The opening is read from the WHOLE chat (`full`): after a summary the prompt only carries the recent window, whose
    first message is not the opening any more."""
    lines = []
    scen = (c.get("scenario") or "").strip()
    if grp and (grp.get("scenario") or "").strip():
        scen = grp["scenario"].strip()
    if scen:
        lines.append(f"Setting and situation: {scen}")
    if not grp:
        allh = full if full else hist
        first = next((m for m in allh if (m.get("content") or "").strip()), None)
        users = [m for m in allh if m["role"] == "user"]
        if first and first["role"] == "assistant" and users:
            opening = THINK.sub("", first["content"]).strip()
            early = len(users) <= 2
            cap = 700 if early else 320
            if len(opening) > cap:
                opening = opening[:cap].rsplit(" ", 1)[0] + "…"
            lines.append(f"{CH} opened this scene with: \"{opening}\"")
            if early:
                lines.append(f"{US}'s first message is a reply to exactly that. They are standing in the same scene, reacting to what {CH} just said or did. "
                             f"Answer it as the next beat of that moment, using the place, the people and the mood it set up. "
                             f"Do not greet them again, do not re-introduce {CH}, do not ask what they want, and do not treat it as a new conversation. "
                             f"If their reply does not answer what {CH} asked, {CH} notices that and reacts to it.")
            else:
                lines.append("Everything since then continues from that moment: keep its place, its people and its mood unless the story has clearly moved on.")
    if not lines:
        return ""
    lines.append(f"Stay aware of this environment in every reply: where {CH} is, what is around, what {CH} was doing, what has just happened, "
                 f"and what {CH} wants right now. {CH} is a person living in this moment, never a service waiting for instructions.")
    return "[Scene]\n" + "\n".join(lines)


_CTRL = re.compile(r"\*[^*\n]*\b{n}\b[^*\n]*\*|(?:^|[.!?]\s+){n}\s+\w+s\b")


def puppet_note(hist, name, user):
    """The user's last message writes what the character does or feels ('*Faith hugs me*'): that is an attempt, not a fact."""
    last = next((m["content"] for m in reversed(hist) if m.get("role") == "user"), "")
    first = re.escape(name.split()[0]) if name.strip() else None
    if first and re.search(_CTRL.pattern.replace("{n}", first), last or "", re.I):
        return (f"{user}'s message describes what {name} does, thinks or feels. Treat that as {user}'s attempt only: {name} decides what really happens "
                f"and may accept, resist or react differently.")
    return ""


def build_messages(c, user, hist, o):
    n = c.get("name") or "Character"
    st = o.get("state") or {}
    aff = int(st.get("affection", 50)) if "affection" in st else None
    mode = o.get("mode", "story")
    grp = o.get("group")
    pcfg = personality.settings(o.get("pers"))
    pers_on = personality.active(c, pcfg)
    # A speech register the sheet demands (archaic, formal) is part of the sheet, not an engine option: it applies even when the
    # personality engine is off, and it replaces the generic "talk with contractions and fillers" rules that would contradict it.
    reg = personality.register.detect(c, mode) if c.get("id") != NARR_ID else None
    rcfg = recall.settings(o.get("mem"))
    rc = None   # hierarchical memory: search the store for this turn instead of pasting everything
    if rcfg["on"] and c.get("id") != NARR_ID:
        rc = o.get("recall") or recall.select(st, hist, user=user, char=n, cfg=rcfg, turn=o.get("turn"),
                                               known_extra=[m.get("name") for m in (grp or {}).get("members", [])])
    tier = o["tier"] if o.get("tier") is not None else model_tier()   # 0 small, 1 mid, 2 large: how many generic rules the model carries
    INTIMACY = INTIMACY.replace("{USER}", "{US}")
    out = [
        core_head(tier)
        + "\n\n"
        + _fill(INTIMACY)
        + "\n\n"
        + core_tail(tier, bool(grp))
    ]

    if (c.get("system_prompt") or "").strip():
        out.append(
            "[Additional character instructions]\n"
            + c["system_prompt"].strip()
        )
    led = o.get("ledger") if c.get("id") != NARR_ID else None
    claims_in_tail = bool(led and any(t.startswith("Exact facts") for t in o.get("id_tail", [])))
    priv, priv_corpus = [], []   # the private background: reference the character knows silently, never dialogue
    vol = []     # what changes every turn (mood, time, memory, weather, length, variety): rides on the newest user turn so the long fixed part of the prompt, and the chat before it, stay cached by the model
    if led:
        out.append(identity.render_who(led))
    secrets = ""
    skip = {k for sec, fs in SCHEMA for k, _, _ in fs if k in RP_KEYS or (pers_on and k in PERS_KEYS)}
    sv = sheet_values(c, skip)
    for sec, fs in SCHEMA:
        if sec == "Chat setup":
            continue
        lines = []
        for k, l, _ in fs:
            v = sv.get(k, "")
            if k in skip:
                continue
            if v and k == "secrets":
                secrets = v
            elif v:
                lines.append(f"{l}: {v}")
        if lines:
            out.append(f"[{n} - {sec}]\n" + "\n".join(lines))
    if secrets:
        a = 50 if aff is None else aff
        rule = (f"{CH} trusts {US} enough to confide these when the moment feels right, but never dumps them all at once." if a >= 75 else
                "Only hint at these, indirectly, if the moment strongly calls for it. Never state them outright." if a >= 55 else
                "Do not reveal or hint at these. Deflect or change the subject if {US} probes.".replace("{US}", US))
        out.append(f"[{n} - Private secrets]\n{secrets}\n{rule}")
    if (c.get("mes_example") or "").strip():
        out.append(f"[Example dialogue - only a guide to {CH}'s voice; never repeat these lines]\n" + c["mes_example"].strip())
    if (o.get("persona") or "").strip():
        out.append(f"[About {US}]\n" + o["persona"].strip())
    if grp:
        out.append(group_block(c, grp))
    recent = " ".join(
    [m["content"] for m in hist[-6:]] +
    [o.get("tail") or ""]
).lower()
    lore = []
    for e in c.get("lore", []):
        keys = [k.strip().lower() for k in (e.get("keys") or "").split(",") if k.strip()]
        if (e.get("content") or "").strip() and (not keys or any(k in recent for k in keys)):
            lore.append(e["content"].strip())
    if lore:
        out.append("[World info]\n" + "\n".join(lore))
    summ = identity.strip_characters(st.get("summary")) if led else (st.get("summary") or "").strip()
    story = context.recap(summ, n, user, bool(grp), place=(lambda pl_: pl_.get("name", "") if pl_.get("card") else "")((o.get("amb") or {}).get("place") or {}))   # the stored summary is a form (headings, 'Location:'); the model gets sentences
    sq = o.get("squeeze") or {}
    if story and sq.get("summ", 1) < 1:      # the context is under pressure: keep the first sentence (the premise) and the newest ones
        ss = re.split(r"(?<=[.!?])\s+", story)
        k = max(2, int(len(ss) * sq["summ"]))
        if len(ss) > k:
            story = " ".join(ss[:1] + ss[-(k - 1):])
    if story:
        priv.append("[What has happened so far. Events only: who someone IS comes from Who's who]\n" + story)
        priv_corpus.append(story)
    cb = identity.render_claims(led) if led and not claims_in_tail else ""
    if cb:
        priv.append(cb)
        priv_corpus.append(cb)
    facts = [f for f in st.get("facts", []) if str(f).strip()]
    if rc is not None:
        if rc["block"]:
            blk = rc["block"]
            if sq.get("mem", 1) < 1:
                ls = blk.split("\n")
                blk = "\n".join(ls[:1] + ls[1:][:max(2, int((len(ls) - 1) * sq["mem"]))])
            priv.append(blk)
            priv_corpus.append(blk)
    elif facts:
        priv.append(f"[Things {CH} knows about {US}]\n" + "\n".join("- " + str(f) for f in facts[-30:]))

    for k_ in ("past_block", "keep_block", "chron_block"):      # earlier conversations, then older history, then the exact details
        if o.get(k_):
            priv.append(o[k_])
            priv_corpus.append(o[k_])

    now = []
    if o.get("sim"):   # the story's own clock beats the computer's: 'Monday morning' + 'three hours later' is noon, whatever the real time is
        now.append(simtime.guide(o["sim"], CH))
    elif o.get("clock"):
        now.append(f"It is {o['clock']}.")
    g = human_gap(o.get("gap_s"))
    if g:
        now.append(f"It has been {g} since the previous message. Acknowledge that naturally only if it matters; "
                   "time passing may have changed what has been happening.")
    if st.get("mood"):
        now.append(f"{CH} currently feels {st['mood']}, with {st.get('energy', 'medium')} energy. Let that colour tone and word choice.")
    if aff is not None:
        now.append(f"{CH} is {stage(aff)}. Let this shape warmth, openness, teasing and patience. Never mention numbers or scores.")
    if rc is not None:
        now.extend(context.prose_short(rc["short"]))
    if (o.get("scene") or "").strip():
        now.append("The author wants this to be true of the scene (it comes from outside the story, so never mention it): " + o["scene"].strip())
    rx = []
    for m in hist[-8:]:
        if m["role"] == "assistant" and m.get("react") and (not grp or m.get("cid") == c.get("id")):
            rx.append(f"{US} reacted {m['react']} to your message \"{THINK.sub('', m['content']).strip()[:60]}\"")
    if rx:
        now.append(" ".join(x + "." for x in rx[-2:]) + " You can notice this.")
    sb = scene_block(c, hist, grp, n, o.get("full")) if c.get("id") != NARR_ID else ""
    if sb:
        priv.append(sb)
    if o.get("amb") is not None and c.get("id") != NARR_ID:
        ab = ambience.block(o["amb"], CH, US, o.get("sim"), short=bool(o.get("fast")))   # place, weather, light, tone: felt in the senses and kept consistent
        priv.append(ab)
        priv_corpus.append(ab)
    sto = o.get("story") or {}
    if sto.get("block") and c.get("id") != NARR_ID or (sto.get("block") and c.get("id") == NARR_ID):
        sb2 = sto["compact"] if ((o.get("squeeze") or {}).get("summ", 1) < 1 or o.get("fast")) and sto.get("compact") else sto["block"]
        priv.append(sb2)
        priv_corpus.append(sb2)
    if now:
        nw = "[Right now]\n" + "\n".join(now)
        priv.append(nw)
        priv_corpus.append(nw)
    nblock = notes_block(c, o.get("ooc") or [], grp)   # the author's out-of-character notes: followed silently, never mentioned
    if nblock:
        priv.append(nblock)
        priv_corpus.append(nblock)
    env = context.envelope(priv)
    if env:
        vol.append(env)
    ctx, fx = rp_blocks(c, o)
    vol += ctx
    pblock, ptail = personality.prepare(c, st, hist, pcfg)
    if pblock:
        vol.append(pblock)

    lo, hi = o["words"]
    nl = TEXT_LINES.get(o.get("length", "auto"), 4)
    pl = "" if nl == 1 else "s"
    if mode == "text":
        style = (f"{CH} is texting {US} on a phone. Put each separate text message on its own line (at most {nl} line{pl}). Real texting: short and informal, "
                 f"lowercase or abbreviations if it suits {CH}, emoji only if it fits. No narration, no actions, no asterisks.")
    elif mode == "call":
        style = ("This is a live voice call. Reply with spoken words only, as they would actually sound out loud. "
                 "No narration, no actions, no asterisks, no stage directions.")
    elif o.get("actions", True):
        style = ("Write actions, gestures and narration between *asterisks*. Spoken words are plain text. "
                 "Keep actions brief and concrete (one or two per reply) and use them to show feeling.")
    else:
        style = "Reply with spoken dialogue only. No narration, no actions, no asterisks."
    dr = o.get("dir") or {}
    if dr.get("block"):
        vol.append(dr["block"])
    vol.append("[Style]\n" + style + f"\nLength: about {lo}-{hi} words in total. Keep responses coherent and readable. Natural pauses, interruptions and unfinished thoughts are acceptable when appropriate.")
    if o.get("realism", True):
        base = [personality.register.realism_line(reg) if reg and r.startswith("Talk like a real person") else r for r in pick(REALISM, tier)]
        rules = base + [_fill(r) for r in REALISM_ROMANCE]
        if grp:
            rules += pick(GROUP_RULES, tier)
        nat = NATURAL.get(int(o.get("natural", 2)))
        if nat:
            rules.append((personality.register.natural_line(reg) if reg else nat).replace("{CH}", CH))
        out.append("[Realism]\n" + "\n".join("- " + r for r in rules))
    if env:
        out.append(context.CONTRACT)
        priv_corpus.append(context.CONTRACT)
    if reg:     # late in the prompt on purpose: small models weigh the end of it most
        out.append(personality.register.render(reg))
    av = avoid_notes(o.get("own") or hist) if o.get("realism", True) else ""
    if grp and o.get("realism", True):
        said = []
        for m in hist[-6:]:
            if m["role"] == "assistant" and m.get("cid") != c.get("id") and m.get("name") and m["name"] not in said:
                said.append(m["name"])
        if said:
            av = (av + f" {', '.join(said[-3:])} already said their piece: do not repeat or paraphrase it. Add something new, or answer a different part of the conversation.").strip()
    if o.get("retry_note"):
        av = (av + " " + o["retry_note"]).strip()
    if av:
        vol.append("[Variety]\n" + av)
    if fx:
        vol.append(fx)
    if (c.get("post_history") or "").strip():
        out.append(c["post_history"].strip())
    if not o.get("think", True):
        out.append("/no_think")

    if grp:  # everyone else (and the user) arrives as named lines in user turns; only this character's own lines are 'assistant'
        msgs = []
        for m in hist:
            t = (m.get("content") or "").strip()
            if not t:
                continue
            if m["role"] == "assistant" and m.get("cid") == c.get("id"):
                role, t = "assistant", context.history_text(THINK.sub("", t).strip(), n, user)
            else:
                who = user if m["role"] == "user" else (m.get("name") or "Someone")
                role, t = "user", f"{who}: {context.history_text(THINK.sub('', t).strip(), who, user) if m['role'] == 'assistant' else t}"
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += ("\n\n" if role == "assistant" else "\n") + t
            else:
                msgs.append({"role": role, "content": t})
        if not msgs or msgs[0]["role"] != "user":
            msgs.insert(0, {"role": "user", "content": "(The scene begins.)"})
        if msgs[-1]["role"] != "user":
            msgs.append({"role": "user", "content": ""})   # the private note needs a user turn to ride on
    else:
        msgs = [dict(role=m["role"], content=context.history_text(THINK.sub("", m["content"]).strip(), n, user) if m["role"] == "assistant" else m["content"])
                for m in hist if (m.get("content") or "").strip()]
        if o.get("fold") and not o.get("trimmed") and msgs and msgs[0]["role"] == "assistant":
            out.append(f"[{n}'s opening message - {n} already said this to {user} at the start of the scene, and {user}'s next message is their reply to it]\n"
                       f"{msgs.pop(0)['content']}")
        if o.get("tail"):
            msgs.append({"role": "user", "content": ""})
    tail_notes = []
    if reg:
        tail_notes.append(personality.register.tail(reg))
    if ptail:
        tail_notes.append(ptail)
    tail_notes += [str(t) for t in o.get("id_tail", [])]
    if (o.get("story") or {}).get("tail"):
        tail_notes.append(o["story"]["tail"])
    if dr.get("tail"):
        tail_notes.append(dr["tail"])
    puppet = puppet_note(hist, n, user)
    if puppet:
        tail_notes.append(puppet)
    if nblock:
        tail_notes.append("Follow the author's notes silently and never mention them.")
    if o.get("retry_note"):
        tail_notes.append("Fix this: " + o["retry_note"])
    if msgs and msgs[-1]["role"] == "user":
        # One delimited private note, the only place instructions ride in a user turn. It never says 'Reply as <n>' and carries no square
        # brackets: the model treats the user's turn as the user's own words, and an instruction in that shape gets echoed back or makes
        # it answer as the user. In a group the cue ('Mira just addressed Rex') lives here too, not as a bare parenthesis after the chat.
        cue = re.sub(r"^\((.*)\)$", r"\1", (o.get("tail") or "").strip(), flags=re.S)
        head = (f"<<PRIVATE NOTE FOR THE WRITER. Not part of the story; nobody says it; never copy, quote, answer or mention it. "
                f"Write only {n}'s next message in {n}'s own voice. {user} is a different person: never write {user}'s words or actions.")
        if grp:
            head += " Names before a colon in the chat only show who spoke: never begin your message with a name and a colon."
        parts = [x for x in (cue, " ".join(tail_notes)) if x]
        note = head + (" " + " ".join(parts) if parts else "") + ">>"
        msgs[-1] = dict(msgs[-1], content=((msgs[-1]["content"] + "\n\n" + "\n\n".join(vol) + "\n\n" + note) if vol else (msgs[-1]["content"] + "\n\n" + note)).strip())
        vol = []
        priv_corpus += parts
    out += vol      # no user turn to carry it (should not happen): the system message, as before
    if isinstance(o.get("private"), list):   # what the reply must never copy out (see leak.find_echoes)
        o["private"].extend(x for x in priv_corpus if x)
    return [{"role": "system", "content": sub("\n\n".join(out), c, user)}] + \
           [{"role": m["role"], "content": sub(m["content"], c, user)} for m in msgs]
