
"""Prompt blocks for fights, romance and intimacy."""
from ..config import CH, US
from .combat import cond
from .intimacy import intim_block, settings as intim_settings
from .narrator import NARR_ID
from .romance import rom_stage


def rp_blocks(c, o):
    """Return roleplay context blocks and resolved-outcome instructions."""
    r = o.get("rp") or {}

    if not r.get("on", True) or c.get("id") == NARR_ID:
        return [], ""

    cfg = r.get("cfg") or {}
    rp = r.get("state") or {}
    fx = str(r.get("fx") or "")[:3500]

    ctx = []
    cb = (rp.get("combat") or {}) if (rp.get("combat") or {}).get("on") else None

    # ---------------------------------------------------------
    # COMBAT
    # ---------------------------------------------------------
    if cb or "[Combat" in fx:
        mine = (
            next(
                (u for u in cb.get("units", []) if u.get("id") == c.get("id")),
                None
            )
            if cb else None
        )

        if mine and mine.get("side") == "foe":
            role = f"{CH} is fighting against {US}."
        elif mine and mine.get("side") == "ally":
            role = f"{CH} is fighting on {US}'s side."
        else:
            role = (
                f"{CH} is not fighting: watching, fleeing, pleading "
                f"or stepping in, as fits {CH}."
            )

        s = "[Fight]\n" + role

        if cb:
            units = cb.get("units", [])
            if units:
                s += "\nConditions: " + "; ".join(
                    f"{u.get('name', 'Unknown')}: {cond(u)}"
                    for u in units
                ) + "."

        fighting_style = (c.get("combat") or "").strip()
        if fighting_style:
            s += f"\n{CH}'s fighting style and gear: {fighting_style}"

        s += (
            f"\nFight the way {CH} would. Use the character's fighting "
            f"style, surroundings, personality and emotions. Show pain, "
            f"fear, anger, hesitation, confidence or desperation when "
            f"appropriate. Keep combat vivid and consistent with the scene. "
            f"A badly injured or exhausted fighter should behave accordingly. "
            f"Never mention game mechanics, hit points, dice or numerical stats."
        )

        ctx.append(s)

    # ---------------------------------------------------------
    # ROMANCE
    # ---------------------------------------------------------
    rom = (rp.get("rom") or {}).get(c.get("id")) or {}

    romance_enabled = cfg.get("romance", True)

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
        rp_state = rp  # same state dict that holds rom, combat, etc.
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
