
"""Prompt blocks for conflict, romance and intimacy."""
from ..config import CH, US
from . import body as B
from . import skillset as SK
from ..story import tension
from .intimacy import intim_block, settings as intim_settings
from .narrator import NARR_ID
from .relations import effective, rel_block
from .romance import rom_stage


def body_blocks(c, o, rp):
    """Wounds, sickness and death: how this body must be written, and who is gone. (The dead never reach a prompt: they do not speak.)"""
    bodies = rp.get("body") or {}
    members = ((o.get("group") or {}).get("members")) or []
    names = {m.get("id"): m.get("name") for m in members}
    out = []
    mine = bodies.get(c.get("id")) or {}
    if mine and not mine.get("dead") and c.get("id") != NARR_ID:
        g = B.guidance(mine, CH, US)
        if g:
            out.append(g)
    ub = bodies.get("user") or {}
    if ub and not ub.get("dead") and c.get("id") != NARR_ID:
        g = B.guidance(ub, CH, US, you=True)
        if g:
            out.append(g)
    gone = [(cid, v) for cid, v in bodies.items() if cid != "user" and isinstance(v, dict) and v.get("dead")]
    if gone:
        who = [f"{names.get(cid) or 'someone'} ({(v.get('died') or {}).get('how') or 'died'})" for cid, v in gone]
        out.append("[Loss]\n" + "; ".join(who) + (" has" if len(who) == 1 else " have") + " died. The dead never speak, act, think or answer again unless brought back by a resurrection. "
                   f"Those who knew them carry the loss in their own way (grief, anger, numbness, guilt, relief, silence) and may mention them, but never talk as if they were alive.")
    if c.get("id") == NARR_ID:
        L = []
        for cid, v in bodies.items():
            if isinstance(v, dict) and not v.get("dead"):
                d = B.describe(v, cid == "user")[:2]
                if d:
                    L.append(f"{US if cid == 'user' else (names.get(cid) or 'someone')}: " + "; ".join(d))
        if L:
            out.append("[Bodies in the scene]\nThe wounded and sick are still hurt until the story gives them time and care: " + " | ".join(L) + ". Show it in how they move and speak.")
    return out


def rp_blocks(c, o):
    """Return roleplay context blocks and resolved-outcome instructions."""
    r = o.get("rp") or {}

    if not r.get("on", True):
        return [], ""
    if c.get("id") == NARR_ID:
        rp0 = r.get("state") or {}
        fx0 = str(r.get("fx") or "")[:3500]
        outn = ("[Resolved this turn - these are established facts. Narrate them happening without changing who succeeded or failed]\n" + fx0.strip()
                + "\nNever mention dice, numbers, hit points or game rules.") if fx0.strip() else ""
        return body_blocks(c, o, rp0), outn

    cfg = r.get("cfg") or {}
    rp = r.get("state") or {}
    fx = str(r.get("fx") or "")[:3500]

    ctx = body_blocks(c, o, rp)
    # ---------------------------------------------------------
    # CONFLICT (story, not a fight engine): the guidance appears only once tension is really brewing
    # ---------------------------------------------------------
    st = o.get("story") or {}
    cblock = tension.block(c, int((st.get("info") or {}).get("tension") or 0), CH, US, str(r.get("uskills") or "")[:1200], str(r.get("ugear") or "")[:400])
    if cblock:
        ctx.append(cblock)

    # ---------------------------------------------------------
    # ROMANCE
    # ---------------------------------------------------------
    rom = (rp.get("rom") or {}).get(c.get("id")) or {}

    rel = (rp.get("rel") or {}).get(c.get("id")) or {}
    path = effective(c, rel)                      # auto and romance keep the romance block; every other path replaces it
    rb = rel_block(c, rel, CH, US)
    if rb:
        ctx.append(rb)

    romance_enabled = cfg.get("romance", True) and path in ("auto", "romance")

    if romance_enabled:
        romance_value = rom.get("v", 0)
        shared_moments = rom.get("ms") or []

        # Include romance context whenever romance is enabled.
        # This allows relationships to develop naturally from the beginning.
        s = f"[Romance with {US}]\n"

        s += (
            f"{CH}'s current feelings toward {US}: "
            f"{rom_stage(romance_value)}."
        )

        if shared_moments:
            s += "\nShared moments: " + "; ".join(
                str(moment) for moment in shared_moments
            ) + "."

        romance_style = (c.get("romance") or "").strip()
        if romance_style:
            s += f"\n{CH}'s approach to romance: {romance_style}"

        tone = cfg.get("tone", "natural")

        tone_rules = {
            "sweet": (
                "Use a gentle, affectionate and emotionally focused style."
            ),
            "natural": (
                "Write romantic interactions naturally according to "
                "the character's personality, feelings and relationship."
            ),
            "dramatic": (
                "Emphasize emotional tension, chemistry, vulnerability "
                "and dramatic romantic interactions."
            ),
        }

        selected_tone = tone_rules.get(
            tone,
            tone_rules["natural"]
        )

        s += (
            f"\nLet the relationship influence flirting, affection, "
            f"jealousy, vulnerability, closeness and emotional reactions. "
            f"Allow the relationship to develop naturally through "
            f"conversation and shared experiences. "
            f"Do not force romantic interest or relationship progression. "
            f"Respect character autonomy, consent and established boundaries. "
            f"{selected_tone}"
        )

        ctx.append(s)

    # ---------------------------------------------------------
    # INTIMACY
    # ---------------------------------------------------------
    icfg = intim_settings(cfg.get("intimacy"))
    if icfg["on"]:
        rp_state = rp  # same state dict that holds rom, rel, body, etc.
        ib = intim_block(c, rp_state, icfg)
        if ib:
            ctx.append(ib)

    # ---------------------------------------------------------
    # RESOLVED EVENTS
    # ---------------------------------------------------------
    out = ""

    if fx.strip():
        out = (
            "[Resolved this turn - these are established facts. "
            "Show them happening naturally without changing who succeeded "
            "or failed]\n"
            + fx.strip()
            + "\nNever mention dice, rolls, hit points, numerical stats "
            "or game rules in the story."
        )

    return ctx, out
