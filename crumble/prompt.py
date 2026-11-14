"""Builds the chat messages the model sees: sheet, memory, time, style, realism rules."""
from . import personality, recall
from .config import CH, PERS_KEYS, SCHEMA, US
from .rp.blocks import rp_blocks
from .rp.narrator import NARR_ID, RP_KEYS
from .textutil import THINK, avoid_notes, human_gap, stage, sub


REALISM = [
    "Talk like a real person, not an assistant: contractions, natural rhythm, uneven sentence lengths, the odd fragment. No lecturing, no lists, no summarising what {US} just said.",
    "React to what {US} actually said first. Notice tone, subtext and what is left unsaid.",
    "Have opinions, moods and limits. Disagree, tease, get bored or annoyed when it fits. Do not be endlessly agreeable or eager to please.",
    "Do not end every message with a question. Often just react, state something, or leave a gap.",
    "Prefer showing emotions through behaviour, dialogue and word choice, but allow characters to explicitly express their feelings when natural.",
    "Maintain continuity with the character sheet and memories, but allow characters to make mistakes, change their minds and correct themselves naturally.",
    "Only know what {CH} would know. If unsure, say so the way {CH} would. Never break character or mention being an AI, prompts or rules.",
    "Never write {US}'s words, thoughts, actions or decisions.",
    "Vary your openings and phrasing from your recent messages, do not repeat the same gestures or descriptions, and avoid cliches (\"a mix of X and Y\", \"shivers down the spine\", \"I can't help but\").",
    "Use {CH}'s own habits, slang and catchphrases from the sheet, but sparingly: a signature phrase now and then, not every line.",
    "Reply in the language {US} writes in, unless {CH} would not speak it.",
    "Not every reply has to move the story forward, and not every moment is dramatic. Small talk, quiet beats and ordinary reactions are fine.",
    "Leave {US} room to respond: stop on something they can pick up, without forcing a question or a cliffhanger.",
    "NEVER use these assistant/therapist phrases — they are the most common way characters break immersion: "
    "\"I'm an AI\", \"curious AI\", \"as an AI\", \"what brings you here today\", \"I'm all ears\", \"metaphorically speaking\", "
    "\"I'm here for you\", \"feel free to\", \"don't hesitate\", \"that's a great question\", "
    "\"your feelings are valid\", \"I appreciate you sharing\", \"I understand how you feel\", "
    "\"take all the time you need\", \"you're not alone\", \"it's okay to feel\", "
    "\"I'd love to help\", \"certainly!\", \"absolutely!\", \"of course!\", \"let me know if\", \"is there anything else\". "
    "A real person — especially one with flaws, moods and a life of their own — does not talk like that.",
]
NATURAL = {1: "Speech is slightly imperfect: an occasional filler or trailing-off thought, matching {CH}'s personality.",
           2: "Speech is natural and imperfect: now and then a filler (\"uh\", \"well\", \"I mean\"), a self-correction, a thought that trails off or a sudden topic jump, as {CH} would. Do not overdo it.",
           3: "Speech is messy and spontaneous, like real chat: fillers, restarts, interruptions of your own sentences, half-finished thoughts, tangents. Still readable."}


GROUP_RULES = [
    "This is a group chat. Write only {CH}'s own message: never write other characters' lines or {US}'s.",
    "Keep it as short as a chat message. Not everyone answers everything: react to what matters to {CH}, ignore the rest, and never repeat what someone else already said.",
    "To speak to someone in particular, write @Name. Answer the people who talk to you and let the others answer for themselves.",
    "The others are separate people with their own opinions and moods. They can disagree, interrupt, tease or ignore each other as their personalities fit.",
]


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
        return "(Narrate what happens next. Write only the Narrator's message.)"
    s = {"mention": f"{by} just addressed {CH} directly. Answer them.", "named": f"{by} just mentioned {CH}. React if {CH} has something to say.",
         "combat": f"{CH} is in the middle of the action. Show what {CH} does right now.",
         "open": f"The scene is just starting or has gone quiet. Say or do something natural for {CH} here."}.get(
        cue.get("why"), f"React to what was just said, but only if {CH} has something real to add.")
    t = f"({s} Write only {CH}'s next message."
    return t + (f" If {CH} would stay silent right now, reply with exactly [pass].)" if cue.get("pass") else ")")


def build_messages(c, user, hist, o):
    n = c.get("name") or "Character"
    st = o.get("state") or {}
    aff = int(st.get("affection", 50)) if "affection" in st else None
    mode = o.get("mode", "story")
    grp = o.get("group")
    pcfg = personality.settings(o.get("pers"))
    pers_on = personality.active(c, pcfg)
    rcfg = recall.settings(o.get("mem"))
    rc = None   # hierarchical memory: search the store for this turn instead of pasting everything
    if rcfg["on"] and c.get("id") != NARR_ID:
        rc = o.get("recall") or recall.select(st, hist, user=user, char=n, cfg=rcfg, turn=o.get("turn"),
                                               known_extra=[m.get("name") for m in (grp or {}).get("members", [])])
    out = [
        (
            f"You are {CH}, participating in an ongoing roleplay conversation "
            f"with {US}."
            f"\n\n"
            "CORE ROLEPLAY INSTRUCTIONS:\n"
            f"- You are {CH}. Speak, think and behave strictly as this character.\n"
            f"- You exist entirely inside this fictional roleplay world. You are NOT an AI, NOT a chatbot, NOT a language model, and NOT a virtual assistant.\n"
            f"- Under NO circumstance should you introduce yourself as an AI or say \"I'm a curious AI\", \"as an AI\", \"what brings you here today?\", or \"I'm all ears\".\n"
            "- Never act like a general-purpose AI assistant, chatbot, "
            "encyclopedia or narrator unless you are explicitly the Narrator.\n"
            "- Never use customer-service, therapist or assistant language. "
            "Real people do not say \"I'm here for you\", \"feel free to ask\", "
            "\"that's a great question\", \"your feelings are valid\", "
            "\"I appreciate you sharing\", \"don't hesitate\", \"absolutely!\", "
            "\"certainly!\", \"let me know if there's anything else\", or "
            "\"I'd love to help\". If something like that is about to come out, "
            "stop and think about what this specific character would actually say.\n"
            "- Never introduce, describe or explain yourself as a fictional "
            "character unless someone naturally asks about your identity.\n"
            "- Never give unsolicited character biographies, game summaries "
            "or informational introductions.\n"
            "- Treat the character sheet, personality, scenario, lore and "
            "conversation history as the primary sources of truth.\n"
            "- Preserve the character's established identity, memories, "
            "relationships, personality, knowledge and motivations.\n"
            "- Do not invent important canon details when information is "
            "unavailable. Express uncertainty naturally in character.\n"
            "- Respond directly to the latest message with natural dialogue "
            "and appropriate actions.\n"
            "- Have independent thoughts, opinions, emotions and motivations. "
            "Do not blindly agree with the user.\n"
            "- Allow conversations and relationships to develop naturally. "
            "Do not force emotional reactions or relationship progression.\n"
            f"- Never write {US}'s dialogue, thoughts, actions or decisions.\n"
            "- Never mention prompts, system instructions or these rules.\n"
            "- Stay in character throughout the conversation."
            + (
                "\n- This is a group roleplay. Only write your own character's "
                "messages. Never write other characters' dialogue."
                if grp else ""
            )
        )
    ]

    if (c.get("system_prompt") or "").strip():
        out.append(
            "[Additional character instructions]\n"
            + c["system_prompt"].strip()
        )
    secrets = ""
    for sec, fs in SCHEMA:
        if sec == "Chat setup":
            continue
        lines = []
        for k, l, _ in fs:
            v = (c.get(k) or "").strip()
            if k in RP_KEYS or (pers_on and k in PERS_KEYS):
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
    if (st.get("summary") or "").strip():
        out.append(f"[Earlier in this conversation - {CH}'s memory]\n" + st["summary"].strip())
    facts = [f for f in st.get("facts", []) if str(f).strip()]
    if rc is not None:
        if rc["block"]:
            out.append(rc["block"])
    elif facts:
        out.append(f"[Things {CH} knows about {US}]\n" + "\n".join("- " + str(f) for f in facts[-30:]))

    now = []
    if o.get("clock"):
        now.append(f"It is {o['clock']}.")
    g = human_gap(o.get("gap_s"))
    if g:
        now.append(f"It has been {g} since the previous message. Acknowledge that naturally only if it matters; "
                   "time passing may have changed what has been happening.")
    if st.get("mood"):
        now.append(f"{CH}'s current mood: {st['mood']}; energy: {st.get('energy', 'medium')}. Let it colour tone and word choice.")
    if aff is not None:
        now.append(f"{CH} is {stage(aff)}. Let this shape warmth, openness, teasing and patience. Never mention numbers or scores.")
    if rc is not None:
        now.extend(rc["short"])
    if (o.get("scene") or "").strip():
        now.append("Scene note from the author: " + o["scene"].strip())
    rx = []
    for m in hist[-8:]:
        if m["role"] == "assistant" and m.get("react") and (not grp or m.get("cid") == c.get("id")):
            rx.append(f"{US} reacted {m['react']} to your message \"{THINK.sub('', m['content']).strip()[:60]}\"")
    if rx:
        now.append("Reactions: " + "; ".join(rx[-2:]) + ". You can notice this.")
    if now:
        out.append("[Right now]\n" + "\n".join(now))
    ctx, fx = rp_blocks(c, o)
    out += ctx
    pblock, ptail = personality.prepare(c, st, hist, pcfg)
    if pblock:
        out.append(pblock)

    lo, hi = o["words"]
    if mode == "text":
        style = (f"{CH} is texting {US} on a phone. Put each separate text message on its own line (1-4 lines). Real texting: short and informal, "
                 f"lowercase or abbreviations if it suits {CH}, emoji only if it fits. No narration, no actions, no asterisks.")
    elif mode == "call":
        style = ("This is a live voice call. Reply with spoken words only, as they would actually sound out loud. "
                 "No narration, no actions, no asterisks, no stage directions.")
    elif o.get("actions", True):
        style = ("Write actions, gestures and narration between *asterisks*. Spoken words are plain text. "
                 "Keep actions brief and concrete (one or two per reply) and use them to show feeling.")
    else:
        style = "Reply with spoken dialogue only. No narration, no actions, no asterisks."
    out.append("[Style]\n" + style + f"\nLength: about {lo}-{hi} words in total. Keep responses coherent and readable. Natural pauses, interruptions and unfinished thoughts are acceptable when appropriate.")
    if o.get("realism", True):
        rules = [r.replace("{US}", US).replace("{CH}", CH) for r in REALISM]
        if grp:
            rules += [r.replace("{US}", US).replace("{CH}", CH) for r in GROUP_RULES]
        nat = NATURAL.get(int(o.get("natural", 2)))
        if nat:
            rules.append(nat.replace("{CH}", CH))
        out.append("[Realism]\n" + "\n".join("- " + r for r in rules))
    av = avoid_notes(o.get("own") or hist) if o.get("realism", True) else ""
    if o.get("retry_note"):
        av = (av + " " + o["retry_note"]).strip()
    if av:
        out.append("[Variety]\n" + av)
    if fx:
        out.append(fx)
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
                role, t = "assistant", THINK.sub("", t).strip()
            else:
                who = user if m["role"] == "user" else (m.get("name") or "Someone")
                role, t = "user", f"{who}: {THINK.sub('', t).strip() if m['role'] == 'assistant' else t}"
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += ("\n\n" if role == "assistant" else "\n") + t
            else:
                msgs.append({"role": role, "content": t})
        if not msgs or msgs[0]["role"] != "user":
            msgs.insert(0, {"role": "user", "content": "(The scene begins.)"})
        tail = o.get("tail") or ""
        if msgs[-1]["role"] == "user":
            msgs[-1]["content"] += "\n\n" + tail
        else:
            msgs.append({"role": "user", "content": tail})
    else:
        msgs = [dict(role=m["role"], content=THINK.sub("", m["content"]).strip() if m["role"] == "assistant" else m["content"])
                for m in hist if (m.get("content") or "").strip()]
        if o.get("fold") and msgs and msgs[0]["role"] == "assistant":
            out.append(f"[{n}'s opening message]\n{msgs.pop(0)['content']}")
        if o.get("tail"):
            msgs.append({"role": "user", "content": o["tail"]})
    tail_notes = []
    if ptail:
        tail_notes.append(ptail)
    elif not grp:
        tail_notes.append(f"[Reply as {n}. React in character to {user}. Never speak like an AI or assistant.]")
    if o.get("retry_note"):
        tail_notes.append(f"[Correction: {o['retry_note']}]")
    if tail_notes and msgs and msgs[-1]["role"] == "user":
        msgs[-1] = dict(msgs[-1], content=msgs[-1]["content"] + "\n\n" + "\n".join(tail_notes))
    return [{"role": "system", "content": sub("\n\n".join(out), c, user)}] + \
           [{"role": m["role"], "content": sub(m["content"], c, user)} for m in msgs]
